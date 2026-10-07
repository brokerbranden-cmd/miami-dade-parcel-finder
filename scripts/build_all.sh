#!/usr/bin/env bash
# Rebuild every data pack from the public Miami-Dade sources (about 30-40 minutes, ~1.5 GB of raw downloads).
# Needs: python3, pandas, pyarrow, geopandas, shapely, requests.
set -euo pipefail
cd "$(dirname "$0")/.."
RAW="${RAW:-/workspace/raw}"
mkdir -p "$RAW/pagis"
python3 scripts/fetch_pagis.py "$RAW/pagis"     # property roll, sales, owners, exemptions, points (~944K rows)
python3 scripts/fetch_layers.py "$RAW"          # county + municipal zoning polygons, CRA polygons, TINC codes
python3 scripts/load_raw.py "$RAW"              # chunks -> pagis.parquet
python3 scripts/fetch_zone_desc.py "$RAW"       # one PA lookup per Property Appraiser zoning code (~270 calls)
python3 scripts/spatial_join.py "$RAW"          # parcel point -> city/county zoning district + CRA
# --- distress layers (weekly refresh; each fetcher is non-fatal so one blocked source never stops the build) ---
python3 scripts/fetch_clerk.py "$RAW" || echo "WARN: Clerk lis pendens blocked (reCAPTCHA) - using cached raw/clerk data"
python3 scripts/fetch_auctions.py "$RAW" || echo "WARN: realforeclose fetch failed - using cached auctions.json"
python3 scripts/fetch_tax.py "$RAW"      || echo "WARN: TaxSys reports failed - using cached raw/tax"
python3 scripts/fetch_violations.py "$RAW" || echo "WARN: violations fetch failed - using cached raw/viol"
RAW="$RAW" python3 scripts/build_distress.py data  # -> raw/distress.parquet + data/distress.json.gz
RAW="$RAW" python3 scripts/build_data.py data   # -> data/meta.json + data/*.bin.gz
echo "Done. Serve with: python3 -m http.server 8080"
