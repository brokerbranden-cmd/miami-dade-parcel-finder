#!/usr/bin/env python3
"""Download every record of the Miami-Dade Property Appraiser 'PaGis' layer
(MD_ComparableSales/MapServer/5 on gisweb.miamidade.gov) in OBJECTID chunks.
Output: raw/pagis/chunk_<start>.json (ArcGIS JSON, geometry in WGS84)."""
import json, os, sys, time, concurrent.futures as cf, requests
BASE = 'https://gisweb.miamidade.gov/arcgis/rest/services/MD_ComparableSales/MapServer/5/query'
FIELDS = ("OBJECTID,FOLIO,TRUE_SITE_ADDR,TRUE_SITE_UNIT,TRUE_SITE_CITY,TRUE_SITE_ZIP_CODE,"
 "TRUE_MAILING_ADDR1,TRUE_MAILING_ADDR2,TRUE_MAILING_ADDR3,TRUE_MAILING_CITY,TRUE_MAILING_STATE,TRUE_MAILING_ZIP_CODE,TRUE_MAILING_COUNTRY,"
 "TRUE_OWNER1,TRUE_OWNER2,TRUE_OWNER3,CANCEL_FLAG,REFERENCE_ONLY_FLAG,CONDO_FLAG,PARENT_FOLIO,MUNICIPALITY_CODE,DOR_CODE_CUR,DOR_DESC,PRIMARY_ZONE,"
 "BEDROOM_COUNT,BATHROOM_COUNT,HALF_BATHROOM_COUNT,FLOOR_COUNT,UNIT_COUNT,BUILDING_COUNT,BUILDING_ACTUAL_AREA,BUILDING_HEATED_AREA,LOT_SIZE,YEAR_BUILT,"
 "ASSESSMENT_YEAR_CUR,LAND_VAL_CUR,BUILDING_VAL_CUR,TOTAL_VAL_CUR,TOTAL_VAL_PRI,ASSESSED_VAL_CUR,CNTY_TAXABLE_VAL_CUR,"
 "HSTEAD_EX_VAL_CUR,CNTY_SR_EX_VAL_CUR,CNTY_LNG_TERM_SR_EX_VAL_CUR,WIDOW_EX_VAL_CUR,VETERAN_EX_VAL_CUR,DISABLED_EX_VAL_CUR,STATE_EX_CODE_CUR,STATE_EX_CODE_2_CUR,"
 "DOS_1,PRICE_1,QU_FLG_1,VI_1,GRANTOR_1,OR_BK_1,OR_PG_1,DOS_2,PRICE_2,QU_FLG_2,DOS_3,PRICE_3,QU_FLG_3,LEGAL")
OUT = sys.argv[1] if len(sys.argv) > 1 else '/workspace/raw/pagis'
STEP = 5000
def get_max():
    r = requests.get(BASE, params={'where':'1=1','returnCountOnly':'false','f':'json','outStatistics':json.dumps([{'statisticType':'max','onStatisticField':'OBJECTID','outStatisticFieldName':'mx'}])}, timeout=120)
    return r.json()['features'][0]['attributes']['mx']
def fetch(start):
    fn = os.path.join(OUT, f'chunk_{start:07d}.json')
    if os.path.exists(fn) and os.path.getsize(fn) > 100: return start, 'cached'
    p = {'where': f'OBJECTID>{start} AND OBJECTID<={start+STEP}', 'outFields': FIELDS, 'returnGeometry': 'true',
         'outSR': '4326', 'geometryPrecision': '6', 'f': 'json'}
    for attempt in range(6):
        try:
            r = requests.post(BASE, data=p, timeout=300)
            d = r.json()
            if 'features' not in d: raise RuntimeError(str(d)[:200])
            if d.get('exceededTransferLimit'): raise RuntimeError('exceeded limit')
            tmp = fn + '.tmp'; json.dump(d['features'], open(tmp, 'w')); os.replace(tmp, fn)
            return start, len(d['features'])
        except Exception as e:
            print('retry', start, attempt, e, flush=True); time.sleep(5 * (attempt + 1))
    return start, 'FAILED'
if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    mx = get_max(); starts = list(range(0, mx, STEP)); print('max OBJECTID', mx, 'chunks', len(starts), flush=True)
    t = time.time()
    with cf.ThreadPoolExecutor(6) as ex:
        for s, n in ex.map(fetch, starts): print(s, n, f'{time.time()-t:.0f}s', flush=True)
