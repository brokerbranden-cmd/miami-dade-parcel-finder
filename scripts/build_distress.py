#!/usr/bin/env python3
"""Match every distress layer to a PA folio and write:
  RAW/distress.parquet   folio, hard-signal bits, hard points, newest event day  (read by build_data.py -> score columns in the packs)
  data/distress.json.gz  per-folio signal details for the drawer / CSV / top_leads.py
  RAW/distress_seen.json first date each (folio, signal) was seen by this pipeline (for "new since" reports)
Inputs (all made by the fetch_* scripts): RAW/pagis.parquet, RAW/clerk/**, RAW/auctions.json, RAW/tax/*.csv, RAW/viol/*.json, RAW/leads/*.csv
Nothing is guessed: a record that can't be tied to exactly one folio is counted as unmatched and left out.
"""
import csv, glob, gzip, json, os, re, sys, datetime as dt, collections
import numpy as np, pandas as pd

RAW = os.environ.get('RAW', '/workspace/raw')
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'data')
TODAY = dt.date.today()
DAY0 = dt.date(1900, 1, 1)

# ---------- signal codes (bit, short code, label, points) ----------  keep in sync with app.js DSIG + README
SIG = [
    ('FC', 'Foreclosure sale scheduled', 35),
    ('LP', 'Lis pendens (foreclosure suit)', 25),   # 25 if recorded in last 12 months, 15 if 12-24 months
    ('TD', 'Tax deed application / sale', 30),
    ('TC', 'Unpaid tax certificates', 10),          # 10 + 4 per extra tax year, max 18
    ('TX', 'Delinquent taxes (no certificate yet)', 6),
    ('US', 'Unsafe structure case', 22),
    ('BV', 'Open building violation', 8),
    ('CC', 'Open code compliance case', 8),
    ('LN', 'Code / building lien', 12),
    ('RC', '40/50-yr recertification overdue', 8),
    ('PR', 'Probate / estate / unknown heirs', 15),
    ('DC', 'Owner deceased (obituary match)', 15),
]
BIT = {c: i for i, (c, _, _) in enumerate(SIG)}

def d2s(d): return d.isoformat() if d else ''
def ms2d(v):
    try: return (dt.datetime(1970, 1, 1) + dt.timedelta(milliseconds=int(v))).date() if v not in (None, '') else None
    except Exception: return None
def pdate(s):
    s = (s or '').strip().split(' ')[0]
    for f in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y'):
        try: return dt.datetime.strptime(s, f).date()
        except ValueError: pass
    return None
def money(s):
    try: return float(re.sub(r'[^\d.]', '', str(s)) or 0)
    except ValueError: return 0.0
fol = lambda s: re.sub(r'\D', '', str(s or ''))

# ---------- PA roll index ----------
pa = pd.read_parquet(f'{RAW}/pagis.parquet', columns=['FOLIO', 'TRUE_MAILING_ADDR1', 'TRUE_MAILING_ZIP_CODE', 'TRUE_SITE_ADDR', 'TRUE_SITE_UNIT', 'TRUE_SITE_ZIP_CODE', 'TRUE_OWNER1', 'TRUE_OWNER2', 'TRUE_OWNER3', 'LEGAL'])
pa = pa[pa.FOLIO.notna()].drop_duplicates('FOLIO')
pa['FOLIO'] = pa.FOLIO.astype(str).str.strip()
FOLIOS = set(pa.FOLIO)
SUF = {'STREET': 'ST', 'AVENUE': 'AVE', 'AV': 'AVE', 'COURT': 'CT', 'TERRACE': 'TER', 'TERR': 'TER', 'PLACE': 'PL', 'ROAD': 'RD', 'DRIVE': 'DR',
       'BOULEVARD': 'BLVD', 'LANE': 'LN', 'CIRCLE': 'CIR', 'PARKWAY': 'PKWY', 'HIGHWAY': 'HWY', 'NORTHWEST': 'NW', 'NORTHEAST': 'NE',
       'SOUTHWEST': 'SW', 'SOUTHEAST': 'SE', 'NORTH': 'N', 'SOUTH': 'S', 'EAST': 'E', 'WEST': 'W', 'WAY': 'WAY'}
def norm_addr(a):
    a = re.sub(r'[.,#]', ' ', str(a or '').upper())
    a = re.split(r'\b(UNIT|APT|STE|SUITE)\b', a)[0]
    w = [SUF.get(x, x) for x in a.split()]
    w = [re.sub(r'^(\d+)(ST|ND|RD|TH)$', r'\1', x) for x in w]
    return ' '.join(w)
pa['NA'] = [norm_addr(a) for a in pa.TRUE_SITE_ADDR.fillna('')]
pa['Z5'] = pa.TRUE_SITE_ZIP_CODE.fillna('').astype(str).str[:5]
pa['UNIT'] = pa.TRUE_SITE_UNIT.fillna('').astype(str).str.strip().str.upper()
by_addr = collections.defaultdict(list)
for f, a, z, u in zip(pa.FOLIO, pa.NA, pa.Z5, pa.UNIT):
    if a: by_addr[a].append((f, z, u))
def addr_to_folio(addr, zip5='', unit=''):
    """exact normalized street address (+zip, +unit when several parcels share it); None unless exactly one folio"""
    c = by_addr.get(norm_addr(addr), [])
    if zip5: c = [x for x in c if x[1] == zip5] or ([] if any(x[1] for x in c) else c)
    if len(c) > 1 and unit: c = [x for x in c if x[2] == unit.upper()]
    return c[0][0] if len(c) == 1 else None

owners = (pa.TRUE_OWNER1.fillna('') + ' ' + pa.TRUE_OWNER2.fillna('') + ' ' + pa.TRUE_OWNER3.fillna('')).str.upper()
OWN = dict(zip(pa.FOLIO, owners))
# legal index: (plat book, plat page, lot, block)
LEG = collections.defaultdict(list)
for f, l in zip(pa.FOLIO, pa.LEGAL.fillna('')):
    l = l.upper(); m = re.search(r'\bPB\s*(\d+)\s*-\s*(\d+)', l)
    if not m: continue
    lots = re.findall(r'\bLOTS?\s+(\d+[A-Z]?)', l); blk = re.search(r'\bBLK\s+(\w+)', l)
    for lot in lots[:1]:
        LEG[(int(m.group(1)), int(m.group(2)), lot, blk.group(1) if blk else '')].append(f)

STATS = collections.OrderedDict()
recs = collections.defaultdict(list)  # folio -> [ [code, date, title, amount, case/ref, url, extra] ]
def add(folio, code, date, title, amount=0, ref='', url='', extra=''):
    recs[folio].append([code, d2s(date), title, round(float(amount or 0), 2), ref, url, extra])

ARC = lambda layer, field, val: f"{layer}/query?where={field}%3D%27{val}%27&outFields=*&returnGeometry=false&f=html"

# ---------- 1. lis pendens (Clerk Official Records) ----------
lp_docs = {}
def take_model(m):
    if not str(m.get('doC_TYPE', '')).startswith('LIS PENDENS'): return
    cfn = (m.get('clerk_File') or '').strip()
    if cfn: lp_docs.setdefault(cfn, []).append(m)
for f in glob.glob(f'{RAW}/clerk/LIS/*.json') + glob.glob(f'{RAW}/clerk/LIS_legacy/*.json'):
    try: d = json.load(open(f))
    except Exception: continue
    for m in (d.get('models') or d.get('recordingModels') or []) if isinstance(d, dict) else []: take_model(m)
for f in glob.glob(f'{RAW}/clerk/LIS_legacy/*lis-pendens-raw-all.csv'):
    for m in csv.DictReader(open(f, encoding='utf-8', errors='replace')): take_model(m)
# fresh Official Records CSV exports (logged-in browser session) -> same model shape; one row per party pairing
LPDIR = os.environ.get('LP_DOWNLOADS', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'raw', 'lp_downloads'))
PLF_RX = re.compile(r'\b(BANK|BANC|MORTGAGE|MTG|LOAN|LENDING|SERVIC|FUNDING|FINANC|CAPITAL|CREDIT UNION|FEDERAL|SAVINGS|FSB|N\s?A$|NATIONAL ASS|TRUST CO|TRUSTEE|SECRETARY OF|HOUSING|ASS(OCIATIO)?N|ASSOC|CONDO|HOMEOWNER|HOA|MASTER|COMMUNITY|NATIONSTAR|MR COOPER|LAKEVIEW|FREEDOM|NEWREZ|CARRINGTON|ROCKET|PENNYMAC|DEUTSCHE|WILMINGTON|U S BANK|US BANK|COMPUTERSHARE|FANNIE|FREDDIE|CITIBANK|WELLS FARGO|JPMORGAN|CHASE|HSBC|MIDFIRST|SPECIALIZED|SELECT PORTFOLIO|SHELLPOINT|PHH|LOANCARE|PLANET HOME|CHAMPION|REVERSE|CIVIC|ONEMAIN)')
n_csv_rows = 0; n_csv_dups = 0
# the weekly exports overlap (e.g. lp_20261001_20261002 and lp_20260930_20261001 both hold 10/01): pool every row of every file by CFN and
# drop exact duplicate rows, so one CFN is one document and its party pairings are complete even if they were split across two files
by = collections.defaultdict(list); seen_rows = set()
for f in sorted(glob.glob(f'{LPDIR}/*.csv')):
    for r in csv.DictReader(open(f, encoding='utf-8-sig', errors='replace')):
        n_csv_rows += 1; k = tuple(r.values())
        if k in seen_rows: n_csv_dups += 1; continue
        seen_rows.add(k); by[r["Clerk's File Number"].strip()].append(r)
if True:
    for cfn, rs in by.items():
        if not cfn or not rs[0]['Document Type'].startswith('LIS PENDENS'): continue
        G = collections.defaultdict(set)
        for r in rs:
            a, _, b = r['Party Name'].partition(' / '); a, b = a.strip(), b.strip()
            if a and b: G[a].add(b); G[b].add(a)
        side, plfs, defs = {}, set(), set()   # pairings are plaintiff x defendant -> 2-colour each component, plaintiff side = more lender/HOA names
        for n0 in G:
            if n0 in side: continue
            comp, st = [], [(n0, 0)]
            while st:
                n, c = st.pop()
                if n in side: continue
                side[n] = c; comp.append(n); st += [(x, 1 - c) for x in G[n]]
            score = [sum(1 for n in comp if side[n] == k and PLF_RX.search(n)) - sum(1 for n in comp if side[n] == k and not PLF_RX.search(n)) * .01 for k in (0, 1)]
            k = 0 if score[0] >= score[1] else 1
            for n in comp: (plfs if side[n] == k else defs).add(n)
        r0 = rs[0]; bp = (r0['Rec Book/Page'] + '/').split('/'); pp = (r0['Plat Book/Page'] + '/').split('/')
        lp_docs[cfn] = [{'clerk_File': cfn, 'doC_TYPE': r0['Document Type'], 'reC_DATE': r0['Rec Date'], 'reC_BOOK': bp[0], 'reC_PAGE': bp[1],
                         'plaT_BOOK': pp[0], 'plaT_PAGE': pp[1], 'blocK_NO': r0['Block Number'], 'legaL_DESCRIPTION': r0['Legal'], 'misC_REF': r0['Misc Ref'],
                         'address': r0['Address'].strip(), '_plfs': plfs, '_defs': defs, '_src': 'csv'}]   # fresh export replaces cached JSON copy of the same CFN
cancelled = set()  # CFNs of lis pendens released by a recorded cancellation (CLP links to the original by book/page)
for f in glob.glob(f'{RAW}/clerk/CLP/*.json'):
    for m in json.load(open(f)).get('models', []):
        if m.get('oriG_REC_BOOK'): cancelled.add((int(m['oriG_REC_BOOK']), int(m['oriG_REC_PAGE'])))
prior = {}  # earlier assistants' one-by-one PA lookups (unique GIS legal / address matches), keyed by CFN
for f in glob.glob(f'{RAW}/clerk/LIS_legacy/*pa-addresses.csv'):
    for r in csv.DictReader(open(f)):
        if fol(r.get('folio_out')) in FOLIOS: prior[r['cfn'].strip()] = fol(r['folio_out'])
for f in glob.glob(f'{RAW}/clerk/LIS_legacy/*CRM.csv'):
    for r in csv.DictReader(open(f)):
        if fol(r.get('folio')) in FOLIOS: prior.setdefault(r['cfn_or_instrument'].strip(), fol(r['folio']))
LEGALS = dict(zip(pa.FOLIO, pa.LEGAL.fillna('').str.upper()))
NAMEIDX = collections.defaultdict(set)
for f, o in OWN.items():
    for t in set(re.findall(r'[A-Z]{3,}', o)): NAMEIDX[t].add(f)
TOK_SKIP = {'THE', 'OF', 'AND', 'INC', 'LLC', 'TR', 'TRUST', 'EST', 'ESTATE', 'UNKNOWN', 'SPOUSE', 'HEIRS', 'JR', 'SR', 'II', 'III', 'TENANT', 'NKA', 'AKA'}
def name_tokens(n): return [t for t in re.findall(r'[A-Z]{2,}', n.upper()) if t not in TOK_SKIP]
def owner_has(folio, toks): o = OWN.get(folio, ''); return len(toks) >= 2 and all(re.search(r'\b' + t + r'\b', o) for t in toks[:2])
n_lp, n_lp_m, how = 0, 0, collections.Counter()
LPKIND = collections.Counter(); _hl = ['']
CLERK_URL = 'https://onlineservices.miamidadeclerk.gov/officialrecords/StandardSearch.aspx'
for cfn, ms in lp_docs.items():
    m0 = ms[0]; n_lp += 1
    rd = pdate(m0.get('reC_DATE'))
    try:
        if (int(m0.get('reC_BOOK') or 0), int(m0.get('reC_PAGE') or 0)) in cancelled: continue
    except ValueError: pass
    defs, plfs = set(), set()
    for m in ms:
        if '_plfs' in m: plfs |= m['_plfs']; defs |= m['_defs']; continue
        a, b = (m.get('firsT_PARTY') or '').strip(), (m.get('seconD_PARTY') or '').strip()
        if (m.get('partY_CODE') or '').strip() == 'R': defs.add(a); plfs.add(b)
        else: plfs.add(a); defs.add(b)
    defs -= plfs; defs.discard(''); plfs.discard('')
    folio = prior.get(cfn) if prior.get(cfn) else None
    mh = 'prior PA lookup' if folio else ''
    if folio: how[mh] += 1
    if not folio:
        try: pb, pg = int(m0.get('plaT_BOOK') or 0), int(m0.get('plaT_PAGE') or 0)
        except ValueError: pb = pg = 0
        lot = re.search(r'\bLOTS?\s+(\d+[A-Z]?)', (m0.get('legaL_DESCRIPTION') or '').upper())
        if pb and lot:
            blk = (m0.get('blocK_NO') or '').strip().upper()
            c = []
            for pgv in {pg, pg // 10 if pg % 10 == 0 else pg}:  # Clerk index sometimes carries a trailing 0 on the plat page
                c += LEG.get((pb, pgv, lot.group(1), blk), []) or (LEG.get((pb, pgv, lot.group(1), ''), []) if blk else [])
            c = sorted(set(c))
            if len(c) > 1: c = [f for f in c if any(owner_has(f, name_tokens(d)) for d in defs)]
            if len(c) == 1: folio = c[0]; mh = 'plat book/page + lot/block'; how[mh] += 1
        if not folio:  # defendant name on the PA roll + the same lot number or subdivision word in the PA legal
            subw = [w for w in re.findall(r'[A-Z]{4,}', (m0.get('subdiV_NAME') or '').upper()) if w not in ('CONDO', 'CONDOMINIUM', 'ESTATES', 'SECTION', 'ADDITION', 'SUBDIVISION', 'REVISED', 'AMENDED', 'PLAT')]
            lotn = lot.group(1) if lot else None
            unit = re.search(r'\bUNIT\s+(?:NO\s+)?(\w+)', (m0.get('legaL_DESCRIPTION') or '').upper())
            hits = set()
            for d in defs:
                t = name_tokens(d)
                if len(t) < 2: continue
                cand = NAMEIDX.get(t[0], set()) & NAMEIDX.get(t[1], set())
                for f in cand:
                    l = LEGALS.get(f, '')
                    ok_sub = bool(subw) and subw[0] in l
                    ok_lot = bool(lotn) and re.search(r'\bLOTS?\s+(?:\d+[A-Z]?\s*(?:&|AND|,)\s*)*' + lotn + r'\b', l)
                    ok_unit = bool(unit) and re.search(r'\bUNIT\s+(?:NO\s+)?' + unit.group(1) + r'\b', l)
                    ok_pb = bool(pb) and re.search(r'\bPB\s*%d\s*-\s*%d\b' % (pb, pg if pg % 10 or pg < 10 else pg), l) is not None
                    blkv = (m0.get('blocK_NO') or '').strip().upper()
                    ok_blk = not blkv or re.search(r'\bBLK\s+' + re.escape(blkv) + r'\b', l)
                    if (ok_sub or ok_pb) and (ok_lot or ok_unit or not (lotn or unit)): hits.add(f)
                    elif (ok_lot and ok_blk and blkv) or ok_unit: hits.add(f)
            if len(hits) == 1: folio = hits.pop(); mh = 'defendant name + legal (plat/lot/block/unit)'; how[mh] += 1
    if not folio and m0.get('address'):
        folio = addr_to_folio(m0['address'])
        if folio and defs and not any(owner_has(folio, name_tokens(d)) for d in defs): folio = None  # precision: owner must be a defendant
        if folio: mh = 'address + defendant name'; how[mh] += 1
    if not folio: continue
    n_lp_m += 1
    case = re.sub(r'\s+LIS\w*$', '', (m0.get('casE_NUM') or m0.get('misC_REF') or '').strip())
    BANKY = r'BANK|NATIONAL ASS|N\s?A$|TRUST|LOAN|MORTGAGE|MTG|SERVIC|FUNDING|LENDING|FEDERAL|SAVINGS|CREDIT UNION|FINANC|CAPITAL'
    hoa = any(re.search(r'ASS(OCIATIO)?N|ASSOC|CONDO|HOMEOWNER|HOA\b|MASTER|COMMUNITY|\bCOA\b|\bPOA\b', p) and not re.search(BANKY, p) for p in plfs)
    lender = any(PLF_RX.search(p) for p in plfs)
    kind = 'HOA/condo lien foreclosure' if hoa else ('Mortgage foreclosure' if '-CA-' in case and lender else 'Other lis pendens')
    LPKIND[kind] += 1
    conf = 'high' if mh != 'plat book/page + lot/block' or any(owner_has(folio, name_tokens(d)) for d in defs) else 'medium'
    add(folio, 'LP', rd, 'Lis pendens: ' + kind, 0, case or cfn,
        CLERK_URL, f"CFN {cfn}; match: {mh} ({conf} confidence); plaintiff: {'; '.join(sorted(plfs))[:120]}; defendant: {'; '.join(sorted(defs))[:120]}")
lp_range = sorted(pdate(v[0].get('reC_DATE')) for v in lp_docs.values() if pdate(v[0].get('reC_DATE')))
STATS['lis_pendens'] = {'documents': n_lp, 'matched': n_lp_m, 'how': dict(how), 'kind': dict(LPKIND), 'csv_rows': n_csv_rows, 'csv_duplicate_rows_dropped': n_csv_dups, 'csv_files': len(glob.glob(f'{LPDIR}/*.csv')), 'recorded_from': d2s(lp_range[0]) if lp_range else '', 'recorded_to': d2s(lp_range[-1]) if lp_range else '',
                        'source': 'https://onlineservices.miamidadeclerk.gov/officialrecords/ (LIS PENDENS - LIS)'}

# ---------- 2. foreclosure + tax-deed sales (RealAuction) ----------
if os.path.exists(f'{RAW}/auctions.json'):
    A = json.load(open(f'{RAW}/auctions.json'))
    c = collections.Counter()
    for x in A['items']:
        if x['status'] != 'scheduled': continue
        un = re.search(r'\b(?:UNIT|APT|#)\s*(\S+)$', x['address'].upper())
        f = x['folio'] if x['folio'] in FOLIOS else (addr_to_folio(x['address'], (re.search(r'\b(\d{5})', x['city']) or [None, ''])[1], un.group(1) if un else '') if x['address'] else None)
        c[x['type'] + (' matched' if f else ' unmatched')] += 1
        if not f: continue
        if x['type'] == 'FORECLOSURE':
            add(f, 'FC', pdate(x['date']), 'Foreclosure sale ' + x['date'], money(x['judgment']), x['case'], x['url'], 'final judgment ' + x['judgment'])
        else:
            add(f, 'TD', pdate(x['date']), 'Tax deed sale ' + x['date'], money(x['opening_bid']), x['case'], x['url'], f"opening bid {x['opening_bid']}; cert {x['cert']}")
    STATS['auctions'] = {'scheduled': dict(c), 'pulled': A['pulled'], 'source': A['source']}

# ---------- 3. tax collector reports ----------
TAXURL = lambda acct: f'https://miamidade.county-taxes.com/public/search/property_tax?search_query={acct}'
T = f'{RAW}/tax'
roll_year = TODAY.year if TODAY.month >= 11 else TODAY.year - 1  # bills go out in November; unpaid after April 1 = delinquent
if os.path.exists(f'{T}/Public-Open Certificates wAddr.csv'):
    d = pd.read_csv(f'{T}/Public-Open Certificates wAddr.csv', dtype=str).fillna('')
    d['f'] = d['Account Number'].map(fol)
    g = d.groupby('f'); n = 0
    for f, x in g:
        if f not in FOLIOS: continue
        n += 1
        yrs = sorted(set(x['Tax Yr']))
        face = sum(money(v) for v in x['Face Amount'])
        held = 'county-held' if (x['County Held'] == 'Yes').any() else ''
        add(f, 'TC', pdate(x['Issued Date'].max()) if False else min((pdate(v) for v in x['Issued Date'] if pdate(v)), default=None),
            f"{len(x)} open tax certificate{'s' if len(x) > 1 else ''} ({', '.join(yrs)})", face, ', '.join('#' + c for c in x['Cert #'][:6]), TAXURL(x['Account Number'].iloc[0]),
            f"face total ${face:,.0f}; holders: {'; '.join(sorted(set(x['Cert Buyer'])))[:120]} {held}".strip())
    STATS['tax_certificates'] = {'rows': len(d), 'accounts': int(d.f.nunique()), 'matched': n, 'source': 'https://miamidade.county-taxes.com/govhub/reports/real-estate (Public-Open Certificates wAddr)'}
if os.path.exists(f'{T}/Public-unpaid accts non-cert.csv'):
    d = pd.read_csv(f'{T}/Public-unpaid accts non-cert.csv', dtype=str).fillna('')
    d['f'] = d['Account Number'].map(fol); d['bal'] = d['Balance Amount'].map(money); d['yr'] = pd.to_numeric(d['Tax Yr'], errors='coerce')
    d = d[(d.bal > 1) & (d.yr <= roll_year)]
    n = 0
    for f, x in d.groupby('f'):
        if f not in FOLIOS: continue
        n += 1
        add(f, 'TX', None, f"Unpaid {', '.join(sorted(set(x['Tax Yr'])))} taxes" + (' (bankruptcy)' if (x.Bankrupt == 'Yes').any() else '') + (' (in litigation)' if (x.Litigation == 'Yes').any() else ''),
            x.bal.sum(), '', TAXURL(x['Account Number'].iloc[0]), f"balance ${x.bal.sum():,.0f}; deed status: {', '.join(sorted(set(x['Deed Status'])))}")
    STATS['unpaid_taxes'] = {'rows': len(d), 'matched': n, 'source': 'https://miamidade.county-taxes.com/govhub/reports/real-estate (Public-unpaid accts non-cert)'}
if os.path.exists(f'{T}/Public-Open Deeds.csv'):
    d = pd.read_csv(f'{T}/Public-Open Deeds.csv', dtype=str).fillna('')
    n = 0
    for _, r in d.iterrows():
        f = fol(r['Account Number'])
        if f not in FOLIOS: continue
        n += 1
        sd = pdate(r['Deed Sale Date'])
        add(f, 'TD', pdate(r['Application Date']), f"Tax deed application ({r['Deed Status']})" + (f", sale {r['Deed Sale Date']}" if sd else ''), money(r['TDA Base Amount']),
            'TDA #' + r['Deed Application #'], TAXURL(r['Account Number']), f"applicant: {r['Applicant']}; tax year {r['Tax Yr']}")
    STATS['tax_deed_applications'] = {'rows': len(d), 'matched': n, 'source': 'https://miamidade.county-taxes.com/govhub/reports/real-estate (Public-Open Deeds)'}

# ---------- 4. violations / unsafe / liens / recert (ArcGIS) ----------
def V(name):
    p = f'{RAW}/viol/{name}.json'
    return json.load(open(p)) if os.path.exists(p) else {'rows': [], 'source': ''}
v = V('bldg_open'); c = collections.Counter()
for r in v['rows']:
    f = fol(r['FOLIO']); 
    if f not in FOLIOS: c['unmatched'] += 1; continue
    us = r['CASE_TYPE'] == 'Unsafe Structure'; c['unsafe' if us else 'other'] += 1
    add(f, 'US' if us else 'BV', ms2d(r['OPEN_DATE']), ('Unsafe structure case' if us else 'Building violation: ' + r['CASE_TYPE']), 0, r['CASE_NUM'], ARC(v['source'], 'CASE_NUM', r['CASE_NUM']),
        f"violator: {(r['VIOL_NAME'] or '').strip()}" + (f"; permit {r['PERMIT_NUM']}" if r.get('PERMIT_NUM') else ''))
STATS['building_violations_open'] = {**c, 'rows': len(v['rows']), 'source': v['source']}
v = V('cc_open'); c = collections.Counter()
for r in v['rows']:
    f = fol(r['FOLIO'])
    if f not in FOLIOS: c['unmatched'] += 1; continue
    c['matched'] += 1
    add(f, 'CC', ms2d(r['CASE_DATE']), 'Code case: ' + r['PROBLEM_DESC'].strip(), 0, r['CASE_NUM'], ARC(v['source'], 'CASE_NUM', r['CASE_NUM']), f"last action: {r['LAST_ACTV'].strip()}")
STATS['code_cases_open'] = {**c, 'rows': len(v['rows']), 'source': v['source']}
seen_lien = set(); c = collections.Counter()
for nm, label in (('cc_lien', 'Code lien'), ('cc_finance', 'Code fines sent to collections')):
    v = V(nm)
    for r in v['rows']:
        f = fol(r['FOLIO'])
        if f not in FOLIOS: c[nm + ' unmatched'] += 1; continue
        if (f, r['CASE_NUM']) in seen_lien: continue
        seen_lien.add((f, r['CASE_NUM'])); c[nm + ' matched'] += 1
        rec = f"recorded {r['LN_RECDATE'].strip()} OR {r['LN_RECBOOK'].strip()}-{r['LN_RECPAGE'].strip()}" if r['LN_RECBOOK'].strip() else 'lien status (not yet recorded)'
        add(f, 'LN', ms2d(r['CASE_DATE']), f"{label}: {r['PROBLEM_DESC'].strip()}", 0, r['CASE_NUM'], ARC(v['source'], 'CASE_NUM', r['CASE_NUM']), rec + f"; status {r['STAT_DESC'].strip()}")
ball = {r['CASE_NUM']: r for r in V('bldg_all')['rows']}
v = V('bldg_lien')
for r in v['rows']:
    b = ball.get(r['CASE_NUM']); f = fol(b['FOLIO']) if b else ''
    if f not in FOLIOS: c['bldg_lien unmatched'] += 1; continue
    if b.get('CLOSED_DATE') and ms2d(b['CLOSED_DATE']) and ms2d(r['LIEN_RECDT']) and ms2d(b['CLOSED_DATE']) > ms2d(r['LIEN_RECDT']):
        c['bldg_lien case closed after lien'] += 1; continue
    c['bldg_lien matched'] += 1
    add(f, 'LN', ms2d(r['LIEN_RECDT']), 'Building violation lien: ' + b['CASE_TYPE'], 0, r['CASE_NUM'], ARC(v['source'], 'CASE_NUM', r['CASE_NUM']), f"recorded OR {r['LIEN_BOOK']}-{r['LIEN_PAGE']}")
STATS['liens'] = dict(c)
v = V('miami_recert'); c = collections.Counter()
for r in v['rows']:
    if r['CertificationStatus'] != 'Pending' or int(r['RecertificateYear'] or 9999) > TODAY.year - 1: continue
    f = fol(r['FolioNumber'])
    if f not in FOLIOS: c['unmatched'] += 1; continue
    c['matched'] += 1
    add(f, 'RC', None, f"Recertification due {r['RecertificateYear']} still pending", 0, r['PlanNumber'] or '', ARC(v['source'], 'FolioNumber', r['FolioNumber']), f"{r['RecertificationProcessStatus']}; plan status {r['PlanStatus'] or ''}; built {r['YearBuilt']}")
STATS['recert_overdue_city_of_miami'] = {**c, 'rows': len(v['rows']), 'source': v['source']}

# ---------- 5. probate / heirs / obituaries (outputs of the No Heir Probates and Obituary Scraper bots) ----------
c = collections.Counter()
for p in glob.glob(f'{RAW}/leads/leads_south_florida.csv'):
    for r in csv.DictReader(open(p)):
        if r['county'] != 'Miami-Dade': continue
        f = fol(r['folio_or_parcel'])
        if f not in FOLIOS:
            a = re.sub(r',?\s*(MIAMI|HIALEAH|HOMESTEAD|[A-Z ]+),?\s*FL.*$', '', r['property_address'].upper())
            z = re.search(r'\b(33\d{3})\b', r['property_address']); unit = re.search(r'\bUNIT\s+(\S+)', r['property_address'].upper())
            f = addr_to_folio(a, z.group(1) if z else '', unit.group(1) if unit else '') if r['property_address'] and 'none' not in r['property_address'] else None
        if not f: c['unmatched'] += 1; continue
        c['matched'] += 1
        add(f, 'PR', pdate(r['first_notice_date_seen']), ('Unknown heirs: ' if 'heir' in r['no_heir_evidence'].lower() else 'Probate: ') + r['notice_type'], 0, r['case_number'], r['source_url'],
            f"decedent {r['decedent_name']}; {r['action_subtype']}" + (f"; sale {r['sale_date']}" if r['sale_date'] else ''))
STATS['no_heir_probate_notices'] = dict(c)
c = collections.Counter()
for p in sorted(glob.glob(f'{RAW}/leads/matches_*.csv')):
    for r in csv.DictReader(open(p)):
        if r['county'] != 'Miami-Dade' or r['confidence'] not in ('high', 'medium'): c['skipped (other county / low confidence)'] += 1; continue
        f = fol(r['folio'])
        if f not in FOLIOS: c['unmatched'] += 1; continue
        c['matched'] += 1
        add(f, 'DC', pdate(r['date_of_death']), f"Owner obituary: {r['decedent_name']} ({r['confidence']} confidence)", 0, '', r['obit_url'], r['reason'][:160])
STATS['obituary_matches'] = dict(c)

# ---------- 5b. Clerk probate exports (PAD / PRO / DCE) -> PR + DC, merged into the records above ----------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probate_lib
PRDIR = os.environ.get('PROBATE_DOWNLOADS', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'raw', 'probate_downloads'))
PCDIR = os.environ.get('PROBATE_CASES', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'raw', 'probate_cases'))
if glob.glob(f'{PRDIR}/probate_*.csv') or glob.glob(f'{PCDIR}/ocs_*.txt'):
    probate_lib.run(pa, PRDIR, add, recs, norm_addr, addr_to_folio, LEG, CLERK_URL, pdate, STATS, PCDIR)

# ---------- points per folio ----------
def points(rs):
    have = collections.defaultdict(list)
    for r in rs: have[r[0]].append(r)
    pts = {}
    for code, lst in have.items():
        base = SIG[BIT[code]][2]
        if code == 'LP':
            nd = max((pdate(r[1]) for r in lst if r[1]), default=None)
            base = 25 if nd and (TODAY - nd).days <= 365 else 15
        if code == 'TC':
            yrs = max(len(re.findall(r'\d{4}', r[2])) for r in lst)
            base = min(18, 10 + 4 * (yrs - 1))
        pts[code] = base
    if 'PR' in pts and 'DC' in pts: pts['DC'] = 7  # PR + DC capped at 22
    if 'BV' in pts and 'CC' in pts: pts['CC'] = 4  # violations capped at 12
    return pts
rows = []; PTS = {}
for f, rs in recs.items():
    p = points(rs); PTS[f] = p
    bits = 0
    for k in p: bits |= 1 << BIT[k]
    ev = [pdate(r[1]) for r in rs if r[1]]
    rows.append((f, bits, min(100, sum(p.values())), (max(ev) - DAY0).days if ev else 0, json.dumps(p)))
dp = pd.DataFrame(rows, columns=['FOLIO', 'dsig', 'dhard', 'dlast', 'dpts'])
dp.to_parquet(f'{RAW}/distress.parquet', index=False)

# first-seen bookkeeping (for top_leads.py "new since")
sp = f'{RAW}/distress_seen.json'
seen = json.load(open(sp)) if os.path.exists(sp) else {'_first_build': d2s(TODAY)}
for f, rs in recs.items():
    for r in rs:
        k = f'{f}|{r[0]}|{r[4] or r[2]}'
        seen.setdefault(k, d2s(TODAY))
json.dump(seen, open(sp, 'w'))
for f, rs in recs.items():
    for r in rs: r.append(seen[f'{f}|{r[0]}|{r[4] or r[2]}'])

STATS['parcels_with_signals'] = len(recs)
STATS['by_signal'] = {code: int(((dp.dsig.values.astype(np.int64) >> BIT[code]) & 1).sum()) for code, _, _ in SIG}
out = {'built': d2s(TODAY), 'firstBuild': seen['_first_build'], 'sig': [[c, l, p] for c, l, p in SIG], 'stats': STATS,
       'cols': ['code', 'date', 'title', 'amount', 'ref', 'url', 'extra', 'firstSeen'], 'recs': recs, 'pts': PTS}
raw = json.dumps(out, separators=(',', ':')).encode()
open(os.path.join(OUT, 'distress.json.gz'), 'wb').write(gzip.compress(raw, 9, mtime=0))
json.dump(STATS, open(f'{RAW}/distress_stats.json', 'w'), indent=1)
print(json.dumps(STATS, indent=1)); print('distress.json.gz', round(os.path.getsize(os.path.join(OUT, 'distress.json.gz')) / 1e6, 2), 'MB')
