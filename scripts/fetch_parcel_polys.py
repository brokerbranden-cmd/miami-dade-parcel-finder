#!/usr/bin/env python3
"""Waterfront layer input: parcel polygons for Broward (BCPA Broward_County_Parcel_Boundary layer 1) and Monroe (Monroe County GIS
APO_GIS/MapServer/6 "Current Parcels"). Miami-Dade polygons already come from scripts/fetch_parcels.py ($RAW/parcels/p_*.json).
  python3 scripts/fetch_parcel_polys.py broward|monroe
Output: $RAW/<county>/polys/<oid0>_<oid1>.jsonl, one line per polygon: [parcel id, use code, esri rings (lon/lat, 6 decimals)].
Resumable: finished chunks are kept; chunks older than MAX_AGE_DAYS (default 28) are re-fetched, so a weekly run refreshes the
polygons about once a month (parcel lines change slowly). Read-only public GIS queries, ~3 requests/second at most."""
import json, os, sys, time, glob, requests, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
C = sys.argv[1]
SRC = {'broward': ('https://services5.arcgis.com/wI5GZmCtnUU8ueya/ArcGIS/rest/services/Broward_County_Parcel_Boundary/FeatureServer/1/query', 'PARCELNO', 'DOR_UC', 2000, True),
       # mcgis4 serves an incomplete TLS chain (same note as counties/monroe/arcgis_lib.py): verify off for this public read-only host only
       'monroe': ('https://mcgis4.monroecounty-fl.gov/public/rest/services/APO_GIS/MapServer/6/query', 'PARCELNO', 'PC', 1000, False)}[C]
URL, PF, UF, PAGE, VERIFY = SRC
OUT = os.path.join(os.environ.get('RAW', '/workspace/raw'), C, 'polys'); os.makedirs(OUT, exist_ok=True)
MAX_AGE = float(os.environ.get('MAX_AGE_DAYS', '28')) * 86400
H = {'User-Agent': 'parcel-finder/1.0 (public data research)'}
def get(p, tries=6):
    for i in range(tries):
        try:
            r = requests.post(URL, data=p, headers=H, timeout=240, verify=VERIFY); r.raise_for_status(); j = r.json()
            if 'error' in j: raise RuntimeError(str(j['error'])[:200])
            return j
        except Exception as e:
            if i == tries - 1: raise
            print('retry', str(e)[:140], flush=True); time.sleep(5 * (i + 1))
ids = sorted(get({'where': '1=1', 'returnIdsOnly': 'true', 'f': 'json'})['objectIds']); print(C, 'ids', len(ids), flush=True)
keep = set()
for k in range(0, len(ids), PAGE):
    c = ids[k:k + PAGE]; fn = os.path.join(OUT, f'{c[0]}_{c[-1]}.jsonl'); keep.add(os.path.basename(fn))
    if os.path.exists(fn) and time.time() - os.path.getmtime(fn) < MAX_AGE: continue
    j = get({'where': f'OBJECTID>={c[0]} AND OBJECTID<={c[-1]}', 'outFields': f'{PF},{UF}', 'returnGeometry': 'true', 'outSR': 4326, 'geometryPrecision': 6, 'f': 'json'})
    with open(fn + '.tmp', 'w') as fh:
        for f in j['features']:
            g = f.get('geometry') or {}; a = f['attributes']
            if g.get('rings'): fh.write(json.dumps([str(a.get(PF) or ''), str(a.get(UF) or ''), g['rings']], separators=(',', ':')) + '\n')
    os.replace(fn + '.tmp', fn); print(k + len(c), '/', len(ids), flush=True); time.sleep(0.3)
for fn in glob.glob(OUT + '/*.jsonl'):   # chunks from an older OBJECTID layout
    if os.path.basename(fn) not in keep: os.remove(fn)
print('done', C, len(keep), 'chunks')
