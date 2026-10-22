#!/usr/bin/env python3
"""PoC (not wired): Key West eTRAKiT (CentralSquare) permit + code-case search by date.
Plain HTTP ASP.NET postbacks; no login/captcha needed for public search (2026-10-22).
Findings: every query is capped at 20 result pages (100 case rows / ~400 permit rows) sorted ascending,
so slice narrowly: permits by ISSUED EQUALS <day>; code cases (case.aspx only offers CASE_NO/SITE_ADDR)
by CASE_NO BEGINS WITH 'CC2026-000', 'CC2026-001', ... (100 numbers per prefix). Case rows carry
no status/date; those need a per-case detail postback (not done here).
Usage: poc_monroe_keywest.py permit MM/DD/YYYY [max_pages]   (EQUALS that issue date)
       poc_monroe_keywest.py case CC2026-000 [max_pages]     (BEGINS WITH prefix)"""
import re, sys, time, html, json, requests
BASE = 'https://etrakit.cityofkeywest-fl.gov/etrakit/Search/'
UA = 'Mozilla/5.0 (PropHunters parcel research; Branden@prop-hunters.com)'
DELAY = 3.0  # polite seconds between requests

def hidden(t):
    return {m.group(1): html.unescape(m.group(2)) for m in
            re.finditer(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', t)}

def rows(t):
    out = []
    for tr in re.findall(r'<tr class="rg(?:Alt)?Row".*?</tr>', t, re.S):
        out.append([html.unescape(re.sub(r'<[^>]+>', '', c)).strip() for c in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)])
    return out

def pageinfo(t):
    m = re.search(r'page (\d+) of (\d+)', t); return (int(m.group(1)), int(m.group(2))) if m else (1, 1)

def sweep(kind='permit', since='10/01/2026', max_pages=50):
    S = requests.Session(); S.headers['User-Agent'] = UA
    url = BASE + ('permit.aspx' if kind == 'permit' else 'case.aspx')
    t = S.get(url, timeout=60).text
    datefld, oper = ('Permit_Main.ISSUED', 'EQUALS') if kind == 'permit' else ('Case_Main.CASE_NO', 'BEGINS WITH')
    f = hidden(t); f.update({'ctl00$cplMain$ddSearchBy': datefld, 'ctl00$cplMain$ddSearchOper': oper,
        'ctl00$cplMain$txtSearchString': since, 'ctl00$cplMain$btnSearch': 'Search', 'ctl00$cplMain$activeTab': '0'})
    t = S.post(url, data=f, timeout=90).text
    if 'data-sitekey' in t or 'g-recaptcha' in t: raise SystemExit('captcha shown - stop')
    allrows = rows(t); p, n = pageinfo(t); print(f'{kind} {datefld} {oper} {since}: page {p}/{n}', file=sys.stderr)
    while p < n and p < max_pages:
        time.sleep(DELAY)
        f = hidden(t); f.update({'__EVENTTARGET': 'ctl00$cplMain$rgSearchRslts',
            '__EVENTARGUMENT': 'FireCommand:ctl00$cplMain$rgSearchRslts$ctl00;Page;next',
            'ctl00$cplMain$ddSearchBy': datefld, 'ctl00$cplMain$ddSearchOper': oper,
            'ctl00$cplMain$txtSearchString': since, 'ctl00$cplMain$activeTab': '0'})
        t = S.post(url, data=f, timeout=90).text
        np_, n = pageinfo(t)
        if np_ <= p: print('paging stalled', file=sys.stderr); break
        p = np_; allrows += rows(t)
    return datefld, allrows

if __name__ == '__main__':
    kind = sys.argv[1] if len(sys.argv) > 1 else 'permit'
    since = sys.argv[2] if len(sys.argv) > 2 else '10/01/2026'
    mp = int(sys.argv[3]) if len(sys.argv) > 3 else 50
    fld, r = sweep(kind, since, mp)
    print(json.dumps({'field': fld, 'n': len(r), 'sample': r[:3]}, indent=1))
