#!/usr/bin/env python3
"""Normalize every permit + code-case source to per-folio records and write the permit/code coverage table.

Inputs (all produced by fetch_*.py; any may be missing - the merge degrades gracefully):
  RAW/pagis.parquet                       PA roll (folio, site address, municipality code)
  RAW/permits.json                        City of Miami permits 2014-today (+ County Building Dept last ~2 years)       fetch_permits.py
  RAW/permits/county_bp_l1.json           County Building Dept permit layer, status A/E/F, dense 2023-today             fetch_county_permits.py
  RAW/permits/county_co.json              County certificates of occupancy 2002-today                                    fetch_county_permits.py
  RAW/permits/energov/<slug>_<kind>.jsonl Municipal EnerGov portals (permits + code cases)                                 fetch_energov.py
  RAW/viol/cc_all.json                    County Code Compliance cases incl. closed (unincorporated)                    fetch_violations.py
  RAW/viol/bldg_closed5.json bldg_open.json  County building cases
Matching: the record's own folio (13 digits; EnerGov 'MainParcel') when it is a real PA folio, else exact normalized street address
(+ZIP) inside the portal's own municipality, only when exactly one folio carries that address.

Outputs:
  RAW/permit_index.json   {built, coverage:{muni_code:{city, permits:{...}, code:{...}}}, permits:{folio:[...]}, cases:{folio:[...]}, stats}
     permits[folio] = [last_date, n_5y, n_open, n_expired, n_revoked, last_expired_date, last_type, src, n_all, first_in_window?]
     cases[folio]   = [n_open, n_5y, last_opened, last_status, last_type, lien(0/1), flag_bits, src, n_all]   flag bits: 1 neglect, 2 unsafe, 4 foreclosure registry, 8 work-without-permit / permit case
  RAW/muni_cases.json     open / lien case items per folio (feeds the distress layer): {folio:[[kind,opened,type,status,case_no,src,url,desc]]}
"""
import json, os, re, sys, glob, time, collections, datetime as dt
import pandas as pd

RAW = sys.argv[1] if len(sys.argv) > 1 else '/workspace/raw'
TODAY = dt.date.today(); T5 = (TODAY - dt.timedelta(days=1826)).isoformat(); T2 = (TODAY - dt.timedelta(days=730)).isoformat()
OPEN_CASE_SINCE = '2016-01-01'      # an "open" municipal case older than this is treated as stale legacy data (kept in counts, not flagged)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------- PA roll index ----------------
pa = pd.read_parquet(f'{RAW}/pagis.parquet', columns=['FOLIO', 'TRUE_SITE_ADDR', 'TRUE_SITE_UNIT', 'TRUE_SITE_ZIP_CODE', 'MUNICIPALITY_CODE'])
pa = pa[pa.FOLIO.notna()].drop_duplicates('FOLIO'); pa['FOLIO'] = pa.FOLIO.astype(str).str.strip()
FOLIOS = set(pa.FOLIO)
SUF = {'STREET': 'ST', 'AVENUE': 'AVE', 'AV': 'AVE', 'COURT': 'CT', 'TERRACE': 'TER', 'TERR': 'TER', 'PLACE': 'PL', 'ROAD': 'RD', 'DRIVE': 'DR', 'BOULEVARD': 'BLVD', 'LANE': 'LN', 'CIRCLE': 'CIR',
       'PARKWAY': 'PKWY', 'HIGHWAY': 'HWY', 'NORTHWEST': 'NW', 'NORTHEAST': 'NE', 'SOUTHWEST': 'SW', 'SOUTHEAST': 'SE', 'NORTH': 'N', 'SOUTH': 'S', 'EAST': 'E', 'WEST': 'W'}
def norm_addr(a):
    a = re.sub(r'[.,#]', ' ', str(a or '').upper())
    a = re.split(r'\b(UNIT|APT|STE|SUITE)\b', a)[0]
    w = [SUF.get(x, x) for x in a.split()]
    return ' '.join(re.sub(r'^(\d+)(ST|ND|RD|TH)$', r'\1', x) for x in w)
by_addr = collections.defaultdict(list)
for f, a, z in zip(pa.FOLIO, pa.TRUE_SITE_ADDR.fillna(''), pa.TRUE_SITE_ZIP_CODE.fillna('').astype(str).str[:5]):
    if a: by_addr[norm_addr(a)].append((f, z))
CITY_WORDS = None
def addr_folio(addr, muni=None):
    """'7234 W 4 AVE Hialeah FL 33014' -> unique folio in that municipality (None if ambiguous / unknown)"""
    s = str(addr or '').upper(); z = ''
    m = re.search(r'\bFL\b\s*,?\s*(\d{5})?', s)
    if m: z = m.group(1) or ''; s = s[:m.start()]
    t = norm_addr(s).split()
    if len(t) > 2 and t[1] == 'GB': del t[1]                  # Surfside legacy rows carry a stray 'GB' after the house number
    if not t or not t[0][:1].isdigit(): return None
    cand = []
    for k in range(len(t), max(2, len(t) - 4), -1):          # drop trailing city words / unit tokens one at a time
        c = by_addr.get(' '.join(t[:k]))
        if c:
            c = [x for x in c if (not muni or x[0][:2] == muni) and (not z or not x[1] or x[1] == z)]
            if len(c) == 1: return c[0][0]
            if c: return None
    return None
def parcel_folio(p):
    s = str(p or '').strip()
    m = re.match(r'^(\d{2}-?\d{4}-?\d{3}-?\d{4})\b', s) or re.match(r'^(\d{13})\b', s)
    if not m: return ''
    f = re.sub(r'\D', '', m.group(1))
    return f if f in FOLIOS else ''

# ---------------- classification ----------------
INC = re.compile(r'build|bldg|roof|electr|plumb|mechan|hvac|a/c|\bac\b|air cond|pool|\bspa\b|fence|wall|demo|window|door|shutter|slab|driveway|paving|addition|alter|renov|remodel|repair|new (const|res|com|build)|solar|photovolt|generator|sprinkler|fire|\bgas\b|boiler|seawall|dock|shed|screen|deck|awning|canopy|carport|garage|foundation|structur|sewer|septic|irrigat|water heater|interior|exterior|tenant|impact|storm|certificate of (completion|occupancy)|co/cc|\b(bd|el|me|pl|rf|fb|bld)\b|historical - (building|electrical|plumbing|mechanical|co)|legacy|imported|converted|^$', re.I)
EXC = re.compile(r'microfilm|records request|garage sale|elevator|garbage|roll-?off|vendor|lottery|\bfilm\b|special event|right[- ]of[- ]way|\brow\b|utilit(y|ies)|engineering|banner|\bsigns?\b|\btree|parking|alarm|burglar|licen[sc]e|\bbtr\b|business tax|re-?occupancy|certificate of use|recertif|extension|renewal|revision|shop drawing|cancellation req|contractor|zoning|\bpz\b|public works|\bpw\b|kmgb|dumpster|crane|temporary|\btemp\b|portable|\bpod\b|newsrack|sidewalk caf|outdoor seating|variance|plan review|pre-?app|waiver|letter of|administrative|donation|moving|storage unit|paint|garbage|drain|lien|bluebeam|qualifier', re.I)
def relevant(t): return bool(INC.search(t)) and not EXC.search(t)
RX_X = re.compile(r'void|cancel|denied|withdraw|abandon|application expired|incomplete|invalid|duplicate|rejected|revision', re.I)
RX_E = re.compile(r'expired', re.I)
RX_R = re.compile(r'revok|suspend|stop work|legal action', re.I)
RX_F = re.compile(r'final|complete|closed|co issued|cc issued|ro issued|co/cc|passed|no further action|certificate', re.I)
RX_P = re.compile(r'appl|submit|review|pending|prescreen|pre-screen|fees|hold|approved|plans|correction|upload|initial|incomplete', re.I)
def pclass(st):
    """x ignore | e expired | r revoked/suspended/stop-work | f final | p pending (applied, not yet issued) | o open (issued, not finaled)"""
    if RX_X.search(st): return 'x'
    if RX_R.search(st): return 'r'
    if RX_E.search(st): return 'e'
    if RX_F.search(st): return 'f'
    if RX_P.search(st): return 'p'
    return 'o'
RX_CLOSED = re.compile(r'pass|close|complied|compliance|resolved|void|invalid|cancel|dismiss|withdraw|unfounded|no violation|abated|paid|satisfied|final|complete|duplicate|unsubstantiated|legacy - closed|inactive|superseded|rescind', re.I)
RX_RELEASED = re.compile(r'(lien|fine|fines)s? (released|settled|satisf|paid|removed|waived|reduced)|released|settled|satisfaction|case closed( -|\W)*(no |complied|in compliance)|^closed', re.I)
RX_LIEN = re.compile(r'fine owed|lien|fines? (running|accru)|running fine|judgment|foreclos(ure)? of lien', re.I)
NEG = re.compile(r'junk|trash|overgrow|debris|abandon|vacant|unsecur|structure maint|minimum hous|housing|property maint|exterior|sanitation|lot clear|weed|grass|nuisance|dilapidat|board(ed)?\b|pool|swimming|bee|infest|sewage|rubbish|garbage|blight|unkempt|derelict|mainten', re.I)
UNS = re.compile(r'unsafe|dangerous|condemn|demolition order', re.I)
FRG = re.compile(r'foreclos|registry|registration of vacant', re.I)
BWP = re.compile(r'without (a )?permit|expired permit|unpermitted|no permit|work w/o|permit (violation|required)|open permit', re.I)
NOTCASE = re.compile(r'^request|complaint|inquiry|public records|information request|311|lien search|lien letter|^tickets?$|parking|animal', re.I)
def case_flags(txt):
    b = 0
    if NEG.search(txt): b |= 1
    if UNS.search(txt): b |= 2
    if FRG.search(txt): b |= 4
    if BWP.search(txt): b |= 8
    return b
def ms2d(v):
    try: return (dt.datetime(1970, 1, 1) + dt.timedelta(milliseconds=int(v))).date().isoformat() if v not in (None, '') else ''
    except Exception: return ''
def d8(s):
    s = str(s or '').strip()
    return f'{s[:4]}-{s[4:6]}-{s[6:8]}' if re.fullmatch(r'\d{8}', s) and s != '00000000' else ''

STATS = collections.OrderedDict()
PERM = collections.defaultdict(list)    # folio -> [[date, cls, type, src]]
CASE = collections.defaultdict(list)    # folio -> [[opened, status_class(open|closed|lien), status, type, src, no, desc, flags, closed]]
SRCDEF = {}                             # src key -> {city, muni, url, kind}
yearly = collections.defaultdict(collections.Counter)   # (src, kind) -> year -> n  (for the coverage-window estimate)
def stat(src, kind, **k): STATS.setdefault(f'{src}/{kind}', collections.Counter()).update(k)

# ---------------- 1. City of Miami + legacy county aggregate (permits.json) ----------------
MIAMI = {}; COUNTY_OLD = {}
pf = f'{RAW}/permits.json'
if os.path.exists(pf):
    P = json.load(open(pf)); MIAMI = P.get('city', {}); COUNTY_OLD = P.get('county', {})
    SRCDEF['miami'] = {'city': 'Miami', 'muni': '01', 'url': P['sources']['city'], 'kind': 'permit', 'label': 'City of Miami Building_Permits_Since_2014 (ArcGIS FeatureServer)'}
    stat('miami', 'permit', records=sum(v[1] for v in MIAMI.values()), folios=len(MIAMI), matched=sum(v[1] for f, v in MIAMI.items() if f in FOLIOS))

# ---------------- 2. County Building Dept layer + certificates of occupancy ----------------
CNTY_URL = 'https://gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer/1'
CNTY_ST = {'A': 'o', 'E': 'e', 'F': 'f'}
def jload(p):
    try: return json.load(open(p))
    except Exception: return None
L1 = jload(f'{RAW}/permits/county_bp_l1.json')
if L1:
    SRCDEF['county'] = {'city': 'Unincorporated Miami-Dade', 'muni': '30', 'url': CNTY_URL, 'kind': 'permit', 'label': 'Miami-Dade County Building Dept permits (gisweb MD_LandInformation layer 1)'}
    for r in L1['rows']:
        f = re.sub(r'\D', '', r.get('FOLIO') or ''); stat('county', 'permit', records=1)
        if f in FOLIOS: stat('county', 'permit', matched=1)
        else:
            f = addr_folio((r.get('ADDRESS') or '') + ' FL', '30') or ''
            if not f: continue
            stat('county', 'permit', matched_addr=1)
        d = ms2d(r.get('ISSUDATE'))
        if not d: continue
        t = (r.get('DESC1') or '').strip().title() or (r.get('TYPE') or '')
        PERM[f].append([d, CNTY_ST.get(r.get('BPSTATUS'), 'o'), f"{r.get('TYPE') or ''} {t}".strip()[:48], 'county'])
        yearly[('county', 'permit')][d[:4]] += 1
CO = jload(f'{RAW}/permits/county_co.json')
if CO:
    SRCDEF['county_co'] = {'city': 'Unincorporated Miami-Dade', 'muni': '30', 'url': 'https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/certif_of_occupancy_daily_data/FeatureServer/0', 'kind': 'permit', 'label': 'County Certificates of Occupancy 2002-today (AGOL)'}
    for r in CO['rows']:
        f = re.sub(r'\D', '', str(r.get('FOLIO') or '')).zfill(13); stat('county_co', 'permit', records=1)
        if f not in FOLIOS: continue
        stat('county_co', 'permit', matched=1)
        d = str(r.get('ISSUE_DATE') or '')[:10]
        if d: PERM[f].append([d, 'f', 'Certificate of Occupancy', 'county_co'])

# ---------------- 3. EnerGov portals ----------------
import fetch_energov_cfg as ecfg
for slug, (city, muni, base) in ecfg.PORTALS.items():
    SRCDEF[slug] = {'city': city, 'muni': muni, 'url': base.rsplit('/api', 1)[0].replace('/apps/selfservice', '/apps/selfservice') , 'kind': 'energov', 'label': f'{city} Tyler EnerGov self-service portal (public search API)'}
    for kind in ('permit', 'code'):
        fn = f'{RAW}/permits/energov/{slug}_{kind}.jsonl'
        if not os.path.exists(fn): continue
        seen = set()
        for ln in open(fn):
            try: rows = json.loads(ln)['rows']
            except Exception: continue
            for r in rows:
                if r['id'] in seen: continue
                seen.add(r['id']); stat(slug, kind, records=1)
                f = parcel_folio(r['parcel'])
                if f: stat(slug, kind, matched=1)
                else:
                    if r['parcel']: stat(slug, kind, parcel_not_in_roll=1)
                    f = addr_folio(r['addr'], muni) or ''
                    if f: stat(slug, kind, matched_addr=1)
                if kind == 'permit':
                    d = r['apply'] or r['issue']     # apply date: legacy imports stamp the migration day into IssueDate
                    if not d or d < '1950' or d > TODAY.isoformat(): stat(slug, kind, bad_date=1); continue
                    ty = (r['type'] or r['wc'])
                    if not relevant(ty) and not relevant(r['wc']): stat(slug, kind, other_type=1); continue
                    c = pclass(r['st'])
                    if c == 'x': stat(slug, kind, void_cancelled=1); continue
                    yearly[(slug, 'permit')][d[:4]] += 1
                    if f: PERM[f].append([d, c, ty[:48], slug])
                else:
                    d = r['apply']
                    if not d or d < '1950' or d > TODAY.isoformat(): stat(slug, kind, bad_date=1); continue
                    txt = f"{r['type']} {r['wc']} {r['desc']}"
                    if NOTCASE.search(r['type'] or ''): stat(slug, kind, not_a_case=1); continue
                    st = r['st']; sc = 'closed' if RX_RELEASED.search(st) and not re.search(r'lien filed', st, re.I) else 'lien' if RX_LIEN.search(st) else 'closed' if RX_CLOSED.search(st) else 'open'
                    yearly[(slug, 'code')][d[:4]] += 1
                    if f: CASE[f].append([d, sc, st, (r['type'] or '')[:40], slug, r['no'], r['desc'][:160], case_flags(txt), r['final'] or ''])

# ---------------- 4. County code compliance (all cases incl. closed) + building cases ----------------
CC_URL = 'https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/ArcGIS/rest/services/CCVIOL_gdb/FeatureServer/0'
cc = jload(f'{RAW}/viol/cc_all.json')
if cc:
    SRCDEF['county_cc'] = {'city': 'Unincorporated Miami-Dade', 'muni': '30', 'url': CC_URL, 'kind': 'code', 'label': 'Miami-Dade Code Compliance (CCVIOL_gdb, all cases)'}
    liens = {(re.sub(r'\D', '', r['FOLIO'] or ''), r['CASE_NUM']) for nm in ('cc_lien', 'cc_finance') for r in (jload(f'{RAW}/viol/{nm}.json') or {'rows': []})['rows']}
    for r in cc['rows']:
        f = re.sub(r'\D', '', r.get('FOLIO') or ''); stat('county_cc', 'code', records=1)
        if f not in FOLIOS: continue
        stat('county_cc', 'code', matched=1)
        d = ms2d(r.get('CASE_DATE')); stt = (r.get('STAT_DESC') or '').strip()
        if not d: continue
        lien = bool((r.get('LN_RECBOOK') or '').strip()) or (f, r['CASE_NUM']) in liens or bool(RX_LIEN.search(stt))
        sc = 'lien' if lien else 'closed' if RX_CLOSED.search(stt) else 'open'
        desc = (r.get('PROBLEM_DESC') or '').strip()
        yearly[('county_cc', 'code')][d[:4]] += 1
        CASE[f].append([d, sc, stt, desc[:40], 'county_cc', r['CASE_NUM'], '', case_flags(desc), ''])
bo = jload(f'{RAW}/viol/bldg_open.json'); bc = jload(f'{RAW}/viol/bldg_closed5.json')
if bo or bc:
    SRCDEF['county_bv'] = {'city': 'Unincorporated Miami-Dade', 'muni': '30', 'url': 'https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/ArcGIS/rest/services/Open_Building_Violations/FeatureServer/0', 'kind': 'code', 'label': 'Miami-Dade Building Violations (open + closed past 5 yrs)'}
    for nm, V, sc in (('open', bo, 'open'), ('closed', bc, 'closed')):
        for r in (V or {'rows': []})['rows']:
            f = re.sub(r'\D', '', r.get('FOLIO') or ''); stat('county_bv', 'code', records=1)
            if f not in FOLIOS: continue
            stat('county_bv', 'code', matched=1)
            d = ms2d(r.get('OPEN_DATE'))
            if not d: continue
            ty = (r.get('CASE_TYPE') or '').strip()
            fl = 2 if ty == 'Unsafe Structure' else 8 if ty == 'Expired Permit' else 0
            yearly[('county_bv', 'code')][d[:4]] += 1
            CASE[f].append([d, sc, 'Open' if sc == 'open' else 'Closed', ty[:40], 'county_bv', r.get('CASE_NUM') or '', '', fl, ms2d(r.get('CLOSED_DATE'))])

# ---------------- coverage windows ----------------
def window(counter):
    """first year from which the source is complete: every later year holds >= 40% of the median of the last three full years"""
    ys = sorted(int(y) for y in counter if y.isdigit() and 1950 < int(y) <= TODAY.year)
    if not ys: return None, 0
    full = [counter.get(str(y), 0) for y in range(TODAY.year - 3, TODAY.year)]
    ref = sorted(full)[1]
    if ref < 25: return None, ref                       # tiny / brand-new portal: no reliable history
    start = TODAY.year
    for y in range(TODAY.year - 1, ys[0] - 1, -1):
        if counter.get(str(y), 0) >= 0.4 * ref: start = y
        else: break
    return start, ref
COV = {}
def cov_for(slug, kind):
    if (slug, kind) not in yearly: return None
    y, ref = window(yearly[(slug, kind)])
    return {'from': f'{y}-01-01' if y else '', 'ref_per_year': ref, 'records': sum(yearly[(slug, kind)].values())}
munis = {}
for slug, d in SRCDEF.items():
    if d['muni'] not in munis: munis[d['muni']] = {'city': d['city']}
    m = munis[d['muni']]
    for kind in ('permit', 'code'):
        k2 = 'code' if (kind == 'code') else 'permit'
        c = cov_for(slug, 'permit' if kind == 'permit' else 'code')
        if c and (slug != 'county_co') and (d['kind'] == 'energov' or d['kind'] == kind):
            c.update({'src': slug, 'label': d['label'], 'url': d['url'], 'matched': dict(STATS.get(f'{slug}/{kind}', {}))})
            m.setdefault(kind, {})
            if not m[kind] or (c['from'] and (not m[kind].get('from') or c['from'] < m[kind]['from'])): m[kind] = c
if 'miami' in SRCDEF:
    munis.setdefault('01', {'city': 'Miami'})['permit'] = {'src': 'miami', 'label': SRCDEF['miami']['label'], 'url': SRCDEF['miami']['url'], 'from': '2014-01-01', 'records': STATS['miami/permit']['records'], 'ref_per_year': 0}
# county layer is only dense (>=40% of recent volume) for its recent years; unincorporated code history from CCVIOL (since opened-date start)
for m, v in munis.items(): v['permit_from'] = (v.get('permit') or {}).get('from', ''); v['code_from'] = (v.get('code') or {}).get('from', '')

# ---------------- per-folio aggregation ----------------
OUT_P = {}; OUT_C = {}
for f, L in PERM.items():
    L.sort()
    acts = [x for x in L if x[1] in 'oferp']
    if not acts: continue
    last = acts[-1]; five = [x for x in acts if x[0] >= T5]
    exp = [x for x in acts if x[1] == 'e']; rev = [x for x in acts if x[1] == 'r']
    op = [x for x in acts if x[1] in 'o' and x[0] >= T5]
    le = max([x[0] for x in exp + rev], default='')
    OUT_P[f] = [last[0], len(five), len(op), len([x for x in exp if x[0] >= T5]), len([x for x in rev if x[0] >= T5]), le, last[2], last[3], len(acts)]
# City of Miami + legacy county aggregates (no per-permit rows): fold in
for f, v in MIAMI.items():
    if f not in FOLIOS: continue
    n5 = v[5] if len(v) > 5 else 0
    cur = OUT_P.get(f)
    row = [v[0], n5, v[4], 0, 0, v[2], 'City of Miami permit', 'miami', v[1]]
    if v[3] and v[2]: row[3] = v[3] if v[2] >= T5 else 0
    OUT_P[f] = row if not cur else [max(cur[0], row[0])] + [a + b for a, b in zip(cur[1:5], row[1:5])] + [max(cur[5], row[5]), cur[6], cur[7], cur[8] + row[8]]
for f, v in COUNTY_OLD.items():                                    # legacy 2-yr county table: only extends the last-permit date where the layer lacks it
    if f in FOLIOS and v[0]:
        cur = OUT_P.get(f)
        if not cur: OUT_P[f] = [v[0], 1 if v[0] >= T5 else 0, 0, 0, 0, '', 'County building permit', 'county', v[1]]
        elif v[0] > cur[0]: cur[0] = v[0]
for f, L in CASE.items():
    L.sort()
    seen = set(); U = []
    for x in L:
        k = (x[4], x[5])
        if k in seen: continue
        seen.add(k); U.append(x)
    live = [x for x in U if x[1] in ('open', 'lien') and (x[0] >= OPEN_CASE_SINCE or x[1] == 'lien')]
    five = [x for x in U if x[0] >= T5]
    last = U[-1]; fl = 0
    for x in live: fl |= x[7]
    OUT_C[f] = [len(live), len(five), last[0], last[2][:30], last[3], int(any(x[1] == 'lien' for x in U if x[0] >= '2010')), fl, last[4], len(U)]
# open / lien case items for the distress layer
ITEMS = {}
for f, L in CASE.items():
    for x in L:
        if x[1] in ('open', 'lien') and x[4] not in ('county_cc', 'county_bv') and (x[0] >= OPEN_CASE_SINCE or x[1] == 'lien'):
            ITEMS.setdefault(f, []).append([x[1], x[0], x[3], x[2], x[5], x[4], x[6], x[7]])

# ---------------- coverage + match table ----------------
rows = []
for slug, d in SRCDEF.items():
    for kind in ('permit', 'code'):
        s = STATS.get(f'{slug}/{kind}')
        if not s: continue
        rec = s['records']; mt = s['matched'] + s['matched_addr']
        rows.append({'src': slug, 'city': d['city'], 'muni': d['muni'], 'kind': kind, 'records': rec, 'matched_folio': s['matched'], 'matched_address': s['matched_addr'],
                     'match_rate': round(mt / rec, 4) if rec else 0, **{k: v for k, v in s.items() if k not in ('records', 'matched', 'matched_addr')}, 'url': d['url'], 'label': d['label']})
# per municipality: parcels with data / built parcels
cnt_p = collections.Counter(f[:2] for f in OUT_P); cnt_c = collections.Counter(f[:2] for f in OUT_C)
for m, v in munis.items(): v['parcels_with_permit'] = cnt_p.get(m, 0); v['parcels_with_case'] = cnt_c.get(m, 0)
out = {'built': TODAY.isoformat(), 'coverage': munis, 'sources': rows, 'permits': OUT_P, 'cases': OUT_C,
       'stats': {'permit_folios': len(OUT_P), 'case_folios': len(OUT_C), 'open_case_items': sum(len(v) for v in ITEMS.values())}}
json.dump(out, open(f'{RAW}/permit_index.json', 'w'), separators=(',', ':'))
json.dump(ITEMS, open(f'{RAW}/muni_cases.json', 'w'), separators=(',', ':'))
print(json.dumps(out['stats']))
for r in rows: print(r['city'].ljust(18), r['kind'].ljust(7), str(r['records']).rjust(8), 'matched', f"{r['match_rate']:.1%}".rjust(6), f"(folio {r['matched_folio']}, addr {r['matched_address']})")
for m, v in sorted(munis.items()): print(m, v['city'].ljust(26), 'permits from', v.get('permit_from') or '-', 'code from', v.get('code_from') or '-', 'parcels w/ permit', v['parcels_with_permit'], 'w/ case', v['parcels_with_case'])
