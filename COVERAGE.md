# Data coverage by county / city (updated 2026-10-22)

Counties are kept separate (own raw dirs, packs and status rows). Status rows live in `data/refresh-status.json`.

## Lis pendens / probate (county clerks)

| County | Lis pendens | Probate | Route | Status |
|---|---|---|---|---|
| Miami-Dade | Clerk Official Records LIS (+CLP/COT) | PAD/PRO/DCE + OCS case lists | Logged-in Official Records CSV export (registered login skips Turnstile). Paid alternatives: Clerk API $0.20/request (CFN/folio lookup only, no date/doc-type search), daily FTP $110/folder/mo | WIRED (manual browser export); LP data through 2026-10-05, probate through 2026-10-08 -> **stale**, now reported stale by filing date (>3 days) |
| Monroe | Clerk court case search: foreclosure cases (lis pendens proxy; Official Records LandmarkWeb is reCAPTCHA-gated) | Probate cases, same search | cr.monroe-clerk.com public search, no login/captcha | WIRED into weekly (`monroe_clerk`) 2026-10-21; filings through 2026-10-16 |
| Broward | County Records (RTT) free Official Records daily index FTP (doc type LP) | Broward Clerk probate: paid Case API (api.browardclerk.org, notarized agreement); probate viewing needs registered user; AcclaimWeb returns 403 to the box | sftp://bcftp.broward.org (published public login), only last 7-10 days kept | SCRIPT READY (`scripts/counties/broward/fetch_broward_or.sh`) but the box has no port-22 egress -> needs a runner with SFTP; status row `broward_lp` reports stale until files arrive. Not yet parsed into the Broward pack |
| Broward (published notices) | Foreclosure notices published in newspapers (Notice of action / Notice of sale / notice of lis pendens), labelled **Foreclosure notice (published)** in the app | - | floridapublicnotices.com search API (Florida Press Association; POST `/` with `Accept: application/hal+json`, county 6; keywords 'lis pendens', 'notice of action foreclosure', 'foreclosure'; paged, deduped by case number, ~1 request / 2 s, no captcha) | WIRED into weekly (`broward_fc_notices`) 2026-10-22. Pull 2026-10-22: 384 Broward foreclosure cases (notices 2026-09-18 to 2026-10-22), 234 with a street address, 192 matched to 190 parcels: match rate 82.1% of notices with an address, 50.0% of all cases (the rest give only a legal description, and the roll's short legal is too truncated to match on). Not the recorded LP index: only cases that get advertised, window about 5 weeks |

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
| Key West | Monroe | since 2023-01 (eTRAKiT, by issue date) | since 2023-01 (CC cases via detail panel: status, opened/closed) | etrakit.cityofkeywest-fl.gov (CentralSquare eTRAKiT, public, no login/captcha) | WIRED into weekly (`monroe_keywest`) 2026-10-22; joined by RE number |
| Islamorada | Monroe | since 2023 (CityView permit locator + permit detail dates) | since 2023 (public CityView code-case locator: type, status, RE#; year opened only, no case detail page) | cvportal.us/CityViewPortal (Harris CityView, public, no login/captcha) | WIRED into weekly (`monroe_islamorada`) 2026-10-22; joined by RE number |
| Key Colony Beach | Monroe | issued 2023-01-03 to 2026-10-26 (1,717 permits: type, subtype, description, status, issue / expiration dates, cost, contractor) | opened 2023-01-03 to 2026-10-21 (1,059 records: code enforcement, violations, warnings, liens; open / closed, parcel number) | Ch. 119 public-records export from the City (Citizenserve Excel, received 2026-10-27; portal search itself needs reCAPTCHA) | LOADED 2026-10-27 from a one-off export (`load_kcb_records.py`; drop new xlsx in `$RAW/monroe/key_colony_beach/`). The City sends reports only on request - no automatic monthly feed, so re-request periodically. Joined by parcel number (cases) or unique site address (permits; condo buildings with many units at one address are left unmatched) |
| Layton | Monroe | - | - | none published | NO PUBLIC DATA; Ch. 119 request drafted in MONROE_GAP_PLAN.md |

## Broward (31 municipalities + unincorporated)

| City | County | Permits | Code cases | Source | Status |
|---|---|---|---|---|---|
| Fort Lauderdale | Broward | yes (ArcGIS, source itself updated only through 2026-03-16) | no public layer found (CodeComplianceArea = zones only) | gis.fortlauderdale.gov BuildingPermits FeatureServer | WIRED (`broward_permits`), joined into the Broward score + filters 2026-10-22 (distress-type permits: demolition, unsafe, roof, damage repair). 31,194 parcels with permits, 1,972 distress-type permits in the last 24 months (to 2026-03-16). |
| Unincorporated Broward | Broward | BCS/POSSE permit search (per-address only) | CodeEnforcement ArcGIS folder exists but returns 404 publicly | dpepp.broward.org, bcgishub.broward.org/posse | NOT WIRED - no public bulk endpoint reachable |
| Coconut Creek | Broward | - | - | EnerGov energov.coconutcreek.net (connection fails from the box) | NOT WIRED - unreachable from the box; may work from another network |
| Cooper City | Broward | - | - | Accela ACA | NOT WIRED - interactive portal only, no bulk/API |
| Coral Springs | Broward | - | - | eTRAKiT (per-address only) | NOT WIRED - interactive portal only, no bulk/API |
| Dania Beach | Broward | EnerGov tenant nearly empty (7) | EnerGov nearly empty (9) | cityofdaniabeachfl-energovweb.tylerhost.net | NOT WIRED - tenant just went live; re-check |
| Davie | Broward | - | - | eSuite | NOT WIRED - interactive portal only, no bulk/API |
| Deerfield Beach | Broward | - | - | gov-easy portal | NOT WIRED - interactive portal only, no bulk/API |
| Hallandale Beach | Broward | - | - | AGOL Experience app only | NOT WIRED - interactive only |
| Hillsboro Beach | Broward | - | - | none found (probe 2026-10-22) | NO PUBLIC DATA |
| Hollywood | Broward | - | - | Accela ACA (since 2026-08-04) | NOT WIRED - interactive portal only, no bulk/API |
| Lauderdale-By-The-Sea | Broward | - | - | none found (probe 2026-10-22) | NO PUBLIC DATA |
| Lauderdale Lakes | Broward | - | - | none found (probe 2026-10-22) | NO PUBLIC DATA |
| Lauderhill | Broward | EnerGov nearly empty (23) | EnerGov nearly empty (2) | cityoflauderhillfl-energovweb.tylerhost.net; legacy eGovPlus unreachable | NOT WIRED - nearly empty |
| Lazy Lake | Broward | - | - | none found (probe 2026-10-22) | NO PUBLIC DATA |
| Lighthouse Point | Broward | - | - | none found (probe 2026-10-22) | NO PUBLIC DATA |
| Margate | Broward | - | - | Click2Gov BP | NOT WIRED - interactive portal only, no bulk/API |
| Miramar | Broward | yes, EnerGov (466k records) | none public (EnerGov code module returns 0) | Tyler EnerGov CSS miramarfl-energovweb.tylerhost.net | WIRED permits only (`broward_energov`) 2026-10-22. Pulled 2026-10-22: 466,286 permits (458,072 with a folio), 3,244 distress-type permits in the last 24 months; newest 2026-10-22. |
| North Lauderdale | Broward | - | - | none found (probe 2026-10-22) | NO PUBLIC DATA |
| Oakland Park | Broward | yes, EnerGov (29.6k records, tenant since 2023) | yes, EnerGov (8.2k records) | Tyler EnerGov CSS oaklandparkfl-energovweb.tylerhost.net | WIRED (`broward_energov`) 2026-10-22. Pulled 2026-10-22: 29,558 permits (26,316 with a folio), 1,140 distress-type permits in the last 24 months; 8,167 code cases (8,055 with a folio), 6,511 opened in the last 5 years, 961 open; newest 2026-10-22. |
| Parkland | Broward | - | - | MyGovernmentOnline | NOT WIRED - interactive portal only, no bulk/API |
| Pembroke Park | Broward | - | - | none found (probe 2026-10-22) | NO PUBLIC DATA |
| Pembroke Pines | Broward | yes, EnerGov (253k records) | yes, EnerGov (158k records) | Tyler EnerGov CSS pembrokepinesfl-energovweb.tylerhost.net | WIRED (`broward_energov`) 2026-10-22. Pulled 2026-10-22: 253,233 permits (229,951 with a folio), 4,492 distress-type permits in the last 24 months; 158,208 code cases (83,845 with a folio), 17,721 opened in the last 5 years, 1,693 open; newest 2026-10-22. Note: about 47% of Pembroke Pines code cases carry no parcel number and cannot be joined. |
| Plantation | Broward | - | - | Accela ACA | NOT WIRED - interactive portal only, no bulk/API |
| Pompano Beach | Broward | - | - | Click2Gov BP | NOT WIRED - interactive portal only, no bulk/API |
| Sea Ranch Lakes | Broward | - | - | none found (probe 2026-10-22) | NO PUBLIC DATA |
| Southwest Ranches | Broward | - | - | none found (probe 2026-10-22) | NO PUBLIC DATA |
| Sunrise | Broward | yes, EnerGov (338k records) | yes, EnerGov (150k records) | Tyler EnerGov CSS energov.sunrisefl.gov | WIRED (`broward_energov`) 2026-10-22. Pulled 2026-10-22: 338,456 permits (336,351 with a folio), 2,534 distress-type permits in the last 24 months; 149,955 code cases (149,018 with a folio), 22,023 opened in the last 5 years, 4,097 open; newest 2026-10-22. |
| Tamarac | Broward | - | - | Click2Gov BP | NOT WIRED - interactive portal only, no bulk/API |
| West Park | Broward | - | - | none found (probe 2026-10-22) | NO PUBLIC DATA |
| Weston | Broward | - | - | Accela ACA; portal.westonfl.org layers need a token | NOT WIRED - interactive portal only, no bulk/API |
| Wilton Manors | Broward | - | - | Citizenserve | NOT WIRED - interactive portal only, no bulk/API |


Broward probe details: `BROWARD_PROBE.md` (2026-10-22). Broward permits / code cases join to parcels by the 12-character BCPA folio (EnerGov `MainParcel`, FTL `PARCELID`); scoring and filters in `scripts/counties/broward/broward_permit_lib.py` + `build_broward.py`.

Broward auctions (`broward_auctions`, weekly since 2026-10-22): `fetch_auctions_fl.py broward https://broward.realforeclose.com https://broward.realtaxdeed.com`. Checked 2026-10-22: both sites return 403 to plain curl and to a bare `Mozilla/5.0` User-Agent but 200 to the full browser User-Agent the script sends; `www.broward.realtaxdeed.com` fails with an SSL hostname mismatch, so the hosts are used without `www.` (tax-deed sales had been silently missing).
