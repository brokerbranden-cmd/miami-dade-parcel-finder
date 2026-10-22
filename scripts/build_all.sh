#!/usr/bin/env bash
# Rebuild every data pack from the public Miami-Dade sources + Monroe (about 1.5-2 hours, ~1.5 GB of raw downloads; EnerGov ~45 min, permits ~20 min).
# Needs: python3, pandas, pyarrow, geopandas, shapely, requests.
#
# Robust + resumable:
#  - every step writes a checkpoint to $RAW/.build_state/<step>.ok; rerunning after an interruption skips finished steps
#    (FRESH=1 starts over; a run older than RESUME_HOURS (default 36) also starts over).
#  - fetch steps retry (RETRIES, default 3, backoff 60s/120s...) and snapshot their outputs first; if every try fails the
#    last good data for that source is restored and the run continues (the source is reported "stale").
#  - a failed build step is reported and the run carries on with the previous outputs of that step.
#  - status: data/refresh-status.json (per-source fresh/stale, last good date, counts) + $RAW/.build_state/status.txt.
#  - exit code 0 = everything fresh, 3 = finished with stale/failed steps (data still usable), other = script error.
set -uo pipefail
cd "$(dirname "$0")/.."
RAW="${RAW:-/workspace/raw}"; export RAW
ST="$RAW/.build_state"; SNAP="$RAW/.lastgood"; RETRIES="${RETRIES:-3}"; RESUME_HOURS="${RESUME_HOURS:-36}"
mkdir -p "$RAW/pagis" "$ST" "$SNAP"
LOG="$ST/steps.log"
now(){ date '+%Y-%m-%dT%H:%M:%S%z'; }
if [ "${FRESH:-0}" = 1 ] || [ ! -f "$ST/run_started" ] || [ -f "$ST/run_finished" ] || \
   [ -n "$(find "$ST/run_started" -mmin +$((RESUME_HOURS*60)) 2>/dev/null)" ]; then
  rm -f "$ST"/*.ok "$ST"/*.fail "$ST"/*.stale "$ST/run_finished"; now > "$ST/run_started"; echo "== new run $(now)" >> "$LOG"
else
  echo "== resuming run from $(cat "$ST/run_started") at $(now) ($(ls "$ST"/*.ok 2>/dev/null | wc -l) steps already done)" | tee -a "$LOG"
fi
done_(){ [ -f "$ST/$1.ok" ]; }
mark(){ local s=$1 r=$2; rm -f "$ST/$s.ok" "$ST/$s.fail" "$ST/$s.stale"; now > "$ST/$s.$r"; echo "$(now) $s $r" >> "$LOG"; }
snapshot(){ local s=$1; shift; rm -rf "$SNAP/$s.new"; mkdir -p "$SNAP/$s.new"
  for p in "$@"; do [ -e "$RAW/$p" ] && cp -a "$RAW/$p" "$SNAP/$s.new/"; done; rm -rf "$SNAP/$s"; mv "$SNAP/$s.new" "$SNAP/$s"; }
restore(){ local s=$1; shift; for p in "$@"; do b=$(basename "$p"); [ -e "$SNAP/$s/$b" ] || continue; rm -rf "$RAW/$p"; cp -a "$SNAP/$s/$b" "$RAW/$p"; done; }
# fetch <step> "<raw outputs>" cmd...   (retried; on final failure the snapshot is restored -> stale)
fetch(){ local s=$1 outs=$2; shift 2; done_ "$s" && { echo "skip $s (done)"; return 0; }
  [ -f "$ST/$s.stale" ] && { echo "skip $s (already stale this run)"; return 0; }
  snapshot "$s" $outs; local i=1 w=60
  while :; do echo "-- $s try $i/$RETRIES $(now)"
    if "$@"; then mark "$s" ok; return 0; fi
    [ $i -ge "$RETRIES" ] && break; sleep $w; i=$((i+1)); w=$((w*2)); done
  restore "$s" $outs; mark "$s" stale; echo "WARN: $s failed $RETRIES times - kept the last good data"; return 0; }
# build <step> cmd...   (one try; failure is recorded, previous outputs stay)
build(){ local s=$1; shift; done_ "$s" && { echo "skip $s (done)"; return 0; }
  echo "-- $s $(now)"; if "$@"; then mark "$s" ok; else mark "$s" fail; echo "WARN: build step $s failed - previous outputs kept"; fi; return 0; }
note(){ echo "$1"; }

fetch pagis   "pagis"   python3 scripts/fetch_pagis.py "$RAW/pagis"     # property roll, sales, owners, exemptions, points (~944K rows)
fetch layers  "county_zoning.geojson municipal_zoning.geojson cra.geojson tinc.json" python3 scripts/fetch_layers.py "$RAW"
build load_raw python3 scripts/load_raw.py "$RAW"                       # chunks -> pagis.parquet
fetch zone_desc "zone_desc.json" python3 scripts/fetch_zone_desc.py "$RAW"   # one PA lookup per zoning code (~270 calls)
build spatial  python3 scripts/spatial_join.py "$RAW"                    # parcel point -> city/county zoning district + CRA
# --- distress layers ---
# Lis pendens: the weekly routine drops Official Records CSV exports (logged-in browser) into raw/lp_downloads/;
# build_distress.py ingests every lp_*.csv there. The unattended scrape is only a fallback (reCAPTCHA blocks it without login).
if ls raw/lp_downloads/*.csv >/dev/null 2>&1; then
  note "Lis pendens: $(ls raw/lp_downloads/*.csv | wc -l) Clerk CSV exports in raw/lp_downloads - skipping scrape"; done_ clerk || mark clerk ok
else
  RETRIES=1 fetch clerk "clerk" python3 scripts/fetch_clerk.py "$RAW"
fi
# Probate: Official Records exports (PAD / PRO / DCE) in raw/probate_downloads/ + case lists in raw/probate_cases/ (nothing scraped).
for d in probate_downloads probate_cases; do
  if ls raw/$d/* >/dev/null 2>&1; then note "Probate: $(ls raw/$d | wc -l) files in raw/$d"; else note "WARN: raw/$d is empty - probate layer limited to the No-Heir/Obituary outputs"; fi
done
fetch auctions "auctions.json" python3 scripts/fetch_auctions.py "$RAW"
fetch tax      "tax"           python3 scripts/fetch_tax.py "$RAW"
fetch viol     "viol"          python3 scripts/fetch_violations.py "$RAW"
RETRIES=2 fetch permits  "permits.json"  python3 scripts/fetch_permits.py "$RAW"
# --- permit history + municipal code cases ---
fetch county_permits "permits" python3 scripts/fetch_county_permits.py "$RAW"
RETRIES=2 fetch energov        "permits" python3 scripts/fetch_energov.py "$RAW"   # ~20-40 min, ~1 req/s
build merge_permits python3 scripts/merge_permits.py "$RAW"
build distress python3 scripts/build_distress.py data                     # -> raw/distress.parquet + data/distress.json.gz
# Pre-foreclosure "open" check: Clerk CLP / dismissal / certificate-of-title exports in raw/lp_downloads/{clp,dis,cot}_*.csv,
# else the unattended CLP search (Turnstile usually blocks it; one try, non-fatal). The Clerk's daily file is a paid subscription.
# The unattended CLP search is Turnstile-blocked every week (15-min timeout, never succeeds), so it is skipped and marked
# stale at once unless CLP_SCRAPE=1. Dropping Clerk CLP / dismissal / certificate-of-title exports in raw/lp_downloads/ makes it fresh.
if ls raw/lp_downloads/clp_*.csv raw/lp_downloads/cot_*.csv >/dev/null 2>&1; then done_ clerk_clp || mark clerk_clp ok
elif [ "${CLP_SCRAPE:-0}" = 1 ]; then RETRIES=1 fetch clerk_clp "clerk" timeout 900 python3 scripts/fetch_clerk.py "$RAW" --days 120 --types CLP
else done_ clerk_clp || [ -f "$ST/clerk_clp.stale" ] || { mark clerk_clp stale; note "Clerk CLP scrape skipped (Turnstile-blocked; CLP_SCRAPE=1 to try) - marked stale"; }; fi
build signals python3 scripts/build_signals.py data        # -> data/signals.json.gz
# --- estimated owner equity (Miami-Dade): per-owner Clerk Official Records name search (public, no login) for mortgages /
# satisfactions, priority order = open pre-foreclosure, auctions, probate, then distress score. Resumable cache RAW/clerk_owner/;
# time-boxed (MTG_MINUTES, default 240) so each weekly run refreshes the oldest / newest leads first. Non-fatal.
build clerk_mtg python3 scripts/fetch_mortgages.py "$RAW" --workers "${MTG_WORKERS:-6}" --max-age "${MTG_MAX_AGE:-28}" --minutes "${MTG_MINUTES:-240}"
build equity  python3 scripts/build_equity.py data           # -> data/equity.json.gz
build comps   python3 scripts/build_comps.py data          # -> data/comps.json.gz
build commercial bash scripts/commercial/run_commercial.sh   # -> data/commercial.json.gz (Miami-Dade commercial distress score, live tax payoff, owner entity, closed gas; non-fatal)
build data    python3 scripts/build_data.py data           # -> data/meta.json + data/*.bin.gz
build zoning_rules python3 scripts/build_zoning_rules.py data   # -> data/zoning-rules.json + data/extras.json.gz
fetch parcels "parcels" python3 scripts/fetch_parcels.py "$RAW"
build assemblages python3 scripts/build_assemblages.py data    # -> data/asm.json.gz + data/asm-polys.json.gz
# --- other counties (counties.js): each is a non-fatal fetch + build into data/<county>/; a failure keeps that county's last packs ---
# SKIP_COUNTIES="monroe" skips one. Monroe: FL statewide cadastral (CO_NO=54) + FEMA NFHL flood zones, ~3-5 min, no login.
case " ${SKIP_COUNTIES:-} " in *" monroe "*) note "skip monroe (SKIP_COUNTIES)";; *)
  fetch monroe_fetch "monroe" python3 scripts/counties/monroe/fetch_monroe.py
  # Monroe Clerk court cases (foreclosure = lis pendens proxy, probate; public, no captcha) + Marathon code hearings -> used by monroe_enrich
  RETRIES=2 fetch monroe_clerk "monroe/clerk_cases.json" timeout 2400 python3 scripts/counties/monroe/fetch_clerk_monroe.py 36
  RETRIES=2 fetch monroe_marathon_code "monroe/marathon_code.json" timeout 1800 python3 scripts/counties/monroe/fetch_marathon_code.py
  build monroe_data  python3 scripts/counties/monroe/build_monroe.py data/monroe ;;
esac
# Broward city permits (public ArcGIS; Broward-only raw files, not mixed with Miami-Dade)
RETRIES=2 fetch broward_permits "broward/permits" timeout 1800 python3 scripts/counties/broward/fetch_broward_permits.py
python3 scripts/refresh_status.py "$ST" data/refresh-status.json > "$ST/status.txt" || echo "WARN: status file failed"
cat "$ST/status.txt" 2>/dev/null
now > "$ST/run_finished"
if ls "$ST"/*.fail "$ST"/*.stale >/dev/null 2>&1; then echo "Done with stale/failed steps (see above)."; exit 3; fi
echo "Done. Serve with: python3 -m http.server 8080"
