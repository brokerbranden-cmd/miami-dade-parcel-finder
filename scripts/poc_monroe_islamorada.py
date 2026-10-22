#!/usr/bin/env python3
"""PoC (not wired): Islamorada CityView Portal (Harris/municipalsoftware) permits + code cases.
Plain HTTP, no login/captcha for public locator (2026-10-22). The locator does a substring search on
application/case number, address, RE#, contact; results come newest-first, 20 per page, as JSON {View: html}.
Searching the year (e.g. '2026') pages through that year's records -> no per-parcel sweep needed.
Usage: poc_monroe_islamorada.py [permit|code] 2026 [max_pages]"""
import re, sys, time, html, json, requests
B = 'https://cvportal.us/CityViewPortal/'
UA = 'Mozilla/5.0 (PropHunters parcel research; Branden@prop-hunters.com)'
DELAY = 3.0

def parse(view):
    out = []
    t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '|', view)))
    t = re.sub(r'(\| ?)+', '|', t)
    for blk in re.split(r'\|(?=Application Number:|Case Number:)', t)[1:]:
        f = blk.split('|'); d = {}
        for i, x in enumerate(f[:-1]):
            if x.endswith(':') and x[:-1] in ('Application Number', 'Case Number', 'Permit Type', 'Type', 'Status'):
                d[x[:-1]] = f[i + 1].strip()
        if 'Locations:' in f:
            i = f.index('Locations:'); d['address'] = f[i + 1].strip()
            if i + 2 < len(f) and re.match(r'\d{8}-\d{6}$', f[i + 2].strip()): d['re'] = f[i + 2].strip()
        out.append(d)
    return out

def sweep(kind='permit', term='2026', max_pages=5):
    mod, cat = ('Permit', '') if kind == 'permit' else ('CodeEnforcement', 'CE')
    S = requests.Session(); S.headers['User-Agent'] = UA
    S.get(B + f'{mod}/Locator' + (f'?category={cat}' if cat else ''), timeout=60)
    allr, seen = [], set()
    for pg in range(max_pages):
        if pg: time.sleep(DELAY)
        j = S.get(B + f'{mod}/LocatorResults', params={'searchValue': term, 'category': cat, 'pageNumber': pg,
                  'appealPeriodStatusesOnly': 'False', 'isInspectionSearch': 'False'},
                  headers={'X-Requested-With': 'XMLHttpRequest'}, timeout=90).json()
        rows = [r for r in parse(j.get('View') or '') if (r.get('Application Number') or r.get('Case Number')) not in seen]
        if not rows: break
        for r in rows: seen.add(r.get('Application Number') or r.get('Case Number'))
        allr += rows
    return allr

if __name__ == '__main__':
    kind = sys.argv[1] if len(sys.argv) > 1 else 'permit'
    r = sweep(kind, sys.argv[2] if len(sys.argv) > 2 else '2026', int(sys.argv[3]) if len(sys.argv) > 3 else 3)
    print(json.dumps({'n': len(r), 'sample': r[:3]}, indent=1))
