#!/usr/bin/env python3
"""Download Miami-Dade parcel polygons (MD_LandInformation/MapServer/26 PaParcel, ~600K) for assemblage adjacency.
Resumable: one file per OBJECTID block in $RAW/parcels/ (folio + WGS84 rings, 6 decimals, ~0.5 m simplification)."""
import json, os, sys, time, requests
RAW = sys.argv[1] if len(sys.argv) > 1 else '/workspace/raw'
U = 'https://gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer/26/query'
OUT = os.path.join(RAW, 'parcels'); os.makedirs(OUT, exist_ok=True)
ids = requests.get(U, params={'where': '1=1', 'returnIdsOnly': 'true', 'f': 'json'}, timeout=300).json()['objectIds']; ids.sort()
B = 1000
for k in range(0, len(ids), B):
    fn = os.path.join(OUT, f'p_{k:07d}.json')
    if os.path.exists(fn): continue
    part = ids[k:k+B]
    for tries in range(6):
        try:
            r = requests.post(U, data={'where': f'OBJECTID>={part[0]} AND OBJECTID<={part[-1]}', 'outFields': 'FOLIO', 'returnGeometry': 'true', 'outSR': '4326',
                                       'geometryPrecision': '6', 'maxAllowableOffset': '0.000004', 'f': 'json'}, timeout=300).json()
            feats = [[f['attributes']['FOLIO'], f['geometry']['rings']] for f in r['features'] if f.get('geometry')]
            json.dump(feats, open(fn + '.tmp', 'w'), separators=(',', ':')); os.replace(fn + '.tmp', fn); break
        except Exception as e:
            print('retry', k, e, flush=True); time.sleep(5 * (tries + 1))
    if k % 50000 == 0: print('parcels', k, 'of', len(ids), flush=True)
print('done', len(ids), flush=True)
