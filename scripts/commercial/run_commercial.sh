#!/usr/bin/env bash
# Commercial distress layer (Miami-Dade only). Ported from the Commercial Data bot (/workspace/distressed_commercial/work).
# Runs in $RAW/commercial/work so the bot's own deliverables (distressed_commercial.csv/.xlsx) are never overwritten.
#  1. parse_live.py: latest county-taxes.net live reads (results.jsonl from the PC reader) -> live_tax.json
#  2. build3.py: Commercial distress score (ad/live tax, code liens, recert, unsafe structures, FDEP closed gas, OpenCorporates entity status, bankruptcy)
#  3. import_commercial.py: Miami-Dade rows -> data/commercial.json.gz
# Inputs (read-only, symlinked): parcels_v2.json, pa_cache_md.json, oc_status.json (oc_lookup.py results), cl_bk.json, gas_matched.json.
set -euo pipefail
cd "$(dirname "$0")/../.."; REPO=$PWD
RAW="${RAW:-/workspace/raw}"; SRC="${COMM_SRC:-/workspace/distressed_commercial/work}"; LIVE="${LIVE_RESULTS:-/workspace/taxreader/results.jsonl}"
W="$RAW/commercial/work"; mkdir -p "$W"
for f in parcels_v2.json pa_cache_md.json oc_status.json cl_bk.json gas_matched.json; do [ -e "$SRC/$f" ] && ln -sfn "$SRC/$f" "$W/$f"; done
[ -e "$SRC/live_tax_manual.json" ] && cp -f "$SRC/live_tax_manual.json" "$W/"
cp -f scripts/commercial/{parse_live.py,build3.py,classify.py,oc_lookup_owners.py} "$W/"
cd "$W"
python3 parse_live.py "$LIVE"
python3 build3.py > build3_last.txt
cd "$REPO"; python3 scripts/commercial/import_commercial.py "$RAW/commercial/distressed_commercial.csv" data/commercial.json.gz
