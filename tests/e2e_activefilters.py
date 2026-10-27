"""Active filters bar (above Cards / Table / Map), every county: hidden with no filters; preset chips (Preset + its filters + Sort);
chips for select / money-shorthand / checkbox / county-layer filters; × removes only that filter and re-runs; Clear all hides the bar;
phone: one compact horizontally scrolling row. argv: URL [desktop|mobile] [SHOTS_DIR]"""
import sys, os, re
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8117/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
SHOTS = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shots', 'activefilters'); os.makedirs(SHOTS, exist_ok=True)
BASE = URL.split('#')[0].split('?')[0]
COUNTIES = [('miami-dade', 'Miami-Dade'), ('broward', 'Broward'), ('monroe', 'Monroe')]
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
with sync_playwright() as pw:
    b = pw.chromium.launch(); vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, service_workers='block'); pg = ctx.new_page(); pg.set_default_timeout(120000)
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    chips = lambda: pg.evaluate("[...document.querySelectorAll('#afBar .afchip')].map(e=>e.textContent.replace('×','').trim())")
    shown = lambda: pg.evaluate("!document.getElementById('afBar').hidden")
    def setv(id, v, ev='change'):
        pg.evaluate(f"(()=>{{const e=document.getElementById('{id}'); if(e.type==='checkbox') e.checked={str(v).lower()}; else e.value={v!r}; e.dispatchEvent(new Event('{ev}',{{bubbles:true}}))}})()"); pg.wait_for_timeout(2200)
    def x(prefix):
        i = pg.evaluate(f"[...document.querySelectorAll('#afBar .afchip')].findIndex(e=>e.textContent.startsWith({prefix!r}))")
        pg.evaluate(f"document.querySelectorAll('#afBar .afchip')[{i}].click()") if i >= 0 else None; pg.wait_for_timeout(2500); return i >= 0
    for cid, name in COUNTIES:
        pg.goto('about:blank'); pg.goto(BASE + '?county=' + cid + ('&drive=0' if MOB else '') + '#', timeout=180000)
        if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(2500)
        pg.evaluate("document.getElementById('resetBtn').click()"); pg.wait_for_timeout(2500)
        ok(not shown(), f'{name}: bar hidden with no filters')
        # preset
        pg.evaluate("[...document.querySelectorAll('#ideas .chip:not([disabled])')].find(b=>b.textContent.trim()==='Teardowns').click()"); pg.wait_for_timeout(4000)
        c = chips(); ok(shown() and f'County: {name}' in c and 'Preset: Teardowns' in c and 'Teardown' in c and any(t.startswith('Sort: Most value in the land') for t in c), f'{name}: preset chips {c}')
        ok(pg.inner_text('#afN') == pg.inner_text('#sCount'), f"{name}: bar count {pg.inner_text('#afN')} = results count")
        n1 = pg.inner_text('#sCount'); setv('utSel', 'any'); n2 = pg.inner_text('#sCount')
        ok('Power / water cut: Any power / water signal' in chips() and n2 != n1, f'{name}: Power / water chip appears, search narrowed {n1} -> {n2}')
        ok(x('Power / water cut') and pg.inner_text('#sCount') == n1 and 'Teardown' in chips() and pg.evaluate("document.getElementById('utSel').value") == '', f'{name}: × removes just that filter and re-runs (back to {n1}, Teardown kept)')
        pg.evaluate("[...document.querySelectorAll('#ideas .chip:not([disabled])')].find(b=>b.textContent.trim()==='Teardowns').click()"); pg.wait_for_timeout(4000)
        # more filters: money shorthand, select, checkbox, county layer
        pg.evaluate("document.getElementById('mvMin').value='200k';document.getElementById('mvMax').value='500k';document.getElementById('mvMax').dispatchEvent(new Event('input',{bubbles:true}))"); pg.wait_for_timeout(2500)
        setv('utSel', 'any'); setv('wfSel', 'c'); setv('ow_oos', 'yes'); setv('apOnly', True)
        pg.evaluate("document.querySelector('#ownerKind [data-k=\"person\"]').click()"); pg.wait_for_timeout(2500)
        if cid == 'monroe': pg.evaluate("document.querySelector('#mrRate [data-mr=\"rate:G\"]').click()"); pg.wait_for_timeout(2500)
        c = chips()
        want = ['Price: $200k–$500k', 'Power / water cut: Any power / water signal', 'Waterfront: Canal', 'Only: Owner mails from out of state', 'Adverse possession claim', 'Owner: Individuals only', 'Teardown'] + (['Buildability: Green'] if cid == 'monroe' else [])
        ok(all(w in c for w in want), f'{name}: chips for each filter {c}')
        ok('Preset: Teardowns' not in c, f'{name}: preset chip drops once the filters are changed')
        ok(pg.inner_text('#afN') == pg.inner_text('#sCount'), f'{name}: count follows the results')
        pg.screenshot(path=os.path.join(SHOTS, f'af_{cid}_{TAG}.png'))
        if MOB:
            m = pg.evaluate("(()=>{const r=document.querySelector('#afBar .afrow'), cs=getComputedStyle(r); return {wrap:cs.flexWrap, ox:cs.overflowX, sw:r.scrollWidth, cw:r.clientWidth, h:document.getElementById('afBar').offsetHeight, bw:document.getElementById('afBar').getBoundingClientRect().right}})()")
            ok(m['wrap'] == 'nowrap' and m['ox'] == 'auto' and m['sw'] > m['cw'] and m['h'] < 110 and m['bw'] <= 391, f'{name}: phone bar is one compact horizontal scroll row {m}')
        n0 = len(c); before = pg.inner_text('#sCount')
        ok(x('Power / water cut'), f'{name}: × on Power / water cut')
        c2 = chips(); ok(not any(t.startswith('Power / water cut') for t in c2) and len(c2) == n0 - 1 and pg.evaluate("document.getElementById('utSel').value") == '' and 'ut=' not in pg.evaluate('location.hash'), f'{name}: × removed only that filter {c2}')
        ok(x('Price:') and not any(t.startswith('Price') for t in chips()) and pg.evaluate("document.getElementById('mvMin').value") == '', f'{name}: × on Price clears both boxes')
        pg.evaluate("document.getElementById('afClear').click()"); pg.wait_for_timeout(3000)
        ok(not shown() and pg.evaluate("document.getElementById('onCount').hidden"), f'{name}: Clear all hides the bar and resets the filters')
    b.close()
print('ERRORS: ' + '; '.join(errs) if errs else 'ALL PASS'); sys.exit(1 if errs else 0)
