"""Key West (eTRAKiT) + Islamorada (CityView) permits and code cases, joined to Monroe parcels by RE number.
Inputs ($RAW/monroe): kw_permits.json, kw_cases.json (fetch_keywest_etrakit.py), isl_cityview.json (fetch_islamorada_cityview.py), kcb_records.json (load_kcb_records.py, Key Colony Beach Ch. 119 export).
load(RAW) -> {re: {'permits': [...], 'cases': [...]}} with normalised rows:
  permit: {src, no, date (ISO or None), year, type, status, open (bool), expired (bool), desc}
  case:   {src, no, date (ISO open date, or None = only the year is known), year, type, status, open, closed, kind ('US'|'NG'|'')}
Status words follow the portals' own vocab; 'open' = not finaled / closed / void / expired."""
import os, re, json, collections
P_DONE = re.compile(r'FINAL|COMPLET|CLOS|VOID|WITHDR|CANCEL|DENIED|ABANDON|REVOK|EXPIR|INACTIVE|NULL', re.I)
P_EXP = re.compile(r'EXPIR|REVOK|ABANDON', re.I)
C_DONE = re.compile(r'CLOS|COMPLIAN|COMPLIED|VOID|DISMISS|WITHDR|CANCEL|REMEDIED|NO VIOLATION|UNFOUNDED|COMPLIANT|RESOLVED|PAID', re.I)
UNSAFE = re.compile(r'UNSAFE|DANGEROUS|CONDEMN', re.I)
NEGLECT = re.compile(r'OVERGROW|WEED|JUNK|TRASH|RUBBISH|WASTE|DEBRIS|ABANDON|MAINTEN|MINIMUM HOUSING|UNSECURED|POOL MAINT|DERELICT|VACANT|BLIGHT|PROPERTY ISSUE|SANITATION', re.I)
def _y(no):
    m = re.search(r'(20\d\d)', no or ''); return int(m.group(1)) if m else None
def load(RAW):
    out = collections.defaultdict(lambda: {'permits': [], 'cases': []}); st = collections.Counter(); newest = {}
    J = lambda f: json.load(open(os.path.join(RAW, f))) if os.path.exists(os.path.join(RAW, f)) else None
    kp = J('kw_permits.json'); kc = J('kw_cases.json'); isl = J('isl_cityview.json')
    if kp:
        for p in kp.get('permits', {}).values():
            st['kw_permits'] += 1
            if not p.get('re'): continue
            st['kw_permits_re'] += 1; s = p.get('status', '')
            out[p['re']]['permits'].append({'src': 'Key West', 'no': p['no'], 'date': p.get('issued'), 'year': _y(p.get('issued')) or _y(p['no']), 'type': ' '.join(x for x in (p.get('type'), p.get('subtype')) if x), 'status': s,
                                            'open': not P_DONE.search(s), 'expired': bool(P_EXP.search(s)), 'desc': ''})
        newest['kw_permit'] = kp.get('newest')
    if kc:
        for c in kc.get('cases', {}).values():
            st['kw_cases'] += 1
            if not c.get('re'): continue
            st['kw_cases_re'] += 1; s = c.get('status', ''); t = ' '.join(x for x in (c.get('type'), c.get('subtype'), ' '.join(c.get('violations') or [])) if x)
            op = not c.get('closed') and not C_DONE.search(s)
            out[c['re']]['cases'].append({'src': 'Key West', 'no': c['no'], 'date': c.get('opened'), 'year': _y(c.get('opened')) or _y(c['no']), 'type': c.get('type', ''), 'status': s, 'open': op, 'closed': c.get('closed'),
                                          'kind': 'US' if UNSAFE.search(t) else 'NG' if NEGLECT.search(t) else '', 'viol': (c.get('violations') or [''])[0]})
        newest['kw_case'] = kc.get('newest')
    if isl:
        for p in isl.get('permits', {}).values():
            st['isl_permits'] += 1
            if not p.get('re'): continue
            st['isl_permits_re'] += 1; s = p.get('status', ''); d = p.get('issued') or p.get('applied')
            if d: st['isl_permits_dated'] += 1
            out[p['re']]['permits'].append({'src': 'Islamorada', 'no': p['no'], 'date': d, 'year': _y(d) or _y(p['no']), 'type': ' '.join(x for x in (p.get('type'), p.get('category')) if x), 'status': s,
                                            'open': not P_DONE.search(s), 'expired': bool(P_EXP.search(s)), 'desc': p.get('desc', '')})
        for c in isl.get('cases', {}).values():
            st['isl_cases'] += 1
            if not c.get('re'): continue
            st['isl_cases_re'] += 1; s = c.get('status', ''); t = c.get('type', '')
            out[c['re']]['cases'].append({'src': 'Islamorada', 'no': c['no'], 'date': None, 'year': c.get('open_year') or _y(c['no']), 'type': t, 'status': s, 'open': not C_DONE.search(s), 'closed': None,
                                          'kind': 'US' if UNSAFE.search(t) else 'NG' if NEGLECT.search(t) else '', 'viol': ''})
        newest['isl'] = isl.get('newest')
    kcb = J('kcb_records.json')
    if kcb:   # Key Colony Beach: Citizenserve exports sent on request (statuses Closed / Issued / Expired / Canceled; cases Open / Closed, types Code Enforcement / Violation / Warning / Lien)
        for p in kcb.get('permits', []):
            st['kcb_permits'] += 1
            if not p.get('re'): continue
            st['kcb_permits_re'] += 1; s = p.get('status', '')
            out[p['re']]['permits'].append({'src': 'Key Colony Beach', 'no': p['no'], 'date': p.get('issued'), 'year': _y(p.get('issued')), 'type': ' '.join(x for x in (p.get('subtype'),) if x) or p.get('type', ''), 'status': s,
                                            'open': not P_DONE.search(s), 'expired': bool(P_EXP.search(s)), 'desc': p.get('desc', '')})
        for c in kcb.get('cases', []):
            st['kcb_cases'] += 1
            if not c.get('re'): continue
            st['kcb_cases_re'] += 1; s = c.get('status', ''); t = (c.get('type', '') + ' ' + c.get('desc', '')).strip()
            out[c['re']]['cases'].append({'src': 'Key Colony Beach', 'no': c['no'], 'date': c.get('opened'), 'year': _y(c.get('opened')), 'type': c.get('type', ''), 'status': s, 'open': s.strip().lower() == 'open', 'closed': c.get('closed'),
                                          'kind': 'US' if UNSAFE.search(t) else 'NG' if NEGLECT.search(t) else '', 'viol': c.get('desc', '')})
        newest['kcb'] = kcb.get('newest')
    return out, dict(st), newest
