#!/usr/bin/env python3
"""Last building permit per folio (used by the "Likely vacant / neglected" hint).

Two public ArcGIS sources, aggregated server-side (groupBy FolioNumber, 1,000-2,000 groups per request, ~0.3 s pause):
  city   City of Miami Building_Permits_Since_2014  (City of Miami parcels only, permits issued 2014 -> today)
  county Miami-Dade miamidade_permit_data           (permits issued by the County Building Dept, rolling last ~2 years)
Other municipalities (Miami Beach, Hialeah, Coral Gables, ...) publish no permit API, so they have no permit data here.
Output: RAW/permits.json {city: {folio: [last_issued 'YYYY-MM-DD', count, last_expired_or_revoked or '', n_expired_revoked, n_active]},
                          county: {folio: [last_issued, count]}, sources, coverage}
"""
import json, os, sys, time, datetime as dt, requests

RAW = sys.argv[1] if len(sys.argv) > 1 else '/workspace/raw'
CITY = 'https://services1.arcgis.com/CvuPhqcTQpZPT9qY/arcgis/rest/services/Building_Permits_Since_2014/FeatureServer/0'
CNTY = 'https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/miamidade_permit_data/FeatureServer/0'
UA = {'User-Agent': 'parcel-finder weekly refresh (python-requests)'}

def agg(url, where, datef, page):
    out, off = [], 0
    stats = json.dumps([{'statisticType': 'max', 'onStatisticField': datef, 'outStatisticFieldName': 'mx'},
                        {'statisticType': 'count', 'onStatisticField': 'ObjectId', 'outStatisticFieldName': 'n'}])
    while True:
        for i in range(4):
            try:
                j = requests.get(url + '/query', params={'where': where, 'groupByFieldsForStatistics': 'FolioNumber', 'outStatistics': stats,
                                 'orderByFields': 'FolioNumber', 'resultOffset': off, 'resultRecordCount': page, 'f': 'json'}, headers=UA, timeout=120).json()
                if 'error' in j: raise RuntimeError(j['error'])
                break
            except Exception as e:
                print('  retry', e, flush=True); time.sleep(5)
        else:
            raise SystemExit('failed ' + url)
        f = [x['attributes'] for x in j.get('features', [])]
        out += f; off += len(f)
        if not f or (not j.get('exceededTransferLimit') and len(f) < page): break
        time.sleep(0.3)
    return out

def rows(url, where, fields):
    out, off = [], 0
    while True:
        for i in range(4):
            try:
                j = requests.get(url + '/query', params={'where': where, 'outFields': fields, 'returnGeometry': 'false', 'orderByFields': 'ObjectId',
                                 'resultOffset': off, 'resultRecordCount': 2000, 'f': 'json'}, headers=UA, timeout=120).json()
                if 'error' in j: raise RuntimeError(j['error'])
                break
            except Exception as e:
                print('  retry', e, flush=True); time.sleep(5)
        else:
            raise SystemExit('failed ' + url)
        f = [x['attributes'] for x in j.get('features', [])]
        out += f; off += len(f)
        if not f or (not j.get('exceededTransferLimit') and len(f) < 2000): break
        time.sleep(0.3)
    return out

def fol(v):
    if v is None: return ''
    s = str(int(v)) if isinstance(v, (int, float)) else ''.join(c for c in str(v) if c.isdigit())
    return s.zfill(13) if s and len(s) <= 13 else ''

def d(v):
    if v in (None, ''): return ''
    if isinstance(v, (int, float)): return (dt.datetime(1970, 1, 1) + dt.timedelta(milliseconds=v)).date().isoformat()
    return str(v)[:10]

if __name__ == '__main__':
    city = {}
    for r in agg(CITY, '1=1', 'IssuedDate', 2000):
        f = fol(r['FolioNumber'])
        if f: city[f] = [d(r['mx']), r['n'], '', 0, 0]
    print('city folios', len(city), flush=True)
    for r in rows(CITY, "BuildingPermitStatusDescription IN ('Expired','Revoked','Active')", 'FolioNumber,IssuedDate,BuildingPermitStatusDescription'):
        f = fol(r['FolioNumber'])
        if f not in city: continue
        if r['BuildingPermitStatusDescription'] == 'Active': city[f][4] += 1
        else: city[f][3] += 1; city[f][2] = max(city[f][2], d(r['IssuedDate']))
    county = {}
    for r in agg(CNTY, '1=1', 'PermitIssuedDate', 1000):
        f = fol(r['FolioNumber'])
        if f: county[f] = [d(r['mx']), r['n']]
    print('county folios', len(county), flush=True)
    rng = requests.get(CNTY + '/query', params={'where': '1=1', 'outStatistics': json.dumps([{'statisticType': 'min', 'onStatisticField': 'PermitIssuedDate', 'outStatisticFieldName': 'mn'},
                       {'statisticType': 'max', 'onStatisticField': 'PermitIssuedDate', 'outStatisticFieldName': 'mx'}]), 'f': 'json'}, headers=UA, timeout=60).json()['features'][0]['attributes']
    json.dump({'pulled': time.strftime('%Y-%m-%d %H:%M'), 'sources': {'city': CITY, 'county': CNTY},
               'coverage': {'city': 'City of Miami permits issued 2014-present', 'county': f"Miami-Dade County Building Dept permits issued {rng['mn']} to {rng['mx']}"},
               'city': city, 'county': county}, open(f'{RAW}/permits.json', 'w'), separators=(',', ':'))
    print('wrote', f'{RAW}/permits.json', rng)
