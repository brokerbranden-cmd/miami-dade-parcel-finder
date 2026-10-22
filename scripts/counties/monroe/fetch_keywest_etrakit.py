#!/usr/bin/env python3
"""Key West eTRAKiT (CentralSquare) permits + code cases -> $RAW/monroe/keywest/ (built on scripts/poc_monroe_keywest.py; MONROE_GAP_PLAN.md).
Public search, no login; the page loads a reCAPTCHA script but never challenges search (stop if a challenge appears). 3 s between requests.
Every query is capped at 20 result pages, so slices stay narrow:
  permits: ISSUED EQUALS <day> for each day (cached per day; days older than 21 days are not re-pulled) -> permits.json
  cases:   CASE_NO BEGINS WITH CC<YYYY>-0NN (100 numbers per prefix, 5 rows per page); each row is opened with the grid RowClick postback
           to read type, status, opened / closed dates and PARCEL ID (= RE number). Closed cases are cached; open / new ones are re-read each run.
usage: fetch_keywest_etrakit.py [--days 400] [--years 2025,2026] [--minutes 240]"""
import os, re, sys, json, time, html, datetime as dt, requests
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
import poc_monroe_keywest as K
OUT = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe', 'keywest'); os.makedirs(OUT, exist_ok=True)
def opt(n, d):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d
DAYS = int(opt('--days', '400')); YEARS = [int(y) for y in opt('--years', f'{dt.date.today().year - 1},{dt.date.today().year}').split(',')]
DEADLINE = time.time() + 60 * int(opt('--minutes', '240')); DELAY = 3.0
S = requests.Session(); S.headers['User-Agent'] = K.UA; last = [0.0]
def req(method, url, **kw):
    for i in range(5):
        w = DELAY - (time.time() - last[0])
        if w > 0: time.sleep(w)
        try:
            r = S.request(method, url, timeout=90, **kw); last[0] = time.time()
            if r.status_code == 200:
                if 'g-recaptcha-response' in r.text and 'Search Details' not in r.text and 'rgSearchRslts' not in r.text: raise SystemExit('captcha challenge shown - stopping')
                return r.text
            err = r.status_code
        except requests.RequestException as e: last[0] = time.time(); err = repr(e)[:80]
        print('  retry', i, err, flush=True); time.sleep(20 * 2 ** i)
    raise RuntimeError('request failed')
def load(fn, d):
    p = os.path.join(OUT, fn); return json.load(open(p)) if os.path.exists(p) else d
def save(fn, o):
    p = os.path.join(OUT, fn); json.dump(o, open(p + '.tmp', 'w')); os.replace(p + '.tmp', p)
def search(url, fld, oper, val):
    t = req('GET', url); f = K.hidden(t)
    base = {'ctl00$cplMain$ddSearchBy': fld, 'ctl00$cplMain$ddSearchOper': oper, 'ctl00$cplMain$txtSearchString': val, 'ctl00$cplMain$activeTab': '0'}
    f.update(base); f['ctl00$cplMain$btnSearch'] = 'Search'; return req('POST', url, data=f), base
def nextpage(url, t, base):
    f = K.hidden(t); f.update(base); f.update({'__EVENTTARGET': 'ctl00$cplMain$rgSearchRslts', '__EVENTARGUMENT': 'FireCommand:ctl00$cplMain$rgSearchRslts$ctl00;Page;next'}); return req('POST', url, data=f)
def rowclick(url, t, base, k):
    f = K.hidden(t); f.update(base); f.update({'__EVENTTARGET': 'ctl00$cplMain$rgSearchRslts', '__EVENTARGUMENT': f'RowClick;{k}'}); return req('POST', url, data=f)
def fields(t):
    x = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' | ', t))); x = re.sub(r'(\|\s*)+', '| ', x)
    g = lambda lab: (re.search(r'\| ' + re.escape(lab) + r':? \| ([^|]*)', x) or [None, ''])[1].strip()
    return {'type': g('Type'), 'subtype': g('Subtype'), 'status': g('Status'), 'opened': g('Opened'), 'closed': g('Closed'), 're': g('PARCEL ID'), 'name': g('Case Name')[:120]}
def mdy(s):
    try: return dt.datetime.strptime(s, '%m/%d/%Y').date().isoformat()
    except Exception: return ''
OPEN = re.compile(r'close|no violation|complied|compliance|void|dismiss|withdraw|unfounded|resolved|paid', re.I)
def permits():
    P = load('permits.json', {'days': {}}); today = dt.date.today(); url = K.BASE + 'permit.aspx'
    for k in range(DAYS):
        if time.time() > DEADLINE: print('permit deadline reached', flush=True); break
        d = today - dt.timedelta(days=k); key = d.isoformat()
        if key in P['days'] and k > 21: continue
        t, base = search(url, 'Permit_Main.ISSUED', 'EQUALS', d.strftime('%m/%d/%Y')); rows = K.rows(t); p, n = K.pageinfo(t)
        while p < n and p < 20:
            t = nextpage(url, t, base); np_, n = K.pageinfo(t)
            if np_ <= p: break
            p = np_; rows += K.rows(t)
        P['days'][key] = rows; P['pulled'] = time.strftime('%Y-%m-%d %H:%M'); save('permits.json', P)
        if rows: print('permits', key, len(rows), flush=True)
    return P
def cases():
    C = load('cases.json', {'cases': {}}); url = K.BASE + 'case.aspx'
    for y in YEARS:
        empty = 0
        for nn in range(100):
            if time.time() > DEADLINE: print('case deadline reached', flush=True); return C
            pref = f'CC{y}-{nn:03d}'
            t, base = search(url, 'Case_Main.CASE_NO', 'BEGINS WITH', pref); got = 0; page = 1
            while True:
                rows = K.rows(t); got += len(rows)
                for k, r in enumerate(rows):
                    no = r[0]; c = C['cases'].get(no)
                    if c and c.get('status') and OPEN.search(c['status']): continue   # closed: cached
                    d = fields(rowclick(url, t, base, k)); d.update({'addr': r[1] if len(r) > 1 else '', 'key': r[2] if len(r) > 2 else '', 'seen': time.strftime('%Y-%m-%d')})
                    d['opened'] = mdy(d['opened']); d['closed'] = mdy(d['closed']); C['cases'][no] = d
                    t2 = t   # the RowClick response keeps the grid state; keep paging from the list page
                _, n = K.pageinfo(t)
                if page >= n or page >= 20 or not rows: break
                t = nextpage(url, t, base); page += 1
            C['pulled'] = time.strftime('%Y-%m-%d %H:%M'); save('cases.json', C); print('cases', pref, got, 'total', len(C['cases']), flush=True)
            empty = empty + 1 if not got else 0
            if empty >= 2: break
    return C
if __name__ == '__main__':
    what = opt('--only', 'permit,case').split(',')
    if 'permit' in what: P = permits(); print('permit days', len(P['days']), 'rows', sum(len(v) for v in P['days'].values()), flush=True)
    if 'case' in what: C = cases(); print('cases', len(C['cases']), flush=True)
