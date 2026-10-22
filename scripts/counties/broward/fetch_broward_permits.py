#!/usr/bin/env python3
"""Broward city permits from public ArcGIS services -> $RAW/broward/permits/<city>.json  {parcel_id: [last_date, count, n_last5y]}
Broward only (never mixed with Miami-Dade). Cities without a public bulk source are listed in COVERAGE.md.
  fort_lauderdale  gis.fortlauderdale.gov BuildingPermits/FeatureServer/0 (PARCELID = 12-digit BCPA folio, SUBMITDT)
Also keeps distress-type permits of the last 5 years (demolition, unsafe, roof, damage repair; broward_permit_lib.DPERM) per parcel:
  distress: {parcel_id: [[date, permit_id, type, desc, status], ...]} (newest first, max 5)"""
import os, json, sys, time, datetime as dt, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from broward_permit_lib import DPERM
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
    out, oid, mx, dist = {}, -1, '', {}
    while True:
        j = q(url, {'where': f'OBJECTID > {oid}', 'outFields': f'OBJECTID,{pf},{df},PERMITID,PERMITTYPE,PERMITDESC,PERMITSTAT', 'orderByFields': 'OBJECTID', 'resultRecordCount': 5000, 'returnGeometry': 'false'})
        fs = [f['attributes'] for f in j.get('features', [])]
        if not fs: break
        for a in fs:
            p = ''.join(ch for ch in str(a.get(pf) or '') if ch.isdigit()); t = d(a.get(df))
            if not p: continue
            r = out.setdefault(p, ['', 0, 0]); r[0] = max(r[0], t); r[1] += 1; r[2] += t >= c5; mx = max(mx, t)
            ty = str(a.get('PERMITTYPE') or '')
            if t >= c5 and DPERM.search(ty + ' ' + str(a.get('PERMITDESC') or '')[:60]): dist.setdefault(p, []).append([t, str(a.get('PERMITID') or ''), ty, str(a.get('PERMITDESC') or '')[:90], str(a.get('PERMITSTAT') or '')])
        oid = fs[-1]['OBJECTID']; time.sleep(0.2)
    json.dump({'pulled': time.strftime('%Y-%m-%d %H:%M'), 'source': url, 'data_through': mx, 'parcels': out, 'distress': {k: sorted(v, reverse=True)[:5] for k, v in dist.items()}}, open(f'{RAW}/{city}.json', 'w'), separators=(',', ':'))
    print(city, len(out), 'parcels, through', mx, '; distress-type permits (5y) on', len(dist), 'parcels', flush=True)
