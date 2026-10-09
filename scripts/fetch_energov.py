#!/usr/bin/env python3
"""Municipal building permits + code-enforcement cases from public Tyler EnerGov "Citizen Self Service" portals (no login).

Every portal exposes an anonymous JSON search (the same call the public "Search" page makes):
    POST <base>/api/energov/search/search   headers tenantId / tenantName / Tyler-TenantUrl (from <base>/api/Home/GetTenants)
Permits (SearchModule 2) and Code Cases (5) carry the parcel number (MainParcel = Miami-Dade folio), type, status, dates, address.
The search window is capped at 10,000 rows, so the fetch walks apply/opened-date windows (years, split in halves while a window holds
more than 9,500 rows) at 1,000 rows per request and ~1 request/second per portal. Resumable: finished windows are kept in
RAW/permits/energov/<slug>_<kind>.jsonl and skipped on re-run.

usage: fetch_energov.py [RAW] [--only slug,slug] [--kinds permit,code] [--since 1990]
Output: RAW/permits/energov/<slug>_permit.jsonl / <slug>_code.jsonl  (one line per window: {w:[from,to], total, rows:[...]}),
        RAW/permits/energov/summary.json (per portal: reported totals vs rows kept).
"""
import json, os, sys, time, copy, datetime as dt, threading, requests

RAW = '/workspace/raw'
args = [a for a in sys.argv[1:] if not a.startswith('--')]
if args: RAW = args[0]
def opt(name, default=None):
    for i, a in enumerate(sys.argv):
        if a == name and i + 1 < len(sys.argv): return sys.argv[i + 1]
    return default
ONLY = set((opt('--only') or '').split(',')) - {''}
KINDS = (opt('--kinds') or 'permit,code').split(',')
SINCE = int(opt('--since', '1990'))
OUT = f'{RAW}/permits/energov'
UA = 'parcel-finder weekly refresh (python-requests)'
SORT = {'permit': 'PermitNumber.keyword', 'code': 'CaseNumber.keyword'}

# slug: (city, municipality code in the PA roll, portal base). Portals found from each city's own permit page / web search.
PORTALS = {
    'hialeah':       ('Hialeah', '04', 'https://hialeahfl-energovpub.tylerhost.net/apps/selfservice'),
    'miami_gardens': ('Miami Gardens', '34', 'https://miamigardensfl-energovpub.tylerhost.net/apps/selfservice'),
    'coral_gables':  ('Coral Gables', '03', 'https://coralgablesfl-energovpub.tylerhost.net/apps/selfservice'),
    'miami_beach':   ('Miami Beach', '02', 'https://energovcss.miamibeachfl.gov/EnerGovProd/SelfService'),
    'surfside':      ('Surfside', '14', 'https://surfsidefl-energovpub.tylerhost.net/apps/selfservice'),
    'north_bay':     ('North Bay Village', '23', 'https://northbayvillagefl-energovpub.tylerhost.net/apps/selfservice'),
    'miami_shores':  ('Miami Shores', '11', 'https://villageofmiamishoresfl-energovweb.tylerhost.net/apps/selfservice'),
}
EXTRA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'energov_portals.json')   # optional extra portals {slug: [city, code, base]}
if os.path.exists(EXTRA): PORTALS.update({k: tuple(v) for k, v in json.load(open(EXTRA)).items()})

def blank_body(kind):
    crit = {
        'permit': {"PermitNumber": None, "PermitTypeId": "none", "PermitWorkclassId": None, "PermitStatusId": "none", "ProjectName": None, "IssueDateFrom": None, "IssueDateTo": None, "Address": None, "Description": None,
                   "ExpireDateFrom": None, "ExpireDateTo": None, "FinalDateFrom": None, "FinalDateTo": None, "ApplyDateFrom": None, "ApplyDateTo": None, "SearchMainAddress": False, "ContactId": None, "TypeId": None,
                   "WorkClassIds": None, "ParcelNumber": None, "ExcludeCases": None, "EnableDescriptionSearch": False},
        'code': {"CodeCaseNumber": None, "CodeCaseTypeId": "none", "CodeCaseStatusId": "none", "ProjectName": None, "OpenedDateFrom": None, "OpenedDateTo": None, "ClosedDateFrom": None, "ClosedDateTo": None,
                 "Address": None, "ParcelNumber": None, "Description": None, "SearchMainAddress": False, "RequestId": None, "ExcludeCases": None, "ContactId": None, "EnableDescriptionSearch": False,
                 "HiddenCodeCaseTypeIds": None}}[kind]
    return crit

class Portal:
    def __init__(self, slug):
        self.slug = slug; self.city, self.muni, self.base = PORTALS[slug]
        self.s = requests.Session(); self.s.headers['User-Agent'] = UA
        self.last = 0
        for i in range(4):
            try:
                t = self.s.get(self.base + '/api/Home/GetTenants', headers={'Tyler-Tenant-Culture': 'en-US'}, timeout=60).json()['Result'][0]; break
            except Exception as e:
                time.sleep(5)
        else: raise SystemExit(f'{slug}: cannot read tenants')
        self.s.headers.update({'tenantid': str(t['TenantID']), 'tenantname': t['TenantName'], 'Tyler-TenantUrl': t['TenantUrl'], 'Tyler-Tenant-Culture': 'en-US',
                               'Content-Type': 'application/json', 'Accept': 'application/json'})
    def search(self, kind, d0, d1, page, size=1000):
        module = 2 if kind == 'permit' else 5
        ck = 'PermitCriteria' if kind == 'permit' else 'CodeCaseCriteria'
        c = blank_body(kind)
        c.update({'PageNumber': page, 'PageSize': size, 'SortBy': SORT[kind], 'SortAscending': True})
        if kind == 'permit': c.update({'ApplyDateFrom': d0 + 'T00:00:00', 'ApplyDateTo': d1 + 'T23:59:59'})
        else: c.update({'OpenedDateFrom': d0 + 'T00:00:00', 'OpenedDateTo': d1 + 'T23:59:59'})
        body = {"Keyword": "", "ExactMatch": False, "SearchModule": module, "FilterModule": module, "SearchMainAddress": False, "ExcludeCases": None, "HiddenInspectionTypeIDs": None,
                "PageNumber": page, "PageSize": size, "SortBy": SORT[kind], "SortAscending": True, ck: c}
        for other in ('PlanCriteria', 'InspectionCriteria', 'RequestCriteria', 'BusinessLicenseCriteria', 'ProfessionalLicenseCriteria', 'LicenseCriteria', 'ProjectCriteria', 'OperationalPermitCriteria'):
            pass
        for i in range(5):
            wait = 1.0 - (time.time() - self.last)
            if wait > 0: time.sleep(wait)
            try:
                r = self.s.post(self.base + '/api/energov/search/search', data=json.dumps(body), timeout=180); self.last = time.time()
                j = r.json()
                if j.get('Result') is not None: return j['Result']
                err = (r.status_code, str(j)[:120])
            except Exception as e:
                self.last = time.time(); err = repr(e)[:120]
            print(f'  [{self.slug}] retry {i}: {err}', flush=True); time.sleep(5 + 5 * i)
        return None

def d10(v): return (v or '')[:10]
def slim(e, kind):
    a = e.get('Address') or {}
    r = {'id': e['CaseId'], 'no': e['CaseNumber'], 'type': e.get('CaseType') or '', 'wc': e.get('CaseWorkclass') or '', 'st': e.get('CaseStatus') or '',
         'apply': d10(e.get('ApplyDate')), 'issue': d10(e.get('IssueDate')), 'exp': d10(e.get('ExpireDate')), 'final': d10(e.get('FinalDate')),
         'parcel': e.get('MainParcel') or '', 'addr': e.get('AddressDisplay') or '', 'desc': (e.get('Description') or '')[:200]}
    return r

def windows(since):
    ws = [(f'1900-01-01', f'{since - 1}-12-31')] if since > 1900 else []
    ws += [(f'{y}-01-01', f'{y}-12-31') for y in range(since, dt.date.today().year + 1)]
    ws.append((f'{dt.date.today().year + 1}-01-01', '2200-12-31'))
    return ws

def split(w):
    a, b = dt.date.fromisoformat(w[0]), dt.date.fromisoformat(w[1])
    if (b - a).days < 1: return None
    m = a + (b - a) / 2
    m = dt.date(m.year, m.month, m.day)
    return (w[0], m.isoformat()), ((m + dt.timedelta(days=1)).isoformat(), w[1])

def run(slug, kind):
    p = Portal(slug); fn = f'{OUT}/{slug}_{kind}.jsonl'
    done = {}
    if os.path.exists(fn):
        for ln in open(fn):
            try: j = json.loads(ln); done[tuple(j['w'])] = j['total']
            except Exception: pass
    out = open(fn, 'a'); t0 = time.time(); stack = list(reversed(windows(SINCE))); n = 0
    while stack:
        w = stack.pop()
        if w in done: continue
        R = p.search(kind, w[0], w[1], 1)
        if R is None: print(f'[{slug}/{kind}] FAILED window {w}', flush=True); continue
        total = R['TotalFound']; rows = [slim(e, kind) for e in R['EntityResults']]
        if total > 9500 and split(w):
            a, b = split(w); stack.append(b); stack.append(a); continue
        page = 1
        while len(rows) < total and page < 11:
            page += 1; R2 = p.search(kind, w[0], w[1], page)
            if not R2 or not R2['EntityResults']: break
            rows += [slim(e, kind) for e in R2['EntityResults']]
        out.write(json.dumps({'w': w, 'total': total, 'rows': rows}, separators=(',', ':')) + '\n'); out.flush(); n += len(rows)
        if total: print(f'[{slug}/{kind}] {w[0]}..{w[1]} total {total} got {len(rows)} (cum {n}, {int(time.time() - t0)}s)', flush=True)
    out.close()

def summarize():
    S = {}
    for slug in PORTALS:
        for kind in ('permit', 'code'):
            fn = f'{OUT}/{slug}_{kind}.jsonl'
            if not os.path.exists(fn): continue
            tot = got = 0; ids = set(); lo = '9'; hi = ''
            for ln in open(fn):
                j = json.loads(ln); tot += j['total']; got += len(j['rows'])
                for r in j['rows']:
                    ids.add(r['id'])
                    d = r['apply'] or r['issue']
                    if d and d > '1950': lo = min(lo, d); hi = max(hi, d)
            S[f'{slug}_{kind}'] = {'reported': tot, 'rows': got, 'unique': len(ids), 'min_date': lo, 'max_date': hi}
    json.dump({'pulled': time.strftime('%Y-%m-%d %H:%M'), 'portals': S}, open(f'{OUT}/summary.json', 'w'), indent=1)
    return S

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    todo = [s for s in PORTALS if not ONLY or s in ONLY]
    errs = []
    def work(slug):
        for kind in KINDS:
            try: run(slug, kind)
            except BaseException as e:
                errs.append((slug, kind, repr(e))); print(f'[{slug}/{kind}] ERROR {e!r}', flush=True)
    th = [threading.Thread(target=work, args=(s,)) for s in todo]     # one thread per portal host => ~1 req/s per host
    [t.start() for t in th]; [t.join() for t in th]
    for k, v in summarize().items(): print(k, v)
    if errs: print('errors:', errs); sys.exit(1)
