# Broward County + Monroe-gaps progress (resume-friendly)
Started 2026-10-17. Raw inputs: /workspace/raw/broward/. Scripts: scripts/counties/broward/. Template: MONROE_PROGRESS.md.
## Plan
- [ ] M1 Monroe gaps (tax collector / tax certs / SDF sales / MCeSearch / records-request drafts in drafts/)
- [ ] B1 Broward fetch (cadastral CO_NO=16, FEMA 12011, BCPA/GIS, zoning, SDF sales)
- [ ] B2 build_broward.py -> data/broward/ packs
- [ ] B3 app wiring (counties.js, broward module, presets), CSV County column
- [ ] B4 distress layers (tax collector, clerk, code, permits, unsafe)
- [ ] B5 tests (e2e_broward desktop+mobile + regression), push, live verify
## Log
- 15:10 SOURCES FOUND (Broward + Monroe gaps):
  * FDOR PTO data library works via anonymous SharePoint REST listing (…/dataportal/_api/web/GetFolderByServerRelativeUrl). Published: only 2026 preliminary NAL/SDF (Tax Roll Data Files/NAL/2026P, SDF/2026P) + 2026F for 48 counties (NOT Broward/Monroe). Broward NAL16P202601.csv = 754,549 parcels w/ owner, mailing, values, use, 2 sales, exemptions, S_LEGAL (50 MB zip) -> raw/sdf/. SDF only holds sales 2025-2026 (Broward 97,254; Monroe 8,596) => NO older history publicly downloadable; prior-year SDF (2009+) / NAL (2002+) are by request only (PTOTechnology@floridarevenue.com) -> drafts/.
  * Broward owner names are 'LAST,FIRST & SECOND' (comma) => nameOrder last-first. OWN_STATE is the full state name (FLORIDA, NEW YORK, CANADA).
  * Broward geometry: statewide cadastral CO_NO=16 = 766,819 polys (centroids fetched by fetch_broward_parcels.py, chunked/resumable). FEMA: hazards.fema.gov unreliable from box (SSL EOF); using BCGIS hosted FloodZones2024 (17,366 polys).
  * County ArcGIS org JMAJrTsHNLrSsWf5 (services.arcgis.com): FutureLandUse (3,311 polys, county land use plan), BMSD zoning (unincorporated, 4,860 by FOLIO), BCPAParcelsVacant, Broward_BuildingFootPrints (425k). City zoning layers: Fort Lauderdale (official), Miramar, Deerfield, Dania, Cooper City, Pembroke Park, Pompano (Zoning Districts), Lauderhill (by FOLIO). NOT found as public layers: Hollywood, Coral Springs, Sunrise, Davie, Plantation, Tamarac, Hallandale, Weston, Coconut Creek, Margate (address points only), Oakland Park, etc. -> those parcels use county Future Land Use only.
  * Distress: broward.realforeclose.com + broward.realtaxdeed.com calendars are public (fetch_auctions_fl.py). Broward Clerk case search = reCAPTCHA; Official Records (officialrecords.broward.org) + county-taxes.net/broward + broward.org pages = Cloudflare challenge (not bypassed). Monroe realtaxdeed calendar reachable but no sale days Jun 2026-Jan 2027; Monroe Keys Weekly legals Mar-Oct 2026 downloaded: no new tax-deed ads after 3/5/2026; 2026 Monroe cert sale advertised only ~4 parcels (LienHub).

## 16:xx APP WIRING (code committed, data not yet built)
- counties.js: broward entry (layers owners,teardown,comps,flood,mzoning,mscreen,broward; nameOrder last-first; BCPA RecInfo link; area/planning text).
- app.js/index.html: Monroe buildability screen generalized to layer `mscreen` (+`rogo` for Tier/ROGO rows); Broward auction/legal-notice drawer section; Broward presets (duplex, foreclosure/tax-deed sale scheduled).
- RealAuction: broward.realtaxdeed.com works WITHOUT www; only status=scheduled sales used.
- TODO: run build_broward.py once centroids.jsonl exists, tests/e2e_broward.py, regression suites, push.

## 17:xx PHASE 1 DATA BUILT (data/broward/, not yet committed)
- KEY FIX: Broward folios are 12 CHARACTERS and condo units carry letters (474131AA0010). Folio kept alnum-uppercase end to end (pack, saved.js normFolio, skiptrace import, search, deep link, BCPA RecInfo link). Fixes a latent saved.js truncation to 13 digits for Monroe too.
- Counts: 753,239 parcels (487,944 main + 265,295 condo/unit pack); 39,903 comps; 39,514 owner groups (6,606 with 5+ parcels).
- Flood (BCGIS FloodZones2024): X 490k, AE 196k, AH 61k, AO 1.6k, VE 382. Zoning: city/BMSD layers cover 258k (Fort Lauderdale, Miramar, Deerfield, Dania, Cooper City, Pembroke Park, Pompano, Lauderhill, BMSD), the rest uses the county Land Use Plan (flagged in the drawer). Buildability screen: green 321k, yellow 100k, red 3.3k (AE/AH is informational, VE red).
- Absentee = mailing outside Broward ZIPs (112,596 flagged incl. 75,621 out of state); government owners excluded (17,510).
- Auctions (RealAuction): 129 foreclosure + 56 tax-deed parcels matched (RealAuction drops the letters from condo folios; matched by digits then address+unit).
- NOT public: tax collector delinquent / certificates (Cloudflare), Clerk lis pendens / probate, code violations, permits, unsafe structures -> drawer says so, drafts 05/06 written.
- e2e_broward desktop passes (2 expectation tweaks); regression runner /workspace/tmp/full_bw.sh running.
