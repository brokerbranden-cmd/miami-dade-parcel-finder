#!/usr/bin/env bash
# Finish a weekly refresh started by scripts/weekly_refresh_headless.sh. Idempotent: safe to run any number of times.
#   bash scripts/weekly_finish.sh            (DRY=1: report only, no commit/push)
# - not finished yet -> exit 2.  Finished with FAIL -> prints the summary, exit 1, nothing pushed.
# - PASS -> commits ONLY data/ and pushes (git pull --rebase --autostash first, never force); records $W/pushed so a rerun does not push again.
# - prints EMAIL_BODY=<path> and EMAILED_MARKER=<path>. It never sends mail: the agent sends the email via Gmail, then: touch <EMAILED_MARKER>.
set -uo pipefail
cd "$(dirname "$0")/.."
RAW="${RAW:-/workspace/raw}"; ST="$RAW/.build_state"; W="${WEEKLY_DIR:-$ST/weekly/latest}"
[ -d "$W" ] || { echo "NOT STARTED: no $W"; exit 2; }
W=$(readlink -f "$W"); DAY=$(basename "$W")
if [ ! -f "$W/done" ]; then
  if flock -n "$ST/weekly.lock" true; then echo "NOT FINISHED and no weekly run holds the lock - it was killed; relaunch weekly_refresh_headless.sh (the build resumes)"
  else echo "RUNNING: $(tail -1 "$W/summary.txt" 2>/dev/null)"; fi; exit 2; fi
read -r RESULT _ < "$W/done"; cat "$W/summary.txt"; echo; cat "$W/tests.txt" 2>/dev/null; echo
if [ "$RESULT" != PASS ]; then echo "RESULT FAIL - nothing pushed. Fix, then rerun weekly_refresh_headless.sh (SKIP_BUILD=1 FORCE=1 for tests only)."; exit 1; fi

if [ -f "$W/pushed" ]; then echo "ALREADY PUSHED: $(cat "$W/pushed")"
elif [ "${DRY:-0}" = 1 ]; then echo "DRY: would commit data/ ($(git status --porcelain -- data | wc -l) changed paths) and push"
else
  other=$(git diff --cached --name-only | grep -v '^data/'); [ -z "$other" ] || { echo "ABORT: files outside data/ are already staged: $other"; exit 1; }
  git add -A data/
  if git diff --cached --quiet; then echo "no new data changes to commit (pushing any unpushed commit)"
  else
    git commit -q -m "Weekly data refresh $(date -d "$DAY" '+%b %-d, %Y' 2>/dev/null || echo "$DAY"): $(sed -n 1,2p "$ST/status.txt" | tr '\n' ' ' | cut -c1-200)" || { echo "commit failed"; exit 1; }
  fi
  # the weekly suites (incl. tests/e2e_filter_audit.py) passed on exactly this content: record it for scripts/git-hooks/pre-push
  mkdir -p .git/pf-regression; cp "$W/tests.txt" ".git/pf-regression/$(git rev-parse 'HEAD^{tree}').ok" 2>/dev/null
  ok=0; for i in 1 2 3; do
    git pull --rebase --autostash -q || { echo "pull --rebase failed (conflict?) - resolve by hand, nothing was force-pushed"; git rebase --abort 2>/dev/null; exit 1; }
    if git push -q origin HEAD; then ok=1; break; fi; sleep 10; done
  [ $ok = 1 ] || { echo "push failed 3 times (no force) - rerun weekly_finish.sh later"; exit 1; }
  echo "$(git rev-parse --short HEAD) $(date '+%F %T')" > "$W/pushed"; echo "PUSHED $(cat "$W/pushed")"
fi
echo "EMAIL_BODY=$(cat "$W/email_body_path")"
echo "EMAILED_MARKER=$W/emailed"
[ -f "$W/emailed" ] && echo "ALREADY EMAILED at $(cat "$W/emailed" 2>/dev/null; stat -c %y "$W/emailed" | cut -c1-19) - do NOT send again" || echo "NOT YET EMAILED"
