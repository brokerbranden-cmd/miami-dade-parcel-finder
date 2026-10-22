#!/usr/bin/env python3
"""Broward foreclosure notices published in newspapers, from Florida Public Notices (floridapublicnotices.com, Florida Press Association
statewide legal-notice database; free, no login, no captcha). The public search page posts
    POST https://floridapublicnotices.com/   Accept: application/hal+json   {"keywords": "...", "counties": [6], "limit": 100, "offset": 0}
(county 6 = Broward). Keywords 'lis pendens', 'notice of action foreclosure', 'foreclosure'; every page is read (offset += 100), notices are
deduped by notice id and then by case number (newest notice kept, all dates listed). Polite: one request every ~2 s, backoff on errors.
These are PUBLISHED notices (Notice of Action = new suit served by publication, Notice of Sale, notice of lis pendens), not the recorded
lis pendens index, so they only cover cases that get advertised. The site keeps roughly the last ~5 weeks.
Output: $RAW/broward/fpn_foreclosure.json {pulled, keywords:{kw: totalCount}, newest, oldest, notices:[{case, date, dates, kind, plaintiff, defendants, address, zip, legal, paper, id}]}"""
import json, os, re, sys, time, requests
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'broward'); os.makedirs(RAW, exist_ok=True)
URL = 'https://floridapublicnotices.com/'; KW = ['lis pendens', 'notice of action foreclosure', 'foreclosure']; LIM = 100; GAP = 2.0
s = requests.Session(); s.headers.update({'Accept': 'application/hal+json', 'Content-Type': 'application/json'}); last = [0.0]
def post(kw, off):
    for i in range(6):
        w = GAP - (time.time() - last[0])
        if w > 0: time.sleep(w)
        try:
            r = s.post(URL, data=json.dumps({'keywords': kw, 'counties': [6], 'limit': LIM, 'offset': off}), timeout=90); last[0] = time.time()
            if r.status_code == 200: return r.json()
            err = r.status_code
        except Exception as e: last[0] = time.time(); err = repr(e)[:100]
        print(f'  retry {i} {kw!r} off {off}: {err}', flush=True); time.sleep(min(300, 15 * 2 ** i))
    raise SystemExit(f'failed {kw} {off}')
CASE = re.compile(r'\b(CACE|COCE|CONO|COSO|COWE|CACV)[\s\-]*(\d{2})[\s\-]*0*(\d{1,6})\b', re.I)
CASEY = re.compile(r'CASE\s*(?:NO\.?|NUMBER|#)\s*:?\s*(?:06[\s\-]*)?(20\d{2}|\d{2})[\s\-]*(CA|CC)[\s\-]*0*(\d{1,6})', re.I)   # 2025-CA-012345 style, Broward = CACE
def find_case(T):
    m = CASE.search(T)
    if m: return f'{m.group(1).upper()}-{m.group(2)}-{m.group(3).zfill(6)}'
    m = CASEY.search(T)
    if m: return f"{'CACE' if m.group(2).upper() == 'CA' else 'COCE'}-{m.group(1)[-2:]}-{m.group(3).zfill(6)}"
    return ''
ZIP = r'(?:FL|FLORIDA)\.?,?\s*(3\d{4})'
SUF = r'(?:STREET|ST|AVENUE|AVE|ROAD|RD|DRIVE|DR|COURT|CT|TERRACE|TER|TERR|PLACE|PL|LANE|LN|BOULEVARD|BLVD|WAY|CIRCLE|CIR|TRAIL|TRL|PARKWAY|PKWY|HIGHWAY|HWY|ROW|RUN|PATH|POINT|PT|ISLE|CAUSEWAY|LOOP|MANOR|COVE|BEND)'
AKA = re.compile(r'(?:property\s+address|street\s+address|common(?:ly\s+known\s+as)?|a/?k/?a|also\s+known\s+as|located\s+at|physical\s+address|address\s+of)\s*:?\s*(\d{1,6}[^\n;]{3,90}?),?\s*([A-Z][A-Za-z .\-]+?),?\s*' + ZIP, re.I | re.S)
GEN = re.compile(r'(\d{1,6}\s+(?:[NSEW]{1,2}\.?\s+)?[^\n,;]{2,50}?\b' + SUF + r'\b\.?(?:[^\n,;]{0,25}?)),\s*([A-Z][A-Za-z .\-]+?),?\s*' + ZIP, re.I)
COURTHOUSE = re.compile(r'^201\s+S\.?\s*E\.?\s+(6TH|SIXTH)', re.I)
def clean(x): return re.sub(r'\s+', ' ', x or '').strip(' ,.;')
def parse(n):
    t = (n.get('notice') or '').replace('&amp;', '&'); T = re.sub(r'[ \t]+', ' ', t); up = T.upper()
    body = re.split(r'ANY PERSON CLAIMING AN INTEREST|IF YOU ARE A PERSON WITH A DISABILITY|Rule 2\.540|AMERICANS WITH DISABILIT', T, maxsplit=1, flags=re.I)[0]
    kind = 'Notice of sale' if re.search(r'NOTICE OF (FORECLOSURE )?SALE|WILL SELL TO THE HIGHEST', up) else 'Notice of action' if 'NOTICE OF ACTION' in up else 'Notice of lis pendens' if 'LIS PENDENS' in up[:1500] else 'Foreclosure notice'
    pl = df = ''
    mm = re.search(r'(?:CASE\s*(?:NO\.?|NUMBER|#)[^\n]*\n|DIVISION[^\n]*\n)(.{3,600}?),?\s*Plaintiffs?\b(.{0,40}?)\b(?:v\.|vs\.?|versus)\s*(.{3,1500}?),?\s*Defendants?', T, re.I | re.S)
    if mm: pl = clean(re.sub(r'^.*?CASE\s*(?:NO\.?|NUMBER|#)\s*:?\s*\S+\s*', '', clean(mm.group(1)), flags=re.I))[:200]; df = clean(mm.group(3))[:400]
    else:
        mm = re.search(r'\bTO:\s*(.{3,300}?)(?:\n\s*\n|YOU ARE (?:HEREBY )?NOTIFIED|whose (?:last known|residence)|LAST KNOWN)', T, re.I | re.S)
        if mm: df = clean(mm.group(1))[:400]
    addr = city = z = ''
    for rx in (AKA, GEN):
        for a in rx.finditer(body):
            if COURTHOUSE.search(a.group(1)) or re.search(r'P\.?\s*O\.?\s*BOX|SUITE|STE\b', a.group(1), re.I): continue
            pre = body[max(0, a.start() - 160):a.start()].upper()
            if rx is GEN and re.search(r'ATTORNEY|ESQ|LAW GROUP|P\.A\.|LLP|PLLC|LAW FIRM|COUNSEL|TELEPHONE|FACSIMILE|LAST KNOWN|RESIDENCE', pre): continue
            addr, city, z = clean(a.group(1)), clean(a.group(2)), a.group(3); break
        if addr: break
    lg = re.search(r'((?:LOT|UNIT|PARCEL|TRACT|APARTMENT|CONDOMINIUM|THE (?:NORTH|SOUTH|EAST|WEST))\s.{10,600}?PUBLIC RECORDS OF BROWARD COUNTY,?\s*FLORIDA)', T, re.I | re.S)
    return {'case': find_case(T), 'date': n.get('date', ''), 'kind': kind, 'plaintiff': pl, 'defendants': df, 'address': addr, 'city': city, 'zip': z,
            'legal': clean(lg.group(1))[:500] if lg else '', 'paper': n.get('paper', ''), 'id': n.get('id'), 'broward': bool(re.search(r'BROWARD COUNTY', up[:600]) or CASE.search(T))}
if __name__ == '__main__':
    raw = {}; tot = {}; RP = os.path.join(RAW, 'fpn_raw.json')
    if '--reparse' in sys.argv: R0 = json.load(open(RP)); raw = {n['id']: n for n in R0['notices']}; tot = R0['keywords']   # parse the last pull again, no requests
    for kw in ([] if '--reparse' in sys.argv else KW):
        off = 0
        while True:
            j = post(kw, off); tot[kw] = j.get('totalCount', 0); ns = (j.get('_embedded') or {}).get('notices') or []
            for n in ns: raw[n['id']] = n
            print(f'{kw!r} offset {off}: {len(ns)} (total {tot[kw]}, unique so far {len(raw)})', flush=True)
            off += LIM
            if not ns or off >= tot[kw]: break
    if '--reparse' not in sys.argv: json.dump({'pulled': time.strftime('%Y-%m-%d %H:%M'), 'keywords': tot, 'notices': list(raw.values())}, open(RP, 'w'))
    by = {}; nocase = []; offtopic = 0
    for n in raw.values():
        up = (n.get('notice') or '').upper()
        if not re.search(r'FORECLOS|LIS PENDENS', up): offtopic += 1; continue   # the keyword search matches any of the words: keep foreclosure / lis pendens notices only
        p = parse(n)
        if not p['broward'] or 'NON-JUDICIAL' in up or 'TIMESHARE' in up: offtopic += 1; continue   # other counties' courts, timeshare claim-of-lien notices
        if not p['case']: nocase.append(p); continue
        o = by.get(p['case'])
        if not o: p['dates'] = [p['date']]; by[p['case']] = p; continue
        o['dates'] = sorted(set(o['dates'] + [p['date']]))
        if p['date'] > o['date'] or (not o['address'] and p['address']):
            for k in ('address', 'city', 'zip', 'legal', 'plaintiff', 'defendants'):
                if p[k] and (p['date'] > o['date'] or not o[k]): o[k] = p[k]
            if p['date'] > o['date']: o['date'] = p['date']; o['kind'] = p['kind']; o['id'] = p['id']
    out = sorted(by.values(), key=lambda x: x['date'], reverse=True); ds = [x['date'] for x in out if x['date']]
    J = {'pulled': time.strftime('%Y-%m-%d %H:%M'), 'source': URL + ' (Florida Press Association public notices, county 6 = Broward)', 'keywords': tot, 'raw_notices': len(raw), 'not_foreclosure': offtopic,
         'no_case_number': len(nocase), 'cases': len(out), 'with_address': sum(1 for x in out if x['address']), 'newest': max(ds) if ds else '', 'oldest': min(ds) if ds else '', 'notices': out}
    json.dump(J, open(os.path.join(RAW, 'fpn_foreclosure.json'), 'w'), separators=(',', ':'))
    print({k: v for k, v in J.items() if k != 'notices'}, flush=True)
