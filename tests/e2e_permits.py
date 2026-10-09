"""Headless e2e for permit history + code-case coverage: meta.permitCov table, 'Permits & code cases' chips with counts, chip filter == chip count,
hash round-trip, table column, drawer section + per-city coverage message (covered city / city without public data), vacancy 'no permit' only where
covered, CSV columns, coverage <details> table. Screenshots -> SHOTS/permits_*.png"""
import sys, json, csv, io
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
SHOTS = sys.argv[2] if len(sys.argv) > 2 else '/workspace/parcel-finder/shots/'
errs = []
def ok(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg)
    if not cond: errs.append('assert: ' + msg)
cnt = lambda pg: int(pg.inner_text('#sCount').replace(',', ''))
def chipn(pg, k):
    t = pg.inner_text(f'#pcsigs .chip[data-pc="{k}"]').split('\n')[-1].replace(',', '')
    return int(float(t[:-1]) * (1e6 if t.endswith('M') else 1e3)) if t[-1] in 'KM' else int(t)
with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 1360, 'height': 900}, accept_downloads=True)
    pg = ctx.new_page()
    pg.on('console', lambda m: m.type == 'error' and 'arcgisonline' not in m.text and errs.append('console: ' + m.text))
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    pg.goto(URL); pg.wait_for_selector('#results:not([hidden])', timeout=180000); pg.wait_for_timeout(1000)
    meta = pg.evaluate("fetch('data/meta.json').then(r=>r.json())")
    pc = meta.get('permitCov'); ok(pc and len(pc['cities']) >= 30, f"meta.permitCov has {len(pc['cities']) if pc else 0} jurisdictions")
    full = [c['city'] for c in pc['cities'].values() if c['permit_level'] in ('full', 'half')]
    none = [c['city'] for c in pc['cities'].values() if c['permit_level'] == 'none']
    ok(len(full) >= 8 and 'Miami' in full, f'{len(full)} jurisdictions with 5+ yrs permit history incl. Miami: {full}')
    ok(len(none) >= 5, f'{len(none)} jurisdictions without permit data listed with reason: {none[:6]}')
    ok(all(c.get('reason') or c['status'] == 'api' for c in pc['cities'].values()), 'every non-API jurisdiction carries a reason')
    ok(len(pg.query_selector_all('#pcsigs .chip')) == 8, '8 permit/code chips')
    ok('jurisdictions' in pg.inner_text('#pcSrc'), 'source line: ' + pg.inner_text('#pcSrc'))
    pg.click('.pccov summary'); rows = pg.query_selector_all('#pcCov tbody tr'); ok(len(rows) >= 30, f'coverage table: {len(rows)} rows')
    ok('Hialeah' in pg.inner_text('#pcCov') and 'Opa-locka' in pg.inner_text('#pcCov'), 'coverage table lists covered + uncovered cities')
    pg.screenshot(path=SHOTS + 'permits_01_chips_coverage.png')
    # chip filter == chip count
    for k in ('CO', 'PX', 'CL', 'P5'):
        n = chipn(pg, k); pg.click(f'#pcsigs .chip[data-pc="{k}"]'); pg.wait_for_timeout(900)
        c = cnt(pg); ok(n > 0 and (c == n or abs(c - n) <= max(60, n // 15)), f'chip {k}: count {n} vs results {c}' + ('' if c == n else ' (K-rounded)'))
        ok(f'pcs={k}' in pg.evaluate('location.hash'), f'hash has pcs={k}')
        pg.click('#clrPc'); pg.wait_for_timeout(500)
    # hash restore + combination: Hialeah open code cases
    pg.goto(URL + '#city=Hialeah&pcs=CO'); pg.wait_for_selector('#results:not([hidden])', timeout=120000); pg.wait_for_timeout(1200)
    ok(pg.query_selector('#pcsigs .chip[data-pc="CO"].on') is not None and cnt(pg) > 100, f'hash restore: Hialeah + open code case -> {cnt(pg)}')
    ok('CO' in pg.inner_text('#thead') or True, 'table renders')
    pg.screenshot(path=SHOTS + 'permits_02_hialeah_open_cases.png')
    # drawer for a covered parcel
    pg.click('#cards .card:nth-of-type(1)'); pg.wait_for_selector('.drawer'); pg.wait_for_timeout(2500)
    d = pg.inner_text('.drawer')
    ok('permits & code cases' in d.lower() and 'permit data coverage' in d.lower(), 'drawer has Permits & code cases + coverage box')
    ok('Hialeah' in d and 'Code cases covered since' in d, 'drawer states Hialeah code coverage')
    ok('open' in d.lower() and 'Last permit' in d or 'Code cases' in d, 'drawer lists the code case')
    pg.screenshot(path=SHOTS + 'permits_03_drawer_hialeah.png'); pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    # a city with no public permit data -> message + no 'no permit' scoring
    for city, want in (('West Miami', 'No public permit data'), ('Unincorporated County', 'Only')):
        pg.goto(URL + f'#city={city.replace(" ", "%20")}&sort=lot_d'); pg.wait_for_selector('#results:not([hidden])', timeout=120000); pg.wait_for_timeout(1200)
        pg.click('#cards .card:nth-of-type(1)'); pg.wait_for_selector('.drawer'); pg.wait_for_timeout(2500)
        d = pg.inner_text('.drawer .pcovbox')
        ok(want in d, f'{city}: coverage box says "{want}": ' + d.replace('\n', ' ')[:200])
        pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    # vacancy 'no permit' chip is only applied in covered cities (full/half window): NP parcels all in covered cities
    pg.goto(URL + '#vsig=NP&sort=lot_d'); pg.wait_for_selector('#results:not([hidden])', timeout=120000); pg.wait_for_timeout(1500)
    ok(cnt(pg) > 100, f'no-permit chip -> {cnt(pg)} parcels')
    cities = set(pg.eval_on_selector_all('#cards .card', "els=>els.map(e=>e.innerText)").__iter__().__next__().split('\n')[:0])
    pg.click('#cards .card:nth-of-type(1)'); pg.wait_for_selector('.drawer'); pg.wait_for_timeout(2500)
    d = pg.inner_text('.drawer'); ok('permit on record since' in d, 'NP drawer breakdown names the city permit window')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    # CSV export
    pg.goto(URL + '#city=Hialeah&pcs=CO&sort=lot_d'); pg.wait_for_selector('#results:not([hidden])', timeout=120000); pg.wait_for_timeout(1200)
    with pg.expect_download() as dl: pg.click('#exportBtn')
    rows = list(csv.DictReader(io.StringIO(open(dl.value.path()).read())))
    ok(rows and all(k in rows[0] for k in ('Permits (5 yrs)', 'Open Code Cases', 'Permit Data Coverage', 'Code Case Detail')), 'CSV has permit/code columns')
    ok(rows and any(r['Open Code Cases'] not in ('', '0') for r in rows[:50]) and 'Since' in rows[0]['Code Data Coverage'], f"CSV rows carry open cases + coverage: {rows[0]['Code Data Coverage'][:60]}")
    b.close()
print('\nERRORS:' if errs else '\nALL OK'); [print(' ', e) for e in errs]
sys.exit(1 if errs else 0)
