#!/usr/bin/env python3
"""Code / building violations, unsafe structures, code liens and 40-year recertification (official ArcGIS REST APIs).

All public, no login. Paged with resultOffset (2,000 rows per request, ~0.3 s pause). Output: RAW/viol/<name>.json (list of attribute dicts)
"""
import json, os, sys, time, requests

RAW = sys.argv[1] if len(sys.argv) > 1 else '/workspace/raw'
MDC = 'https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/ArcGIS/rest/services'
COM = 'https://services1.arcgis.com/CvuPhqcTQpZPT9qY/ArcGIS/rest/services'
LAYERS = {
    'bldg_open':     f'{MDC}/Open_Building_Violations/FeatureServer/0',              # county Building Dept open cases (incl. Unsafe Structure)
    'bldg_all':      f'{MDC}/BuildingViolation_gdb/FeatureServer/0',                 # all building cases (case -> folio for liens)
    'bldg_lien':     f'{MDC}/BuildingViolationLien/FeatureServer/0',                 # recorded building-violation liens (book/page/date)
    'cc_open':       f'{MDC}/CodeComplianceViolation_Open_View/FeatureServer/0',     # county Code Compliance open cases (unincorporated)
    'cc_lien':       f'{MDC}/CodeComplianceViolation_Lien_View/FeatureServer/0',     # code cases in lien status
    'cc_finance':    f'{MDC}/CodeComplianceViolation_ReferredtoFinance_View/FeatureServer/0',  # unpaid, referred to collections
    'miami_recert':  f'{COM}/40_Year_Recertification/FeatureServer/0',               # City of Miami 40/50-yr recertification
}
UA = {'User-Agent': 'parcel-finder weekly refresh (python-requests)'}

def pull(url):
    out, off = [], 0
    while True:
        for i in range(4):
            try:
                r = requests.get(url + '/query', params={'where': '1=1', 'outFields': '*', 'returnGeometry': 'false', 'f': 'json',
                                 'resultOffset': off, 'resultRecordCount': 2000, 'orderByFields': 'OBJECTID' if 'Lien/' not in url else 'ObjectId'}, headers=UA, timeout=90)
                j = r.json();
                if 'error' in j: raise RuntimeError(j['error'])
                break
            except Exception as e:
                print('  retry', e); time.sleep(5)
        else:
            raise SystemExit('failed ' + url)
        f = [x['attributes'] for x in j.get('features', [])]
        out += f; off += len(f)
        if not f or not j.get('exceededTransferLimit') and len(f) < 2000: break
        time.sleep(0.3)
    return out

if __name__ == '__main__':
    os.makedirs(f'{RAW}/viol', exist_ok=True)
    for k, u in LAYERS.items():
        rows = pull(u); print(k, len(rows), flush=True)
        json.dump({'source': u, 'pulled': time.strftime('%Y-%m-%d %H:%M'), 'rows': rows}, open(f'{RAW}/viol/{k}.json', 'w'))
