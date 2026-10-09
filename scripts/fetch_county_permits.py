#!/usr/bin/env python3
"""County-wide building permit + certificate-of-occupancy history from Miami-Dade County's public ArcGIS layers (no login).

  bp     MD_LandInformation/MapServer/1 "County Building Permits @ BuildingPermit"  (gisweb, ~262K rows: status A=active E=expired F=final, trade type,
         issue date; every permit the County Building Dept has on its books - dense 2023-today, ~99% unincorporated; a handful of municipal folios)
  co     certif_of_occupancy_daily_data (AGOL, ~147K rows, 2002-today): certificates of occupancy issued by the County
Paged by OBJECTID, 1,000 rows per request, ~0.5 s pause. Output: RAW/permits/county_bp_l1.json, RAW/permits/county_co.json (lists of dicts).
"""
import json, os, sys, time, requests

RAW = sys.argv[1] if len(sys.argv) > 1 else '/workspace/raw'
SRC = {
    'county_bp_l1': ('https://gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer/1', 'OBJECTID', 'OBJECTID,FOLIO,PROCNUM,ADDRESS,TYPE,CAT1,DESC1,ISSUDATE,LSTINSDT,RENDATE,BLDCMPDT,RESCOMM,PROPUSE,APPTYPE,BPSTATUS'),
    'county_co':    ('https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/certif_of_occupancy_daily_data/FeatureServer/0', 'ObjectId',
                     'ObjectId,CERTIFICATE_NUMBER,PERMIT_NUMBER,ISSUE_DATE,APPLICATION_TYPE,CERTIFICATE_CODE,FOLIO,PROPERTY_ADDRESS,OCCUPANCY_CODE_DESCRIPTION,SQUARE_FOOTAGE'),
}

def pull(name):
    url, oid, fields = SRC[name]; out, last = [], 0
    while True:
        for i in range(5):
            try:
                j = requests.get(url + '/query', params={'where': f'{oid}>{last}', 'outFields': fields, 'returnGeometry': 'false', 'orderByFields': oid,
                                 'resultRecordCount': 1000, 'f': 'json'}, timeout=120).json()
                if 'error' in j: raise RuntimeError(j['error'])
                break
            except Exception as e:
                print('  retry', repr(e)[:100], flush=True); time.sleep(5)
        else:
            raise SystemExit('failed ' + name)
        f = [x['attributes'] for x in j.get('features', [])]
        if not f: break
        out += f; last = f[-1][oid]
        time.sleep(0.5)
    return out

if __name__ == '__main__':
    os.makedirs(f'{RAW}/permits', exist_ok=True)
    bad = 0
    for k in SRC:
        try:
            rows = pull(k); print(k, len(rows), flush=True)
            json.dump({'source': SRC[k][0], 'pulled': time.strftime('%Y-%m-%d %H:%M'), 'rows': rows}, open(f'{RAW}/permits/{k}.json.tmp', 'w'))
            os.replace(f'{RAW}/permits/{k}.json.tmp', f'{RAW}/permits/{k}.json')
        except BaseException as e:
            print('WARN', k, 'failed:', repr(e)[:200]); bad += 1
    sys.exit(1 if bad else 0)
