# Monroe County enrichment progress (resume-friendly)
Started 2026-10-16. Raw inputs: /workspace/raw/monroe/. Scripts: scripts/counties/monroe/.
## Phases
- [ ] P1 zoning  - [ ] P2 ROGO/Tier  - [ ] P3 env layers  - [x] P4 tax (unpaid taxes layer, Oct 16 2026 pull)  - [ ] P5 clerk/permits  - [ ] P6 absentee/PA link/comps  - [ ] P7 buildability UI  - [ ] tests/push/live
## Log
- 10:40 Fetchers done & committed: county layers (mcgis4 APO_GIS via verify=False for that host only: zoning L19 6522 polys, tier L18, FLUM L20, ROGO dedication pts L1, CBRS, habitat, species focus), city layers (Key West Zoning_all_info w/ setbacks, Marathon Zoning+FLUM, Islamorada Zoning), FNAI cons lands(49), Florida Forever(38), NWI (running, 260 cells), ROGO PDFs (fetch_rogo.py -> raw/monroe/rogo.json 3,920 rows), clerk foreclosure+probate (fetch_clerk_monroe.py, public no login).
- Findings: LandmarkWeb (or.monroe-clerk.com) official records = reCAPTCHA gated (lis pendens not scraped); county-taxes.net / lienhub = Cloudflare challenge; monroe.realtaxdeed.com/realforeclose = 403 from box; Keys Weekly legal PDFs have tax-deed applications only Feb-Mar 2026 (28 parcels, sale 3/25/26).
- PA link bug: folio is 20 digits (3367 25 + 14-digit RE), paUrl needs last 14 digits as 8-6.
- ROGO final allocation period closed 7/13/2026; next opens ~7/13/2027 (657 new allocs pending ordinance) -> vacant lots w/o award can't get market-rate ROGO now.
- 10:55 More sources found: MCeSearch (mcesearch.monroecounty-fl.gov) bulk JSON api: 224,758 legacy permits (<10/2022) + 44,101 code cases (<1/2024) with 14-digit parcel id -> fetch_mcesearch.py (box got connection-reset after ~300 req: retry later with sleeps, resume-safe .mce_*_done files). Marathon code hearing agendas (219 cases w/ parcel IDs) -> marathon_code.json. Monroe Clerk civil/probate case search (cr.monroe-clerk.com) is public: 1,550 cases.
- ABSENTEE finding: of 88,557 parcels ~26k are govt (NPS 14k zip 20240, state BOT TIIF 6.3k zip 32399, USFWS 2.7k) - their mailing in DC/Tallahassee/Atlanta inflated 'absentee' & out-of-state (31k DC/GA). Fix: exclude govt/homestead/same-street; absentee = mail outside Keys zips.
- PLAN: build_monroe.py imports monroe_enrich.py (zoning mz/mzone, tier, rogo, env bits, signals, bld rating) -> new pack cols (tier,rogo,env,sigm,bld,bflag) + detail strs; app: monroe.js module (filters, drawer, preset) county-gated.
- 11:55 Enrichment built: monroe_geo.py (spatial joins -> geo_attrs.pkl), monroe_zoning.py (code->plain language), monroe_enrich.py (ROGO/Tier/env/Clerk/code/buildability), build_monroe.py integrated. BUG FOUND+FIXED: Islamorada/KW-wetlands/hydrants/public-lands layers I had pulled from the wrong (NC/ID/OH) AGOL services -> removed; Islamorada zoning now from Village BaseZoning parcel layer (7,105 rows by RE#).
- Sales: statewide cadastral only carries 2025-2026 sales (7.3k parcels) -> comps window can only reach 1/2025; FDOR SDF history not scriptable (JS portal / FTP unreachable). Holding-period filters are therefore empty for Monroe.
- UI: Monroe-only group #mrGrp (rating / Tier / ROGO / zoning type / signals / leave-out), card badge + 'Screen' line, drawer 'Buildability screen', sort 'Best buildability', ideas 'Buildable lots' etc. qPublic link fixed to KeyValue=RE (8-6).
- 12:50 e2e_monroe desktop PASS (28 checks). Moved Monroe presets to the END of IDEAS (Miami first-load uses IDEAS[0]). Regression runner /workspace/tmp/full8.sh running (monroe mobile, county, simplified, scenarios, distress, permits, vacancy, owners, export, deterrents x desktop/mobile). MCeSearch pull retried: 1999-01..06 permits fetched then host stalls again (rate limit) - will stay partial.
- 13:25 ALL GREEN: monroe desktop+mobile, county, simplified/scenarios(44/44)/distress/permits/vacancy/owners/export/deterrents desktop+mobile. MCeSearch stays unreachable (partial: ~1999-01..06 permits only). Pushing.
- LIVE verified: e2e_monroe desktop+mobile PASS against GitHub Pages (381be06).

## P4 tax layer (2026-10-18)  - resume notes
- Inputs: /workspace/raw/monroe/tax/ (copies of /workspace/downloads/tax/monroe/*.csv; v1 4,025 rows / v2 2,304 rows / county-held list 4 rows). Script: scripts/counties/monroe/add_tax.py (patches packs, no full rebuild; idempotent). Refresh notes: scripts/counties/monroe/TAX_REFRESH.md. Audit: data/monroe/tax-audit.json, meta.json -> tax.
- MATCH: tax 'Account Number'/'Property ID' (7 digits) = PA ALT_KEY (NOT the RE number: 0 accounts equal any RE) -> 20-digit folio. 1,627 of 1,628 accounts in v2 matched (99.94%; unmatched 9104873 is not on the roll). Verified: site address agrees 98.8% (1,427/1,445), owner name 96%; 51 parcels have a different name on the tax bill than the roll owner (flag, drawer note).
- DEDUPE: pulls oldest->newest, key (account, tax yr), newest wins; keys only in the older pull = resolved/paid and dropped (--keep-older-only for sensitivity). v2 is newest: subset of v1, balances up on 791 of 792 changed rows (interest), its 4 county-held balances equal the held list 'Price to Purchase'. v1-only = 1,581 current-year (2026) rows + 140 delinquent-year rows.
- DELINQUENT = tax year <= 2025. The 2026 bill is current-year (delinquent after 3/31/2027): separate flag + drawer line, not counted in years.
- Pack cols (main+condo): txy years, txo oldest yr, txb balance $, txf flags (1 cert, 2 county-held, 4 current-year unpaid, 8 owner differs, 16 3+ certs); detail str taxs; dscore/dsig(TC bit3/TX bit4)/vscore/vsig(TX bit8) include tax (same points as Miami-Dade: cert 10+4/extra yr max 18, no cert 6; vacancy +10).
- App: counties.js layer 'mtax' (Monroe only); index.html #mtGrp; app.js mt* (filters tax:any/y2/y3/cert/county + balance min, hash mtax/mtmin, card tag + Taxes line, drawer section, sort tx_d, preset 'Tax delinquent 2+ years'); export columns unchanged; sw cache v18.
- Tests: e2e_monroe.py extended (58 checks desktop+mobile incl. export header). Regression runner: /workspace/tmp/full9.sh
- 01:15 Monroe tax regression ALL GREEN (16/16, summary9). Pushed.
- 01:20 Monroe tax layer LIVE VERIFIED (e2e_monroe desktop+mobile PASS on Pages, sw v18).

## Oct 19, 2026 - owner-kind fix (RC + Individuals leak)
- Root cause: build-time owner_kind.py let some organization names through as 'person' (IGLESIA/FELLOWSHIP/CATHEDRAL/CH OF GOD etc., clubs, posts, names cut at 30 chars in Monroe/Broward, 'ATT ...'/'C O D ...' read as care-of). The filters themselves were correct.
- Fix: app-side orgName() reclassifies on load (MD 206, Monroe 112, Broward 868 parcels). Python twin scripts/org_name.py.
- tests/e2e_filter_audit.py + scripts/pre_push_regression.sh + git hook; regression at d41c912: unit, ownerkind, scenarios/export/monroe/broward desktop PASS; filter audit + mobile running.
- Oct 19 15:07 ET: pushed e727d4d (13/13 regression green); live on Pages (sw v21); live e2e_ownerkind PASS (RC+Individuals 203, 0 entity names; Monroe/Broward Individuals 0 entity names).
