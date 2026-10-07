# Miami-Dade Parcel Finder

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
- **Owner kinds and flags** (LLC/company, trust, government, estate/heirs) are guessed from the owner names with regex rules, so expect a few misfires. Out-of-state = mailing state isn't FL, or a foreign mailing address. Absentee = mailing ZIP differs from the site ZIP. Homestead and senior come from the PA exemption amounts.
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

## Testing

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
