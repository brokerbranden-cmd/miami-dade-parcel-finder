#!/usr/bin/env bash
# Start the weekly refresh fully detached and return at once (exit 0) so the calling agent/tool step never times out
# and reports a false failure. Progress: $RAW/.build_state/weekly/latest/summary.txt; finished when .../latest/done exists.
cd "$(dirname "$0")/.."; RAW="${RAW:-/workspace/raw}"; mkdir -p "$RAW/.build_state"
setsid nohup bash scripts/weekly_refresh_headless.sh > "$RAW/.build_state/weekly.out" 2>&1 < /dev/null & disown
echo "weekly refresh launched (pid $!); log $RAW/.build_state/weekly.out"; exit 0
