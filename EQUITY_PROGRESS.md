# Estimated equity — progress (resume from here)
- [x] Probe Clerk Official Records: public Name/Document search works in fresh Playwright Chrome (no login needed; login not available on box: last LP run had clerk_logged_in=false). Date-range MOR search caps at 500/day (daily volume higher) -> per-owner name search instead.
- [x] scripts/fetch_mortgages.py -> RAW/clerk_owner/<folio>.json (priority: open pre-foreclosure, auctions, probate, then distress score desc). Background run started 2026-10-21 ~21:00 ET, log RAW/fetch_mortgages.log, ~4 workers, resumable (skips files <30 days old).
- [ ] scripts/build_equity.py -> data/equity.json.gz
- [ ] app.js card/filters/table/CSV, ask.js parser, sw.js v26
- [ ] build_all.sh / weekly hook
- [ ] tests/e2e_equity.py, regression, push, live verify
