"""Estimated owner equity (Miami-Dade): data file sanity, card line / badge / drawer, free & clear + min-equity filters (hash + UI),
presets, Ask box ("free and clear", "equity over 50%"), table columns, CSV export (11 fixed columns first, equity columns appended),
Monroe/Broward hide it. argv: URL [desktop|mobile] [SHOTS_DIR]"""
import sys, json, gzip, csv, io, os, urllib.request
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8097/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
SHOTS = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shots', 'equity'); os.makedirs(SHOTS, exist_ok=True)
BASE = URL.split('#')[0].split('?')[0]; Q = '?drive=0&' if MOB else '?'
HDR = ['Owner Name', 'Property Address', 'Property City', 'Property State', 'Property Zip', 'Property County', 'Mailing Address', 'Mailing City', 'Mailing State', 'Mailing Zip', 'Folio']
EQH = ['Est Equity $', 'Est Equity %', 'Est Loan Balance', 'Open Mortgages', 'Lender', 'Free & Clear', 'Equity Checked']
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
raw = urllib.request.urlopen(BASE + 'data/equity.json.gz', timeout=60).read()
E = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw); R = {r[0]: r for r in E['rows']}
FC = {f for f, r in R.items() if r[2] == 0 and 'c' not in r[7]}
ok(len(R) > 50 and E['meta']['county'] == 'Miami-Dade', f"equity file: {len(R):,} parcels checked, {len(FC):,} free & clear")
ok(all(r[5] == r[4] - r[1] for r in E['rows'] if r[4]), 'equity = value - est. balance on every row')
ok(all(abs(r[1] - sum(l[4] for l in r[9] if l[4] is not None)) <= 3 or r[2] > 6 for r in E['rows']), 'balance = sum of open loan estimates')
ok(all(r[1] == 0 for r in E['rows'] if r[0] in FC), 'free & clear rows carry no balance')
with sync_playwright() as pw:
    b = pw.chromium.launch(); vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, service_workers='block', accept_downloads=True); pg = ctx.new_page(); pg.set_default_timeout(120000)
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    def boot(url):
        pg.goto('about:blank'); pg.goto(url, timeout=180000)
        if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_function('window.PFEQ && PFEQ.data', timeout=60000); pg.wait_for_timeout(1200)
    def go(h): pg.evaluate(f"location.hash={json.dumps(h)}"); pg.wait_for_timeout(2500)
    samp = lambda k=2000: pg.evaluate(f'PF.sample({k})')
    # 1. free & clear filter by link
    boot(BASE + Q.rstrip('&?') + '#fc=1&gov=1'); s = samp()
    ok(s['n'] > 0 and all(r['folio'] in FC for r in s['rows']), f"#fc=1: {s['n']:,} results, all free & clear")
    ok(s['n'] <= len(FC), 'never more than the free & clear set')
    ok(pg.evaluate("document.getElementById('eqFC').checked"), 'Free & clear checkbox reflects the link')
    ok(pg.locator('#cards .card .eqfc').count() > 0, 'cards show the Free & clear (est.) tag')
    t = pg.inner_text('#cards .card .eqline') if pg.locator('#cards .card .eqline').count() else ''
    ok('Free & clear' in t and 'est. equity' in t, f'card equity line: {t.strip()[:90]!r}')
    ttl = pg.get_attribute('#cards .card .eqline .v', 'title') or ''
    ok('ESTIMATE' in ttl, 'card line tooltip says it is an estimate')
    pg.screenshot(path=os.path.join(SHOTS, f'eq_fc_{TAG}.png'))
    # 2. min equity
    go('eq=50&gov=1'); s = samp()
    bad = [r['folio'] for r in s['rows'] if not (r['folio'] in FC or (r['folio'] in R and R[r['folio']][6] is not None and R[r['folio']][6] >= 50))]
    ok(s['n'] > 0 and not bad, f"#eq=50: {s['n']:,} results, all est. equity >= 50% or free & clear (bad {bad[:3]})")
    ok(pg.evaluate("document.getElementById('eqMin').value") == '50', 'min equity select reflects the link')
    n50 = s['n']; go('eq=90&gov=1'); n90 = samp()['n']; ok(n90 <= n50, f'90%+ ({n90}) <= 50%+ ({n50})')
    # 3. UI control
    go('gov=1'); n0 = samp()['n']
    pg.evaluate("(()=>{const e=document.getElementById('eqMin'); e.value='70'; e.dispatchEvent(new Event('change'))})()"); pg.wait_for_timeout(2500)
    n70 = samp()['n']; ok(0 < n70 < n0, f'select 70%+ narrows {n0:,} -> {n70:,}'); ok('eq=70' in pg.evaluate('location.hash'), 'filter goes into the link')
    pg.evaluate("(()=>{const e=document.getElementById('eqMin'); e.value='0'; e.dispatchEvent(new Event('change'))})()"); pg.wait_for_timeout(1500)
    # 4. card with open loans + drawer
    opn = next((f for f, r in sorted(R.items()) if r[2] > 0 and r[1] > 0 and r[4]), None)
    if opn:
        fd = f'{opn[:2]}-{opn[2:6]}-{opn[6:9]}-{opn[9:]}'
        boot(BASE + Q + 'folio=' + fd); pg.wait_for_selector('.drawer', timeout=60000); pg.wait_for_timeout(800)
        d = pg.text_content('.drawer'); r = R[opn]
        ok('Estimated equity' in d and f"{r[1]:,}" in d, f'drawer shows equity block with est. balance ${r[1]:,} for {opn}')
        ok(r[9][0][5] in d, 'drawer lists the Clerk CFN of the open mortgage')
        pg.screenshot(path=os.path.join(SHOTS, f'eq_drawer_{TAG}.png')); pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
        c = pg.locator(f'.card[data-folio="{opn}"] .eqline')
        ok(c.count() == 1 and 'est. loans' in c.inner_text() and 'open' in c.inner_text(), 'card shows est. loans, # open, lender, est. equity')
    # 5. presets + Ask
    boot(BASE + Q.rstrip('&?') + '#gov=1')
    labs = pg.eval_on_selector_all('#ideas .chip', 'e=>e.map(x=>x.textContent)')
    ok(any('High-equity' in l for l in labs) and any('Free & clear' in l for l in labs), 'High equity + Free & clear presets offered')
    pg.fill('#askQ', 'free and clear houses'); pg.press('#askQ', 'Enter'); pg.wait_for_timeout(3500)
    ok(pg.evaluate("document.getElementById('eqFC').checked") and 'fc=1' in pg.evaluate('location.hash'), 'Ask "free and clear houses" -> Free & clear filter')
    pg.fill('#askQ', 'equity over 50%'); pg.press('#askQ', 'Enter'); pg.wait_for_timeout(3500)
    ok(pg.evaluate("document.getElementById('eqMin').value") == '50', 'Ask "equity over 50%" -> min equity 50%')
    # 6. table + export
    go('fc=1&gov=1&view=table'); pg.wait_for_timeout(1500)
    th = [x.strip() for x in pg.eval_on_selector_all('#thead th', 'e=>e.map(x=>x.textContent)')]
    ok(th[-2:] == ['Est. equity', 'Est. loans'], f'table has Est. equity / Est. loans columns at the end ({th[-3:]})')
    with pg.expect_download(timeout=240000) as dl: pg.evaluate("document.querySelector('#exportBtn').click()")
    rows = list(csv.reader(io.StringIO(open(dl.value.path(), encoding='utf-8').read())))
    ok(rows[0] in (HDR + EQH, HDR + EQH + ['Waterfront']), f'CSV: the 11 fixed columns in order, equity columns appended at the end ({rows[0][9:]})')
    body = rows[1:]; ok(body and all(len(x) == 18 and x[16] == 'Y' and x[13] == '0' for x in body), f'CSV: {len(body)} rows, all Free & Clear = Y, balance 0')
    # 7. other counties hide it
    for cty in ('monroe', 'broward'):
        pg.goto('about:blank'); pg.goto(BASE + Q + 'county=' + cty, timeout=180000)
        if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_function('window.PF_READY', timeout=240000)
        ok(pg.evaluate("(()=>{const e=document.querySelector('.eqrow'); return !e||e.hidden||!e.offsetParent})()"), f'{cty}: equity filter hidden (no Clerk mortgage data)')
        ok(not any('equity' in l.lower() for l in pg.eval_on_selector_all('#ideas .chip:not([data-na])', 'e=>e.map(x=>x.textContent)')), f'{cty}: no enabled equity presets (unavailable ones disabled)')
    b.close()
print(f'{len(errs)} failures: {errs}' if errs else 'ALL PASS'); sys.exit(1 if errs else 0)
