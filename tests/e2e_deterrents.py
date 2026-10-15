"""Light copy deterrents (deterrents.js): right-click / view-source / save shortcuts blocked, image drag blocked, UI text not selectable,
but inputs stay selectable/copyable, tel:/sms: links, CSV exports, Mark as sent and the county switcher still work.
usage: python3 tests/e2e_deterrents.py [url] [desktop|mobile]"""
import sys, json, csv, io
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
BASE = URL.split('#')[0].split('?')[0]; Q = '?drive=0' if MOB else ''
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
# records, in the bubble phase on window, whether a given event type was default-prevented
PROBE = """(()=>{ window.__dp={}; for (const t of ['contextmenu','keydown','dragstart','copy','selectstart','click']) window.addEventListener(t, e=>{ window.__dp[t]=e.defaultPrevented; }); })()"""
with sync_playwright() as pw:
    b = pw.chromium.launch(); vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, accept_downloads=True, service_workers='block'); pg = ctx.new_page(); pg.set_default_timeout(120000)
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    pg.goto(BASE + Q, timeout=180000)
    if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
    pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(800)
    pg.evaluate(PROBE)
    def dp(t): return pg.evaluate(f'window.__dp[{json.dumps(t)}]')
    def fire(t, sel, **kw):  # dispatch a synthetic cancelable event at selector, return defaultPrevented
        return pg.evaluate("([t,s,kw])=>{const el=document.querySelector(s); const ev=(t==='keydown')?new KeyboardEvent(t,Object.assign({bubbles:true,cancelable:true},kw)):(t==='dragstart')?new Event(t,{bubbles:true,cancelable:true}):new MouseEvent(t,{bubbles:true,cancelable:true}); el.dispatchEvent(ev); return ev.defaultPrevented;}", [t, sel, kw])
    # static bits
    ok(pg.get_attribute('meta[name=robots]', 'content') == 'noindex,nofollow', 'robots noindex,nofollow meta')
    ok('© Prop Hunters LLC. Not for redistribution.' in pg.inner_text('#copyr'), 'copyright footer present')
    ok(pg.evaluate("!!document.getElementById('pf-deterrents')"), 'deterrents.js active')
    # selection CSS
    us = lambda s: pg.evaluate(f"getComputedStyle(document.querySelector({json.dumps(s)})).userSelect")
    ok(us('body') == 'none' and us('header.top h1') == 'none', 'UI text is not selectable')
    ok(us('#q') == 'text' and us('#zips') == 'text', 'inputs keep text selection')
    # context menu / keys
    ok(fire('contextmenu', '#cards') or fire('contextmenu', 'header.top h1'), 'right-click on page content is blocked')
    ok(fire('contextmenu', 'header.top h1'), 'right-click on header blocked')
    ok(not fire('contextmenu', '#q'), 'right-click inside an input still allowed (paste menu)')
    for name, kw in [('Ctrl+S', dict(key='s', code='KeyS', ctrlKey=True)), ('Cmd+S', dict(key='s', code='KeyS', metaKey=True)), ('Ctrl+U', dict(key='u', code='KeyU', ctrlKey=True)),
                     ('Ctrl+Shift+I', dict(key='I', code='KeyI', ctrlKey=True, shiftKey=True)), ('Ctrl+Shift+J', dict(key='J', code='KeyJ', ctrlKey=True, shiftKey=True)),
                     ('Ctrl+Shift+C', dict(key='C', code='KeyC', ctrlKey=True, shiftKey=True)), ('Cmd+Opt+I', dict(key='i', code='KeyI', metaKey=True, altKey=True)), ('F12', dict(key='F12', code='F12'))]:
        ok(fire('keydown', 'body', **kw), f'{name} blocked')
        ok(fire('keydown', '#q', **kw), f'{name} blocked inside input too')
    for name, kw in [('Ctrl+C', dict(key='c', code='KeyC', ctrlKey=True)), ('Ctrl+V', dict(key='v', code='KeyV', ctrlKey=True)), ('Ctrl+A', dict(key='a', code='KeyA', ctrlKey=True)), ('Ctrl+F', dict(key='f', code='KeyF', ctrlKey=True)), ('Escape', dict(key='Escape', code='Escape'))]:
        ok(not fire('keydown', '#q', **kw), f'{name} still allowed')
    # image drag-saving + tel:/sms: links + selection in non-inputs
    pg.evaluate("""()=>{const i=document.createElement('img'); i.id='tImg'; i.src='icons/icon-192.png'; document.body.appendChild(i);
      for (const [id,h] of [['tTel','tel:+13055550100'],['tSms','sms:+13055550100'],['tMail','mailto:a@b.co']]) { const a=document.createElement('a'); a.id=id; a.href=h; a.textContent=h; a.addEventListener('click',e=>{ window.__lnk=(window.__lnk||[]).concat(id+':'+!e.defaultPrevented); e.preventDefault(); }); document.body.appendChild(a); } }""")
    ok(fire('dragstart', '#tImg'), 'dragging an image is blocked')
    pg.evaluate("document.getElementById('tTel').click(); document.getElementById('tSms').click(); document.getElementById('tMail').click()")
    ok(pg.evaluate('window.__lnk') == ['tTel:true', 'tSms:true', 'tMail:true'], 'tel:/sms:/mailto: link clicks are not prevented')
    ok(fire('selectstart', 'header.top h1'), 'selectstart on UI blocked')
    ok(not fire('selectstart', '#q'), 'selectstart in input allowed')
    # input selection + copy
    pg.fill('#q', 'hello world'); pg.focus('#q'); pg.keyboard.press('Control+A')
    ok(pg.evaluate("(()=>{const q=document.getElementById('q'); return q.selectionEnd-q.selectionStart})()") == 11, 'text in input can be selected (Ctrl+A -> 11 chars)')
    pg.evaluate("window.__copy=null; document.addEventListener('copy',e=>{window.__copy=e.defaultPrevented},false)")
    pg.keyboard.press('Control+C'); ok(pg.evaluate('window.__copy') is False, 'copy inside an input is not prevented')
    pg.evaluate("document.getElementById('tImg').remove()")
    pg.fill('#q', '')
    # mouse right-click for real on the header: no menu event default left unprevented
    pg.evaluate("window.__dp={}"); pg.click('header.top h1', button='right'); ok(dp('contextmenu') is True, 'real right-click on header is default-prevented')
    # CSV export + Mark as sent
    def go(h): pg.evaluate(f"location.hash={json.dumps(h)}"); pg.wait_for_timeout(2500)
    def jsclick(sel): pg.evaluate(f"document.querySelector({json.dumps(sel)}).click()")
    go('type=vacant&city=Homestead'); n = pg.evaluate('PF.sample(5)')['n']; ok(0 < n < 3000, f'small search: {n} results')
    with pg.expect_download() as dl: jsclick('#exportBtn')
    rows = list(csv.reader(io.StringIO(open(dl.value.path(), encoding='utf-8').read()))); ok(len(rows) - 1 == n and dl.value.suggested_filename.endswith('.csv'), f'CSV export downloads: {len(rows)-1} rows ({dl.value.suggested_filename})')
    ok(any('@' in c or c.isdigit() for r in rows[1:20] for c in r), 'exported rows still contain public contact/owner data')
    pg.wait_for_selector('#expBar:not([hidden])'); pg.select_option('#expTeam', 'sms'); pg.click('#expMark'); pg.wait_for_timeout(1500)
    ok(pg.is_hidden('#expBar'), 'Mark as sent works (bar closes)')
    f0 = rows[1][3].replace('-', ''); it = pg.evaluate(f'PF.SV.get("{f0}")')
    ok(bool(it and it['acts'] and it['acts'][0]['outcome'] == 'Sent to list'), 'sent activity logged')
    # open a card drawer by click (links/buttons still work)
    go('type=vacant&city=Homestead'); pg.wait_for_selector('#cards .card'); pg.evaluate("document.querySelector('#cards .card').click()"); pg.wait_for_selector('#drawerHost *', timeout=20000)
    ok(pg.evaluate("document.getElementById('drawerHost').innerHTML.length") > 500, 'property drawer opens')
    # county switcher
    pg.goto(BASE + '?county=miami-dade' + ('&drive=0' if MOB else ''), timeout=180000); pg.wait_for_function('window.PF_READY', timeout=240000)
    pg.select_option('#countySel', 'monroe'); pg.wait_for_function("window.PFCounty && PFCounty.id==='monroe' && window.PF_READY", timeout=240000); pg.wait_for_timeout(1500)
    ok(pg.evaluate('PFCounty.id') == 'monroe' and 'county=monroe' in pg.url and pg.inner_text('header.top h1').lower().startswith('monroe'), 'county switcher -> Monroe works')
    ok(pg.evaluate("!!document.getElementById('pf-deterrents')"), 'deterrents still active after county switch')
    ok(pg.query_selector('#cards .card') is not None, 'Monroe cards render')
    b.close()
print(f'[{TAG}] ' + ('ALL PASS' if not errs else f'{len(errs)} FAIL: ' + '; '.join(errs[:8])))
sys.exit(1 if errs else 0)
