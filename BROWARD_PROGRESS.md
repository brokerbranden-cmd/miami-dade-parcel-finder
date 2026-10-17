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
