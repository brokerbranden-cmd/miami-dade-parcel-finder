"""Broward permits / code cases -> per-parcel columns for build_broward.py (Fort Lauderdale ArcGIS permits + EnerGov portals of Pembroke Pines,
Sunrise, Oakland Park, Miramar). Records join to the roll by the 12-character BCPA folio (EnerGov MainParcel / FTL PARCELID).
Distress permit types (the same idea as Miami-Dade's unsafe-structure / building-violation signals): demolition, unsafe structure,
roof (re-roof / roof repair), fire / storm / water damage repair, structural repair, board-up, 40/50-year recertification repairs.
A distress permit counts when it was applied for in the last 24 months. Code cases count when opened in the last 5 years; an open case
(status not closed / complied / void ...) is flagged separately. Closed-status / neglect / unsafe regexes mirror scripts/merge_permits.py."""
import json, os, re, glob, collections, datetime as dt
DPERM = re.compile(r'demol|wreck|unsafe|condemn|dangerous|\broof|re-?roof|reroof|fire (damage|repair|restor)|storm damage|hurricane (damage|repair)|water damage|flood damage|structural (repair|damage)|board(ed)?[- ]?up|recertif|40[- ]?y(ea)?r|50[- ]?y(ea)?r|milestone', re.I)
NOTP = re.compile(r'void|cancel|denied|withdraw|abandon|rejected|duplicate|invalid', re.I)
RX_CLOSED = re.compile(r'pass|close|complied|compliance|resolved|void|invalid|cancel|dismiss|withdraw|unfounded|no violation|abated|paid|satisfied|final|complete|duplicate|unsubstantiated|inactive|superseded|rescind', re.I)
NEG = re.compile(r'junk|trash|overgrow|debris|abandon|vacant|unsecur|structure maint|minimum hous|housing|property maint|exterior|sanitation|lot clear|weed|grass|nuisance|dilapidat|board(ed)?\b|pool|swimming|infest|sewage|rubbish|garbage|blight|unkempt|derelict|mainten', re.I)
UNS = re.compile(r'unsafe|dangerous|condemn|demolition order', re.I)
NOTCASE = re.compile(r'^request|complaint|inquiry|public records|information request|311|lien search|lien letter|^tickets?$|parking|animal', re.I)
CITY = {'pembroke_pines': 'Pembroke Pines', 'sunrise': 'Sunrise', 'oakland_park': 'Oakland Park', 'miramar': 'Miramar', 'fort_lauderdale': 'Fort Lauderdale'}
def fol(p): return re.sub(r'[^0-9A-Za-z]', '', str(p or '')).upper()

def load(rawb, today=None):
    """-> perm {folio: {'last': iso, 'n5': int, 'dist': [(date, city, no, type, desc, status)]}}, code {folio: [(date, city, no, type, status, open, flags)]}, stats"""
    today = today or dt.date.today(); y5 = (today - dt.timedelta(days=1826)).isoformat(); m24 = (today - dt.timedelta(days=730)).isoformat(); td = today.isoformat()
    perm = collections.defaultdict(lambda: {'last': '', 'n5': 0, 'dist': []}); code = collections.defaultdict(list)
    st = {'by_city': {}, 'newest': {}}
    for fn in sorted(glob.glob(os.path.join(rawb, 'permits', 'energov', '*_*.jsonl'))):
        slug, kind = os.path.basename(fn)[:-6].rsplit('_', 1); city = CITY.get(slug, slug); seen = set()
        c = st['by_city'].setdefault(city, collections.Counter()); hi = ''
        for ln in open(fn):
            try: w = json.loads(ln)
            except Exception: continue
            for r in w['rows']:
                if r['id'] in seen: continue
                seen.add(r['id']); f = fol(r.get('parcel')); d = r.get('apply') or r.get('issue') or ''
                if d > td: d = ''
                if d: hi = max(hi, d)
                c[kind + '_rows'] += 1
                if len(f) != 12: c[kind + '_no_folio'] += 1; continue
                c[kind + '_with_folio'] += 1
                txt = ' '.join((r.get('type', ''), r.get('wc', ''), r.get('desc', '')))
                if kind == 'permit':
                    p = perm[f]; p['last'] = max(p['last'], d); p['n5'] += d >= y5
                    if d >= m24 and DPERM.search(r.get('type', '') + ' ' + r.get('wc', '')) and not NOTP.search(r.get('st', '')):
                        p['dist'].append((d, city, r['no'], (r.get('type') or '') + (' / ' + r['wc'] if r.get('wc') else ''), (r.get('desc') or '')[:90], r.get('st', ''))); c['permit_distress_24m'] += 1
                else:
                    if NOTCASE.search(r.get('type', '')) or d < y5: continue
                    op = not RX_CLOSED.search(r.get('st', '')); fl = (1 if NEG.search(txt) else 0) | (2 if UNS.search(txt) else 0)
                    code[f].append((d, city, r['no'], r.get('type', '') or 'Code case', r.get('st', ''), op, fl)); c['code_5y'] += 1; c['code_open'] += op
        st['newest'][f'{city} {kind}'] = hi
    ftl = os.path.join(rawb, 'permits', 'fort_lauderdale.json')
    if os.path.exists(ftl):
        J = json.load(open(ftl)); c = st['by_city'].setdefault('Fort Lauderdale', collections.Counter()); st['newest']['Fort Lauderdale permit'] = J.get('data_through', '')
        for f, v in J['parcels'].items():
            f = fol(f); p = perm[f]; p['last'] = max(p['last'], v[0]); p['n5'] += v[2]; c['permit_parcels'] += 1
            for d, no, ty, desc, s in (J.get('distress', {}).get(f) or []):
                if d >= m24 and not NOTP.search(s or ''): p['dist'].append((d, 'Fort Lauderdale', no, ty, desc, s)); c['permit_distress_24m'] += 1
    st['by_city'] = {k: dict(v) for k, v in st['by_city'].items()}
    return dict(perm), dict(code), st
