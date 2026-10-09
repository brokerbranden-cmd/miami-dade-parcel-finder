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
# Lis pendens: the weekly routine drops Official Records CSV exports (logged-in browser) into raw/lp_downloads/;
# build_distress.py ingests every lp_*.csv there. The unattended scrape is only a fallback (reCAPTCHA blocks it without login).
if ls raw/lp_downloads/*.csv >/dev/null 2>&1; then
  echo "Lis pendens: $(ls raw/lp_downloads/*.csv | wc -l) Clerk CSV exports in raw/lp_downloads - skipping scrape"
else
  python3 scripts/fetch_clerk.py "$RAW" || echo "WARN: Clerk scrape blocked and no raw/lp_downloads CSVs - using cached raw/clerk data"
fi
python3 scripts/fetch_auctions.py "$RAW" || echo "WARN: realforeclose fetch failed - using cached auctions.json"
python3 scripts/fetch_tax.py "$RAW"      || echo "WARN: TaxSys reports failed - using cached raw/tax"
python3 scripts/fetch_violations.py "$RAW" || echo "WARN: violations fetch failed - using cached raw/viol"
python3 scripts/fetch_permits.py "$RAW"    || echo "WARN: permit fetch failed - using cached permits.json (vacancy hint)"
RAW="$RAW" python3 scripts/build_distress.py data  # -> raw/distress.parquet + data/distress.json.gz
RAW="$RAW" python3 scripts/build_data.py data   # -> data/meta.json + data/*.bin.gz
echo "Done. Serve with: python3 -m http.server 8080"
