# Waterfront / oceanfront filter — progress
Requested by Branden 2026-10-25. Clone: /workspace/pf-water (from origin/main a1bae0f).

## Plan
- Uniform geometric method for all 3 counties (no PA waterfront flag exists in MD layer 5, BCPA/FDOR NAL, Monroe FDOR roll).
- Marine water = OSM water polygons (osmdata.openstreetmap.de water-polygons-split-4326, coastline-derived).
- Inland water = OSM natural=water / waterway=canal|river (Overpass).
- Parcel polygons: MD raw/parcels (PA layer 5), Broward BCPA FeatureServer, Monroe Florida Statewide Cadastral.
- Subtypes by width of water in front: ocean (open water), bay, canal; lake/other for inland.

## Log
- 21:20 started; water polygons download running in raw/water.

## 2026-10-25 21:50 EDT
- Overpass (all 3 mirrors) was too slow / 502-504 for the 53 land tiles; Geofabrik PBF download hung from the box.
  Switched inland water to **Overture Maps base/water** (OSM-derived, ODbL, public S3, anonymous bbox-filtered parquet read,
  ~30.8K features in 4 s). `fetch_water.py` now writes `$RAW/water/overture/water_sfl.parquet`; build reads it.
- Front end done: `waterfront.js` (PFWF), select `#wfSel` in a "Waterfront" group (all counties, not layer-gated), hash `wf=any|o|b|c|l`,
  card tag, table column (last), drawer line, CSV column `Waterfront` appended last (main / saved / folder exports; not team lists), sw v27.
- Tests: `tests/e2e_waterfront.py` (3 counties, desktop+mobile) added to pre_push_regression + weekly; header tests accept the trailing column.
- build_all.sh: fetch water / broward_polys / monroe_polys + build water_<county> steps before refresh_status.
- Monroe rebuilt with inland: any 38,005 (ocean 14,342, bay 15,305, canal 27,765, lake 3,987).
- 22:06 resumed after interruption; desktop e2e_waterfront passed (after county-slug fix); running mobile
- 22:17 mobile e2e passed; README; committing + pre_push regression (PORT=8115)
