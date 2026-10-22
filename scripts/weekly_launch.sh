#!/usr/bin/env bash
# Start the weekly refresh fully detached and return at once (exit 0) so the calling agent/tool step never times out
# and reports a false failure.
# Includes (via build_all.sh, Monroe block) the Key West eTRAKiT and Islamorada CityView permit / code-case fetchers
# (scripts/counties/monroe/fetch_keywest_etrakit.py, fetch_islamorada_cityview.py): polite pacing (KW_DELAY / ISL_DELAY 1.5 s, one request at a time),
# time-boxed by MAX_MINUTES and resumable. Status rows: monroe_keywest, monroe_islamorada in data/refresh-status.json. Progress: $RAW/.build_state/weekly/latest/summary.txt; finished when .../latest/done exists.
cd "$(dirname "$0")/.."; RAW="${RAW:-/workspace/raw}"; mkdir -p "$RAW/.build_state"
setsid nohup bash scripts/weekly_refresh_headless.sh > "$RAW/.build_state/weekly.out" 2>&1 < /dev/null & disown
echo "weekly refresh launched (pid $!); log $RAW/.build_state/weekly.out"; exit 0
