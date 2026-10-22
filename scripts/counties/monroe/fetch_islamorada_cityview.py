#!/usr/bin/env python3
"""Islamorada, Village of Islands: building permits + code-enforcement cases from the public CityView Portal
(https://cvportal.us/CityViewPortal, Harris / municipalsoftware.com; no login, no captcha) -> $RAW/monroe/isl_cityview.json

The Permit and CodeEnforcement locators do a substring search over number / address / RE# / contact and return JSON
{View: html} with 20 results per page, newest first. Searching a year ('2025') pages through that year's records
(permit numbers PR<type><year><seq>, case numbers CE<type><year><seq>) -> number, type, status, address, RE#.
  permits: each list item links /CityViewPortal/Permit/Status?permitId=N -> application / issued / expiration dates,
           category and description of work. Detail pages are slow (~5-8 s), so a run reads at most ISL_MAX_DETAIL of them:
           new permits first, then permits whose list status changed, then still-open permits not read for ISL_RECHECK_DAYS.
  code cases: the portal has no case detail page, so the only date is the year in the case number (open_year).
Every run re-lists the current and previous year (status changes) and back-fills earlier years once (from ISL_START_YEAR).
Polite: one request at a time, ISL_DELAY s apart. Resumable (checkpoints). MAX_MINUTES bounds a run."""
import os, re, sys, json, time, html, datetime as dt, requests
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe'); os.makedirs(RAW, exist_ok=True)
OUT = os.path.join(RAW, 'isl_cityview.json')
B = 'https://cvportal.us/CityViewPortal/'
UA = 'Mozilla/5.0 (parcel-finder; Prop Hunters LLC research; Branden@prop-hunters.com)'
DELAY = float(os.environ.get('ISL_DELAY', '1.5')); Y0 = int(os.environ.get('ISL_START_YEAR', '2023'))
MAX_DETAIL = int(os.environ.get('ISL_MAX_DETAIL', '1500')); RECHECK = int(os.environ.get('ISL_RECHECK_DAYS', '27'))
MAX_MIN = float(os.environ.get('MAX_MINUTES', '240')); T0 = time.time(); today = dt.date.today()
def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)
def out_of_time(): return (time.time() - T0) / 60 > MAX_MIN
st = json.load(open(OUT)) if os.path.exists(OUT) else {}
for k in ('permits', 'cases', 'years_done'): st.setdefault(k, {})
def save():
    ds = [d for p in st['permits'].values() for d in (p.get('issued'), p.get('applied')) if d]
    st['newest'] = {'permit_date': max(ds) if ds else None, 'case_year': max((c['open_year'] for c in st['cases'].values()), default=None)}
    st['pulled'] = dt.datetime.now().astimezone().isoformat(timespec='seconds'); st['source'] = 'Islamorada CityView Portal (cvportal.us/CityViewPortal)'
    tmp = OUT + '.tmp'; json.dump(st, open(tmp, 'w')); os.replace(tmp, OUT)
S = requests.Session(); S.headers['User-Agent'] = UA; _last = [0.0]
def get(path, params=None, ajax=False):
    for i in range(4):
        w = DELAY - (time.time() - _last[0])
        if w > 0: time.sleep(w)
        try:
            r = S.get(B + path, params=params, timeout=120, headers={'X-Requested-With': 'XMLHttpRequest'} if ajax else {}); _last[0] = time.time()
            if r.status_code in (429, 503): raise RuntimeError(f'HTTP {r.status_code}')
            r.raise_for_status()
            if 'g-recaptcha' in r.text or 'data-sitekey' in r.text: raise SystemExit('captcha appeared - stopping (not bypassed)')
            return r.json() if ajax else r.text
        except (requests.RequestException, RuntimeError, ValueError) as e:
            log('retry', i + 1, path[:60], str(e)[:80]); time.sleep(30 * (i + 1))
    raise RuntimeError('unreachable: ' + path)

def items(view):
    out = []
    for li in re.findall(r'<li>(.*?)</li>', view, re.S):
        g = lambda k: (re.search(r'data-cy="inp-' + k + r'\d+">([^<]*)<', li) or [None, ''])[1].strip()
        no = g('permitNumber') or g('caseNumber') or g('complaintNumber')
        if not no:
            m = re.search(r'(?:Application|Case) Number:</label>.*?class="inputText"[^>]*>([^<]+)<', li, re.S); no = m.group(1).strip() if m else ''
        if not no: continue
        lab = dict((a.strip(':'), html.unescape(re.sub(r'<[^>]+>', '', b)).strip()) for a, b in re.findall(r'<label[^>]*>([^<]+)</label>\s*</div>\s*<div class="right1">\s*<div class="cv-input-wrapper">\s*<div[^>]*>(.*?)</div>', li, re.S))
        locs = [html.unescape(x).strip() for x in re.findall(r'<span class="basicText">([^<]+)</span>', li)]
        rid = next((x for x in locs if re.fullmatch(r'\d{8}-\d{6}', x)), ''); addr = next((x for x in locs if x != rid and not x.startswith('Inspections')), '')
        pid = re.search(r'permitId=(\d+)', li)
        out.append({'no': html.unescape(no), 'type': lab.get('Permit Type') or lab.get('Type', ''), 'status': lab.get('Status', ''), 'addr': addr, 're': rid, 'pid': pid.group(1) if pid else ''})
    return out

def list_year(mod, cat, y):
    get(f'{mod}/Locator' + (f'?category={cat}' if cat else ''))
    got = {}; pat = re.compile(r'^[A-Z]+' + str(y) + r'\d+$')
    for pg in range(400):
        j = get(f'{mod}/LocatorResults', {'searchValue': str(y), 'category': cat, 'pageNumber': pg, 'appealPeriodStatusesOnly': 'False', 'isInspectionSearch': 'False'}, ajax=True)
        it = items(j.get('View') or '')
        if not it: break
        new = 0
        for r in it:
            if pat.match(r['no']) and r['no'] not in got: got[r['no']] = r; new += 1
        if not new and pg > 3: break
    return got

DET = {'Application Date': 'applied', 'Issued Date': 'issued', 'Expiration Date': 'expires', 'Category of Work': 'category', 'Description of Work': 'desc', 'Application Status': 'app_status', 'Finaled Date': 'finaled', 'Closed Date': 'closed_date'}
def iso(s):
    try: return dt.datetime.strptime(s.strip(), '%m/%d/%Y').date().isoformat()
    except Exception: return None
def detail(pid):
    t = get('Permit/Status', {'permitId': pid}); i = t.find('Summary')
    s = re.sub(r'<script.*?</script>|<style.*?</style>', '', t[i:i + 60000], flags=re.S)
    f = [y.strip() for y in re.split(r'\s*\|\s*', re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '|', s)))) if y.strip()]
    d = {}
    for j, y in enumerate(f[:-1]):
        k = y.rstrip(':')
        if y.endswith(':') and k in DET and DET[k] not in d:
            v = f[j + 1]; d[DET[k]] = '' if v.endswith(':') else v
            if k.endswith('Date'): d[DET[k]] = iso(d[DET[k]] or '')
    d['desc'] = (d.get('desc') or '')[:200]; return d

def open_status(s): return not re.search(r'clos|final|complet|void|withdr|cancel|expir|abandon|denied|remedied|compliant|revoked|no violation|unfounded', (s or '').lower())

if __name__ == '__main__':
    P, C = st['permits'], st['cases']
    years = [y for y in range(Y0, today.year + 1) if y >= today.year - 1 or not st['years_done'].get(str(y))]
    for y in sorted(years, reverse=True):
        if out_of_time(): break
        for mod, cat, D in (('Permit', '', P), ('CodeEnforcement', 'CE', C)):
            got = list_year(mod, cat, y); log(mod, y, len(got), 'listed')
            for no, r in got.items():
                old = D.get(no, {})
                if D is P: r.update({k: old[k] for k in ('applied', 'issued', 'expires', 'category', 'desc', 'finaled', 'detail_checked', 'detail_status') if k in old})
                else: r['open_year'] = y
                r['seen'] = today.isoformat(); D[no] = r
        st['years_done'][str(y)] = today.isoformat(); save()
    # permit details: new, status changed, open + stale
    def prio(p):
        if not p.get('detail_checked'): return 0
        if p.get('detail_status') != p['status']: return 1
        if open_status(p['status']) and (today - dt.date.fromisoformat(p['detail_checked'])).days >= RECHECK: return 2
        return None
    todo = sorted(((prio(p), -int(re.sub(r'\D', '', no)[:4] or 0), no) for no, p in P.items() if p.get('pid') and prio(p) is not None))
    log('permit details to read', len(todo), 'cap', MAX_DETAIL); n = 0
    for _, _, no in todo[:MAX_DETAIL]:
        if out_of_time(): break
        p = P[no]
        try: p.update(detail(p['pid']))
        except Exception as e: log('detail fail', no, str(e)[:80]); continue
        p['detail_checked'] = today.isoformat(); p['detail_status'] = p['status']; n += 1
        if n % 25 == 0: save(); log('details', n, no, p.get('issued') or p.get('applied'))
    save(); log('done: permits', len(P), 'with dates', sum(1 for p in P.values() if p.get('issued') or p.get('applied')), 'cases', len(C), 'newest', st['newest'])
