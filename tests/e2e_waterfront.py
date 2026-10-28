"""Waterfront / oceanfront filter, every county (Miami-Dade, Broward, Monroe): data file sanity, the select (+ counts), hash link,
every result carries the picked water bit, card tag, drawer line, CSV 'Waterfront' column appended at the end, Clear resets.
argv: URL [desktop|mobile] [SHOTS_DIR]"""
import sys, json, gzip, csv, io, os, urllib.request
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8115/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
SHOTS = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shots', 'waterfront'); os.makedirs(SHOTS, exist_ok=True)
BASE = URL.split('#')[0].split('?')[0]
HDR = ['Owner Name', 'Property Address', 'Property City', 'Property State', 'Property Zip', 'Property County', 'Mailing Address', 'Mailing City', 'Mailing State', 'Mailing Zip', 'Folio']
COUNTIES = [('miami-dade', '', 'Miami-Dade'), ('broward', 'broward/', 'Broward'), ('monroe', 'monroe/', 'Monroe')]
MASK = {'any': 15, 'o': 1, 'b': 2, 'c': 4, 'l': 8}
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
with sync_playwright() as pw:
    b = pw.chromium.launch(); vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, service_workers='block', accept_downloads=True); pg = ctx.new_page(); pg.set_default_timeout(120000)
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    for cid, d, name in COUNTIES:
        raw = urllib.request.urlopen(BASE + 'data/' + d + 'water.json.gz', timeout=60).read()
        W = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw); c = W['counts']
        G = {}
        for k, v in W['groups'].items():
            for f in (v.split(',') if v else []): G[f] = int(k)
        ok(W['county'] == cid and c['any'] == len(G) > 500, f"{name}: water file {c['any']:,} waterfront ({c['ocean']:,} ocean, {c['bay']:,} bay, {c['canal']:,} canal, {c['lake']:,} lake)")
        ok(c['ocean'] > 100 and c['ocean'] == sum(1 for b2 in G.values() if b2 & 1), f'{name}: oceanfront count matches the groups')
        q = '?county=' + cid + ('&drive=0' if MOB else '')
        def boot(h):
            pg.goto('about:blank'); pg.goto(BASE + q + '#' + h, timeout=180000)
            if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
            pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_function('window.PFWF && PFWF.data', timeout=90000); pg.wait_for_timeout(2500)
        boot('gov=1&wf=o')
        s = pg.evaluate('PF.sample(3000)'); n = s['n']
        ok(n > 0 and all(r['wf'] & 1 for r in s['rows']), f'{name}: #wf=o -> {n:,} results, every sampled row is oceanfront')
        ok(all(G.get(r['folio'], 0) & 1 for r in s['rows']), f'{name}: sampled oceanfront folios are in the water file')
        ok(pg.evaluate("document.getElementById('wfSel').value") == 'o', f'{name}: select reflects the link')
        opt = pg.evaluate("[...document.getElementById('wfSel').options].map(o=>o.textContent)")
        ok(len(opt) == 6 and all('(' in t for t in opt[1:]), f'{name}: every option shows a count {opt}')
        ok(pg.locator('#cards .card .tt.wf').count() > 0 and 'Oceanfront' in pg.inner_text('#cards .card .tt.wf >> nth=0'), f'{name}: cards show the Oceanfront tag')
        ok(name in pg.inner_text('#wfSrc'), f"{name}: source line {pg.inner_text('#wfSrc')[:110]!r}")
        pg.screenshot(path=os.path.join(SHOTS, f'wf_{cid}_{TAG}.png'))
        # each option through the UI
        for v in ['any', 'b', 'c', 'l']:
            pg.select_option('#wfSel', v) if pg.is_visible('#wfSel') else pg.evaluate(f"(()=>{{const e=document.getElementById('wfSel'); e.value='{v}'; e.dispatchEvent(new Event('change'))}})()")
            pg.wait_for_timeout(2500); s2 = pg.evaluate('PF.sample(1500)')
            ok(all(r['wf'] & MASK[v] for r in s2['rows']) and ('wf=' + v) in pg.evaluate('location.hash'), f"{name}: wf={v} -> {s2['n']:,}, all rows match, hash updated")
            if v == 'any': ok(s2['n'] >= n, f'{name}: any waterfront >= oceanfront')
        # drawer
        pg.select_option('#wfSel', 'o') if pg.is_visible('#wfSel') else pg.evaluate("(()=>{const e=document.getElementById('wfSel'); e.value='o'; e.dispatchEvent(new Event('change'))})()")
        pg.wait_for_timeout(2500)
        if pg.locator('#cards .card').count():
            pg.locator('#cards .card').first.click(); pg.wait_for_timeout(2500)
            t = pg.inner_text('body'); ok('Waterfront' in t and 'Oceanfront' in t, f'{name}: drawer shows the Waterfront line')
            pg.keyboard.press('Escape'); pg.wait_for_timeout(600)
        # CSV
        if not MOB:
            with pg.expect_download(timeout=240000) as dl: pg.evaluate("document.querySelector('#exportBtn').click()")
            rows = list(csv.reader(io.StringIO(open(dl.value.path(), encoding='utf-8').read())))
            ok(rows[0][:11] == HDR and (rows[0][-1] == 'Waterfront' or rows[0][-4:] == ['Waterfront', 'Power / water cut', 'Utility shut off date', 'Utility shut off source']), f'{name}: CSV header = 11 fixed columns, Waterfront last (or before Power / water cut) ({rows[0][11:]})')
            ok(len(rows) > 1 and all('Oceanfront' in r[rows[0].index('Waterfront')] for r in rows[1:]), f'{name}: every exported row says Oceanfront ({len(rows) - 1:,} rows)')
        # clear
        pg.evaluate("document.getElementById('clrWf').click()"); pg.wait_for_timeout(2500)
        ok(pg.evaluate("document.getElementById('wfSel').value") == '' and 'wf=' not in pg.evaluate('location.hash') and pg.evaluate('PF.sample(10)')['n'] >= n, f'{name}: Clear removes the filter')
    b.close()
print(('FAILED: ' + '; '.join(errs[:8])) if errs else f'ALL PASS [{TAG}]')
sys.exit(1 if errs else 0)
