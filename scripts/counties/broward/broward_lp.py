"""Broward recorded lis pendens + certificates of title from Broward Official Records (AcclaimWeb) browser CSV exports.
Files: raw/broward/lp_downloads/LP_*.csv and CET_*.csv (cols DirectName, IndirectName, RecordDate, DocTypeDescription, InstrumentNumber,
BookType, BookPage, DocLegalDescription, Consideration, CaseNumber). No address / parcel id, so documents are matched to the Broward roll by
  1. legal description (subdivision + plat book-page + lot / block, or condo name + unit) vs the roll's S_LEGAL, then confirmed by owner name, and
  2. defendant name (IndirectName, 'LAST,FIRST M') vs roll owner names (OWN_NAME 'LAST,FIRST M & CO-OWNER').
Confidence: high = legal + name agree, or name (with middle initial / full entity name) unique in the county and agreeing with an HOA plaintiff's
subdivision; medium = full name (last + first) unique in the county; anything else (common name, several parcels, no name) stays unmatched.
Broward-only: never reads or writes Miami-Dade / Monroe files."""
import csv, glob, os, re, collections, datetime as dt

ENT = re.compile(r'\b(LLC|L L C|INC|CORP|CORPORATION|COMPANY|CO|LTD|LP|LLP|TRUST|TR|TRUSTEE|ASSN|ASSOCIATION|BANK|HOLDINGS|PROPERTIES|INVESTMENTS|GROUP|FUND|PA|PLLC|ESTATE|EST)\b')
SKIP = {'JR', 'SR', 'II', 'III', 'IV', 'H/E', 'HE', 'TR', 'TRUSTEE', 'EST', 'ESTATE', 'OF', 'THE', 'LE', 'REM', 'ET', 'AL', 'ETAL', 'UNKNOWN'}
HOA = re.compile(r'\b(ASSN|ASSOCIATION|HOMEOWNERS|CONDOMINIUM|CONDO|HOA|MASTER|COMMUNITY|CLUB|VILLAS|TOWNHOMES)\b')
LENDER = re.compile(r'\b(BANK|MORTGAGE|LOAN|LENDING|SERVICING|SAVINGS|FINANCIAL|CREDIT|TRUST COMPANY|FUND|NEWREZ|PENNYMAC|NATIONSTAR|FREEDOM|ROCKET|CARRINGTON|LAKEVIEW|FEDERAL NATIONAL|FANNIE|FREDDIE|HOME LOAN|CAPITAL|INSURANCE|SECRETARY OF HOUSING|MIDFIRST|SHELLPOINT)\b')
GOV = re.compile(r'\b(TOWN|CITY|COUNTY|STATE OF|VILLAGE|DISTRICT)\b')

def norm(s): return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9,&/ ]', ' ', str(s or '').upper())).strip()
def is_entity(s): return bool(ENT.search(norm(s).replace(',', ' ')))
def ent_key(s):
    w = [t for t in re.sub(r'[^A-Z0-9 ]', ' ', norm(s)).split() if t not in ('THE', 'A', 'AN', 'OF')]
    w = [{'L L C': 'LLC', 'CORPORATION': 'CORP', 'COMPANY': 'CO', 'ASSOCIATION': 'ASSN', 'INCORPORATED': 'INC'}.get(t, t) for t in w]
    return ' '.join(w)

def persons(own):
    """roll OWN_NAME 'LEITE,KARLUCIO G & ALINE' -> [('LEITE','KARLUCIO','G'), ('LEITE','ALINE','')]; entities -> []"""
    own = norm(own)
    if not own or is_entity(own) and ',' not in own: return []
    out, last = [], ''
    for part in [p.strip() for p in own.split('&')]:
        if ',' in part: last, rest = [x.strip() for x in part.split(',', 1)]
        elif last: rest = part
        else: continue
        w = [t for t in rest.replace('/', ' ').split() if t not in SKIP]
        if last and w: out.append((last.replace(' ', ''), w[0], w[1][0] if len(w) > 1 else ''))
    return out

def defendant(name):
    """LP IndirectName 'MCMILLAN,PHILIP' / 'GAYLE,JOYCE JOSEPHINE' -> ('P', last, first, mi) or ('E', entity key) or None"""
    s = norm(name)
    if not s: return None
    if ',' in s and not is_entity(s.split(',', 1)[0]):
        last, rest = [x.strip() for x in s.split(',', 1)]; w = [t for t in rest.split() if t not in SKIP]
        if not last or not w or len(last) < 2: return None
        return ('P', last.replace(' ', ''), w[0], w[1][0] if len(w) > 1 else '')
    return ('E', ent_key(s)) if is_entity(s) else None

PLAT = re.compile(r'\b(\d{1,3})-(\d{1,3})\s*B\b')
def legal_key(legal):
    """'CORAL GATE SECTION TEN 161-8 B LOT 5 BLK 3' -> (subdivision words, 'pb-pg', lot, blk, unit)"""
    s = norm(legal).replace(',', ' ')
    m = PLAT.search(s); plat = f'{m.group(1)}-{m.group(2)}' if m else ''
    sub = s[:m.start()].strip() if m else re.split(r'\b(CONDO|CONDOMINIUM|UNIT|LOT|BLK|BLOCK|POR|PER)\b', s)[0].strip()
    g = lambda pat: (re.search(pat, s) or [None, ''])[1]
    return sub, plat, g(r'\bLOT\s+([0-9A-Z]+)\b'), g(r'\b(?:BLK|BLOCK)\s+([0-9A-Z]+)\b'), g(r'\bUNIT\s+([0-9A-Z\-]+)\b')

def kind(plaintiff, case):
    p = norm(plaintiff)
    if HOA.search(p) and not LENDER.search(p): return 'H', 'HOA/condo lien foreclosure'
    if LENDER.search(p): return 'M', 'Mortgage foreclosure'
    if GOV.search(p): return 'G', 'Government lien / code foreclosure'
    return 'O', 'Other lis pendens'

def read_csvs(d, prefix):
    rows, seen = [], set()
    for f in sorted(glob.glob(os.path.join(d, prefix + '_*.csv'))):
        for r in csv.DictReader(open(f, encoding='utf-8-sig', newline='')):
            k = r.get('InstrumentNumber') or (r.get('CaseNumber'), r.get('IndirectName'))
            if k in seen: continue
            seen.add(k); rows.append({k2: (v or '').strip() for k2, v in r.items()})
    return rows

class Roll:
    def __init__(self, owners, legals):
        self.own = [norm(o) for o in owners]; self.legal = [norm(l).replace(',', ' ') for l in legals]
        self.p_lf, self.ent = collections.defaultdict(set), collections.defaultdict(set)
        self.pers = []
        for i, o in enumerate(self.own):
            ps = persons(o); self.pers.append(ps)
            for last, first, mi in ps: self.p_lf[(last, first)].add(i)
            if is_entity(o) and ',' not in o: self.ent[ent_key(o)].add(i)
        self.plat = collections.defaultdict(set)
        for i, l in enumerate(self.legal):
            m = PLAT.search(l)
            if m: self.plat[f'{m.group(1)}-{m.group(2)}'].add(i)

    def name_cands(self, d):
        if not d: return set(), False
        if d[0] == 'E': return set(self.ent.get(d[1], ())), True
        _, last, first, mi = d; c = set(self.p_lf.get((last, first), ()))
        if mi:
            c0 = c; c = {i for i in c if any(p[0] == last and p[1] == first and p[2] in ('', mi) for p in self.pers[i])}
            if c and c != c0 and not any(p[0] == last and p[1] == first and p[2] == mi for i in c for p in self.pers[i]): c = c0   # only a conflicting initial and bare names left: stays ambiguous
        strong = bool(mi) and all(any(p[0] == last and p[1] == first and p[2] == mi for p in self.pers[i]) for i in c)
        return c, strong

    def legal_cands(self, legal):
        sub, plat, lot, blk, unit = legal_key(legal)
        c = set()
        if plat: c = set(self.plat.get(plat, ()))
        elif sub and len(sub) >= 8: c = {i for i, l in enumerate(self.legal) if l.startswith(sub[:30])}
        if lot: c = {i for i in c if re.search(r'\bLOT\s+' + re.escape(lot) + r'\b', self.legal[i])} or (set() if plat else c)
        if blk: c = {i for i in c if re.search(r'\b(?:BLK|BLOCK)\s+' + re.escape(blk) + r'\b', self.legal[i])} or c
        if unit: c = {i for i in c if re.search(r'\b(?:UNIT|U)\s*' + re.escape(unit) + r'\b', self.legal[i])} or set()
        return c

def match(doc, roll, use_name=True):
    """-> (row index or None, confidence 'high'/'medium'/None, how)"""
    d = defendant(doc.get('IndirectName')) if use_name else None
    nc, strong = roll.name_cands(d)
    lg = doc.get('DocLegalDescription', '')
    if lg:
        lc = roll.legal_cands(lg)
        both = lc & nc
        if len(both) == 1: return next(iter(both)), 'high', 'legal+name'
        if len(lc) == 1 and not use_name: return next(iter(lc)), 'medium', 'legal only (unique)'
        if len(lc) == 1 and use_name: return None, None, 'legal unique but owner name differs'   # legal and name point at different parcels: do not guess
        if len(lc) > 1 and not nc: return None, None, f'legal ambiguous ({len(lc)} parcels; roll legal has no lot / unit)'
        if not use_name: return None, None, 'legal not on roll'
    if not use_name: return None, None, 'no legal description'
    if not d: return None, None, 'no usable defendant name'
    if not nc: return None, None, 'name not on roll'
    if len(nc) > 1:   # HOA plaintiff: its community name in the parcel legal can single one out
        k, _ = kind(doc.get('DirectName'), doc.get('CaseNumber'))
        if k == 'H':
            w = [t for t in re.sub(r'[^A-Z ]', ' ', norm(doc.get('DirectName'))).split() if len(t) > 3 and not HOA.search(t) and t not in ('INC', 'HOMES', 'ASSN')]
            hit = {i for i in nc if w and sum(t in roll.legal[i] for t in w) >= max(1, len(w) - 1)}
            if len(hit) == 1: return next(iter(hit)), 'high', 'name+HOA community in legal'
        return None, None, f'name ambiguous ({len(nc)} parcels)'
    i = next(iter(nc))
    return i, ('high' if strong or d[0] == 'E' and len(d[1]) > 12 else 'medium'), 'name unique in county'

def run(d, owners, legals, today=None):
    """match every LP / CET export in d against the roll -> (lp_hits {i: [doc...]}, cet_hits {i: [doc...]}, stats, unmatched rows)"""
    roll = Roll(owners, legals); today = today or dt.date.today()
    lp, cet = read_csvs(d, 'LP'), read_csvs(d, 'CET')
    st = {'lp_docs': len(lp), 'cet_docs': len(cet), 'files': len(glob.glob(os.path.join(d, '*.csv'))), 'lp_with_legal': sum(1 for r in lp if r.get('DocLegalDescription')),
          'matched_high': 0, 'matched_medium': 0, 'unmatched': 0, 'how': collections.Counter(), 'kind': collections.Counter(), 'cet_matched': 0, 'recorded_from': '', 'recorded_to': '',
          'source': 'Broward County Official Records (AcclaimWeb, officialrecords.broward.org) - Lis Pendens / Certificate of Title browser exports'}
    lp_hits, cet_hits, unmatched = collections.defaultdict(list), collections.defaultdict(list), []
    dates = []
    for r in lp:
        try: rd = dt.datetime.strptime(r['RecordDate'].split()[0], '%m/%d/%Y').date()
        except Exception: rd = None
        r['_date'] = rd.isoformat() if rd else ''; dates.append(r['_date'])
        r['_kind'] = kind(r.get('DirectName'), r.get('CaseNumber')); st['kind'][r['_kind'][1]] += 1
        i, conf, how = match(r, roll); st['how'][how] += 1
        if i is None: st['unmatched'] += 1; unmatched.append({**{k: v for k, v in r.items() if not k.startswith('_')}, 'reason': how}); continue
        r['_conf'] = conf; st['matched_' + conf] += 1; lp_hits[i].append(r)
    for r in cet:   # buyer at sale is in IndirectName, so match by legal only (unique)
        i, conf, how = match(r, roll, use_name=False)
        st['how']['CET ' + how] += 1
        if i is not None: st['cet_matched'] += 1; r['_conf'] = conf; cet_hits[i].append(r)
    ds = sorted(x for x in dates if x); st['recorded_from'], st['recorded_to'] = (ds[0], ds[-1]) if ds else ('', '')
    st['matched'] = st['matched_high'] + st['matched_medium']; st['how'] = dict(st['how']); st['kind'] = dict(st['kind'])
    # a certificate of title on the same case closes the lis pendens (sale held)
    closed = 0
    for i, cs in cet_hits.items():
        cases = {c.get('CaseNumber') for c in cs}
        if i in lp_hits:
            keep = [r for r in lp_hits[i] if r.get('CaseNumber') not in cases]; closed += len(lp_hits[i]) - len(keep)
            if keep: lp_hits[i] = keep
            else: del lp_hits[i]
    st['closed_by_cet'] = closed; st['parcels'] = len(lp_hits)
    return dict(lp_hits), dict(cet_hits), st, unmatched

def text(r): return f"{r['_date']} Lis pendens recorded ({r['_kind'][1]}), case {r.get('CaseNumber') or '-'}, instrument {r.get('InstrumentNumber')}, plaintiff {r.get('DirectName', '')[:60]}; match {r['_conf']}"
