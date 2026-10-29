"""Mark as sent after the MAIN export (sticky orange bar, team picker Text/SMS / Call center / Door knock / Mail), Text/SMS + Mail teams
in Send to, Tag all results, Already contacted filter, Hide already sent. argv: URL [desktop|mobile]"""
import sys, json, csv, io
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
BASE = URL.split('#')[0].split('?')[0]; Q = '?drive=0' if MOB else ''
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
    n_of = lambda: pg.evaluate('PF.sample(5)')['n']
    def jsclick(sel): pg.evaluate(f"document.querySelector({json.dumps(sel)}).click()")
    def setcheck(sel, v): pg.evaluate(f"(()=>{{const e=document.querySelector({json.dumps(sel)}); if(e.checked!=={str(v).lower()}){{e.checked={str(v).lower()}; e.dispatchEvent(new Event('change',{{bubbles:true}}));}}}})()"); pg.wait_for_timeout(2000)
    go('type=vacant&city=Homestead'); n = n_of(); ok(0 < n < 3000, f'small search: {n} results')
    with pg.expect_download() as dl: jsclick('#exportBtn')
    rows = list(csv.reader(io.StringIO(open(dl.value.path(), encoding='utf-8').read()))); ok(len(rows) - 1 == n, f'main export: {len(rows)-1} rows')
    pg.wait_for_selector('#expBar:not([hidden])'); bar = pg.inner_text('#expBar')
    ok(f'Mark these {n:,}' in bar and 'as sent' in bar, f'sticky bar after main export: "{bar[:80]}"')
    ok(pg.evaluate("getComputedStyle(document.getElementById('expBar')).position") == 'sticky', 'bar is sticky')
    opts = pg.eval_on_selector_all('#expTeam option', 'e=>e.map(x=>x.textContent)'); ok(opts == ['Text / SMS', 'Call center', 'Door knock', 'Mail', 'Smarter Contact'], f'team options {opts}')
    pg.select_option('#expTeam', 'sms'); pg.click('#expMark'); pg.wait_for_timeout(1500)
    ok(pg.is_hidden('#expBar'), 'bar closes after marking')
    f0 = rows[1][10].replace('-', ''); it = pg.evaluate(f'PF.SV.get("{f0}")')
    ok(it and it['acts'] and it['acts'][0]['type'] == 'text' and it['acts'][0]['outcome'] == 'Sent to list', 'outreach activity (text, Sent to list) logged on an exported folio')
    sent = pg.evaluate(f"JSON.parse(localStorage.getItem('{pg.evaluate('Object.keys(localStorage).find(k=>/send/i.test(k))')}')).sent")
    ok(sum(1 for r in rows[1:] if r[10].replace('-', '') in sent and 'sms' in sent[r[10].replace('-', '')]) == n, 'all exported folios marked sent to Text / SMS with the date')
    # filters
    go('type=vacant&city=Homestead&cont=1'); ok(n_of() == n, f'Already contacted shows the {n} reached')
    go('type=vacant&city=Homestead&hs=1'); ok(n_of() == 0, 'Hide already sent hides them')
    go('type=vacant&city=Florida%20City'); m = n_of()
    go('type=vacant&city=Florida%20City&hs=1'); ok(n_of() == m and m > 0, 'other search unaffected by Hide already sent')
    # Send to: Text / SMS team + Tag all
    chips = pg.eval_on_selector_all('#sendChips .chip', 'e=>e.map(x=>x.textContent)'); ok(any(c.startswith('Text / SMS') for c in chips) and any(c.startswith('Mail') for c in chips), f'Send to has Text / SMS and Mail: {chips}')
    go('type=vacant&city=Florida%20City'); pg.evaluate("document.getElementById('tagAllTeam').value='sms'"); jsclick('#tagAll'); pg.wait_for_timeout(1500)
    ti = pg.evaluate("document.getElementById('tagAllInfo').textContent"); ok(f'{m:,} newly tagged' in ti, f'Tag all results: {ti}')
    jsclick('#sendChips .chip[data-send="sms"]'); pg.wait_for_timeout(2000); ok(n_of() == m, 'Text / SMS filter shows the tagged results')
    with pg.expect_download() as dl: jsclick('#sendExp-sms')
    r2 = list(csv.reader(io.StringIO(open(dl.value.path(), encoding='utf-8').read()))); ok(len(r2) - 1 == m and r2[0] == ['Owner Name', 'Property Address', 'Property City', 'Property State', 'Property Zip', 'Property County', 'Mailing Address', 'Mailing City', 'Mailing State', 'Mailing Zip', 'Folio'], f'Text / SMS list export: {len(r2)-1} rows')
    jsclick('#sendBar [data-sendmark="1"]'); pg.wait_for_timeout(1000); ok(pg.is_disabled('#sendExp-sms'), 'after Mark as sent nothing new for Text / SMS')
    b.close()
print(f'[{TAG}] ' + ('ALL PASS' if not errs else f'{len(errs)} FAIL: ' + '; '.join(errs[:8])))
sys.exit(1 if errs else 0)
