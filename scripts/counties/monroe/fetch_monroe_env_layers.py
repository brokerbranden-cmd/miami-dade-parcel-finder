#!/usr/bin/env python3
"""Environmental / conservation layers for Monroe -> $RAW/monroe/layers/: FNAI Florida Conservation Lands (managed areas), Florida Forever BOT projects,
USFWS National Wetlands Inventory (FDEP MapDirect mirror, fetched only around parcel clusters). Public, no login."""
import sys, os, json, math; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arcgis_lib import *
FN = 'https://services.arcgis.com/9Jk4Zl9KofTtvg3x/ArcGIS/rest/services/'
only = sys.argv[1:]
if not only or 'fnai' in only: fetch_layer('fnai_conslands', FN + 'FL_Conservation_Lands_web/FeatureServer/9', fields='MANAME,MATYPE,MANAGING_A,OWNER,COUNTY,PROTSTAT,TOTACRES', where="UPPER(COUNTY) LIKE '%MONROE%'", offset_tol=0.000005)
if not only or 'ff' in only: fetch_layer('florida_forever', FN + 'Florida_Forever_BOT_Projects/FeatureServer/1', fields='SITENAME,FF_CAT,FF_RANK,COUNTY', where="UPPER(COUNTY) LIKE '%MONROE%'", offset_tol=0.000005)
if not only or 'nwi' in only:
    NWI = 'https://ca.dep.state.fl.us/arcgis/rest/services/Map_Direct/Program_Support/MapServer/6/query'
    out = os.path.join(LAY, 'nwi.geojson')
    if os.path.exists(out): print('cached nwi')
    else:
        import pandas as pd
        d = pd.read_json(os.path.join(RAW, 'parcels.jsonl'), lines=True, dtype=False)[['LON', 'LAT']].dropna()
        cells = sorted({(math.floor(x / 0.04), math.floor(y / 0.04)) for x, y in zip(d.LON, d.LAT)}); print('nwi cells', len(cells), flush=True)
        seen, feats = set(), []
        for i, (cx, cy) in enumerate(cells):
            env = f'{cx*0.04:.4f},{cy*0.04:.4f},{(cx+1)*0.04:.4f},{(cy+1)*0.04:.4f}'
            off = 0
            while True:
                j = q(NWI, {'where': '1=1', 'geometry': env, 'geometryType': 'esriGeometryEnvelope', 'inSR': 4326, 'spatialRel': 'esriSpatialRelIntersects', 'outFields': 'ATTRIBUTE,WETLAND_TYPE',
                            'outSR': 4326, 'f': 'geojson', 'geometryPrecision': 5, 'maxAllowableOffset': 0.00002, 'resultOffset': off, 'resultRecordCount': 1000})
                fs = j.get('features', [])
                for f in fs:
                    k = (f['properties'].get('ATTRIBUTE'), json.dumps(f['geometry']['coordinates'][0][0][:2]) if f.get('geometry') else None)
                    if k not in seen: seen.add(k); feats.append(f)
                if len(fs) < 1000 and not j.get('exceededTransferLimit'): break
                off += len(fs)
            print(f'nwi cell {i+1}/{len(cells)} total {len(feats)}', flush=True)
        json.dump({'type': 'FeatureCollection', 'features': feats}, open(out + '.tmp', 'w')); os.replace(out + '.tmp', out)
