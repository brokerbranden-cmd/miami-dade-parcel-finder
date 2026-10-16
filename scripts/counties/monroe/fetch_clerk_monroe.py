#!/usr/bin/env python3
"""Monroe Clerk of Courts public case search (https://cr.monroe-clerk.com/Attorney/SearchCriteria, no login, no captcha) -> $RAW/monroe/clerk_cases.json
Foreclosure (civil) and probate cases filed in the last N months (monthly windows, case-type filtered): case #, style (plaintiff vs defendants / In re Estate of), type, status, filed date.
The site shows NO property address or parcel; build_monroe_signals.py ties defendants / decedents to roll owners by exact-name logic (precision first).
Not available here: Official Records (LandmarkWeb) lis pendens search is reCAPTCHA-gated -> not scraped."""
import os, re, json, sys, time, datetime as dt, requests
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe'); OUT = os.path.join(RAW, 'clerk_cases.json')
MONTHS = int(sys.argv[1]) if len(sys.argv) > 1 else 36
B = 'https://cr.monroe-clerk.com/Attorney/'; s = requests.Session(); s.headers['User-Agent'] = 'Mozilla/5.0 (parcel-finder public records research)'
def form(ct):
    h = s.get(B + f'SearchCriteria?caseType={ct}', timeout=60).text
    return re.search(r'name="__RequestVerificationToken" type="hidden" value="([^"]+)"', h).group(1), re.findall(r'<option[^>]*value="(\d+)">([^<]*)</option>', h)
def search(group, types, d1, d2):
    tok, _ = form(group)
    s.post(B + 'SearchCriteria', timeout=60, data=[('__RequestVerificationToken', tok), ('CaseTypeGroup', group), ('FirstName', ''), ('MiddleName', ''), ('LastName', ''), ('BusinessName', ''),
        ('CaseNumber', ''), ('DateFrom', d1), ('DateTo', d2)] + [('CaseTypes', v) for v in types])
    out, page = [], 1
    while True:
        for i in range(3):
            try:
                j = s.post(B + 'ReadCaseList', data={'page': page, 'pageSize': 500}, headers={'X-Requested-With': 'XMLHttpRequest'}, timeout=90).json(); break
            except Exception as e: print('retry', e); time.sleep(4)
        d = j.get('Data') or []; out += d
        if len(out) >= (j.get('Total') or 0) or not d: break
        page += 1
    return out, (j.get('Total') or 0)
_, cv = form('CV'); _, pr = form('PR')
fc = [v for v, n in cv if re.search(r'foreclos|tax deed|quiet title', n, re.I) and 'DO NOT USE' not in n]
pc = [v for v, n in pr]
print('foreclosure types', len(fc), 'probate types', len(pc))
today = dt.date.today(); res = {}
for kind, group, types in (('foreclosure', 'CV', fc), ('probate', 'PR', pc)):
    m = (today.replace(day=1) - dt.timedelta(days=30 * MONTHS)).replace(day=1)
    while m <= today:
        e = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1); e = min(e, today)
        rows, tot = search(group, types, m.strftime('%m/%d/%Y'), e.strftime('%m/%d/%Y'))
        for r in rows:
            f = r.get('DtFile'); ms = re.search(r'\d+', f or ''); d = dt.datetime.utcfromtimestamp(int(ms.group()) / 1000 + 43200).strftime('%Y-%m-%d') if ms else ''
            res[(kind, r['CaseNbr'])] = {'kind': kind, 'case': r['CaseNbr'], 'filed': d, 'style': r['Style'], 'type': r['CaseType'], 'status': r['CaseStatus'], 'div': r.get('Division', '')}
        print(kind, m.strftime('%Y-%m'), len(rows), 'of', tot, flush=True)
        if tot > 500: print('WARN window truncated at 500', kind, m)
        m = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1); time.sleep(0.5)
json.dump({'fetched': dt.datetime.now().isoformat(timespec='seconds'), 'months': MONTHS, 'cases': list(res.values())}, open(OUT, 'w'))
print('total', len(res))
