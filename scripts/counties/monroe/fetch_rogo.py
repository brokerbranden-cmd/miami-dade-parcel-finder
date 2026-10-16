#!/usr/bin/env python3
"""ROGO / NROGO allocation ranking lists (Monroe County Planning & Environmental Resources, public PDFs) -> $RAW/monroe/rogo.json
Downloads the quarterly + year-end result PDFs linked from https://www.monroecounty-fl.gov/186/ROGONROGO-System, parses each ranked row
(rank, '*' = ranking sufficient for an allocation award, '@' = subject to further review, permit #, applicant, key, subdivision, lot, block, RE#, tier).
Needs pdftotext (poppler-utils). Rows are matched to parcels by RE# (8 digits - 6 digits = the last 14 digits of the roll PARCEL_ID)."""
import os, re, json, subprocess, sys, urllib.request, ssl
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe'); D = os.path.join(RAW, 'rogo_pdf'); os.makedirs(D, exist_ok=True)
BASE = 'https://www.monroecounty-fl.gov'; UA = {'User-Agent': 'Mozilla/5.0 parcel-finder/1.0'}
def get(u): return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=120).read()
html = get(BASE + '/186/ROGONROGO-System').decode('utf8', 'ignore')
docs, cur = [], ''
for m in re.finditer(r'<h3[^>]*>(.*?)</h3>|<a [^>]*href="(/documentview\.aspx\?did=(\d+))"[^>]*>([^<]*)', html, re.S):
    if m.group(1) is not None: cur = re.sub(r'<[^>]+>|&[a-z#0-9]+;', ' ', m.group(1)).strip(); continue
    t = m.group(4).strip()
    if re.search(r'Year \d+', t) and re.search(r'ROGO', cur + t): docs.append({'did': m.group(3), 'sec': cur, 'title': t, 'kind': 'NROGO' if 'NROGO' in cur else 'ROGO'})
print(len(docs), 'result documents')
RE = re.compile(r'(\d{7,8})\s*[-\u2010\u2011\u2012\u2013]\s*(\d{4,7})')
rows = []
for d in docs:
    pdf = f"{D}/{d['kind']}_{d['did']}.pdf"
    if not os.path.exists(pdf): open(pdf, 'wb').write(get(BASE + f"/documentview.aspx?did={d['did']}"))
    txt = subprocess.run(['pdftotext', '-layout', pdf, '-'], capture_output=True, text=True).stdout
    area = cat = ''; yr = q = 0
    for ln in txt.splitlines():
        u = ln.upper()
        h = re.search(r'(LOWER AND UPPER|UPPER AND LOWER|LOWER|UPPER|BIG PINE/NO NAME|BIG PINE|NO NAME)[A-Z ]*[:\-,]*\s*YEAR\s*(\d+)\s*,?\s*QUARTER\s*(\d)', u)
        if h: area, yr, q = h.group(1).title(), int(h.group(2)), int(h.group(3))
        if 'AFFORDABLE DWELLING' in u or 'AFFORDABLE HOUSING' in u: cat = 'affordable'
        elif 'MARKET RATE' in u and 'DWELLING' in u: cat = 'market'
        elif 'ADMINISTRATIVE RELIEF' in u: cat = 'admin relief'
        if d['kind'] == 'NROGO': cat = 'nonresidential'
        m = re.match(r'^\s*(\d{1,4})\s+(\*?@?)\s*([A-Z0-9][\w\u2010\u2011-]{4,})\s{2,}(\S.*?)\s{2,}(\d{1,2}[-/][A-Za-z0-9]{1,3}[-/]\d{2,4})\s+\d', ln)
        r = RE.search(ln)
        if not (m and r): continue
        rest = ln[r.end():]; tier = re.search(r'\b(3-?A|[123])\b', rest)
        rows.append({'kind': d['kind'], 'did': d['did'], 'year': yr, 'q': q, 'area': area, 'cat': cat, 'rank': int(m.group(1)), 'award': '*' in m.group(2), 'review': '@' in m.group(2),
                     'permit': m.group(3).replace('\u2010', '-').replace('\u2011', '-'), 'name': re.sub(r'\s+', ' ', m.group(4)), 'date': m.group(5),
                     're': r.group(1).zfill(8) + '-' + r.group(2).ljust(6, '0')[:6], 'tier': tier.group(1) if tier else ''})
json.dump(rows, open(os.path.join(RAW, 'rogo.json'), 'w'))
import collections
print(len(rows), 'rows; by year/q award:', collections.Counter((r['year'], r['q'], r['award']) for r in rows if r['year'] >= 33))
