#!/usr/bin/env python3
"""Last building permit per folio (used by the "Likely vacant / neglected" hint).

Two public ArcGIS sources, aggregated server-side (groupBy FolioNumber, 1,000-2,000 groups per request, ~0.3 s pause):
  city   City of Miami Building_Permits_Since_2014  (City of Miami parcels only, permits issued 2014 -> today)
  county Miami-Dade miamidade_permit_data           (permits issued by the County Building Dept, rolling last ~2 years)
Other municipalities (Miami Beach, Hialeah, Coral Gables, ...) publish no permit API, so they have no permit data here.
Output: RAW/permits.json {city: {folio: [last_issued 'YYYY-MM-DD', count, last_expired_or_revoked or '', n_expired_revoked, n_active, count_last_5y]},
                          county: {folio: [last_issued, count]}, sources, coverage}
"""
import json, os, sys, time, datetime as dt, requests

RAW = sys.argv[1] if len(sys.argv) > 1 else '/workspace/raw'
CITY = 'https://services1.arcgis.com/CvuPhqcTQpZPT9qY/arcgis/rest/services/Building_Permits_Since_2014/FeatureServer/0'
CNTY = 'https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/miamidade_permit_data/FeatureServer/0'
UA = {'User-Agent': 'parcel-finder weekly refresh (python-requests)'}

def agg(url, where, datef, page):
    """groupBy FolioNumber with keyset paging (FolioNumber > last) instead of resultOffset: deep offsets on the
    county service time out server-side and come back as HTTP 400 'Unable to perform query' (Oct 2026).
    On error: exponential backoff (5s..160s) and the page is halved (down to 100)."""
    out, last = [], None
    stats = json.dumps([{'statisticType': 'max', 'onStatisticField': datef, 'outStatisticFieldName': 'mx'},
                        {'statisticType': 'count', 'onStatisticField': 'ObjectId', 'outStatisticFieldName': 'n'}])
    while True:
        w = where if last is None else f"({where}) AND FolioNumber > {last}"
        for i in range(8):
            try:
                j = requests.get(url + '/query', params={'where': w, 'groupByFieldsForStatistics': 'FolioNumber', 'outStatistics': stats,
                                 'orderByFields': 'FolioNumber', 'resultRecordCount': page, 'f': 'json'}, headers=UA, timeout=180).json()
                if 'error' in j: raise RuntimeError(j['error'])
                break
            except Exception as e:
                print('  retry', i, 'page', page, e, flush=True); time.sleep(5 * 2 ** min(i, 5)); page = max(100, page // 2)
        else:
            raise SystemExit('failed ' + url)
        f = [x['attributes'] for x in j.get('features', []) if x['attributes'].get('FolioNumber') not in (None, '')]
        raw = j.get('features', [])
        out += f
        if not raw or len(raw) < page and not j.get('exceededTransferLimit'): break
        v = raw[-1]['attributes']['FolioNumber']
        nl = repr(v) if isinstance(v, (int, float)) else "'" + str(v).replace("'", "''") + "'"
        if nl == last: break
        last = nl; time.sleep(0.3)
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
    # 5-year permit count per folio (permits issued since today-5y) -> 6th array element
    c5 = (dt.date.today() - dt.timedelta(days=1826)).isoformat()
    for r in agg(CITY, f"IssuedDate >= DATE '{c5}'", 'IssuedDate', 2000):
        f = fol(r['FolioNumber'])
        if f in city: city[f].append(r['n'])
    for v in city.values():
        if len(v) < 6: v.append(0)
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
