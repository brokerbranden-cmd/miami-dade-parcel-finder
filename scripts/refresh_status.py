#!/usr/bin/env python3
"""Summarise the last build_all.sh run: per-source fresh/stale + counts -> data/refresh-status.json, short text on stdout."""
import json, os, sys, glob, gzip, datetime
st, out = sys.argv[1], sys.argv[2]
RAW = os.environ.get('RAW', '/workspace/raw')
SOURCES = {  # step -> label
    'pagis': 'Property Appraiser roll', 'layers': 'Zoning/CRA layers', 'zone_desc': 'Zoning descriptions',
    'clerk': 'Clerk lis pendens', 'clerk_clp': 'Clerk CLP (open check)', 'auctions': 'Foreclosure/tax auctions',
    'tax': 'Tax delinquency', 'viol': 'Code violations', 'permits': 'City of Miami permits',
    'county_permits': 'County permits', 'energov': 'EnerGov city permits', 'parcels': 'Parcel polygons',
    'probate': 'Clerk probate (PAD/PRO/DCE)', 'cot': 'Clerk certificates of title (CTI)',
    'monroe_clerk': 'Monroe Clerk foreclosure+probate cases', 'monroe_marathon_code': 'Monroe: Marathon code hearings',
    'monroe_keywest': 'Monroe: Key West permits + code cases (eTRAKiT)', 'monroe_islamorada': 'Monroe: Islamorada permits + code cases (CityView)',
    'broward_permits': 'Broward: Fort Lauderdale permits (ArcGIS to 2026-03-16 + LauderBuild)', 'broward_lp': 'Broward lis pendens (County Records FTP)',
    'broward_energov': 'Broward: EnerGov permits + code cases (Pembroke Pines, Sunrise, Oakland Park; Miramar permits)',
    'broward_fc_notices': 'Broward: foreclosure notices (published, floridapublicnotices.com)', 'broward_auctions': 'Broward: foreclosure + tax-deed auctions'}
MAX_LAG_DAYS = int(os.environ.get('MAX_LAG_DAYS', '3'))
import re
def through(globs):
    """Newest filing date actually held: max end date in *_YYYYMMDD_YYYYMMDD.csv / ocs_YYYYMMDD.txt / RAW/clerk cache names."""
    ds = []
    for g in globs:
        for f in glob.glob(g):
            m = re.findall(r'(\d{8})', os.path.basename(f))
            if m: ds.append(m[-1])
    return max(ds) if ds else None
DATA_THROUGH = {  # source -> newest filing date held (stale when older than MAX_LAG_DAYS, whatever the step said)
    'clerk': lambda: through(['raw/lp_downloads/lp_*.csv', os.path.join(RAW, 'clerk/LIS/*.json')]),
    'clerk_clp': lambda: through(['raw/lp_downloads/clp_*.csv', 'raw/lp_downloads/cot_*.csv', 'raw/lp_downloads/dis_*.csv', os.path.join(RAW, 'clerk/CLP/*.json')]),
    'cot': lambda: through(['raw/lp_downloads/cot_*.csv', os.path.join(RAW, 'clerk/COT/*.json')]),
    'probate': lambda: through(['raw/probate_downloads/probate_*.csv', 'raw/probate_cases/ocs_*.txt']),
    'monroe_clerk': lambda: jmax(os.path.join(RAW, 'monroe/clerk_cases.json'), lambda d: max((c.get('filed') or '' for c in d.get('cases', [])), default='')),
    'broward_lp': lambda: max((m[2] + m[0] + m[1] for f in glob.glob(os.path.join(RAW, 'broward/official_records/*doc-ver.txt')) for m in re.findall(r'(\d\d)-(\d\d)-(\d{4})', os.path.basename(f))), default=None),   # MM-DD-YYYYdoc-ver.txt
    # newest record actually held (not the pull time): FTL's own layer stopped updating 2026-03-16, so it reports stale honestly
    'broward_permits': lambda: jmax(os.path.join(RAW, 'broward/permits/fort_lauderdale.json'), lambda d: d.get('data_through') or ''),
    'broward_energov': lambda: jmax(os.path.join(RAW, 'broward/permits/energov/summary.json'), lambda d: min((v.get('newest') or v['max_date'] for v in d['portals'].values() if v.get('rows')), default='')),   # the OLDEST of the per-portal newest dates
    # Key West: the older of the newest permit issue date and the newest code-case open date (both must be current to count as fresh)
    'monroe_keywest': lambda: min_d(jmax(os.path.join(RAW, 'monroe/kw_permits.json'), lambda d: d.get('newest') or ''), jmax(os.path.join(RAW, 'monroe/kw_cases.json'), lambda d: d.get('newest') or '')),
    # Islamorada: newest permit application / issue date read from the permit detail pages (code cases carry only a year, so they cannot date the feed)
    'monroe_islamorada': lambda: jmax(os.path.join(RAW, 'monroe/isl_cityview.json'), lambda d: (d.get('newest') or {}).get('permit_date') or ''),
    'broward_fc_notices': lambda: jmax(os.path.join(RAW, 'broward/fpn_foreclosure.json'), lambda d: d.get('newest') or ''),
}
# Clerk Official Records sources can never be newer than the Clerk's own index ("This database contains official records recorded
# through: <date>", public GET api/home/GetDate that the search page itself calls). Holding everything through that date = fresh.
def min_d(*a): return min(a) if all(a) else None
CLERK_INDEXED = {'clerk', 'clerk_clp', 'cot', 'probate'}
def clerk_index():
    cache = os.path.join(RAW, 'clerk_index_through.json')
    try:
        import urllib.request
        rq = urllib.request.Request('https://onlineservices.miamidadeclerk.gov/officialrecords/api/home/GetDate', headers={'User-Agent': 'Mozilla/5.0'})
        v = json.load(urllib.request.urlopen(rq, timeout=20))[:10]; datetime.date.fromisoformat(v)
        json.dump({'through': v, 'checked': datetime.datetime.now().astimezone().isoformat(timespec='seconds')}, open(cache, 'w')); return v, 'live'
    except Exception:
        try: return json.load(open(cache))['through'], 'cached'
        except Exception: return None, None
CLERK_IDX, CLERK_IDX_HOW = clerk_index()
LAG = {'monroe_clerk': 7, 'broward_lp': 4, 'broward_permits': 10, 'broward_energov': 4, 'broward_fc_notices': 4, 'monroe_keywest': 7, 'monroe_islamorada': 7}
def jmax(p, f):
    try: v = f(json.load(open(p))).replace('-', '')
    except Exception: return None
    return v or None
BUILDS = ['load_raw', 'spatial', 'merge_permits', 'distress', 'signals', 'comps', 'commercial', 'data', 'zoning_rules', 'assemblages', 'broward_data']
def state(s):
    for k in ('ok', 'stale', 'fail'):
        p = os.path.join(st, f'{s}.{k}')
        if os.path.exists(p): return k, open(p).read().strip()
    return 'not run', ''
def lastgood(s):
    p = os.path.join(st, 'history.json'); h = json.load(open(p)) if os.path.exists(p) else {}
    return h, h.get(s)
def J(p):
    try:
        if p.endswith('.gz'): return json.load(gzip.open(p, 'rt'))
        return json.load(open(p))
    except Exception: return None
def nfiles(d): return len(glob.glob(os.path.join(RAW, d, '**', '*'), recursive=True))
counts = {}
m = J('data/meta.json') or {}
if m: counts['parcels'] = m.get('total'); counts['salesThrough'] = m.get('salesThrough'); counts['rollYear'] = m.get('rollYear')
ds = J(os.path.join(RAW, 'distress_stats.json')) or {}
lp = ds.get('lis_pendens') or {}
if lp: counts['lis_pendens_matched'] = lp.get('matched'); counts['lis_pendens_through'] = lp.get('recorded_to')
a = J(os.path.join(RAW, 'auctions.json')) or {}
if a: counts['auction_items'] = len(a.get('items') or []); counts['auctions_pulled'] = a.get('pulled')
sg = J('data/signals.json.gz')
if isinstance(sg, dict):
    for k, n in (('pf', 'open_preforeclosures'), ('pb', 'probate'), ('au', 'auctions_with_max_bid')):
        if isinstance(sg.get(k), list): counts[n] = len(sg[k])
cp = J('data/comps.json.gz')
if isinstance(cp, dict): counts['comps'] = len(cp.get('rows') or [])
cm = J('data/commercial.json.gz')
if isinstance(cm, dict): counts['commercial_list'] = len(cm.get('rows') or {}); counts['commercial_live_tax'] = sum('chk' in v for v in (cm.get('rows') or {}).values())
for s, d in (('tax', 'tax'), ('viol', 'viol'), ('permits_files', 'permits'), ('parcel_files', 'parcels'), ('clerk_files', 'clerk')):
    counts[s] = nfiles(d)
hist, _ = lastgood(None)
res = {'built': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
       'run_started': (open(os.path.join(st, 'run_started')).read().strip() if os.path.exists(os.path.join(st, 'run_started')) else None),
       'sources': {}, 'builds': {}, 'counts': counts}
for s, label in SOURCES.items():
    k, t = state(s)
    if s in DATA_THROUGH:
        d = DATA_THROUGH[s]()
        if d:
            iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"; lag = (datetime.date.today() - datetime.date.fromisoformat(iso)).days
            hist[s] = iso; k = 'ok' if lag <= LAG.get(s, MAX_LAG_DAYS) else 'stale'
            res['sources'][s] = {'label': label, 'status': 'fresh' if k == 'ok' else 'stale', 'last_good': iso, 'data_through': iso, 'lag_days': lag}
            if s in CLERK_INDEXED and CLERK_IDX:
                cur = iso >= CLERK_IDX; dd = datetime.date.fromisoformat(min(iso, CLERK_IDX) if cur else iso)
                res['sources'][s].update({'clerk_index_through': CLERK_IDX, 'clerk_index_checked': CLERK_IDX_HOW, 'behind_clerk_days': 0 if cur else (datetime.date.fromisoformat(CLERK_IDX) - dd).days,
                                          'note': f"through {dd.strftime('%b')} {dd.day} (Clerk's latest)" if cur else f"through {dd.strftime('%b')} {dd.day}; Clerk has records through {CLERK_IDX}"})
                if cur: res['sources'][s]['status'] = 'fresh'
        else:
            res['sources'][s] = {'label': label, 'status': 'stale', 'last_good': None, 'data_through': None}
        continue
    if k == 'ok': hist[s] = t
    res['sources'][s] = {'label': label, 'status': {'ok': 'fresh', 'stale': 'stale', 'fail': 'stale'}.get(k, k), 'last_good': hist.get(s)}
for b in BUILDS:
    k, t = state(b); res['builds'][b] = {'ok': 'ok', 'fail': 'failed'}.get(k, k)
json.dump(hist, open(os.path.join(st, 'history.json'), 'w'), indent=1)
json.dump(res, open(out, 'w'), indent=1)
fresh = [v['label'] for v in res['sources'].values() if v['status'] == 'fresh']
stale = [f"{v['label']} (last good {(v['last_good'] or 'never')[:10]})" for v in res['sources'].values() if v['status'] == 'stale']
bad = [b for b, v in res['builds'].items() if v == 'failed']
print(f"Data refresh {res['built'][:16]}: {len(fresh)}/{len(SOURCES)} sources fresh" + (f"; build steps failed: {', '.join(bad)}" if bad else '; all build steps ok'))
if stale: print('Stale: ' + '; '.join(stale))
c = counts; print(f"Parcels {c.get('parcels')}, sales through {c.get('salesThrough')}, lis pendens matched {c.get('lis_pendens_matched')} (through {c.get('lis_pendens_through')}), auction items {c.get('auction_items')}, open pre-foreclosures {c.get('open_preforeclosures')}, probate {c.get('probate')}, comps {c.get('comps')}")
