# Estimated equity — progress (resume from here)
- [x] Probe Clerk Official Records: public Name/Document search works in fresh Playwright Chrome (no login needed; login not available on box: last LP run had clerk_logged_in=false). Date-range MOR search caps at 500/day (daily volume higher) -> per-owner name search instead.
- [x] scripts/fetch_mortgages.py -> RAW/clerk_owner/<folio>.json (priority: open pre-foreclosure, auctions, probate, then distress score desc). Background run started 2026-10-21 ~21:00 ET, log RAW/fetch_mortgages.log, ~4 workers, resumable (skips files <30 days old).
- [x] scripts/build_equity.py -> data/equity.json.gz (commit 6xx)
- [x] equity.js + app.js hooks (card/drawer/table/CSV/filters/presets), ask.js parser, sw.js v26, tests updated for appended CSV cols (07f081f)
- [x] build_all.sh clerk_mtg + equity steps, README section
- [ ] tests/e2e_equity.py, regression, push, live verify
- e2e_equity desktop+mobile ALL PASS on local 8098 (server in /workspace/pf-fx). Fetcher restarted with 8 workers (~60-100/min).
- NEXT: let fetch run, rebuild data/equity.json.gz, commit, PORT=8098 bash scripts/pre_push_regression.sh, push, live verify.
