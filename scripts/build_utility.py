#!/usr/bin/env python3
"""'Power / water cut' layer, built the same way for every county (Miami-Dade, Broward, Monroe; counties never mixed).
  python3 scripts/build_utility.py miami-dade|broward|monroe      -> data/<dir>/utility.json.gz
Signals, most accurate first (bit, code):
  1 'list'  Utility shutoff list: a utility's own list of service addresses shut off / disconnected (public-records request, Fla. ch. 119).
            Drop CSV / XLSX into $RAW/utility_shutoffs/<county>/ (optional sidecar <file>.meta.json: source, city, kind, sheet, address_col, date_col;
            unmatched rows -> <county>/unmatched/<file>_unmatched.csv) (any column names containing 'address' (service address), optional
            'city' / 'zip', a date column ('shut', 'disconnect' or 'date'), optional 'service' / 'type' and 'utility'); rows are matched to
            parcels by normalized street address (+ zip when given). Last 12 months count. Empty / missing folder = no list signal yet.
  2 'case'  Code case that says the property has no water / water shut off / utilities off or disconnected / no power or electricity
            (precise phrases only; generic 'electrical' violations do not count). Opened in the last 36 months, open or closed.
  4 'rc'    Permit in the last 24 months for an electrical / power reconnect (safety check for reconnection), FPL / power release,
            meter release / set, or water meter reconnect (A/C, appliance, sink, gas ... reconnects excluded; void / cancelled excluded).
  8 'uv'    Weaker: open unsafe-structure case, or open vacant / abandoned / boarded-up code case.
File: {v, county, built, counts:{list,case,rc,uv,any}, by_source, sources, notes, rows:{folio:[bits, best_code, date, label, source]}}"""
import os, sys, json, gzip, glob, re, csv, struct, collections, datetime as dt
C = sys.argv[1]; REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'); RAW = os.environ.get('RAW', '/workspace/raw')
DD = {'miami-dade': 'data/', 'broward': 'data/broward/', 'monroe': 'data/monroe/'}[C]; DATA = os.path.join(REPO, DD)
TODAY = dt.date.fromisoformat(os.environ['UT_TODAY']) if os.environ.get('UT_TODAY') else dt.date.today()
C36 = (TODAY - dt.timedelta(days=1096)).isoformat(); C24 = (TODAY - dt.timedelta(days=730)).isoformat(); C12 = (TODAY - dt.timedelta(days=366)).isoformat(); TD = TODAY.isoformat()

CASE_RX = re.compile(r"\bno (running )?water\b|\bwater (service )?(is |was |has been )?(shut ?off|shut-off|turned off|disconnected|terminated|cut off)"
    r"|\bwithout (running )?(water|power|electric(ity)?|utilities)\b|\bno (electric(ity)?|power|utilities|utility service)\b(?! ?wash)"
    r"|\butilit(y|ies)( service)? (are |is |were |was |have been )?(off|disconnected|shut ?off|terminated|turned off|cut off)"
    r"|\b(power|electricity|electric service) (is |was |has been )?(off|shut ?off|disconnected|turned off|cut off)\b|\bdisconnected (lights|utilit)"
    r"|\black of (water|utilities|electric|power)\b|\bshut ?off (of )?(the )?(water|power|electric|utilit)|\bliving without water meter", re.I)
CASE_FALSE = re.compile(r"pergola|gazebo|\bshed\b|carport|without (a )?permit[^.]{0,30}\(no electric|no water (leak|intrusion|damage)|power ?wash", re.I)
WATER = re.compile(r'water', re.I); POWER = re.compile(r'power|electric|light|fpl', re.I)
P_WMETER = re.compile(r"water meter (re-?connect|restor|re-?install|re-?set|turn[- ]?on)|re-?connect (the )?water (meter|service)", re.I)
P_FPL = re.compile(r"\bfpl (release|reconnect|re-connect)|\bpower release\b|\brelease (of |for |to )?(power|electric(al)?( service)?|fpl)\b|\b(release|reconnect) (to|for) fpl\b", re.I)
P_METER = re.compile(r"\b(electric(al)? )?meter (release|set|reset|re-?set|re-?install|re-?connect)\b|\b(commercial|residential) meter release|re-?energiz", re.I)
P_RECON = re.compile(r"re-?connect(ion)?\b|safety check", re.I)
P_ECTX = re.compile(r"electric|power|meter|fpl|service|panel|safety check", re.I)
P_EXCL = re.compile(r"\ba/?c\b|hvac|mechanical|\bduct|sink|toilet|\bgas\b|appliance|water heater|generator|\bpool|pump|slurpee|dryer|washer|fixture|receptacle|\blights?\b|\bsign\b|motor|equipment|elevator|chiller|condenser|air handler|sprinkler|irrigation|sewer|plumbing", re.I)
P_NOT = re.compile(r'void|cancel|denied|withdraw|abandon|rejected|duplicate|invalid|revoked|not issued', re.I)
CASE_NOT = re.compile(r'invalid|duplicate|unfounded|void|cancel|withdraw|no violation|unsubstantiated|error', re.I)
CLOSED = re.compile(r'pass|close|complied|compliance|resolved|void|invalid|cancel|dismiss|withdraw|unfounded|no violation|abated|paid|satisfied|final|complete|duplicate|unsubstantiated|inactive|superseded|rescind', re.I)
UV_RX = re.compile(r"unsafe|condemn|dangerous (building|structure)|demolition order|\bvacant (building|structure|property|house|home|dwelling|unit)|abandon(ed)? (property|building|structure|house|home)|boarded|board(ed)?[- ]?up|unsecured (structure|building|property)", re.I)
SRC_NAME = {}

def ms(v):
    try: return dt.datetime.fromtimestamp(v / 1000, dt.timezone.utc).date().isoformat() if v else ''
    except Exception: return ''
def d10(s):
    s = str(s or '').strip()
    if re.match(r'^\d{4}-\d\d-\d\d', s): return s[:10]
    for f in ('%B %d, %Y', '%m/%d/%Y', '%m/%d/%y', '%Y%m%d', '%m-%d-%Y', '%b %d, %Y'):
        try: return dt.datetime.strptime(s[:20].strip(), f).date().isoformat()
        except Exception: pass
    if re.fullmatch(r'\d{4}', s): return s + '-01-01'
    return ''

def read_pack(path, cols):
    b = gzip.decompress(open(path, 'rb').read()); hl = struct.unpack('<I', b[:4])[0]; h = json.loads(b[4:4 + hl]); base = 4 + hl; out = {'n': h['n']}
    import numpy as np
    for c in h['cols']:
        if c['name'] not in cols: continue
        raw = b[base + c['offset']: base + c['offset'] + c['bytes']]
        out[c['name']] = np.frombuffer(raw, dtype=c['type']) if c['type'] != 'str' else raw.decode('utf-8').split('\n')
    return out
meta = json.load(open(os.path.join(DATA, 'meta.json'))); ZIPD = (meta.get('dicts') or {}).get('zip') or []
FOL = []; ADDR = []; ZIP = []; CITY = []; CITYD = (meta.get('dicts') or {}).get('city') or []
for name in ('main', 'condo'):
    p = os.path.join(DATA, name + '.bin.gz')
    if not os.path.exists(p): continue
    k = read_pack(p, {'folio', 'addr', 'zip', 'city'}); FOL += k['folio'][:k['n']]; ADDR += k['addr'][:k['n']]
    CITY += [str(CITYD[z]) if z < len(CITYD) else '' for z in k['city'][:k['n']]] if 'city' in k else [''] * k['n']
    ZIP += [str(ZIPD[z]) if z < len(ZIPD) else '' for z in k['zip'][:k['n']]] if 'zip' in k else [''] * k['n']
FSET = set(FOL)
def key_md(f): f = re.sub(r'\D', '', str(f or '')); return f if len(f) == 13 else None
def key_br(f): f = re.sub(r'[^0-9A-Za-z]', '', str(f or '')).upper(); return f if len(f) == 12 else None
MO_RE = {}
if C == 'monroe':
    for f in FOL: MO_RE.setdefault(f[-14:], f)
def key_mo(f): d = re.sub(r'\D', '', str(f or '')); return MO_RE.get(d[-14:]) if len(d) >= 14 else None
KEY = {'miami-dade': key_md, 'broward': key_br, 'monroe': key_mo}[C]

# ---------- address index (for shutoff lists) ----------
SUF = {'STREET': 'ST', 'AVENUE': 'AVE', 'AV': 'AVE', 'ROAD': 'RD', 'DRIVE': 'DR', 'COURT': 'CT', 'PLACE': 'PL', 'TERRACE': 'TER', 'TERR': 'TER', 'BOULEVARD': 'BLVD',
       'LANE': 'LN', 'CIRCLE': 'CIR', 'HIGHWAY': 'HWY', 'PARKWAY': 'PKWY', 'WAY': 'WAY', 'NORTH': 'N', 'SOUTH': 'S', 'EAST': 'E', 'WEST': 'W', 'NORTHWEST': 'NW',
       'NORTHEAST': 'NE', 'SOUTHWEST': 'SW', 'SOUTHEAST': 'SE', 'APARTMENT': 'APT', 'UNIT': 'UNIT', '#': 'UNIT', 'TRAIL': 'TRL', 'CAUSEWAY': 'CSWY'}
def norm_addr(a):
    a = re.sub(r'[^A-Z0-9# ]', ' ', str(a or '').upper()); a = a.replace('#', ' # ')
    w = [SUF.get(x, x) for x in a.split()]
    w = [re.sub(r'^(\d+)(ST|ND|RD|TH)$', r'\1', x) for x in w]
    return ' '.join(w)
def street_only(n): return re.sub(r'\s+(APT|UNIT|STE|SUITE|BLDG|#)\s*\S+$', '', n)
AIDX = {}
def addr_index(city=None):
    # city (optional, from the list's sidecar <file>.meta.json): only parcels in that city (pack 'city' column) are candidates
    k = (city or '').upper()
    if k not in AIDX:
        ix = AIDX[k] = collections.defaultdict(list)
        for f, a, z, c in zip(FOL, ADDR, ZIP, CITY or [''] * len(FOL)):
            if not a or (k and c.upper() != k): continue
            n = norm_addr(a); ix[n].append((f, z))
            s = street_only(n)
            if s != n: ix['S:' + s].append((f, z))
    return AIDX[k]
def read_rows(fn):
    # CSV or XLSX (first sheet, or meta 'sheet'); header names are stripped (city exports carry trailing spaces)
    if fn.lower().endswith('.xlsx'):
        import openpyxl
        wb = openpyxl.load_workbook(fn, read_only=True, data_only=True); m = list_meta(fn)
        ws = wb[m['sheet']] if m.get('sheet') in wb.sheetnames else wb.worksheets[0]; it = ws.iter_rows(values_only=True)
        hd = [str(h or '').strip() for h in next(it, [])]
        rows = [{h: ('' if v is None else v.date().isoformat() if hasattr(v, 'date') else str(v)) for h, v in zip(hd, r)} for r in it if any(v is not None for v in r)]
        return hd, rows
    with open(fn, newline='', encoding='utf-8-sig', errors='replace') as fh:
        rd = csv.DictReader(fh); rows = [{(k or '').strip(): v for k, v in r.items()} for r in rd]
        return [(h or '').strip() for h in (rd.fieldnames or [])], rows
def list_meta(fn):
    p = os.path.splitext(fn)[0] + '.meta.json'
    return json.load(open(p)) if os.path.exists(p) else {}

# ---------- collect ----------
best = {}   # folio -> dict(bits, code, date, label, src)
RANK = {1: 4, 2: 3, 4: 2, 8: 1}
cnt = collections.Counter(); bysrc = collections.Counter(); notes = []; sources = []
def add(f, bit, date, label, src):
    if not f or f not in FSET: return
    b = best.get(f)
    if b is None: b = best[f] = {'bits': 0, 'code': 0, 'date': '', 'label': '', 'src': ''}
    if not b['bits'] & bit: bysrc[(bit, src)] += 1
    b['bits'] |= bit
    if RANK[bit] > RANK.get(b['code'], 0) or (bit == b['code'] and date > b['date']): b.update(code=bit, date=date, label=label, src=src)
def case_label(t):
    w, pw = bool(re.search(r'water', t, re.I)), bool(POWER.search(t))
    if re.search(r'utilit', t, re.I) or (w and pw): return 'No water / power'
    return 'No water' if w else 'No power'
def do_case(f, date, text, status, src):
    if not date or date < C36 or date > TD or CASE_NOT.search(status or ''): return
    m = CASE_RX.search(text)
    if not m or CASE_FALSE.search(text): return
    add(f, 2, date, case_label(m.group(0)) + (' (open)' if not CLOSED.search(status or '') else ''), src)
def perm_label(t):
    if P_WMETER.search(t): return 'Water meter reconnected'
    if P_EXCL.search(t): return None
    if P_FPL.search(t): return 'FPL / power release'
    if P_METER.search(t) and not re.search(r'\bgas\b', t, re.I): return 'Meter release / set'
    if P_RECON.search(t) and P_ECTX.search(t) and re.search(r'electric|power|meter|fpl|reconnect', t, re.I): return 'Power reconnected'
    return None
def do_perm(f, date, text, status, src):
    if not date or date < C24 or date > TD or P_NOT.search(status or ''): return
    l = perm_label(text)
    if l: add(f, 4, date, l, src)
def do_uv(f, date, text, status, src, is_open=None):
    op = (not CLOSED.search(status or '')) if is_open is None else is_open
    if not op or CASE_NOT.search(status or '') or not UV_RX.search(text): return
    l = 'Unsafe structure' if re.search(r'unsafe|condemn|dangerous|demolition', text, re.I) else 'Vacant / boarded'
    add(f, 8, date or '', l + ' (open case)', src)
def energov(base, label_of):
    for fn in sorted(glob.glob(os.path.join(base, '*_*.jsonl'))):
        slug, kind = os.path.basename(fn)[:-6].rsplit('_', 1); src = label_of(slug) + (' permits' if kind == 'permit' else ' code cases'); seen = set(); n = 0
        for ln in open(fn):
            try: w = json.loads(ln)
            except Exception: continue
            for r in w.get('rows') or []:
                if r.get('id') in seen: continue
                seen.add(r.get('id')); n += 1; f = KEY(r.get('parcel')); d = d10(r.get('apply') or r.get('issue'))
                t = ' | '.join(str(r.get(k) or '') for k in ('type', 'wc', 'desc')); s = r.get('st', '')
                if kind == 'permit': do_perm(f, d, t, s, src)
                else: do_case(f, d, t, s, src); do_uv(f, d, t, s, src)
        if n: sources.append(f'{src} (Tyler EnerGov, {n:,} records)')
nice = lambda s: {'nmb': 'North Miami Beach', 'north_bay': 'North Bay Village'}.get(s, s.replace('_', ' ').title())

if C == 'miami-dade':
    V = f'{RAW}/viol'
    for nm in ('cc_all', 'cc_open', 'cc_lien'):
        p = f'{V}/{nm}.json'
        if not os.path.exists(p): continue
        for r in json.load(open(p))['rows']:
            f = KEY(r.get('FOLIO')); d = ms(r.get('CASE_DATE')); t = (r.get('PROBLEM_DESC') or '') + ' | ' + (r.get('LAST_ACTV') or ''); s = (r.get('STAT_DESC') or '').strip()
            do_case(f, d, t, s, 'County code compliance')
            if nm == 'cc_open' and re.search(r'Abandoned Property|vacant', r.get('PROBLEM_DESC') or '', re.I): add(f, 8, d, 'Vacant / abandoned (open case)', 'County code compliance')
    sources.append('Miami-Dade County code compliance cases (ArcGIS)')
    for nm in ('bldg_all', 'bldg_open'):
        p = f'{V}/{nm}.json'
        if not os.path.exists(p): continue
        for r in json.load(open(p))['rows']:
            if r.get('CASE_TYPE') == 'Unsafe Structure' and not r.get('CLOSED_DATE'): add(KEY(r.get('FOLIO')), 8, ms(r.get('OPEN_DATE')), 'Unsafe structure (open case)', 'County building cases')
    sources.append('Miami-Dade County building / unsafe-structure cases (ArcGIS)')
    p = f'{RAW}/permits/county_bp_l1.json'
    if os.path.exists(p):
        for r in json.load(open(p))['rows']:
            do_perm(KEY(r.get('FOLIO')), ms(r.get('ISSUDATE')), (r.get('TYPE') or '') + ' ' + (r.get('DESC1') or ''), r.get('BPSTATUS') or '', 'County building permits')
        sources.append('Miami-Dade County Building Dept permits (unincorporated)')
    p = f'{RAW}/muni_cases.json'
    if os.path.exists(p):
        for f, v in json.load(open(p)).items():
            for c in v:
                src = nice(c[5]) + ' code cases'; t = ' | '.join(str(x or '') for x in (c[2], c[3], c[6])); st = 'open' if c[0] in ('open', 'lien') else 'closed'
                do_case(KEY(f), d10(c[1]), t, c[3] if st == 'closed' else '', src); do_uv(KEY(f), d10(c[1]), t, '', src, is_open=(st == 'open'))
    energov(f'{RAW}/permits/energov', nice)
    notes.append('City of Miami permits are only published as per-parcel dates (no work descriptions), so City of Miami reconnect permits cannot be detected; '
                 'municipalities without a public permit / code source (see COVERAGE.md) have no permit or case signal.')
elif C == 'broward':
    energov(f'{RAW}/broward/permits/energov', nice)
    notes.append('Broward permits / code cases come from Pembroke Pines, Sunrise, Oakland Park and Miramar (EnerGov; Miramar has no public code cases). '
                 'Fort Lauderdale permits are stored as distress-type summaries only (no reconnect detail) and the other Broward cities publish no bulk permit / code data, so they have no permit / case signal.')
elif C == 'monroe':
    M = f'{RAW}/monroe'
    def kwc(path, src):
        if not os.path.exists(path): return
        for c in json.load(open(path))['cases'].values():
            t = ' | '.join(str(x or '') for x in (c.get('type'), c.get('subtype'), c.get('name'), ' '.join(c.get('violations') or []), c.get('last_action')))
            f = KEY(c.get('re')); d = d10(c.get('opened')); s = c.get('status', '')
            do_case(f, d, t, s, src); do_uv(f, d, t, s, src, is_open=not c.get('closed') and not CLOSED.search(s))
    kwc(f'{M}/kw_cases.json', 'Key West code cases'); kwc(f'{M}/keywest/cases.json', 'Key West code cases'); sources.append('City of Key West eTRAKiT code cases and permits')
    p = f'{M}/kw_permits.json'
    if os.path.exists(p):
        for c in json.load(open(p))['permits'].values(): do_perm(KEY(c.get('re')), d10(c.get('issued')), ' | '.join(str(c.get(k) or '') for k in ('type', 'subtype', 'desc')), c.get('status', ''), 'Key West permits')
    p = f'{M}/isl_cityview.json'
    if os.path.exists(p):
        J = json.load(open(p))
        for c in J['permits'].values(): do_perm(KEY(c.get('re')), d10(c.get('issued') or c.get('applied')), ' | '.join(str(c.get(k) or '') for k in ('type', 'category', 'desc')), c.get('status', ''), 'Islamorada permits')
        for c in J['cases'].values():
            f = KEY(c.get('re')); d = d10(c.get('open_year')); t = str(c.get('type') or '') + ' | ' + str(c.get('desc') or ''); do_case(f, d, t, c.get('status', ''), 'Islamorada code cases'); do_uv(f, d, t, c.get('status', ''), 'Islamorada code cases')
        sources.append('Village of Islamorada CityView permits and code cases')
    p = f'{M}/marathon_code.json'
    if os.path.exists(p):
        for c in json.load(open(p)):
            if c.get('withdrawn'): continue
            f = KEY(c.get('re')); d = d10(c.get('date')); do_case(f, d, c.get('violation') or '', '', 'Marathon code cases'); do_uv(f, d, c.get('violation') or '', '', 'Marathon code cases')
        sources.append('City of Marathon Special Magistrate code agendas')
    p = f'{M}/mce_permits.jsonl'
    if os.path.exists(p):
        for ln in open(p):
            c = json.loads(ln); do_perm(KEY(c.get('parcel_id')), d10(c.get('apply_date')), str(c.get('permit_type')) + ' | ' + str(c.get('permit_desc')), c.get('status') or '', 'Monroe County permits')
    notes.append('Unincorporated Monroe permits / code cases only exist publicly up to 2022 / 2024 (MCeSearch), so the 24-month reconnect and 36-month case windows find little there; '
                 'Marathon only publishes hearing agendas; Key Colony Beach and Layton publish nothing.')

# ---------- utility shutoff lists (top accuracy) ----------
UD = os.path.join(RAW, 'utility_shutoffs', C); lists = []
UNM_DIR = os.environ.get('UT_UNMATCHED') or os.path.join(UD, 'unmatched')
for fn in sorted(glob.glob(os.path.join(UD, '*.csv')) + glob.glob(os.path.join(UD, '*.xlsx'))):
    # optional sidecar <file>.meta.json: {"source": label, "city": pack city, "kind": water|power, "date_col", "address_col", "sheet"}
    nrow = nmatch = nold = 0; m = list_meta(fn); unm = []
    hd, rows = read_rows(fn); low = {h: h.lower() for h in hd}
    pick = lambda *keys, excl=(): next((h for h in hd if any(k in low[h] for k in keys) and not any(x in low[h] for x in excl)), None)
    ca = m.get('address_col') or pick('service address', 'service_address', 'svc addr', 'premise') or pick('address', 'addr', 'location', excl=('mail', 'billing', 'email'))
    cz = pick('zip'); cd = m.get('date_col') or pick('shut', 'disconnect', 'cut', 'off date', 'complete') or pick('date'); cs = pick('service', 'type', excl=('address', 'addr', 'date')); cu = pick('utility', 'provider')
    if not ca: notes.append(f'{os.path.basename(fn)}: no address column found ({hd[:8]})'); continue
    idx = addr_index(m.get('city')); util = m.get('source') or re.sub(r'[_-]+', ' ', os.path.splitext(os.path.basename(fn))[0])
    for r in rows:
        nrow += 1; n = norm_addr(r.get(ca)); z = re.sub(r'\D', '', str(r.get(cz) or ''))[:5] if cz else ''
        d = d10(r.get(cd)) if cd else ''
        if d and d < C12: nold += 1; continue
        hits = idx.get(n) or idx.get('S:' + n) or idx.get('S:' + street_only(n)) or []
        mu = re.match(r'^(.* (?:ST|AVE|RD|DR|CT|PL|TER|BLVD|LN|CIR|HWY|PKWY|WAY|TRL|MNR|CIRCLE)) ([A-Z]|\d{1,3})$', n)
        if not hits and mu:   # trailing unit / building token without APT/UNIT ('3991 WOODSIDE DR B', '11000 NW 44 ST W'): base street address, max 4 parcels
            hits = idx.get(mu.group(1)) or idx.get('S:' + mu.group(1)) or []
            if len({h[0] for h in hits}) > 4: hits = []
        if z: hits = [h for h in hits if not h[1] or h[1] == z] or []
        fs = sorted({h[0] for h in hits})
        if not fs or len(fs) > 50: unm.append({'address': r.get(ca), 'normalized': n, 'date': d, 'reason': 'no parcel at this address' if not fs else f'{len(fs)} parcels'}); continue
        nmatch += 1; sv = (r.get(cs) or '').strip() if cs else ''
        kind = m.get('kind') or ('water' if re.search(r'water|sewer|wasd|aqueduct', sv + ' ' + util, re.I) else 'power' if re.search(r'power|electric|energy', sv + ' ' + util, re.I) else 'service')
        lab = {'water': 'Water shut off', 'power': 'Power shut off', 'service': 'Service shut off'}[kind]
        src = m.get('source') or ('Utility shutoff list: ' + ((r.get(cu) or '').strip() if cu else util))
        for f in fs: add(f, 1, d, lab, src)
    if unm and not os.environ.get('UT_OUT'):
        os.makedirs(UNM_DIR, exist_ok=True); up = os.path.join(UNM_DIR, os.path.splitext(os.path.basename(fn))[0] + '_unmatched.csv')
        with open(up, 'w', newline='') as fh: w = csv.DictWriter(fh, ['address', 'normalized', 'date', 'reason']); w.writeheader(); w.writerows(unm)
    lists.append({'file': os.path.basename(fn), 'source': util, 'rows': nrow, 'matched': nmatch, 'unmatched': len(unm), 'older': nold})
    sources.insert(0, f'{util}: {os.path.basename(fn)} ({nrow:,} rows, {nmatch:,} matched)')
    print(f'LIST {os.path.basename(fn)} rows={nrow} matched_rows={nmatch} unmatched={len(unm)} older_than_12m={nold}', file=sys.stderr)
if not lists: notes.insert(0, f'No utility shutoff list on file yet for this county (drop CSVs in raw/utility_shutoffs/{C}/).')

for b in best.values():
    for bit, k in ((1, 'list'), (2, 'case'), (4, 'rc'), (8, 'uv')):
        if b['bits'] & bit: cnt[k] += 1
cnt['any'] = len(best)
out = {'v': 1, 'county': C, 'built': TD, 'packVer': meta.get('ver'), 'counts': {k: cnt.get(k, 0) for k in ('any', 'list', 'case', 'rc', 'uv')},
       'by_source': {f'{bit}|{src}': n for (bit, src), n in sorted(bysrc.items())}, 'lists': lists, 'sources': sources, 'notes': notes,
       'windows': {'case_from': C36, 'permit_from': C24, 'list_from': C12},
       'rows': {f: [b['bits'], b['code'], b['date'], b['label'], b['src']] for f, b in sorted(best.items())}}
p = os.environ.get('UT_OUT') or os.path.join(DATA, 'utility.json.gz')
with gzip.open(p, 'wt', encoding='utf-8', compresslevel=9) as fh: json.dump(out, fh, separators=(',', ':'))
print(C, json.dumps(out['counts']), 'bytes', os.path.getsize(p)); print(json.dumps(out['by_source'], indent=0)); print('\n'.join(notes))
