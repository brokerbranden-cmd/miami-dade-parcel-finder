#!/usr/bin/env python3
"""City of Key West building permits + code-compliance cases from the public eTRAKiT portal (CentralSquare,
https://etrakit.cityofkeywest-fl.gov/etrakit; no login, no captcha challenge on search) -> $RAW/monroe/kw_etrakit.json

Plain ASP.NET postbacks, one request at a time, DELAY s apart (polite; identifying User-Agent).
  permits: Search/permit.aspx  ISSUED EQUALS <day>, every result page (20 rows: permit no, issued, type, subtype, status, RE, address).
           First run back-fills from START (2023-01-01); later runs re-pull the last RECENT_DAYS days (status changes) + new days.
  cases:   Search/case.aspx only offers CASE_NO / SITE_ADDR. Case numbers are CC<year>-NNNNN, so each case is read with
           CASE_NO EQUALS + the grid row-click postback -> detail panel (type, status, opened, closed, parcel id, violations).
           Walks CC<year>-00001.. until MISS_STOP consecutive misses past the highest hit; re-reads open cases older than RECHECK_DAYS.
Resumable: state is checkpointed every few records; MAX_MINUTES bounds a run (the rest continues next run).
Usage: fetch_keywest_etrakit.py [--permits-only|--cases-only]"""
import os, re, sys, json, time, html, datetime as dt, requests
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe'); os.makedirs(RAW, exist_ok=True)
OUTP = os.path.join(RAW, 'kw_permits.json'); OUTC = os.path.join(RAW, 'kw_cases.json')   # separate files so the two halves can run side by side
B = 'https://etrakit.cityofkeywest-fl.gov/etrakit/Search/'
UA = 'Mozilla/5.0 (parcel-finder; Prop Hunters LLC research; Branden@prop-hunters.com)'
DELAY = float(os.environ.get('KW_DELAY', '1.5')); START = dt.date.fromisoformat(os.environ.get('KW_START', '2023-01-01'))
RECENT_DAYS = int(os.environ.get('KW_RECENT_DAYS', '120')); RECHECK_DAYS = int(os.environ.get('KW_RECHECK_DAYS', '6'))
MISS_STOP = int(os.environ.get('KW_MISS_STOP', '25')); MAX_MIN = float(os.environ.get('MAX_MINUTES', '300'))
T0 = time.time(); today = dt.date.today()
def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)
def out_of_time(): return (time.time() - T0) / 60 > MAX_MIN
L = lambda p: json.load(open(p)) if os.path.exists(p) else {}
sp, sc = L(OUTP), L(OUTC)
st = {'permits': sp.get('permits', {}), 'permit_days': sp.get('permit_days', {}), 'cases': sc.get('cases', {}), 'case_hi': sc.get('case_hi', {})}
MODE = 'both'
def save():
    now = dt.datetime.now().astimezone().isoformat(timespec='seconds')
    ds = [p['issued'] for p in st['permits'].values() if p.get('issued')]; cs = [c['opened'] for c in st['cases'].values() if c.get('opened')]
    st['newest'] = {'permit_issued': max(ds) if ds else None, 'case_opened': max(cs) if cs else None}
    for f, keys, on in ((OUTP, ('permits', 'permit_days'), MODE != 'cases'), (OUTC, ('cases', 'case_hi'), MODE != 'permits')):
        if not on: continue
        d = {k: st[k] for k in keys}; d['pulled'] = now; d['newest'] = st['newest']['permit_issued' if f == OUTP else 'case_opened']
        d['source'] = 'City of Key West eTRAKiT (etrakit.cityofkeywest-fl.gov)'
        tmp = f + '.tmp'; json.dump(d, open(tmp, 'w')); os.replace(tmp, f)

class Portal:
    def __init__(self, page):
        self.url = B + page; self.S = requests.Session(); self.S.headers['User-Agent'] = UA; self.t = None; self.last = 0
    def _req(self, method, data=None):
        for i in range(4):
            w = DELAY - (time.time() - self.last)
            if w > 0: time.sleep(w)
            try:
                r = self.S.request(method, self.url, data=data, timeout=90); self.last = time.time()
                if r.status_code in (429, 503): raise RuntimeError(f'HTTP {r.status_code}')
                r.raise_for_status(); t = r.text
                if 'data-sitekey' in t or 'g-recaptcha' in t: raise SystemExit('captcha challenge appeared - stopping (not bypassed)')
                return t
            except (requests.RequestException, RuntimeError) as e:
                log('retry', i + 1, str(e)[:100]); time.sleep(30 * (i + 1)); self.S = requests.Session(); self.S.headers['User-Agent'] = UA; self.t = None
                if method == 'POST': raise
        raise RuntimeError('portal unreachable')
    def form(self):
        if self.t is None: self.t = self._req('GET')
        return {m.group(1): html.unescape(m.group(2)) for m in re.finditer(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', self.t)}
    def post(self, extra):
        for i in range(3):
            try:
                f = self.form(); f.update(extra); self.t = self._req('POST', f); return self.t
            except (requests.RequestException, RuntimeError) as e:
                log('post retry', i + 1, str(e)[:100]); time.sleep(30 * (i + 1)); self.t = None
        raise RuntimeError('post failed')
    def search(self, by, oper, val):
        self.crit = {'ctl00$cplMain$ddSearchBy': by, 'ctl00$cplMain$ddSearchOper': oper, 'ctl00$cplMain$txtSearchString': val, 'ctl00$cplMain$activeTab': '0'}
        return self.post(dict(self.crit, **{'ctl00$cplMain$btnSearch': 'Search'}))
    def grid(self, arg): return self.post(dict(self.crit, **{'__EVENTTARGET': 'ctl00$cplMain$rgSearchRslts', '__EVENTARGUMENT': arg}))

def rows(t):
    return [[html.unescape(re.sub(r'<[^>]+>', '', c)).strip() for c in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)]
            for tr in re.findall(r'<tr class="rg(?:Alt)?Row".*?</tr>', t, re.S)]
def pageinfo(t):
    m = re.search(r'page (\d+) of (\d+)', t); return (int(m.group(1)), int(m.group(2))) if m else (1, 1)
def iso(s):
    try: return dt.datetime.strptime(s.strip(), '%m/%d/%Y').date().isoformat()
    except Exception: return None
RE_ = lambda s: s if re.fullmatch(r'\d{8}-\d{6}', s or '') else ''

def permits():
    P = Portal('permit.aspx'); days = st['permit_days']
    d = START; n_new = 0
    while d <= today and not out_of_time():
        k = d.isoformat()
        if k in days and (today - d).days > RECENT_DAYS: d += dt.timedelta(days=1); continue
        if d.weekday() >= 5 and k in days: d += dt.timedelta(days=1); continue
        t = P.search('Permit_Main.ISSUED', 'EQUALS', d.strftime('%m/%d/%Y')); got = rows(t); p, n = pageinfo(t)
        while p < n:
            t = P.grid('FireCommand:ctl00$cplMain$rgSearchRslts$ctl00;Page;next'); p2, n = pageinfo(t)
            if p2 <= p: log('paging stalled', k); break
            p = p2; got += rows(t)
        for r in got:
            if len(r) < 7 or not r[0]: continue
            if r[0] not in st['permits']: n_new += 1
            st['permits'][r[0]] = {'no': r[0], 'issued': iso(r[1]), 'type': r[2], 'subtype': r[3], 'status': r[4], 're': RE_(r[5]), 'addr': r[6], 'seen': today.isoformat()}
        days[k] = len(got)
        if d.day == 1 or len(got) > 40: log('permits', k, len(got), 'total', len(st['permits'])); save()
        d += dt.timedelta(days=1)
    save(); log('permits done:', len(st['permits']), 'new', n_new)

FIELDS = {'Case #': 'no', 'Type': 'type', 'Subtype': 'subtype', 'Status': 'status', 'Opened': 'opened', 'Closed': 'closed', 'Last Action': 'last_action', 'PARCEL ID': 're', 'Address': 'addr'}
def detail(t):
    i = t.find('id="cplMain_UpdatePanelDetail"')
    if i < 0: return None
    s = re.sub(r'<script.*?</script>|<style.*?</style>', '', t[i:], flags=re.S)
    x = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '|', s))); f = [y.strip() for y in re.split(r'\s*\|\s*', x) if y.strip()]
    d = {}
    for j, y in enumerate(f[:-1]):
        if y.endswith(':') and y[:-1] in FIELDS and FIELDS[y[:-1]] not in d:
            v = f[j + 1]; d[FIELDS[y[:-1]]] = '' if v.endswith(':') or v in FIELDS else v
    if not d.get('no'): return None
    for k in ('opened', 'closed', 'last_action'): d[k] = iso(d.get(k) or '') if d.get(k) else None
    d['re'] = RE_(d.get('re', ''))
    # violations table: 'Sec. ...' rows after the 'Remarks|Notes/Comments|More Info' header
    vi = [y for y in f if re.match(r'(Sec\.|Section|Chapter|Ch\.|FBC|IPMC|LDR)\s', y)]
    d['violations'] = vi[:4]
    return d

def case_open(c): return not c.get('closed') and not re.search(r'CLOSED|COMPLIANCE|COMPLIED|VOID|DISMISS|WITHDRAW|NO VIOLATION|UNFOUNDED|CANCEL', c.get('status', '').upper())
def cases():
    P = Portal('case.aspx'); C = st['cases']; n_read = 0
    def read(no):
        nonlocal n_read
        t = P.search('Case_Main.CASE_NO', 'EQUALS', no)
        if not rows(t): return None
        d = detail(P.grid('RowClick;0')); n_read += 1
        if d and d['no'] == no:
            d['checked'] = today.isoformat(); C[no] = d
            if n_read % 20 == 0: save(); log('cases read', n_read, no, 'total', len(C))
            return d
        return None
    for y in range(START.year, today.year + 1):
        hi = st['case_hi'].get(str(y), 0); num = 1; miss = 0
        while not out_of_time():
            no = f'CC{y}-{num:05d}'
            if no in C: miss = 0; hi = max(hi, num); num += 1; continue
            d = read(no)
            if d: miss = 0; hi = max(hi, num)
            else:
                miss += 1
                if num > hi and miss >= MISS_STOP: break
            num += 1
        st['case_hi'][str(y)] = hi; save(); log('year', y, 'highest case', hi)
    # re-read open cases (status / closed date changes)
    stale = sorted((c['checked'], no) for no, c in C.items() if case_open(c) and (today - dt.date.fromisoformat(c['checked'])).days >= RECHECK_DAYS)
    log('re-checking', len(stale), 'open cases')
    for _, no in stale:
        if out_of_time(): break
        read(no)
    save(); log('cases done:', len(C), 'read this run', n_read)

if __name__ == '__main__':
    a = sys.argv[1:]; MODE = 'permits' if '--permits-only' in a else 'cases' if '--cases-only' in a else 'both'
    if '--cases-only' not in a: permits()
    if '--permits-only' not in a: cases()
    n = st['newest']; log('newest', n)
    if out_of_time(): log('MAX_MINUTES reached - partial run, resumes next time'); sys.exit(0)
