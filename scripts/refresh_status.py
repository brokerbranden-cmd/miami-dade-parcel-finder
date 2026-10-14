#!/usr/bin/env python3
"""Summarise the last build_all.sh run: per-source fresh/stale + counts -> data/refresh-status.json, short text on stdout."""
import json, os, sys, glob, gzip, datetime
st, out = sys.argv[1], sys.argv[2]
RAW = os.environ.get('RAW', '/workspace/raw')
SOURCES = {  # step -> label
    'pagis': 'Property Appraiser roll', 'layers': 'Zoning/CRA layers', 'zone_desc': 'Zoning descriptions',
    'clerk': 'Clerk lis pendens', 'clerk_clp': 'Clerk CLP (open check)', 'auctions': 'Foreclosure/tax auctions',
    'tax': 'Tax delinquency', 'viol': 'Code violations', 'permits': 'City of Miami permits',
    'county_permits': 'County permits', 'energov': 'EnerGov city permits', 'parcels': 'Parcel polygons'}
BUILDS = ['load_raw', 'spatial', 'merge_permits', 'distress', 'signals', 'comps', 'commercial', 'data', 'zoning_rules', 'assemblages']
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
