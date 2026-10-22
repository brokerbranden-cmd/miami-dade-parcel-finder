#!/usr/bin/env bash
# Pre-push regression. Runs the e2e suites one after another (each waits for MemAvailable >= MEM_GB, default 3 GB; the box is shared),
# against a local static server on PORT (default 8097; 8080/8081 are used by other jobs). Never kills other processes.
#   bash scripts/pre_push_regression.sh            -> test_runs/summary_prepush_<ts>.txt, exit 0 only if every suite passed
# When everything passes on a clean tracked tree, it records .git/pf-regression/<tree-hash>.ok; scripts/git-hooks/pre-push refuses a push
# whose tree has no such record (and runs this script itself if needed). Install the hook once: git config core.hooksPath scripts/git-hooks
set -uo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8097}"; U="${U:-http://127.0.0.1:$PORT/}"; MEM_GB="${MEM_GB:-3}"
if ! curl -sf -o /dev/null "$U"; then (setsid nohup python3 -m http.server "$PORT" --bind 127.0.0.1 > /dev/null 2>&1 < /dev/null &); sleep 3; fi
curl -sf -o /dev/null "$U" || { echo "test server $U is not reachable"; exit 1; }
TS=$(date +%Y%m%d-%H%M%S); S="test_runs/summary_prepush_$TS.txt"; L="${LOGDIR:-/tmp/pf_prepush_$TS}"; mkdir -p "$L" test_runs; echo "# start $(date +%T) $U" > "$S"
run(){ local n=$1; shift; while [ "$(free -g | awk '/Mem:/{print $7}')" -lt "$MEM_GB" ]; do sleep 20; done
  timeout 3600 "$@" > "$L/$n.log" 2>&1; local rc=$?
  if [ $rc = 0 ]; then echo "PASS $n" | tee -a "$S"; else echo "FAIL $n (exit $rc) $(grep -m1 -E '^FAIL|FAILED|Error' "$L/$n.log" | cut -c1-200)" | tee -a "$S"; fi; }
run unit node tests/unit_skiptrace.js
run unit_ask node tests/unit_ask.js
run ownerkind python3 tests/e2e_ownerkind.py "$U"
for m in desktop mobile; do
  for t in scenarios e2e_export e2e_monroe e2e_monroe_city e2e_broward e2e_broward_signals e2e_layout_counties e2e_filter_audit e2e_email e2e_traced e2e_folders e2e_ask e2e_equity; do run "${t#e2e_}_$m" python3 tests/$t.py "$U" $m; done
done
run county python3 tests/e2e_county.py "$U"
echo "# DONE $(date +%T) logs: $L" >> "$S"
nf=$(grep -c '^FAIL' "$S"); echo "$(grep -c '^PASS' "$S") passed, $nf failed ($S)"
[ "$nf" = 0 ] || exit 1
if git diff --quiet HEAD -- . ':(exclude)shots' ':(exclude)test_runs' ':(exclude)tests/export_sample.csv'; then
  mkdir -p .git/pf-regression; t=$(git rev-parse 'HEAD^{tree}'); cp "$S" ".git/pf-regression/$t.ok"; echo "recorded green regression for tree $t"
else echo "tracked files differ from HEAD: commit first, then rerun so the push is unblocked"; fi
