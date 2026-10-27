#!/usr/bin/env python3
"""City of Key Colony Beach permits + code cases from Ch. 119 public-records exports (Excel, Citizenserve; the city sends reports only on request,
no automatic feed). Inputs: $RAW/monroe/key_colony_beach/*.xlsx ('Issued Building Permits ...xlsx', 'Records Request - Code Cases ...xlsx').
Output: $RAW/monroe/kcb_records.json {'permits': [...], 'cases': [...], 'newest': {...}, 'stats': {...}} with 're' (RE number 00000000-000000)
taken from the code-case Parcel Number, else matched by site address to Key Colony Beach (TAX_AUTH_C 50KC) parcels in parcels.jsonl.
Re-run after each new export: drop the new xlsx files in the folder (newest file of each kind wins)."""
import os, re, json, glob, collections, pandas as pd
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe'); D = os.path.join(RAW, 'key_colony_beach')
SUF = {'STREET': 'ST', 'DRIVE': 'DR', 'LANE': 'LN', 'CIRCLE': 'CIR', 'COURT': 'CT', 'ROAD': 'RD', 'AVENUE': 'AVE', 'PLACE': 'PL', 'WEST': 'W', 'EAST': 'E'}
def norm(a):
    a = re.sub(r'[^A-Z0-9 ]', ' ', str(a or '').upper()); a = re.sub(r'\b(UNIT|APT|STE|#)\b.*$', '', a)
    w = [SUF.get(x, x) for x in a.split()]
    return ' '.join(w)
def key2(a):   # number + street name without suffix (KCB exports often drop ST / DR)
    w = norm(a).split()
    if len(w) < 2 or not w[0].isdigit(): return None
    w = [x for x in w if x not in ('ST', 'DR', 'LN', 'CIR', 'CT', 'RD', 'AVE', 'PL', 'KEY', 'COLONY', 'BEACH', 'FL')]
    return ' '.join(w[:3]) if len(w) >= 2 else None
def unit(a):
    m = re.search(r'\bUNIT\s*([A-Z0-9-]+)', str(a or '').upper()); return m.group(1) if m else None
idx = collections.defaultdict(set); vals = {}
for l in open(os.path.join(RAW, 'parcels.jsonl')):
    p = json.loads(l)
    if p.get('TAX_AUTH_C') != '50KC': continue
    d = re.sub(r'\D', '', p.get('PARCEL_ID') or '')[-14:]
    if len(d) != 14: continue
    re_ = d[:8] + '-' + d[8:]; vals[re_] = p.get('JV') or 0
    k = key2(p.get('PHY_ADDR1'))
    if k: idx[k].add(re_)
def match(a):
    k = key2(a); c = idx.get(k) if k else None
    if not c: return None, 'none'
    if len(c) == 1: return next(iter(c)), 'addr'
    return None, 'multi'   # condo buildings: many units at one street address -> leave unmatched rather than guess
newest = lambda pat: max(glob.glob(os.path.join(D, pat)), key=os.path.getmtime)
iso = lambda v: (pd.to_datetime(v, errors='coerce').date().isoformat() if pd.notna(pd.to_datetime(v, errors='coerce')) else None)
s = lambda v: '' if pd.isna(v) else str(v).strip()
st = collections.Counter(); P = []; C = []
pf = newest('*Permit*.xlsx'); cf = newest('*Code*.xlsx')
for _, r in pd.read_excel(pf).iterrows():
    st['permits'] += 1; re_, how = match(r['Property Address']); st['permit_match_' + how] += 1
    P.append({'no': s(r['Permit#']), 'type': s(r['Permit Type']), 'subtype': s(r['Subtype']), 'desc': s(r['Work Description'])[:200], 'addr': s(r['Property Address']),
              'issued': iso(r['Issue Date']), 'expires': iso(r['Expiration Date']), 'status': s(r['Permit Status']), 'cost': None if pd.isna(r['Construction Cost']) else float(r['Construction Cost']),
              'contractor': s(r['Contractor'])[:80], 're': re_})
for _, r in pd.read_excel(cf).iterrows():
    st['cases'] += 1; pid = re.sub(r'\s', '', s(r['Parcel Number']))
    if re.fullmatch(r'\d{8}-\d{6}', pid): re_, how = pid, 'parcel'
    else: re_, how = match(r['Address'])
    st['case_match_' + how] += 1
    C.append({'no': s(r['File#']), 'type': s(r['Record Type']), 'status': s(r['Open/Closed Status']), 'addr': s(r['Address']), 'opened': iso(r['Open Date']), 'closed': iso(r['Close Date']),
              'desc': re.sub(r'\s+', ' ', s(r['Description']))[:300], 're': re_})
out = {'source': 'City of Key Colony Beach Ch. 119 export (' + os.path.basename(pf) + '; ' + os.path.basename(cf) + ')', 'permits': P, 'cases': C,
       'newest': {'permit': max(x['issued'] for x in P if x['issued']), 'case': max(x['opened'] for x in C if x['opened'])}, 'stats': dict(st), 'kcb_parcels': len(vals)}
json.dump(out, open(os.path.join(RAW, 'kcb_records.json'), 'w')); print(json.dumps(out['stats']), out['newest'], 'kcb parcels', len(vals))
