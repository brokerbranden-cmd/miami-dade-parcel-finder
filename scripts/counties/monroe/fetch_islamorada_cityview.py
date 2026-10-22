#!/usr/bin/env python3
"""Islamorada CityView Portal (cvportal.us/CityViewPortal) permits + code cases -> $RAW/monroe/islamorada.json (built on scripts/poc_monroe_islamorada.py).
Public locator, no login / captcha. Searching a year ('2026') pages through that year's records newest first, 20 per page; 3 s between requests.
Rows: number, type, status, address, RE number. The list has no dates, so the year comes from the record number (e.g. CEWST20260000381).
usage: fetch_islamorada_cityview.py [--years 2025,2026] [--max-pages 400]"""
import os, re, sys, json, time, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
import poc_monroe_islamorada as I
OUT = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe', 'islamorada.json')
def opt(n, d): return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d
YEARS = opt('--years', f'{dt.date.today().year - 1},{dt.date.today().year}').split(','); MAXP = int(opt('--max-pages', '400'))
res = {'pulled': time.strftime('%Y-%m-%d %H:%M'), 'source': I.B, 'permits': [], 'code': []}
for kind, key in (('permit', 'permits'), ('code', 'code')):
    for y in YEARS:
        for i in range(3):
            try: rows = I.sweep(kind, y, MAXP); break
            except Exception as e: print('retry', kind, y, e, flush=True); time.sleep(60 * (i + 1))
        else: raise SystemExit(f'failed {kind} {y}')
        for r in rows:
            no = r.get('Application Number') or r.get('Case Number') or ''
            m = re.search(r'(20\d{2})', no); r['year'] = int(m.group(1)) if m else int(y); r['no'] = no
        rows = [r for r in rows if str(r['year']) == y]   # substring search also hits other years' addresses / numbers
        res[key] += rows; print(kind, y, len(rows), flush=True)
json.dump(res, open(OUT, 'w')); print({k: len(v) for k, v in res.items() if isinstance(v, list)})
