#!/usr/bin/env python3
"""Broward city permits from public ArcGIS services -> $RAW/broward/permits/<city>.json  {parcel_id: [last_date, count, n_last5y]}
Broward only (never mixed with Miami-Dade). Cities without a public bulk source are listed in COVERAGE.md.
  fort_lauderdale  gis.fortlauderdale.gov BuildingPermits/FeatureServer/0 (PARCELID = 12-digit BCPA folio, SUBMITDT)
Also keeps distress-type permits of the last 5 years (demolition, unsafe, roof, damage repair; broward_permit_lib.DPERM) per parcel:
  distress: {parcel_id: [[date, permit_id, type, desc, status], ...]} (newest first, max 5)"""
import os, re, json, sys, time, datetime as dt, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from broward_permit_lib import DPERM
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'broward', 'permits'); os.makedirs(RAW, exist_ok=True)
SRC = {'fort_lauderdale': ('https://gis.fortlauderdale.gov/server/rest/services/BuildingPermits/FeatureServer/0', 'PARCELID', 'SUBMITDT')}
SUFX = {'STREET': 'ST', 'AVENUE': 'AVE', 'AV': 'AVE', 'ROAD': 'RD', 'DRIVE': 'DR', 'COURT': 'CT', 'TERRACE': 'TER', 'TERR': 'TER', 'PLACE': 'PL', 'LANE': 'LN', 'BOULEVARD': 'BLVD', 'CIRCLE': 'CIR',
        'TRAIL': 'TRL', 'PARKWAY': 'PKWY', 'HIGHWAY': 'HWY', 'NORTH': 'N', 'SOUTH': 'S', 'EAST': 'E', 'WEST': 'W', 'NORTHWEST': 'NW', 'NORTHEAST': 'NE', 'SOUTHWEST': 'SW', 'SOUTHEAST': 'SE'}
def akey(a):
    a = re.sub(r'[.,#]', ' ', str(a).upper()); a = re.sub(r'\b([NS])\s+([EW])\b', r'\1\2', a)
    w = [SUFX.get(t, t) for t in a.split()]; return ' '.join(re.sub(r'^(\d+)(ST|ND|RD|TH)$', r'\1', t) for t in w)
def merge_lauderbuild(out, dist, ids, c5):
    """LauderBuild (Accela) monthly exports from fetch_ftl_lauderbuild.py: the ArcGIS layer is frozen at 2026-03-16. No parcel id in the export ->
    joined to the Broward roll (FDOR NAL) by street address + ZIP, unique matches only; records already in the ArcGIS layer (same permit id) skipped."""
    import glob, csv
    fs = sorted(glob.glob(os.path.join(RAW, 'ftl_accela', '*.csv')))
    if not fs: return {}
    nal = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'sdf', 'Broward_Preliminary_NAL_2026', 'NAL16P202601.csv'); ix = {}
    for r in csv.DictReader(open(nal, errors='replace')):
        a = (r.get('PHY_ADDR1') or '').strip()
        if a: ix.setdefault((akey(a), (r.get('PHY_ZIPCD') or '')[:5]), set()).add(re.sub(r'[^0-9A-Za-z]', '', r['PARCEL_ID']).upper())
    st = {'files': len(fs), 'rows': 0, 'dup_of_arcgis': 0, 'no_address': 0, 'matched': 0, 'unmatched': 0, 'ambiguous': 0, 'data_through': ''}; seen = set()
    for fn in fs:
        for r in csv.DictReader(open(fn, encoding='utf-8-sig', errors='replace')):
            no = (r.get('Record Number') or '').strip()
            if not no or no in seen or '.' in no: continue   # .I001 / .R001 = inspection / revision sub-documents
            seen.add(no); st['rows'] += 1
            if no in ids: st['dup_of_arcgis'] += 1; continue
            try: t = dt.datetime.strptime((r.get('Date') or '').strip(), '%m/%d/%Y').date().isoformat()
            except ValueError: continue
            if t > dt.date.today().isoformat(): continue
            ad = (r.get('Address') or '').strip()
            if not ad: st['no_address'] += 1; continue
            m = re.search(r'\bFL\s+(\d{5})', ad); c = ix.get((akey(ad.split(',')[0]), m.group(1) if m else ''), set())
            if len(c) != 1: st['ambiguous' if c else 'unmatched'] += 1; continue
            p = next(iter(c)); st['matched'] += 1; st['data_through'] = max(st['data_through'], t)
            x = out.setdefault(p, ['', 0, 0]); x[0] = max(x[0], t); x[1] += 1; x[2] += t >= c5
            ty = r.get('Record Type') or ''; de = r.get('Description') or r.get('Project Name') or ''
            if t >= c5 and DPERM.search(ty + ' ' + no + ' ' + de[:60]): dist.setdefault(p, []).append([t, no, ty, de[:90], r.get('Status') or ''])
    return st
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
    out, oid, mx, dist, ids = {}, -1, '', {}, set()
    while True:
        j = q(url, {'where': f'OBJECTID > {oid}', 'outFields': f'OBJECTID,{pf},{df},PERMITID,PERMITTYPE,PERMITDESC,PERMITSTAT', 'orderByFields': 'OBJECTID', 'resultRecordCount': 5000, 'returnGeometry': 'false'})
        fs = [f['attributes'] for f in j.get('features', [])]
        if not fs: break
        for a in fs:
            p = ''.join(ch for ch in str(a.get(pf) or '') if ch.isdigit()); t = d(a.get(df))
            if not p: continue
            ids.add(str(a.get('PERMITID') or '')); r = out.setdefault(p, ['', 0, 0]); r[0] = max(r[0], t); r[1] += 1; r[2] += t >= c5; mx = max(mx, t)
            ty = str(a.get('PERMITTYPE') or '')
            if t >= c5 and DPERM.search(ty + ' ' + str(a.get('PERMITDESC') or '')[:60]): dist.setdefault(p, []).append([t, str(a.get('PERMITID') or ''), ty, str(a.get('PERMITDESC') or '')[:90], str(a.get('PERMITSTAT') or '')])
        oid = fs[-1]['OBJECTID']; time.sleep(0.2)
    arc_mx = mx; acc = {}
    if city == 'fort_lauderdale': acc = merge_lauderbuild(out, dist, ids, c5); mx = max(mx, acc.get('data_through', ''))
    json.dump({'pulled': time.strftime('%Y-%m-%d %H:%M'), 'source': url, 'arcgis_through': arc_mx, 'lauderbuild': acc, 'data_through': mx, 'parcels': out, 'distress': {k: sorted(v, reverse=True)[:5] for k, v in dist.items()}}, open(f'{RAW}/{city}.json', 'w'), separators=(',', ':'))
    print(city, len(out), 'parcels, through', mx, '(ArcGIS through', arc_mx, ') LauderBuild', json.dumps(acc), '; distress-type permits (5y) on', len(dist), 'parcels', flush=True)
