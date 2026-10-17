#!/usr/bin/env python3
"""Broward County phase-1 fetch #1: parcel centroids (lon/lat) from the FL statewide cadastral (CO_NO=16, FDOR roll geometry).
The attributes (owners, mailing, values, sales, use codes) come from the FDOR NAL file (fetch_dor.py), which joins on PARCEL_ID (12 digits).
Resume-friendly: chunks of OBJECTIDs are cached in $RAW/broward/cad_chunks/*.jsonl; final merge -> $RAW/broward/centroids.jsonl."""
import json, os, sys, time, glob, requests
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'broward'); CH = os.path.join(RAW, 'cad_chunks'); os.makedirs(CH, exist_ok=True)
CAD = 'https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0/query'
H = {'User-Agent': 'parcel-finder/1.0 (public data research)'}
def get(p, tries=6):
    for i in range(tries):
        try:
            r = requests.post(CAD, data=p, headers=H, timeout=180); r.raise_for_status(); j = r.json()
            if 'error' in j: raise RuntimeError(str(j['error'])[:200])
            return j
        except Exception as e:
            if i == tries - 1: raise
            print('retry', str(e)[:140], flush=True); time.sleep(5 * (i + 1))
ids = get({'where': 'CO_NO=16', 'returnIdsOnly': 'true', 'f': 'json'})['objectIds']; ids.sort(); print('ids', len(ids), flush=True)
PAGE = 2000
for k in range(0, len(ids), PAGE):
    c = ids[k:k + PAGE]; fn = os.path.join(CH, f'{c[0]}_{c[-1]}.jsonl')
    if os.path.exists(fn): continue
    j = get({'where': f'OBJECTID>={c[0]} AND OBJECTID<={c[-1]} AND CO_NO=16', 'outFields': 'PARCEL_ID', 'returnGeometry': 'false', 'returnCentroid': 'true', 'outSR': 4326, 'f': 'json'})
    with open(fn + '.tmp', 'w') as fh:
        for f in j['features']:
            ce = f.get('centroid') or {}
            fh.write(json.dumps([f['attributes']['PARCEL_ID'], round(ce.get('x') or 0, 6), round(ce.get('y') or 0, 6)]) + '\n')
    os.replace(fn + '.tmp', fn); print(k + len(c), '/', len(ids), flush=True); time.sleep(0.3)
n = 0
with open(os.path.join(RAW, 'centroids.jsonl.tmp'), 'w') as out:
    for fn in sorted(glob.glob(CH + '/*.jsonl'), key=lambda p: int(os.path.basename(p).split('_')[0])):
        for line in open(fn): out.write(line); n += 1
os.replace(os.path.join(RAW, 'centroids.jsonl.tmp'), os.path.join(RAW, 'centroids.jsonl')); print('centroids', n)
