# Miami-Dade Parcel Finder

**Live site:** https://brokerbranden-cmd.github.io/miami-dade-parcel-finder/

A fast, static web app for finding investment properties anywhere in Miami-Dade County. It runs on real public data from Miami-Dade County GIS and the Property Appraiser (PA), with nothing made up. There's no server-side code: the browser downloads compact data packs once, caches them in IndexedDB, and does all the filtering locally.

**Current build:** 922,797 properties from the **2026** PA roll (live roll as of the 10/06/2026 pull; newest recorded sale 09/22/2026). Farmland (7,713 parcels) and reference-only folios (7,610) are left out.

## Run it

```bash
cd parcel-finder
python3 -m http.server 8080      # then open http://localhost:8080/
```

Any static file host works. The `.bin.gz` files are fetched as raw bytes and unzipped in the browser (`DecompressionStream`), so the host must **not** add its own `Content-Encoding: gzip` to them. Plain static hosts (GitHub Pages, Netlify, Vercel, S3, Cloudflare Pages) serve them as-is.

## Layout

```
index.html        page markup (same layout as the original app, plus map/link/export controls)
styles.css        original styles + map, drawer and mobile additions
app.js            all app logic (filters, sorting, cards/table/map, drawer, CSV, URL state)
vendor/leaflet/   Leaflet 1.9.4 (stored locally, loaded only when the map is opened)
data/             meta.json + binary packs (see below)
scripts/          reproducible data pipeline (build_all.sh runs everything)
tests/e2e.py      headless Playwright end-to-end smoke test
shots/            screenshots from the test runs
```

## Data packs (about 60 MB total, gzip)

| file | size | loaded |
|---|---|---|
| `meta.json` | 63 KB | at start (dictionaries, zoning tables, stats) |
| `main.bin.gz` | 19.2 MB | at start: 572,960 non-condo properties, all filter columns |
| `main-detail.bin.gz` | 19.1 MB | lazily: first drawer open / export (mailing address, legal, older sales, grantor, deed, assessed/taxable) |
| `main-geo.bin.gz` | 2.4 MB | lazily: map view, area search, export, or about 4 s after load |
| `condo.bin.gz` | 7.9 MB | only when "Condo units" is picked: 349,837 units |
| `condo-detail.bin.gz` | 11.4 MB | lazily |
| `condo-geo.bin.gz` | 48 KB | lazily (units share building points) |

Pack format: `uint32 header length` + JSON header `{n, cols:[{name,type,offset,bytes}]}`, then 4-byte-aligned typed-array columns (uint8/16/32) and newline-joined string columns, with the whole file gzipped. Dates are days since 1900-01-01. Packs are cached in IndexedDB under `meta.ver`, so a rebuild invalidates the cache automatically.

## Data sources

| what | source |
|---|---|
| Property roll: owners, mailing address, site address, land use (DOR), PA zoning, lot, building sqft, beds/baths, units, stories, year built, 2026 + prior values, assessed, taxable, exemptions, last 3 sales with qualification flags, grantor, deed book/page, legal description, TINC (tax-increment) code, parcel point | Miami-Dade GIS `MD_ComparableSales/MapServer/5` <https://gisweb.miamidade.gov/arcgis/rest/services/MD_ComparableSales/MapServer/5> |
| County (unincorporated) zoning districts | `MD_LandInformation/MapServer/18` <https://gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer/18> |
| Municipal zoning districts (Miami 21, Hialeah, Miami Beach, etc.) | `MD_LandInformation/MapServer/19` <https://gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer/19> |
| Community Redevelopment Areas | `MD_LandInformation/MapServer/20` <https://gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer/20> |
| Plain-English names for PA zoning codes (one lookup per distinct code) | PA public service proxy `https://apps.miamidadepa.gov/PApublicServiceProxy/PaServicesProxy.ashx?Operation=GetPropertySearchByFolio` |
| Map tiles | Esri (Canvas gray, World Imagery) and OpenStreetMap |

## Rebuilding the data

```bash
pip install pandas pyarrow geopandas shapely requests
RAW=/workspace/raw scripts/build_all.sh
```

Order: `fetch_pagis` → `fetch_layers` → `load_raw` → `fetch_zone_desc` → `spatial_join` → `build_data`. ArcGIS is paged by OBJECTID in 5,000-row chunks. The fetch is resumable, because finished chunks are skipped.

## How the derived fields work (and where the gaps are)

- **City zoning** is a point-in-polygon join of each parcel's PA point against the municipal zoning layer (preferring a polygon from the parcel's own city). Unincorporated parcels, or parcels with no city match, use the county layer. 931,498 of 938,120 folios matched. About 0.7% (mostly right-of-way, water and edge parcels) show "Not found on the zoning map". Miami 21 transect parameters (stories, units/acre, minimum lot) come from the Miami 21 code tables and are shown only for City of Miami districts.
- **Zoning type (plain-language groups)** comes from the PA's PRIMARY_ZONE code. 266 codes are described. Nine codes (0000, 2900, 3440, 5200, 6707, 7900, 8008, 9751, L1ST) have no description in the PA's own system, so they show the code only.
- **Redevelopment area (CRA)** comes from the county's CRA polygons, named "<name> CRA". Parcels outside those polygons that still carry a PA tax-increment (TINC 90xx) code are labeled "Tax increment district 90xx (city)". The original app's PA-internal CRA names weren't published anywhere, so these names may read differently.
- **Owner kinds and flags** come from `scripts/owner_kind.py` (word-based rules, shared by the owner filters and the owner-portfolio institution flags): **Companies & organizations** = every non-government organization - LLC/INC/CORP/LP/LTD/PA/CO, banks and lenders, utilities (FPL, phone, rail), condo/homeowner associations, churches, schools, hospitals, foundations, holding/property/management/realty companies, with common abbreviations and typos (MANGM, MGMT, ASSN, NATL ...); **Government** = county, cities/towns/villages, state, federal, water-management and other special districts (CDDs), authorities, boards, school boards, public colleges. Ambiguous words that are also surnames or given names (BANK, POWER, LIGHT, CO, PA, CHURCH ...) count only with backing words or when the name is not shaped like a person (`JOHN BANK` stays an individual, `OCEAN BANK` is a bank); `C/O`, `ATTN` and `%` mailing lines are ignored and the remaining owner lines are read together. Trust = TRUST/TRS/REV TR words without an organization suffix. Estate/heirs from EST OF / HEIRS words. Rules are still heuristics, so expect a few misfires. Out-of-state = mailing state isn't FL, or a foreign mailing address. Absentee = mailing ZIP differs from the site ZIP. Homestead and senior come from the PA exemption amounts.
- **Market sales:** the PA qualification flag (Q = market sale, U = not market) is kept for the last two sales. "Only real market sales" uses it.
- **"Updated" date** in the subtitle is the newest recorded sale date in the roll (09/22/2026). Values are the PA's 2026 roll as published at pull time. Final 2026 values can still change.
- **Bulk deeds:** the drawer flags when the last deed (same book-page and date) covers several parcels, because the sale price is then for the whole package.

## Additions beyond the original

- Map view (Leaflet, canvas-drawn so 900K+ points stay smooth), with Simple, Streets and Satellite base maps. Click a dot to open the record. Stacked points (condo towers) open a pick list. Other controls: "Search this map area", "Zoom to results", and "Show on map" from any record.
- All filters, sort, view and map area live in the URL hash. The "Copy link" button shares an exact search, and opening a link restores it.
- Export CSV is always available. It includes 8 extra columns: senior exemption, county taxable value, prior-year value, seller, deed book-page, latitude/longitude and PA link.
- New presets: "Tired landlords (absentee, 20+ yrs)" and "Lots owned from far away". New sort: lowest value per lot sq ft.
- Drawer additions:
  - Street View link
  - Change versus last year's value
  - Last market sale versus today's value
  - Seller, deed book-page and the bulk-deed warning
  - "Same owner name" portfolio count with a one-click "Show them all"
- Lazy-loaded detail, geo and condo packs. The first load is about 19 MB. Later visits read from the browser cache.

## Distress layers & Distress Score

Every signal is a real public record matched to a folio; nothing is inferred except the small "soft" factors.

| Code | Signal | Source | Access | Pts |
|---|---|---|---|---|
| FC | Foreclosure sale scheduled | miamidade.realforeclose.com auction calendar (`fetch_auctions.py`) | scraped, ~1 req/s | 35 |
| TD | Tax deed application / sale | TaxSys "Public-Open Deeds" report + realforeclose TAXDEED sales | scraped (headless browser) | 30 |
| LP | Lis pendens | Clerk Official Records CSV exports (logged-in browser) dropped in `raw/lp_downloads/lp_YYYYMMDD_YYYYMMDD.csv`, merged with cached scrapes, deduped by CFN; matched by plat book/page+lot/block, defendant name+legal, address+defendant; classified mortgage / HOA-condo / other | login (manual/browser export); `fetch_clerk.py` scrape is fallback only (reCAPTCHA) | 25 (15 if >12 mo) |
| US | Unsafe structure case | County Open_Building_Violations (ArcGIS) | official API | 22 |
| TC | Unpaid tax certificates | TaxSys "Public-Open Certificates wAddr" | scraped report | 10 +4/extra yr (max 18) |
| PR | Probate / estate / unknown heirs | (a) Clerk Official Records PAD (probate & administration) and PRO (probate order of distribution) CSV exports in `raw/probate_downloads/`, matched by address / plat+lot+block / decedent name; (b) probate **case filed** records from the Clerk's case system (OCS File Date lists in `raw/probate_cases/ocs_YYYYMMDD.txt`, `-CP-` cases only), matched by case number to a PRO or by decedent name; (c) owner name "EST OF"/heirs; (d) No-Heir Probates output. See "Probate layer" below | Clerk exports (logged-in browser) + local | 15 |
| DC | Owner deceased | Clerk DCE (death certificate recorded, EST OF) exports in `raw/probate_downloads/`, decedents of PAD/PRO/OCS cases whose name matches the current owner, and Obituary Scraper matches; one record per folio per case (evidence is folded together) | Clerk exports + local | 15 (7 with PR) |
| LN | Code / building lien | County BuildingViolationLien, CodeCompliance Lien + ReferredtoFinance (ArcGIS) | official API | 12 |
| BV | Open building violation | County Open_Building_Violations | official API | 8 |
| CC | Open code compliance case | County CodeComplianceViolation_Open_View | official API | 8 (4 with BV) |
| RC | 40/50-yr recert overdue | City of Miami 40_Year_Recertification (ArcGIS) | official API | 8 |
| TX | Delinquent taxes, no cert yet | TaxSys "Public-unpaid accts non-cert" | scraped report | 6 |

Soft factors (capped at 20 total): out-of-state owner 6 / absentee 4; owned 20+ yrs 5 / 10+ yrs 2; teardown (bldg < 20% of value) 6 or vacant lot 3; no homestead 3.
**Score = min(100, hard points + soft points)**; government-owned parcels score 0. The drawer shows the breakdown.

Blocked / not covered: unattended Clerk search (reCAPTCHA; solved by the logged-in CSV exports above; CFN deep links need a per-session token, so links go to the Official Records search page with the CFN + case # shown),
City of Miami code cases/liens (not published; CityView per-case lookup only), miamidade.realtaxdeed.com (403; tax deeds sell on realforeclose).

UI: "Distress signals" filter (chips with counts, min score), presets 🔥 Hottest leads / Pre-foreclosure / Tax deeds / Unsafe,
sort by score, score badge on cards + table column, signal records with source links in the drawer, CSV columns
Distress Score/Signals/Signal Details/Signal Sources, map "Color by score".

Weekly refresh: `scripts/build_all.sh` (or just the four `fetch_*` + `build_distress.py` + `build_data.py`).

New-lead digest: `python3 scripts/top_leads.py --since 2026-10-01 [--min 40 --limit 50 --out out/top_leads]`
writes `out/top_leads.csv` and `out/top_leads.html` (email body). It sends nothing.

## Owner portfolios

`scripts/owners_lib.py` (run inside `build_data.py`) groups every parcel in the county by owner and writes an `og` group id
into the main/condo packs plus `data/owners.json.gz` (per group: parcels, condo units, parcels with public-record distress,
total market value, display name, number of name variants, flags).

* Companies, trusts and government: grouped by normalized first-owner name (punctuation, `L L C`/`LLC`/`INC`/`CORP`/`TR`/`TRS`/`&W`/
  `JTRS`, trust dates and "revocable/living trust" words are stripped, so spelling variants of one entity land together).
* Individuals: normalized name **plus** normalized mailing address (common names would otherwise merge unrelated people).
* Second link: names that share one specific mailing address (street + unit + ZIP; `STE 403`/`#403`/`403`, `2 FL`/`2ND FLOOR` unify)
  are merged when the address isn't the owner's own home, no government / bank / association uses it, and the merged group stays
  at **12 names or fewer** (registered-agent and law-firm addresses can't chain unrelated LLCs).
* Flags: government, bank / lender / GSE, association / church / non-profit / utility, large holder (200+ parcels). Flagged groups are
  left out of the portfolio filters and rank last in the portfolio sorts unless "Include banks, government & big institutions" is checked.
* "Distressed parcel" = has at least one public-record distress signal (foreclosure, lis pendens, tax deed/certificate/delinquency,
  unsafe structure, violation, code case, lien, recert, probate/deceased owner).

Current build: 63,513 owner groups with 2+ parcels (282,908 parcels), 31,090 mailing-address links, 2,945 non-institutional owners
with 2+ distressed parcels.

UI: "Owner holds N+ properties", "Owner has 2+ distressed parcels" and "Include institutions" in *Who owns it*; presets
**🏘 Multi-property motivated owners** and **Owners with 5+ properties**; sorts *Owner's distressed parcels* / *Owner's portfolio size*;
an "Owner has N · M distressed" badge on cards; and an **owner portfolio panel** (from the drawer's Portfolio row): totals, market value,
types, cities, distress signals across the portfolio, avg years held, names and mailing addresses, a map of holdings, the parcel list
(clickable, with ☆), Show all on map / in table (shareable `#ogf=<folio>` link), Export CSV and Copy folios.

## Vacancy & condition hints

A **"likely vacant / neglected" hint** (0–100, `vscore` + `vsig` bits in the main/condo packs) built in `scripts/vacancy_lib.py`
(run inside `build_data.py`). It uses public records only. Nothing comes from imagery, and there are **no utility proxies**:
Miami-Dade publishes no water/electric shut-off or usage data, so none is used.
No county layer carries a "boarded" or "vacant structure" flag either (searched every violation/lien layer). Only parcels with a building (building value > 0)
and a non-government owner are scored.

| Code | Signal | Source | Points |
|---|---|---|---|
| NA | No homestead **and** absentee owner (mails to another ZIP) | PA roll | 15 (18 if out of state; 5 = no homestead, mail at the property) |
| US | Open unsafe structure case | County Open_Building_Violations | 25 |
| NG | Neglect-type code case, open or in lien: junk/trash/overgrowth, abandoned property, structure upkeep, minimum housing, unsecured pool, pool maintenance, bees | County CodeCompliance Open + Lien views | 15 |
| FR | Foreclosure-registry code case (failure to register/renew a foreclosed property) | same | 12 |
| XP | Expired or revoked permit with no newer permit (any covered city), open county "Expired Permit" building case, or an open municipal work-without-permit / expired-permit case | permit index (`merge_permits.py`); County building cases | 8 |
| NP | No permit on record since the start of the city's **permit-data window** (only cities with 5+ years of public permit history; built before the window starts) | permit index, per-city window | 6 (10 if built 1970 or earlier) when the window is 8+ yrs; half (3 / 5) for 5-8 yrs; never otherwise |
| LO | Owned 20+ years | PA last sale | 5 |
| LB | Building worth < 20% of the total value | PA values | 8 |
| TX | Tax delinquent (TC / TX / TD distress signals) | TaxSys | 10 |
| ES | Estate / probate / owner deceased (PR / DC) | distress layer | 8 |
| OV | Other open code / building case | County violations | 4 |
| RP | **Recent permit** (issued in the last 24 months, any covered city), so someone is working on it | permit index | −15 |

**Vacancy hint = clamp(0, 100, sum of points)**. 25+ = "Possibly vacant", 40+ = "Likely vacant / neglected", 60+ = strong.
It feeds the Distress Score as a capped soft signal: **+5 at 40+, +8 at 60+** (on top of the other soft factors; total score still capped at 100).

Permit coverage is uneven, so "no permit" only counts where a city's permit history is public and long enough (see **Permit history & code cases**
below): >= 8 years of history scores full points, 5-8 years half, anything shorter or no data scores nothing. The drawer says which coverage applies
to the parcel's city. Municipal code cases feed NG / FR / OV / XP the same way the county's layers do.

Current build: 449,598 parcels scored; 841 at 40+, 53 at 60+ (before municipal permit / code-case data: 473 and 27). Signal counts: NA 33,777 · US 1,762 · NG 8,585 · FR 442 · XP 9,724 ·
NP 30,479 (only in cities with 5+ yrs of permit history) · LO 108,872 · LB 41,508 · TX 10,100 · ES 3,384 · OV 18,516 · RP 76,357. Signals that went up are from municipal code cases / permits; NA, LO, LB, TX moved by a few hundred or fewer because the roll and owner-type classification were refreshed in the same build.

UI: *Vacancy & condition* filter group (signal chips with counts, "Vacancy hint" 25+/40+/60+, "only ones I marked vacant"),
preset **🏚 Likely vacant / neglected**, sort *Most likely vacant / neglected*, card badge, table column, CSV columns
(Vacancy Hint, Vacancy Signals, Last Permit On Record, Marked Vacant/Damaged, Condition Note). The drawer shows the point breakdown,
the last permit, an **aerial thumbnail** (Esri World Imagery export, dates vary) and **Street View / Satellite** links (Google Maps).
On a saved property you can tick **Looks vacant / damaged** and write a **condition note**. Both are stored with the saved list
(`vacant`, `cond` in `saved.js`) and included in its JSON/CSV export/import.

## Permit history & code cases (all municipalities)

`scripts/fetch_county_permits.py`, `scripts/fetch_energov.py` and `scripts/fetch_violations.py` pull every public machine-readable permit / code-case
source at ~1 request/second; `scripts/merge_permits.py` normalises them to per-folio records (`RAW/permit_index.json`, `RAW/muni_cases.json`);
`scripts/permit_lib.py` turns that into pack columns; `scripts/permit_catalog.py` records, for every municipality, where the portal is and why a city
is not ingested. All steps are non-fatal in `build_all.sh` (a failed source falls back to its cached file; with no index the vacancy hint falls back to the
old City of Miami / County aggregates).

* **Sources**: City of Miami `Building_Permits_Since_2014` (ArcGIS); County Building Dept permits (`MD_LandInformation/MapServer/1`, ~262K rows, dense 2023-today,
  ~99% unincorporated) + County certificates of occupancy (2002-today); County Code Compliance `CCVIOL_gdb` (all cases incl. closed) + building violations;
  and the **Tyler EnerGov Citizen Self-Service public search API** (no login) for Hialeah, Miami Gardens, Miami Beach, Coral Gables, Doral, North Miami Beach,
  Homestead, Miami Shores, Surfside, North Bay Village (+ Sweetwater, Cutler Bay, North Miami, Opa-locka whose tenants went live in 2026 with almost no history).
  EnerGov caps a search at 10,000 rows, so each portal is read in year / half-year / quarter windows that split recursively.
* **Matching**: the record's own 13-digit parcel number when it is a real PA folio, else an exact normalised street address (+ZIP) inside the portal's own
  municipality, only when exactly one folio carries that address (no fuzzy matching).
* **Per folio** (`permit_index.json`): last permit date, permits in the last 5 yrs, open / expired / revoked counts (statuses classified from each portal's
  own wording; voids, cancelled, revisions, signs, licences etc. are ignored), last permit type; code cases: open count (cases older than 2016 that are still "open"
  are kept in totals but not flagged), cases in the last 5 yrs, last opened / status / type, lien flag, neglect / unsafe / foreclosure-registry / work-without-permit flags.
* **Coverage window** per city and kind: the first year from which every later year holds at least 40% of the median of the last three full years. That year
  is stored in `permit_index.json -> coverage`, shipped in `meta.json -> permitCov`, and shown in the filter panel ("Permit & code data coverage by city") and in the drawer.
* **Distress**: municipal open cases become CC (code case), BV (work without / expired permit) or US (unsafe structure) signals, and cases with a lien / fines running add LN.
* **UI**: "Permits & code cases" chips (open permit, expired / revoked permit, permit in last 5 yrs, no permit in the city window, open code case, code case in last
  5 yrs, code lien / fines, city has permit data), a "Permits & cases" table column, a drawer section (last permit, 5-yr count, case summary, per-city coverage), and
  CSV columns (Permits (5 yrs), Last Permit Detail, Open Code Cases, Code Cases (5 yrs), Code Case Detail, Permit/Code Signals, Permit Data Coverage, Code Data Coverage).

<!-- PERMIT_COVERAGE -->
Built 2026-10-09. Window = first year from which the source holds >= 40% of its recent yearly volume.

**Ingested**

| City | Permits | Code cases | Records ingested (permits / code) | Folio+address match | Source |
|---|---|---|---|---|---|
| Coral Gables | since 2022 (<5 yrs) | since 2022 | 63,975 / 27,034 | 96% / 97% | [Tyler EnerGov CSS](https://coralgablesfl-energovpub.tylerhost.net/apps/selfservice) |
| Cutler Bay | none usable | none usable | 93 / 47 | 65% / 57% | [Tyler EnerGov CSS](https://townofcutlerbayfl-energovweb.tylerhost.net/apps/selfservice) |
| Doral | since 2005 (8+ yrs) | since 2009 | 168,964 / 88,489 | 86% / 57% | [Tyler EnerGov CSS](https://doralfl-energovweb.tylerhost.net/apps/selfservice) |
| Hialeah | since 2023 (<5 yrs) | since 2023 | 38,963 / 17,923 | 99% / 100% | [Tyler EnerGov CSS](https://hialeahfl-energovpub.tylerhost.net/apps/selfservice) |
| Homestead | none usable | none usable | 1,270 / 6,849 | 97% / 97% | [Tyler EnerGov CSS](https://cityofhomesteadfl-energovweb.tylerhost.net/apps/selfservice) |
| Miami | since 2014 (8+ yrs) | none usable | 234,315 / 0 | 95% / 0% | [ArcGIS FeatureServer](https://datahub-miamigis.opendata.arcgis.com/datasets/MiamiGIS::building-permits-since-2014) |
| Miami Beach | since 2015 (8+ yrs) | since 2023 | 407,466 / 311,514 | 92% / 86% | [Tyler EnerGov CSS](https://energovcss.miamibeachfl.gov/EnerGovProd/SelfService/) |
| Miami Gardens | since 2007 (8+ yrs) | since 2007 | 123,993 / 65,895 | 91% / 98% | [Tyler EnerGov CSS](https://miamigardensfl-energovpub.tylerhost.net/apps/selfservice) |
| Miami Shores | since 2002 (8+ yrs) | since 2006 | 69,190 / 23,044 | 99% / 98% | [Tyler EnerGov CSS](https://villageofmiamishoresfl-energovweb.tylerhost.net/apps/selfservice) |
| North Bay Village | since 2009 (8+ yrs) | since 2015 | 11,128 / 2,190 | 73% / 84% | [Tyler EnerGov CSS](https://northbayvillagefl-energovpub.tylerhost.net/apps/selfservice) |
| North Miami | none usable | none usable | 9 / 3 | 0% / 0% | [Tyler EnerGov CSS](https://cityofnorthmiamifl-energovweb.tylerhost.net/apps/selfservice) |
| North Miami Beach | since 2004 (8+ yrs) | since 2023 | 101,605 / 9,752 | 94% / 99% | [Tyler EnerGov CSS](https://css.northmiamibeachfl.gov/energovprod/selfservice) |
| Surfside | since 1989 (8+ yrs) | none usable | 66,575 / 4,838 | 74% / 93% | [Tyler EnerGov CSS](https://surfsidefl-energovpub.tylerhost.net/apps/selfservice) |
| Sweetwater | none usable | none usable | 27 / 23 | 11% / 70% | [Tyler EnerGov CSS](https://cityofsweetwaterfl-energovweb.tylerhost.net/apps/selfservice) |
| Unincorporated Miami-Dade | since 2024 (<5 yrs) | since 2021 | 409,006 / 256,654 | 93% / 89% | [County ArcGIS layers](https://gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer/1) |

**No machine-readable public source** (not scored, shown in the drawer and the coverage table)

| City | Why not ingested | Portal |
|---|---|---|
| Aventura | eTRAKiT: 50-row cap, no dates/status in results; per-folio only | [CentralSquare eTRAKiT](https://etrakit.cityofaventura.com/etrakit/) |
| Bal Harbour | public reports need a staff-issued access code | [SmartGov](https://vlg-balharbour-fl.smartgovcommunity.com/Public/Home) |
| Bay Harbor Islands | per-address / folio lookup only, no bulk listing | [Citizenserve](https://www2.citizenserve.com/bhi) |
| Biscayne Park | portals are for applications and plan review, no public search | [CAP / GoGov (applications only)](https://biscayneparkfl.gov/?SEC=37D66DF7-212E-40FF-ABB5-9AED4040A0F7) |
| El Portal | no public search; open-permit search is a $25 request | [CAP plan review + GovPilot](https://elportalvillage.com/code-enforcement-building-department/) |
| Florida City | eTRAKiT: 50-row cap, no dates/status in results; per-folio only | [CentralSquare eTRAKiT](https://flc.csqrcloud.com/community-etrakit) |
| Golden Beach | no public permit / code search found | [online application only](https://goldenbeach.us) |
| Hialeah Gardens | no public permit / code search | [fee-based Lien Library request ($325)](https://www.cityofhialeahgardens.com/city-government/city-clerk-s-office/lien-and-open-permit-search) |
| Indian Creek | no public permit / code search found | none |
| Key Biscayne | Accela ACA search needs address/parcel per query (not bulk); not ingested | [Accela Citizen Access](https://aca-prod.accela.com/keybiscayne/Default.aspx) |
| Medley | no public permit / code search found | [none](https://www.medleyfl.org) |
| Miami Lakes | eTRAKiT: 50-row cap, no dates/status in results; per-folio only | [CentralSquare eTRAKiT](https://trakit.miamilakes-fl.gov/etrakit/) |
| Miami Springs | eTRAKiT search returns max 50 rows per query and no dates/status; per-folio only | [CentralSquare eTRAKiT](https://mias-trk.aspgov.com/etrakit/) |
| Opa-locka | EnerGov tenant exists but holds 0 permits / 1 code case; open-permit search is by mail, $50 per folio | [Tyler EnerGov CSS (empty)](https://cityofopalockafl-energovweb.tylerhost.net/apps/selfservice) |
| Palmetto Bay | per-permit / per-address search only | [Tyler Eden + CivicGov](https://eden.palmettobay-fl.gov/EdenWebNet/Default.aspx?Build=PM.pmPermit.SearchForm) |
| Pinecrest | eTRAKiT: 50-row cap, no dates/status in results; per-folio only | [CentralSquare eTRAKiT](https://pine-trk.aspgov.com/eTRAKiT/) |
| South Miami | eTRAKiT: 50-row cap, no dates/status in results; per-folio only | [CentralSquare eTRAKiT](https://etrakit.southmiamifl.gov/etrakit/) |
| Sunny Isles Beach | needs a portal account + access code | [SmartGov](https://ci-sunnyislesbeach-fl.smartgovcommunity.com/Public/Home) |
| Virginia Gardens | no public permit / code search found | none |
| West Miami | no public permit or code search found; requests go to the Building Department | [none](https://cityofwestmiami.gov/building-department) |
<!-- /PERMIT_COVERAGE -->

## Drive for dollars (phone) + installable app

`drive.js`: a full-screen, phone-first map centered on your GPS position (follows you; drag to look around, ◎ to re-center).
It opens automatically on screens ≤ 600 px wide (unless you opened a shared link with filters, or left drive mode before), from the
**Drive** button in the sticky bar, or from `?drive=1` (the installed app's start URL; `?drive=0` forces the list).
* Every parcel in view (zoom 15+) from the main pack + geo pack, as dots colored by distress score; saved parcels ringed in brand orange.
  A ~200 m grid index keeps it fast on phones.
* Tap a dot → bottom sheet: address, city, type, year built, value, owner, years owned, distress score, vacancy hint and signals,
  a big **☆ Save** button, then status, **Looks vacant / damaged** and a quick note (same saved list as the rest of the app),
  **Full details** (the normal drawer) and **Street View**.
* **📍 Save where I am** saves the parcel nearest your GPS position (within 120 m) and tells you the distance and GPS accuracy so you can
  double-check it's the right one.
* Large touch targets (≥ 44 px, main buttons 56–60 px), safe-area insets, Streets/Satellite layers.
* Location never leaves the phone; it's only used to center the map and find the nearest parcel. GPS stops when the app is hidden.
* Limit: condo units aren't drawn separately in drive mode (one dot per building parcel from the main pack).

PWA: `manifest.webmanifest` (standalone, Prop Hunters reticle icons 192/512 + maskable in `icons/`, apple-touch-icon) and `sw.js`:
app shell network-first with offline fallback, `data/meta.json` network-first, versioned data files (`data/*.gz?v=<build>`) cache-first
with old builds pruned, map tiles stale-while-revalidate (CORS only, capped at 1,500). Property packs are also kept in IndexedDB,
so once a phone has opened the app online it reopens and draws parcels offline (tiles only for areas already viewed).

## Saved properties

Star (☆) any property on a card, table row, map popup or in the detail drawer (keyboard: Tab to the star, Enter/Space).
The **Saved** button in the sticky bar shows the count and switches to your saved list (search filters pause; cards, table, map,
sort incl. "Recently saved", Copy folios and Export CSV all work on the saved list). Each saved property keeps the date saved,
a status (New, Researching, Mailed, Called, Offer sent, Under contract, Pass) and a free-text note, editable in the drawer and
shown on cards; filter the saved list by status. Saved condo units load the condo pack automatically. Saved properties are
ringed in brand orange on the map.

Storage: `saved.js` (`window.PFSaved`) keeps the list in localStorage (`mdpf.saved.v1`), keyed by folio, and syncs across tabs.
**Export saved (JSON/CSV)** and **Import saved (JSON)** move the list between browsers/computers; import merges by folio and keeps
the most recently edited copy. The storage backend is a small `{load(), save(items)}` interface (`PFSaved.use(backend)`), so a
cloud sync can be plugged in later; `PFSaved.onChange(fn)` reports every edit.

## Lender tracking

The **Lenders** button in the sticky bar opens a Lenders & funding page (`lenders-page.js`; also `?page=lenders`):
* **Lenders**: name, company, phone (tap to call), email, rate/points, terms, max loan size, geography, status (Prospect / Active /
  Paused / Not a fit), notes, last contacted (with a one-tap "Contacted today"); search and status filter.
* **Deals**: link a saved property to a lender with amount requested, amount committed, pipeline stage
  (Prospect → Contacted → Interested → Term sheet → Funded) and a note; change the stage inline. A property can be pitched to several lenders.
  Add deals from the page or from the property drawer's **Financing** section, which lists every lender/deal for that property.
* **Dashboard**: needed vs committed (progress bar), still to raise, funded, pipeline counts per stage, a by-lender table (deals,
  requested, committed, funded, max loan, last contact) and a by-property table (needed, committed, % covered, furthest stage).
  "Needed" counts each property once (its largest request), and committed is capped at that amount per property. The total offered
  across lenders is shown separately.
* Export **JSON** (lenders + deals) and **CSV** (lenders, deals); **Import** JSON (merge by id, newest edit wins) or either CSV.

Privacy: everything stays in this browser (`localStorage` key `mdpf.lenders.v1`); nothing is uploaded. `lenders.js`
(`window.PFLenders`) keeps storage behind the same small `{load(), save(data)}` adapter as saved properties (`PFLenders.use(backend)`,
`PFLenders.onChange(fn)`), so login and cloud sync (planned: Supabase) can be added later without changing the UI.

## Testing

`tests/e2e_owners.py` covers owner portfolios. `tests/e2e_lenders.py` covers lender tracking (forms, deals, dashboard math, drawer Financing, JSON/CSV export + import, phone layout). `tests/e2e_mobile.py` covers drive mode at a phone viewport with mocked GPS (sheet, save/status/note, Save where I am, manifest, service worker, offline reload). `tests/e2e_permits.py` covers the permit / code-case chips, per-city coverage table and drawer, CSV columns. `tests/e2e_vacancy.py` covers the vacancy hint (chips, filter, sort, drawer, aerial, saved vacant flag/condition note, exports). `tests/e2e_saved.py` covers save/unsave (mouse + keyboard), notes, status, Saved view, condo units, reload persistence and export/import.

```bash
pip install playwright && playwright install chromium
python3 -m http.server 8080 &   # from this folder
python3 tests/e2e.py
```

The test covers all presets, filters, sorts, the drawer, the table, CSV export, the map, hash restore and condo/folio search, and checks for console errors.

## Hosting permanently

Everything is static and the largest file is 19 MB, so all files are under GitHub's 100 MB per-file limit.
- **GitHub Pages:** needs a GitHub account. Push this folder to a repo and turn on Pages. Free.
- **Netlify** (drag-and-drop deploy) or **Vercel** or **Cloudflare Pages:** each needs a free account on that service.


## Probate layer (Clerk exports -> PR + DC)

`scripts/probate_lib.py`, called from `build_distress.py` after the lis-pendens/tax/code layers. Inputs (all untracked, in `raw/`, which is gitignored because it holds owner names):

* `raw/probate_downloads/probate_{PAD,PRO,DCE}_YYYYMMDD_YYYYMMDD.csv` - Official Records exports, same columns as the lis-pendens exports ("PARTY / OTHER PARTY", one row per party pairing, decedents usually end in `EST OF`). Rows are pooled across files by Clerk's File Number (CFN) and exact duplicate rows are dropped, so overlapping exports are safe.
* `raw/probate_cases/ocs_YYYYMMDD.txt` - daily "File Date" case lists from the Clerk's civil/family/probate case system (CSV: `in_re_name, local_case, state_case, section, case_type, filing_date, status`). `-CP-` rows are probate cases; `-GD-` (guardianship) rows are not probate signals and are skipped. There is no address in these lists.

How records are tied to a folio (precision first; a record that cannot be tied to exactly one owner is left out):

1. **Property match (PRO only - it carries address / legal / plat):** street address -> exactly one folio, or plat book/page + lot (+ block) -> exactly one folio. The owner must contain a party or the decedent (high); a legal-only match with no name agreement is *medium*; an address-only match whose owner is neither party is rejected. The PRO's Misc Ref case number (`CASE NO 2026-002689-CP-02`) links an OCS court case to that folio (high).
2. **Decedent name vs current owner name:** the decedent is the `EST OF` party (PAD/PRO), the only party on a DCE, or `in_re_name` ("LAST, FIRST MIDDLE") on an OCS case. Names are compared as word sets (order-free, so "RAMIREZ MARIA E" = "MARIA ELENA RAMIREZ"), suffixes (JR/SR/II/EST OF/LE/TRS) dropped, initials allowed to match full middle names and never to contradict, "&W SPOUSE" / "& SPOUSE" owner fields split into people. Organization, trust and government owners are never name-matched. Exactly one folio, or several folios with the identical owner name *and* mailing address, is a match; names shared by different owners are skipped as ambiguous. **High** = the middle name/initial agrees, or the roll already shows EST OF / LE, or a recorded document and a court case name the same decedent for the same folio; **medium** = first + last name only, unique county-wide.
3. Flagging: PAD/PRO/DCE matches of high or medium confidence are flagged. **Court cases are flagged only at high confidence** (a filed case does not prove the decedent owned Miami-Dade property). PR/DC bits and points are per signal, so several documents on one folio never add points twice, and a folio that already carries a PR/DC record from the No-Heir-Probates / Obituary outputs gets the new evidence folded into that record (same case number, same decedent, or any existing DC) instead of a duplicate.

Each record carries the document type, case number (when present), recorded/filing date, CFN, match method + confidence, and a link to the Clerk search page (Official Records standard search for recorded documents, the OCS home for court cases - neither offers a stable deep link, so search by the CFN or case number shown). "Probate case filed" appears as a PR record (title "Probate case filed: <case type> (<status>)", case number, filing date, status, section) rather than a thirteenth signal bit, because the packs' hard-signal bits are full (bits 12-15 are the soft factors).

Match counts and rates per source are written to `raw/distress_stats.json` (`clerk_probate`). Weekly routine: the logged-in browser step must drop new `probate_*.csv` exports into `raw/probate_downloads/` and new `ocs_*.txt` lists into `raw/probate_cases/` (as it already does for `raw/lp_downloads/`), then run `scripts/build_all.sh`. The days with no records (e.g. LP 08/01-08/03, 09/12-09/14, 09/27-09/29) are genuine, not gaps.
