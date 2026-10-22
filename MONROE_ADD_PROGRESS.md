# Monroe add: Key West eTRAKiT + Islamorada CityView (started 2026-10-22 11:10 ET)
Clone: /workspace/pf-monroe (fresh from origin, base fa5f716). Do NOT touch parcel-finder / pf-fx.
- 11:10 cloned, copied POCs + MONROE_GAP_PLAN.md
- 11:35 Recon done. KW eTRAKiT case detail = search CASE_NO EQUALS + postback RowClick;0 -> Status/Opened/Closed/Type/PARCEL ID/violations. Islamorada permit detail = /CityViewPortal/Permit/Status?permitId=N (Application/Issued/Expiration dates, description); code cases have NO detail link -> year from case number only.
- Integration plan: monroe_enrich fills lperm/pn5/cn_open/cn5/clast + psum/csum + sigm bits (code 32, permit_recent 64, permit_open 128, NEW code_open 65536 -> sigm becomes uint32) + pcs bits (PCS order) + vsig/vscore bits RP/OV/NG/XP/US like vacancy_lib. MR_SIG chips: Open code case, Open permit, Permit last 2 yrs.
- 11:50 scripts/counties/monroe/fetch_keywest_etrakit.py written + tested. Backfill (2023-01-01 ->) launched detached:
  kw_permits pid 798642 log /workspace/raw/monroe/logs/kw_permits.log -> $RAW/monroe/kw_permits.json
  kw_cases   pid 798643 log /workspace/raw/monroe/logs/kw_cases.log   -> $RAW/monroe/kw_cases.json  (~3.7 s/case, ~4-5 h; resumable: just rerun)
- 12:00 scripts/counties/monroe/fetch_islamorada_cityview.py written + tested (2026: 876 permits, 371 code cases; permit detail ~7 s). Backfill launched: isl pid 802676 log /workspace/raw/monroe/logs/isl.log -> $RAW/monroe/isl_cityview.json (details capped per run; long)
- 12:55 build_all.sh (monroe_keywest / monroe_islamorada fetch steps), weekly_launch.sh note, refresh_status.py rows (+LAG 7), COVERAGE.md rows, README section, tests/e2e_monroe_city.py (+ in pre_push_regression.sh). Test build OK (partial data); e2e passes except data-dependent permit_recent (needs backfill). Test server: python http.server 8113 in pf-monroe. REGRESSION: use PORT=8113 (8097 may be another job's server!). After final build re-run add_tax.py data/monroe.
