"""Every property CSV export: exactly Owner Name,Property Address,Property City,Property State,Property Zip,Property County,Mailing Address,Mailing City,Mailing State,Mailing Zip,Folio; Folio dashed 13-digit; Address never blank
(fallback 'No site address – <use>, near <street>' / legal). Main export, saved-list export, dashed + plain folio search. argv: URL [desktop|mobile]"""
import sys, csv, io, re, json
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
BASE = URL.split('#')[0].split('?')[0]; Q = '?drive=0' if MOB else ''
HDR = ['Owner Name', 'Property Address', 'Property City', 'Property State', 'Property Zip', 'Property County', 'Mailing Address', 'Mailing City', 'Mailing State', 'Mailing Zip', 'Folio']; EQH = ['Est Equity $', 'Est Equity %', 'Est Loan Balance', 'Open Mortgages', 'Lender', 'Free & Clear', 'Equity Checked']; FD = re.compile(r'\d\d-\d{4}-\d{3}-\d{4}'); ZIP = re.compile(r'\d{5}(-\d{4})?')
BLANKS = ['3021250180770', '3040110180060', '0421320130350']
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
with sync_playwright() as pw:
    b = pw.chromium.launch(); vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, accept_downloads=True); pg = ctx.new_page(); pg.set_default_timeout(120000)
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    pg.goto(BASE + Q, timeout=180000)
    if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
    pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(800)
    def go(h): pg.evaluate(f"location.hash={json.dumps(h)}"); pg.wait_for_timeout(2500)
    def export(sel='#exportBtn'):
        if MOB and not pg.is_visible(sel):
            m = pg.query_selector('#moreBtn, .mmore, [data-more]')
            if m: m.click(); pg.wait_for_timeout(300)
        with pg.expect_download(timeout=240000) as dl: pg.evaluate(f"document.querySelector('{sel}').click()")
        t = open(dl.value.path(), encoding='utf-8').read(); return list(csv.reader(io.StringIO(t)))
    def check(rows, what):
        ok(rows and rows[0][:11] == HDR and rows[0][11:] in ([], EQH, ['Waterfront'], EQH + ['Waterfront']), f'{what}: header is the 11 contact columns in order (+ estimated-equity columns appended at the end only)')
        body = rows[1:]; bad_a = [r for r in body if not r[1].strip()]; bad_f = [r for r in body if not FD.fullmatch(r[10])]
        ok(body and not bad_a and not bad_f and all(len(r) == len(rows[0]) and r[5] == 'Miami-Dade' and r[3] == 'FL' for r in body), f'{what}: {len(body)} rows, blank Address {len(bad_a)}, non-dashed Folio {len(bad_f)}')
        bad_z = [r[4] for r in body if r[4] and not ZIP.fullmatch(r[4])]; ok(not bad_z and sum(1 for r in body if r[4]) >= 0.95 * len(body), f'{what}: Property Zip is 5-digit text ({sum(1 for r in body if r[4])}/{len(body)} filled, bad {bad_z[:3]})')
        mp = [r for r in body if r[7]]; bad_m = [r for r in mp if not (re.fullmatch(r'[A-Z]{2}', r[8]) and ZIP.fullmatch(r[9]) and ', ' + r[7] + ',' not in ', ' + r[6] + ',')]
        ok(not bad_m and all(not (r[8] or r[9]) for r in body if not r[7]), f'{what}: mailing city/state/zip split ({len(mp)}/{len(body)} parsed, bad {[r[6:10] for r in bad_m[:2]]})')
        return body
    go('q=' + ' '.join(BLANKS) + '&gov=1'); n = pg.evaluate('PF.sample(10)')['n']
    if n != 3:   # search may not take several folios at once: fall back to the vacant type
        go('type=vacant&gov=1')
    body = check(export(), f'export ({n} via folio search)')
    st = pg.evaluate('PF.expStat()'); print(f'[{TAG}] address stats {st}')
    for f in BLANKS:
        r = [x for x in body if x[10].replace('-', '') == f]
        if r: ok(r[0][1].startswith('No site address – ') and ('near ' in r[0][1] or len(r[0][1]) > 25), f'{f}: blank roll address -> "{r[0][1]}"')
    go('type=vacant&gov=1'); body = check(export(), 'vacant-land export'); st = pg.evaluate('PF.expStat()')
    print(f'[{TAG}] vacant address stats {st}'); ok(st['near'] + st['legal'] + st['use'] > 0 and st['use'] <= 0.02 * len(body), f'fallbacks: near street {st["near"]}, legal {st["legal"]}, land use only {st["use"]}; real {st["real"]}')
    # dashed and plain folio search both work
    for q in ('30-2135-002-2030', '3021350022030'):
        go('q=' + q + '&gov=1'); ok(pg.evaluate('PF.sample(5)')['n'] >= 1, f'search finds folio {q}')
    # saved-list export
    pg.evaluate("()=>{ const s=PF.sample(4).rows; s.forEach(r=>PF.SV.add(r.folio,{addr:r.addr})); }")
    go('saved=1'); pg.wait_for_timeout(1500)
    with pg.expect_download(timeout=240000) as dl: pg.evaluate("document.getElementById('svExportCsv').click()")
    check(list(csv.reader(io.StringIO(open(dl.value.path(), encoding='utf-8').read()))), 'saved-list export')
    b.close()
print(f'[{TAG}] ' + ('ALL PASS' if not errs else f'{len(errs)} FAIL: ' + '; '.join(errs[:8])))
sys.exit(1 if errs else 0)
