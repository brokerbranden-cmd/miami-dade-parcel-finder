# Data coverage by county / city (updated 2026-10-21)

Counties are kept separate (own raw dirs, packs and status rows). Status rows live in `data/refresh-status.json`.

## Lis pendens / probate (county clerks)

| County | Lis pendens | Probate | Route | Status |
|---|---|---|---|---|
| Miami-Dade | Clerk Official Records LIS (+CLP/COT) | PAD/PRO/DCE + OCS case lists | Logged-in Official Records CSV export (registered login skips Turnstile). Paid alternatives: Clerk API $0.20/request (CFN/folio lookup only, no date/doc-type search), daily FTP $110/folder/mo | WIRED (manual browser export); LP data through 2026-10-05, probate through 2026-10-08 -> **stale**, now reported stale by filing date (>3 days) |
| Monroe | Clerk court case search: foreclosure cases (lis pendens proxy; Official Records LandmarkWeb is reCAPTCHA-gated) | Probate cases, same search | cr.monroe-clerk.com public search, no login/captcha | WIRED into weekly (`monroe_clerk`) 2026-10-21; filings through 2026-10-16 |
| Broward | County Records (RTT) free Official Records daily index FTP (doc type LP) | Broward Clerk probate cases: no free bulk source found yet | sftp://bcftp.broward.org (published public login), only last 7-10 days kept | SCRIPT READY (`scripts/counties/broward/fetch_broward_or.sh`) but the box has no port-22 egress -> needs a runner with SFTP; status row `broward_lp` reports stale until files arrive. Not yet parsed into the Broward pack |

## Miami-Dade (34 municipalities + unincorporated)

| City | County | Permits | Code cases | Source | Status |
|---|---|---|---|---|---|
| Aventura | Miami-Dade | - | - | CentralSquare eTRAKiT | NOT WIRED - interactive portal only, no bulk/API |
| Bal Harbour | Miami-Dade | - | - | SmartGov | NOT WIRED - interactive portal only, no bulk/API |
| Bay Harbor Islands | Miami-Dade | - | - | Citizenserve | NOT WIRED - interactive portal only, no bulk/API |
| Biscayne Park | Miami-Dade | - | - | CAP / GoGov (applications only) | NO PUBLIC DATA |
| Coral Gables | Miami-Dade | since 2022 | since 2022 | Tyler EnerGov CSS (public search API) | WIRED (weekly) |
| Cutler Bay | Miami-Dade | yes (recent) | yes (recent) | Tyler EnerGov CSS | WIRED (weekly) |
| Doral | Miami-Dade | since 2005 | since 2009 | Tyler EnerGov CSS (public search API) | WIRED (weekly) |
| El Portal | Miami-Dade | - | - | CAP plan review + GovPilot | NO PUBLIC DATA |
| Florida City | Miami-Dade | - | - | CentralSquare eTRAKiT | NOT WIRED - interactive portal only, no bulk/API |
| Golden Beach | Miami-Dade | - | - | online application only | NO PUBLIC DATA |
| Hialeah | Miami-Dade | since 2023 | since 2023 | Tyler EnerGov CSS (public search API) | WIRED (weekly) |
| Hialeah Gardens | Miami-Dade | - | - | fee-based Lien Library request ($325) | NO PUBLIC DATA |
| Homestead | Miami-Dade | yes (recent) | yes (recent) | Tyler EnerGov CSS (public search API) | WIRED (weekly) |
| Indian Creek | Miami-Dade | - | - | none | NO PUBLIC DATA |
| Key Biscayne | Miami-Dade | - | - | Accela Citizen Access | NOT WIRED - interactive portal only, no bulk/API |
| Medley | Miami-Dade | - | - | none | NO PUBLIC DATA |
| Miami | Miami-Dade | since 2014 | yes (recent) | ArcGIS FeatureServer | WIRED (weekly) |
| Miami Beach | Miami-Dade | since 2015 | since 2023 | Tyler EnerGov CSS (public search API) | WIRED (weekly) |
| Miami Gardens | Miami-Dade | since 2007 | since 2007 | Tyler EnerGov CSS (public search API) | WIRED (weekly) |
| Miami Lakes | Miami-Dade | - | - | CentralSquare eTRAKiT | NOT WIRED - interactive portal only, no bulk/API |
| Miami Shores | Miami-Dade | since 2002 | since 2006 | Tyler EnerGov CSS (public search API) | WIRED (weekly) |
| Miami Springs | Miami-Dade | - | - | CentralSquare eTRAKiT | NOT WIRED - interactive portal only, no bulk/API |
| North Bay Village | Miami-Dade | since 2009 | since 2015 | Tyler EnerGov CSS (public search API) | WIRED (weekly) |
| North Miami | Miami-Dade | yes (recent) | yes (recent) | Tyler EnerGov CSS | WIRED (weekly) |
| North Miami Beach | Miami-Dade | since 2004 | since 2023 | Tyler EnerGov CSS (public search API) | WIRED (weekly) |
| Opa-locka | Miami-Dade | - | - | Tyler EnerGov CSS (empty) | NO PUBLIC DATA |
| Palmetto Bay | Miami-Dade | - | - | Tyler Eden + CivicGov | NOT WIRED - interactive portal only, no bulk/API |
| Pinecrest | Miami-Dade | - | - | CentralSquare eTRAKiT | NOT WIRED - interactive portal only, no bulk/API |
| South Miami | Miami-Dade | - | - | CentralSquare eTRAKiT | NOT WIRED - interactive portal only, no bulk/API |
| Sunny Isles Beach | Miami-Dade | - | - | SmartGov | NOT WIRED - interactive portal only, no bulk/API |
| Surfside | Miami-Dade | since 1989 | yes (recent) | Tyler EnerGov CSS (public search API) | WIRED (weekly) |
| Sweetwater | Miami-Dade | yes (recent) | yes (recent) | Tyler EnerGov CSS | WIRED (weekly) |
| Unincorporated Miami-Dade | Miami-Dade | since 2024 | since 2021 | County ArcGIS layers | WIRED (weekly) |
| Virginia Gardens | Miami-Dade | - | - | none | NO PUBLIC DATA |
| West Miami | Miami-Dade | - | - | none | NO PUBLIC DATA |

Miami-Dade sources in the weekly run: `permits` (City of Miami + County Building Dept ArcGIS, fixed 2026-10-21), `county_permits`, `energov` (14 EnerGov portals, fixed 2026-10-21), `viol` (county code violations).

## Monroe (5 cities + unincorporated)

| City | County | Permits | Code cases | Source | Status |
|---|---|---|---|---|---|
| Unincorporated Monroe | Monroe | legacy permits applied before 2022-10-01 | code cases opened before 2024-01-01 | MCeSearch (mcesearch.monroecounty-fl.gov); newer records only in Oracle OPAL (no bulk export) | Historical one-time pull in pack; newer: NO PUBLIC BULK DATA |
| Marathon | Monroe | - | Special Magistrate hearing agendas (parcel IDs) | ci.marathon.fl.us PDFs | WIRED into weekly (`monroe_marathon_code`) 2026-10-21 |
| Key West | Monroe | not probed yet | not probed yet | - | TODO |
| Islamorada | Monroe | not probed yet | not probed yet | - | TODO |
| Key Colony Beach | Monroe | not probed yet | not probed yet | - | TODO |
| Layton | Monroe | not probed yet | not probed yet | - | TODO |

## Broward (31 municipalities + unincorporated)

| City | County | Permits | Code cases | Source | Status |
|---|---|---|---|---|---|
| Fort Lauderdale | Broward | yes (204,760 records, 31,194 parcels; source itself only updated through 2026-03-16) | no public layer found (CodeComplianceArea = zones only) | gis.fortlauderdale.gov BuildingPermits FeatureServer | FETCH WIRED (`broward_permits`) 2026-10-21; not yet joined into Broward distress score |
| Unincorporated Broward | Broward | BCS/POSSE permit search (per-address only) | CodeEnforcement ArcGIS folder exists but returns 404 publicly | dpepp.broward.org, bcgishub.broward.org/posse | NOT WIRED - no public bulk endpoint reachable |
| Coconut Creek | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Cooper City | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Coral Springs | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Dania Beach | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Davie | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Deerfield Beach | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Hallandale Beach | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Hillsboro Beach | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Hollywood | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Lauderdale-By-The-Sea | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Lauderdale Lakes | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Lauderhill | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Lazy Lake | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Lighthouse Point | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Margate | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Miramar | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| North Lauderdale | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Oakland Park | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Parkland | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Pembroke Park | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Pembroke Pines | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Plantation | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Pompano Beach | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Sea Ranch Lakes | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Southwest Ranches | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Sunrise | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Tamarac | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| West Park | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Weston | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
| Wilton Manors | Broward | not probed yet | not probed yet | - | TODO (inventory not finished this session) |
