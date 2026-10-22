#!/usr/bin/env bash
# Weekly Parcel Finder refresh, run detached from the agent session so an interrupted session cannot kill it.
#
# Launch (returns at once; safe to call twice - a second copy exits on the lock / an already-finished run):
#   bash scripts/weekly_launch.sh     (detaches via setsid nohup and returns in <1s with exit 0)
# Finished when $RAW/.build_state/weekly/latest/done exists (first word PASS or FAIL). Then: bash scripts/weekly_finish.sh
#
# Steps: lock -> back up repo raw/ -> build_all.sh (up to BUILD_TRIES=3, resumes; exit 3 = finished with stale sources) ->
#        re-apply Monroe/Broward tax layers if a rebuild dropped them -> e2e suites (incl. the filter-correctness audit, tests/e2e_filter_audit.py) behind a 3 GB MemAvailable gate ->
#        top_leads.py --since 7 days -> email body (Data refresh status + leads) -> done marker.
# It never commits, pushes or sends mail (weekly_finish.sh pushes; the agent sends the email via Gmail).
#
# Modes:  DRY=1   check prerequisites + print the plan, change nothing.
#         FAST=1  no backup / build / tests: rebuild leads + email body from the current outputs into a scratch dir (smoke test).
#         SKIP_BUILD=1  tests + leads only (e.g. after a manual build).   FORCE=1  rerun even if today's run is already done.
set -uo pipefail
cd "$(dirname "$0")/.."; REPO=$(pwd)
export RAW="${RAW:-/workspace/raw}"; ST="$RAW/.build_state"; mkdir -p "$ST/weekly"
DAY=$(date +%Y%m%d); W="${WEEKLY_DIR:-$ST/weekly/$DAY}"; [ "${FAST:-0}" = 1 ] && W="${WEEKLY_DIR:-/tmp/weekly_fast_$DAY}"
U="${U:-http://localhost:8080/}"; BUILD_TRIES="${BUILD_TRIES:-3}"; MEM_GB="${MEM_GB:-3}"
now(){ date '+%Y-%m-%d %H:%M:%S %Z'; }
log(){ echo "$(now) $*" | tee -a "$W/summary.txt"; }

if [ "${DRY:-0}" = 1 ]; then
  echo "DRY run - nothing is changed"; echo "repo $REPO  RAW $RAW  run dir $W  test url $U"
  for f in scripts/build_all.sh scripts/weekly_finish.sh; do bash -n "$f" && echo "syntax ok $f"; done
  python3 -m py_compile scripts/top_leads.py scripts/build_zoning_rules.py scripts/counties/monroe/build_monroe.py scripts/counties/monroe/add_tax.py scripts/counties/broward/add_tax.py scripts/counties/broward/build_broward.py scripts/counties/broward/fetch_fpn_foreclosure.py scripts/counties/broward/broward_permit_lib.py scripts/counties/broward/fetch_auctions_fl.py scripts/fetch_energov.py && echo "py syntax ok"
  [ -f "$W/done" ] && echo "today's run already done: $(cat "$W/done")"
  flock -n "$ST/weekly.lock" true && echo "lock free" || echo "LOCK HELD - a weekly run is in progress"
  pgrep -f 'scripts/build_all.sh' >/dev/null && echo "WARN a build_all.sh is already running"
  curl -sf -o /dev/null "$U" && echo "test server up at $U" || echo "test server not up (will be started on 8080)"
  echo "MemAvailable $(free -g | awk '/Mem:/{print $7}') GB (gate ${MEM_GB} GB)"; ls "$REPO/raw/seeker/zoning_by_folio.js" "$RAW/monroe/tax/" >/dev/null && echo "seeker + monroe tax inputs present"
  exit 0
fi

exec 9>"$ST/weekly.lock"; flock -n 9 || { echo "another weekly run holds $ST/weekly.lock - exiting"; exit 0; }
if [ -f "$W/done" ] && [ "${FORCE:-0}" != 1 ]; then echo "run $W already done ($(cat "$W/done")); FORCE=1 to rerun"; exit 0; fi
mkdir -p "$W"; rm -f "$W/done"; [ "${FAST:-0}" = 1 ] || ln -sfn "$W" "$ST/weekly/latest"
: > "$W/summary.txt"; log "weekly refresh start (pid $$, FAST=${FAST:-0} SKIP_BUILD=${SKIP_BUILD:-0})"
RESULT=PASS; BUILD_NOTE=""

if [ "${FAST:-0}" != 1 ] && [ "${SKIP_BUILD:-0}" != 1 ]; then
  B=/workspace/backups/parcel-finder-raw-$(date +%Y%m%d-%H%M).tgz; mkdir -p /workspace/backups
  tar czf "$B" raw && log "backed up repo raw/ -> $B" || { log "FAIL raw/ backup failed - stopping before the build"; echo "FAIL $(now) backup" > "$W/done"; exit 1; }
  while pgrep -f "bash scripts/build_all.sh" > /dev/null; do log "a build_all.sh is already running - waiting for it"; sleep 60; done   # never two builds
  : > "$ST/run.log"; brc=1
  for i in $(seq 1 "$BUILD_TRIES"); do
    log "build try $i/$BUILD_TRIES"; bash scripts/build_all.sh >> "$ST/run.log" 2>&1; brc=$?; log "build try $i exit $brc"
    [ $brc = 0 ] || [ $brc = 3 ] && break; sleep 120
  done
  echo "$brc" > "$W/build_exit"; BUILD_NOTE="build tries: $i (exit $brc$([ $brc = 3 ] && echo ', finished with stale sources'))"
  [ $brc = 0 ] || [ $brc = 3 ] || { RESULT=FAIL; log "FAIL build did not finish after $BUILD_TRIES tries (see $ST/run.log)"; }
fi

# tax layers: patched into packs, a county rebuild drops them -> re-apply only when meta.json lost its 'tax' block
for c in monroe broward; do
  m="data/$c/meta.json"; [ -f "$m" ] || continue
  if python3 -c "import json,sys; sys.exit(0 if 'tax' in json.load(open('$m')) else 1)"; then log "$c tax layer present"
  elif [ "${FAST:-0}" = 1 ]; then log "$c tax layer MISSING (FAST: not re-applied)"
  else python3 scripts/counties/$c/add_tax.py data/$c >> "$W/tax_$c.log" 2>&1 && log "$c tax layer re-applied" || { RESULT=FAIL; log "FAIL $c add_tax.py (see $W/tax_$c.log)"; }; fi
done

if [ "${FAST:-0}" != 1 ] && [ "$RESULT" = PASS ]; then
  if ! curl -sf -o /dev/null "$U"; then (setsid nohup python3 -m http.server 8080 > /dev/null 2>&1 < /dev/null &); sleep 3; log "started test server on 8080"; fi
  TS=$(date +%Y%m%d-%H%M); S="test_runs/summary_weekly_$TS.txt"; L="$W/test_logs"; mkdir -p "$L" test_runs; echo "# start $(date +%T)" > "$S"
  run(){ local n=$1; shift; while [ "$(free -g | awk '/Mem:/{print $7}')" -lt "$MEM_GB" ]; do sleep 20; done
    timeout 2400 "$@" > "$L/$n.log" 2>&1; local rc=$?
    if [ $rc = 0 ]; then echo "PASS $n" >> "$S"; else echo "FAIL $n (exit $rc) $(grep -m1 -E '^FAIL|FAILED|Error' "$L/$n.log" | cut -c1-200)" >> "$S"; fi; }
  run unit node tests/unit_skiptrace.js
  for m in desktop mobile; do
    for t in e2e_monroe e2e_broward e2e_broward_signals e2e_export e2e_sendmark e2e_deterrents e2e_skiptrace scenarios e2e_filter_audit; do run "${t#e2e_}_$m" python3 tests/$t.py "$U" $m; done
  done
  run county python3 tests/e2e_county.py "$U"
  run ownerkind python3 tests/e2e_ownerkind.py "$U"
  echo "# DONE $(date +%T)" >> "$S"; cp "$S" "$W/tests.txt"
  np=$(grep -c '^PASS' "$S"); nf=$(grep -c '^FAIL' "$S"); log "tests: $np passed, $nf failed ($S)"; [ "$nf" = 0 ] || RESULT=FAIL
elif [ "${FAST:-0}" = 1 ]; then echo "FAST mode: tests not run" > "$W/tests.txt"
else echo "tests not run (build failed)" > "$W/tests.txt"; fi

# top leads + email body (out/ is git-ignored)
SINCE=$(date -d '7 days ago' +%F); LEADS="$REPO/out/top_leads_$DAY"; [ "${FAST:-0}" = 1 ] && LEADS="$W/top_leads_$DAY"
python3 scripts/top_leads.py --since "$SINCE" --out "$LEADS" >> "$W/summary.txt" 2>&1 || { RESULT=FAIL; log "FAIL top_leads.py"; }
BODY="$W/email_body.html"
python3 - "$ST/status.txt" "$W/tests.txt" "$LEADS.html" "$BODY" "$BUILD_NOTE" "$RESULT" "$REPO/raw/lp_downloads" <<'PY'
import html, os, re, sys
st, tests, leads, body, note, result, lpdir = sys.argv[1:8]
read = lambda p: open(p).read().strip() if os.path.exists(p) else '(missing)'
lp = sorted(re.findall(r'_(\d{8})\.csv$', ' '.join(os.listdir(lpdir)))) if os.path.isdir(lpdir) else []
lp_to = f"{lp[-1][:4]}-{lp[-1][4:6]}-{lp[-1][6:]}" if lp else 'none'
t = read(tests); np, nf = len(re.findall(r'^PASS', t, re.M)), len(re.findall(r'^FAIL', t, re.M))
sec = ("<h2>Data refresh status</h2><pre style='font-size:12px;white-space:pre-wrap'>" + html.escape(read(st)) + "</pre><ul>"
       + (f"<li>{html.escape(note)}</li>" if note else '')
       + f"<li>Newest Clerk lis pendens export: {lp_to} (Clerk browser pulls are manual; if this date is old, the Clerk pulls were skipped this week).</li>"
       + f"<li>Regression tests: {np} passed, {nf} failed. Overall: {result}.</li></ul><hr>")
b = read(leads)
if '<body' not in b: b = "<html><body style='font-family:Arial,sans-serif'><p>No leads file was produced.</p></body></html>"
open(body, 'w').write(re.sub(r'(<body[^>]*>)', lambda m: m.group(1) + sec, b, count=1))
PY
[ -s "$BODY" ] && log "email body -> $BODY" || { RESULT=FAIL; log "FAIL email body not written"; }
echo "$BODY" > "$W/email_body_path"; echo "$W/emailed" > "$W/emailed_marker_path"
log "RESULT $RESULT"; echo "$RESULT $(now)" > "$W/done"
