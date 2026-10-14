#!/usr/bin/env python3
"""Monroe County, FL phase-1 fetch (public, no login): FL statewide cadastral (FDOR roll, CO_NO=54) + FEMA NFHL flood zones (DFIRM 12087).
Writes $RAW/monroe/{parcels.jsonl, flood.geojson, zoning.geojson (optional), fetch_stats.json}. Light on memory: streams pages to disk."""
import json, os, sys, time, requests
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe'); os.makedirs(RAW, exist_ok=True)
CAD = 'https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0/query'
NFHL = 'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query'
ZON = 'https://mcgis4.monroecounty-fl.gov/public/rest/services'
H = {'User-Agent': 'parcel-finder/1.0 (public data research)'}
def get(url, p, tries=4):
    for i in range(tries):
        try:
            r = requests.post(url, data=p, headers=H, timeout=120); r.raise_for_status(); j = r.json()
            if 'error' in j: raise RuntimeError(j['error'])
            return j
        except Exception as e:
            if i == tries - 1: raise
            print('retry', str(e)[:160]); time.sleep(5 * (i + 1))
FIELDS = ('PARCEL_ID,ALT_KEY,ASMNT_YR,DOR_UC,PA_UC,JV,AV_SD,TV_NSD,JV_HMSTD,LND_VAL,LND_SQFOOT,EFF_YR_BLT,ACT_YR_BLT,TOT_LVG_AR,NO_BULDNG,NO_RES_UNT,'
          'SALE_PRC1,SALE_YR1,SALE_MO1,QUAL_CD1,OR_BOOK1,OR_PAGE1,SALE_PRC2,SALE_YR2,SALE_MO2,QUAL_CD2,OWN_NAME,OWN_ADDR1,OWN_ADDR2,OWN_CITY,OWN_STATE,OWN_ZIPCD,'
          'OWN_STATE_,FIDU_NAME,S_LEGAL,PHY_ADDR1,PHY_CITY,PHY_ZIPCD,TAX_AUTH_C,NBRHD_CD,PREV_HMSTD')
stats = {}
n = get(CAD, {'where': 'CO_NO=54', 'returnCountOnly': 'true', 'f': 'json'})['count']; stats['cadastral_count'] = n; print('cadastral', n)
ids = get(CAD, {'where': 'CO_NO=54', 'returnIdsOnly': 'true', 'f': 'json'})['objectIds']; ids.sort()
tmp = f'{RAW}/parcels.jsonl.tmp'; got = 0
with open(tmp, 'w') as fh:
    for k in range(0, len(ids), 1000):
        chunk = ids[k:k + 1000]
        j = get(CAD, {'where': f'CO_NO=54 AND OBJECTID>={chunk[0]} AND OBJECTID<={chunk[-1]}', 'outFields': FIELDS, 'returnGeometry': 'false', 'returnCentroid': 'true', 'outSR': 4326, 'f': 'json'})
        for f in j['features']:
            a = f['attributes']; c = f.get('centroid') or {}
            a['LON'] = c.get('x'); a['LAT'] = c.get('y'); fh.write(json.dumps(a) + '\n'); got += 1
        print(f'{got}/{len(ids)}', flush=True)
os.replace(tmp, f'{RAW}/parcels.jsonl'); stats['parcels_fetched'] = got
# FEMA flood hazard zones
feats, off = [], 0
while True:
    j = get(NFHL, {'where': "DFIRM_ID LIKE '12087%'", 'outFields': 'FLD_ZONE,ZONE_SUBTY,STATIC_BFE,SFHA_TF', 'outSR': 4326, 'f': 'geojson',
                   'resultOffset': off, 'resultRecordCount': 500, 'geometryPrecision': 6})
    feats += j['features']; print('flood', len(feats))
    if len(j['features']) < 500: break
    off += 500
json.dump({'type': 'FeatureCollection', 'features': feats}, open(f'{RAW}/flood.geojson', 'w')); stats['flood_polygons'] = len(feats)
# county zoning (mcgis4) - optional; unreachable from many networks
try:
    r = requests.get(ZON, params={'f': 'json'}, headers=H, timeout=20); r.raise_for_status()
    stats['zoning'] = 'reachable: ' + ','.join(s['name'] for s in r.json().get('services', []))[:500]
except Exception as e:
    stats['zoning'] = f'unreachable ({type(e).__name__}) - skipped'
stats['fetched'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
json.dump(stats, open(f'{RAW}/fetch_stats.json', 'w'), indent=1); print(stats)
