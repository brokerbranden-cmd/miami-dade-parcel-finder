#!/usr/bin/env python3
"""Monroe County MCeSearch (https://mcesearch.monroecounty-fl.gov, public, no login) bulk pull -> $RAW/monroe/mce_permits.jsonl, mce_code.jsonl.
Legacy county permit records (applied before 2022-10-01) and code-compliance cases (opened before 2024-01-01), UNINCORPORATED Monroe only (cities run their own systems).
Uses the portal's own DataTables JSON endpoints by month window. TLS: the county host serves an incomplete chain -> verify off for this host only (read-only public data).
Newer permits/cases live in Oracle OPAL 'Explore Your County' (no bulk export) -> not available."""
import os, re, json, sys, time, datetime as dt, requests, urllib3
urllib3.disable_warnings()
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe'); os.makedirs(RAW, exist_ok=True)
S = requests.Session(); S.verify = False; S.headers['User-Agent'] = 'Mozilla/5.0 (parcel-finder public records research)'
B = 'https://mcesearch.monroecounty-fl.gov'
def csrf(page):
    for i in range(8):
        try: return re.search(r'name="csrf-token" content="([^"]+)"', S.get(B + page, timeout=60).text).group(1)
        except Exception as ex: print('csrf retry', str(ex)[:80]); time.sleep(5 * (i + 1))
    raise RuntimeError('mcesearch unreachable')
def pull(kind, start, end):
    page, api, df, dt_ = ('/search/permits', '/api/search/permit', 'apply_from', 'apply_to') if kind == 'permits' else ('/search/code-compliance', '/api/search/code', 'from', 'to')
    out = os.path.join(RAW, f'mce_{kind if kind == "permits" else "code"}.jsonl'); done = os.path.join(RAW, f'.mce_{kind}_done')
    seen = set(open(done).read().split()) if os.path.exists(done) else set()
    tok = csrf(page); m = start
    with open(out, 'a') as fh:
        while m <= end:
            nxt = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1); e = nxt - dt.timedelta(days=1); key = m.strftime('%Y-%m')
            if key in seen: m = nxt; continue
            rows, off = [], 0
            while True:
                p = {'draw': 1, 'start': off, 'length': 1000, 'order[0][column]': 0, 'order[0][dir]': 'asc', 'columns[0][data]': 'permit_no' if kind == 'permits' else 'case_no'}
                if kind == 'permits': p.update({'apply_from': m.strftime('%m/%d/%Y'), 'apply_to': e.strftime('%m/%d/%Y'), 'type': '', 'permit': '', 're': '', 'address': '', 'status': '', 'issued_from': '', 'issued_to': '', 'co_from': '', 'co_to': ''})
                else: p.update({'from': m.strftime('%m/%d/%Y'), 'to': e.strftime('%m/%d/%Y'), 'case_no': '', 'owner': '', 'address': '', 're': '', 'inspector': ''})
                for i in range(4):
                    try:
                        r = S.get(B + api, params=p, headers={'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-TOKEN': tok}, timeout=120); j = r.json(); break
                    except Exception as ex: print('retry', key, str(ex)[:80]); time.sleep(5); tok = csrf(page)
                d = j.get('data') or []; rows += d
                if len(rows) >= int(j.get('recordsFiltered') or 0) or not d: break
                off += len(d)
            for d in rows: fh.write(json.dumps({k: (v.strip() if isinstance(v, str) else v) for k, v in d.items()}) + '\n')
            fh.flush(); open(done, 'a').write(key + '\n'); print(kind, key, len(rows), flush=True); m = nxt; time.sleep(float(os.environ.get("MCE_SLEEP", "1.2")))
if __name__ == '__main__':
    kinds = sys.argv[1:] or ['permits', 'code']
    if 'permits' in kinds: pull('permits', dt.date(1998, 1, 1), dt.date(2022, 12, 1))
    if 'code' in kinds: pull('code', dt.date(1998, 1, 1), dt.date(2024, 1, 1))
