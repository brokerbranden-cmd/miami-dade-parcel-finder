#!/usr/bin/env python3
"""Broward city permits from public ArcGIS services -> $RAW/broward/permits/<city>.json  {parcel_id: [last_date, count, n_last5y]}
Broward only (never mixed with Miami-Dade). Cities without a public bulk source are listed in COVERAGE.md.
  fort_lauderdale  gis.fortlauderdale.gov BuildingPermits/FeatureServer/0 (PARCELID = 12-digit BCPA folio, SUBMITDT)"""
import os, json, sys, time, datetime as dt, requests
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'broward', 'permits'); os.makedirs(RAW, exist_ok=True)
SRC = {'fort_lauderdale': ('https://gis.fortlauderdale.gov/server/rest/services/BuildingPermits/FeatureServer/0', 'PARCELID', 'SUBMITDT')}
def q(url, params):
    for i in range(7):
        try:
            j = requests.get(url + '/query', params={**params, 'f': 'json'}, timeout=180).json()
            if 'error' in j: raise RuntimeError(j['error'])
            return j
        except Exception as e:
            print('  retry', i, e, flush=True); time.sleep(5 * 2 ** min(i, 5))
    raise SystemExit('failed ' + url)
def d(v): return (dt.datetime(1970, 1, 1) + dt.timedelta(milliseconds=v)).date().isoformat() if isinstance(v, (int, float)) else (v or '')[:10]
c5 = (dt.date.today() - dt.timedelta(days=1826)).isoformat(); errs = 0
for city, (url, pf, df) in SRC.items():
    out, oid, mx = {}, -1, ''
    while True:
        j = q(url, {'where': f'OBJECTID > {oid}', 'outFields': f'OBJECTID,{pf},{df}', 'orderByFields': 'OBJECTID', 'resultRecordCount': 5000, 'returnGeometry': 'false'})
        fs = [f['attributes'] for f in j.get('features', [])]
        if not fs: break
        for a in fs:
            p = ''.join(ch for ch in str(a.get(pf) or '') if ch.isdigit()); t = d(a.get(df))
            if not p: continue
            r = out.setdefault(p, ['', 0, 0]); r[0] = max(r[0], t); r[1] += 1; r[2] += t >= c5; mx = max(mx, t)
        oid = fs[-1]['OBJECTID']; time.sleep(0.2)
    json.dump({'pulled': time.strftime('%Y-%m-%d %H:%M'), 'source': url, 'data_through': mx, 'parcels': out}, open(f'{RAW}/{city}.json', 'w'), separators=(',', ':'))
    print(city, len(out), 'parcels, through', mx, flush=True)
