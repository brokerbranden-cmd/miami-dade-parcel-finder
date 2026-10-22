#!/usr/bin/env python3
"""Pull each priority parcel's current-owner Official Records (mortgages, assignments, modifications, satisfactions,
releases) from the Miami-Dade Clerk public Name/Document search, for the estimated-equity layer (build_equity.py).

Same approach as fetch_clerk.py (real Chrome page, one search at a time, JSON the page loads), but searched by the
current owner's name from the owner's acquisition date (PA DOS_1 - 60 days) to today. The rows carry the folio,
the consideration (loan amount) and, for satisfactions/releases, the original book/page, so build_equity.py can
match them to the parcel by folio and link satisfactions to mortgages.

Cache: RAW/clerk_owner/<folio>.json (one per parcel). A parcel is re-pulled when older than --max-age days
(weekly refresh), so the run is resumable and only spends searches on stale parcels.
Priority order (see priority()): open pre-foreclosure, probate, auctions, then distress score desc, then the
rest of residential parcels if --all. Saved / skip-traced lists live in Branden's browser; add their folios
with --folios FILE (one folio per line) and they go first.

usage: fetch_mortgages.py RAW [--limit N] [--workers 3] [--max-age 7] [--folios FILE] [--minutes M]
"""
import json, os, sys, time, re, gzip, argparse, multiprocessing as mp
from datetime import date, datetime, timedelta

URL = "https://onlineservices.miamidadeclerk.gov/officialrecords/"
KEEP = re.compile(r'MORTGAGE|SATISFACTION OF MORTGAGE|RELEASE|ASSIGNMENT|MODIF|NOTE|DEED|HELOC|CREDIT', re.I)
FIELDS = ['clerk_File', 'doC_TYPE', 'reC_DATE', 'reC_BOOK', 'reC_PAGE', 'firsT_PARTY', 'seconD_PARTY', 'partY_CODE',
          'oriG_CFN_YEAR', 'oriG_CFN_SEQ', 'oriG_REC_BOOK', 'oriG_REC_PAGE', 'misC_REF', 'foliO_NUMBER',
          'consideratioN_1', 'consideratioN_2', 'intangible', 'documentarY_STAMPS', 'address', 'cfN_YEAR', 'cfN_SEQ']
ORG = re.compile(r'\b(LLC|L L C|INC|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLP|PA|TRUST|TR|TRS|TRUSTEE|TRUSTEES|ESTATE|EST OF|BANK|ASSN|ASSOCIATION|'
                 r'HOLDINGS|PROPERTIES|INVESTMENTS?|GROUP|PARTNERS|FUND|CHURCH|MINISTRIES|FOUNDATION|CITY|COUNTY|STATE|AUTHORITY|SCHOOL|REVOCABLE|LIVING)\b')

def search_terms(owner):
    o = re.sub(r'\s+', ' ', str(owner or '').upper().replace('&W', '').replace('&H', '').replace(' JTRS', '').replace(' JTWROS', '')).strip(' &')
    o = o.split(' & ')[0].strip()
    if not o: return None
    if ORG.search(o):
        o = re.sub(r'\b(TRS|TR|TRUSTEE|TRUSTEES)$', '', o).strip()
        return ('company', o[:60])
    w = [x for x in re.sub(r'[^A-Z \-]', ' ', o).split() if x not in ('JR', 'SR', 'II', 'III', 'IV')]
    if len(w) < 2: return ('company', o[:60])
    return ('person', w[-1], w[0])

def priority(raw, extra):
    import pyarrow.parquet as pq
    pa = pq.read_table(os.path.join(raw, 'pagis.parquet'), columns=['FOLIO', 'TRUE_OWNER1', 'DOS_1', 'DOR_CODE_CUR']).to_pandas()
    pa = pa.drop_duplicates('FOLIO').set_index('FOLIO')
    order, seen = [], set()
    def add(f):
        f = str(f).zfill(13)
        if f in pa.index and f not in seen: seen.add(f); order.append(f)
    for f in extra: add(f)
    sig = os.environ.get('SIGNALS', '/workspace/pf-fx/data/signals.json.gz')
    if os.path.exists(sig):
        s = json.load(gzip.open(sig))
        for k in ('pf', 'au', 'pb'):
            for r in s.get(k, []): add(r[0])
    d = pq.read_table(os.path.join(raw, 'distress.parquet'), columns=['FOLIO', 'dpts']).to_pandas()
    d['p'] = d['dpts'].astype(str).str.extract(r'(\d+)')[0].astype(float)
    for f in d.sort_values('p', ascending=False)['FOLIO']: add(f)
    return order, pa

def worker(args):
    wid, jobs, raw, deadline = args
    from playwright.sync_api import sync_playwright
    out = os.path.join(raw, 'clerk_owner'); n = fails = 0
    with sync_playwright() as p:
        br = p.chromium.launch(headless=not os.environ.get('DISPLAY'), executable_path="/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None,
                               args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"])
        ctx = br.new_context(viewport={"width": 1300, "height": 900})
        pg = ctx.new_page(); pg.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"); pg.set_default_timeout(45000)
        got = {'rec': None, 'std': None}
        def on_resp(r):
            try:
                if 'getStandardRecords' in r.url: got['rec'] = r.json()
                elif 'standardsearch' in r.url: got['std'] = r.json()
            except Exception: pass
        pg.on('response', on_resp)
        for folio, term, frm in jobs:
            if time.time() > deadline: break
            got['rec'] = got['std'] = None
            try:
                pg.goto(URL, wait_until="domcontentloaded", timeout=90000)
                pg.locator("text=Name/Document").first.click(); pg.wait_for_selector("#lastName")
                if term[0] == 'company':
                    pg.check('#companySearchRadio'); pg.fill('#companyName', term[1])
                else:
                    pg.fill('#lastName', term[1]); pg.fill('#firstName', term[2])
                pg.fill("#dateRangeFrom", frm); pg.fill("#dateRangeTo", date.today().isoformat())
                pg.locator("button:has-text('SEARCH')").first.click()
                t0 = time.time(); none = False
                while time.time() - t0 < 40:
                    if got['rec'] is not None: break
                    if got['std'] is not None and 'No results found' in pg.inner_text('body'): none = True; break
                    pg.wait_for_timeout(300)
                if got['rec'] is None and not none: raise RuntimeError('no response')
                m = [] if none else (got['rec'].get('recordingModels') or [])
                keep = [{k: x.get(k) for k in FIELDS} for x in m if KEEP.search(x.get('doC_TYPE') or '')]
                json.dump({'folio': folio, 'term': term, 'from': frm, 'pulled': datetime.now().strftime('%Y-%m-%d %H:%M'),
                           'n': len(m), 'capped': len(m) >= 500, 'models': keep}, open(os.path.join(out, folio + '.json'), 'w'))
                n += 1; fails = 0
                if n % 50 == 0: print(f'w{wid} {n} done', flush=True)
            except Exception as e:
                fails += 1; print(f'w{wid} fail {folio} {str(e)[:120]}', flush=True)
                if fails >= 15: print(f'w{wid} too many failures, stopping', flush=True); break
                time.sleep(min(60, 5 * fails))
            time.sleep(0.8)
        br.close()
    return n

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('raw'); ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--workers', type=int, default=3); ap.add_argument('--max-age', type=int, default=7)
    ap.add_argument('--folios'); ap.add_argument('--minutes', type=float, default=0)
    o = ap.parse_args()
    out = os.path.join(o.raw, 'clerk_owner'); os.makedirs(out, exist_ok=True)
    extra = [l.strip() for l in open(o.folios)] if o.folios else []
    order, pa = priority(o.raw, extra)
    cutoff = time.time() - o.max_age * 86400
    jobs = []
    for f in order:
        fp = os.path.join(out, f + '.json')
        if os.path.exists(fp) and os.path.getmtime(fp) > cutoff: continue
        r = pa.loc[f]; t = search_terms(r.TRUE_OWNER1)
        if not t: continue
        dos = str(int(r.DOS_1)) if r.DOS_1 == r.DOS_1 and r.DOS_1 else ''
        try: frm = (datetime.strptime(dos, '%Y%m%d') - timedelta(days=60)).date().isoformat()
        except Exception: frm = '1990-01-01'
        frm = max(frm, '1990-01-01')
        jobs.append((f, t, frm))
        if o.limit and len(jobs) >= o.limit: break
    print(f'priority parcels {len(order)}, to pull {len(jobs)}', flush=True)
    deadline = time.time() + (o.minutes * 60 if o.minutes else 10 ** 9)
    W = max(1, o.workers)
    with mp.Pool(W) as pool:
        r = pool.map(worker, [(i, jobs[i::W], o.raw, deadline) for i in range(W)])
    print('pulled', sum(r))

if __name__ == '__main__':
    main()
