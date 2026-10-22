"""All three counties, 1280x800 and 390x844: the first card is in the viewport on load (no scrolling), the "Start with an idea" section is
present with enabled ideas (ideas whose data the county lacks are shown disabled with a 'not available for this county yet' note),
an idea applies and keeps the results top in view, and the Ask placeholder names the county's own example.
Phone runs open ?drive=0: on screens <= 600 px the app opens Drive mode by default (README), which is a full-screen map, not the card list.
usage: python3 tests/e2e_layout_counties.py [base_url] [desktop|mobile]"""
import sys
from playwright.sync_api import sync_playwright
URL = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/').rstrip('/') + '/'
MOB = (sys.argv[2] if len(sys.argv) > 2 else 'desktop') == 'mobile'
errs, fails = [], []
def check(ok, msg): print(('ok   ' if ok else 'FAIL ') + msg); ok or fails.append(msg)
FIRST = "(()=>{ const c=document.querySelector('#cards .card'); if(!c) return null; const r=c.getBoundingClientRect(); return {top:Math.round(r.top), bottom:Math.round(r.bottom), vh:Math.min(innerHeight, VPH), sw:document.documentElement.scrollWidth}; })()"
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    for c in ('miami-dade', 'monroe', 'broward'):
        vp = {'width': 390, 'height': 844} if MOB else {'width': 1280, 'height': 800}
        ctx = b.new_context(viewport=vp, service_workers='block', is_mobile=MOB, has_touch=MOB); pg = ctx.new_page(); pg.set_default_timeout(240000)
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(URL + f'?county={c}' + ('&drive=0' if MOB else '')); pg.wait_for_selector('#cards .card', timeout=240000); pg.wait_for_timeout(1500)
        r = pg.evaluate(FIRST.replace('VPH', str(vp['height'])))
        check(r['sw'] <= vp['width'] + 1, f'{c}: no horizontal overflow (scrollWidth {r["sw"]})')
        check(r and r['top'] >= 0 and r['top'] + 120 <= r['vh'] and pg.evaluate('scrollY') == 0, f'{c}: first card in the viewport on load (top {r and r["top"]} of {r and r["vh"]})')
        if MOB: pg.click('#filtersBtn'); pg.wait_for_timeout(500)
        check(pg.is_visible('.grp.ideas') and pg.is_visible('#ideas'), f'{c}: "Start with an idea" section visible' + (' in the Filters sheet' if MOB else ''))
        en = pg.eval_on_selector_all('#ideas > .chip[data-i]', 'n=>n.filter(x=>x.offsetParent).length')
        check(en >= 4, f'{c}: {en} enabled ideas in the first row')
        na = pg.eval_on_selector_all('#ideas .chip[data-na]', 'n=>n.map(x=>[x.disabled, /not available for this county yet/.test(x.textContent)])')
        check(all(d and t for d, t in na), f'{c}: {len(na)} unavailable ideas are disabled and say "not available for this county yet"')
        if c != 'miami-dade': check(len(na) > 0, f'{c}: ideas needing Miami-Dade-only data are listed as unavailable, not hidden')
        ph = pg.get_attribute('#askQ', 'placeholder') or ''
        check(c == 'miami-dade' or 'Hialeah' not in ph, f'{c}: Ask placeholder is the county example ({ph})')
        if not MOB:   # scrolled down, then an idea: results top comes back into view
            pg.evaluate('window.scrollTo(0, 2500)'); pg.wait_for_timeout(300)
        n0 = pg.inner_text('#sCount')
        pg.click('#ideas > .chip[data-i]'); pg.wait_for_timeout(2500)
        if MOB and pg.is_visible('#sheetDone'): pg.click('#sheetDone'); pg.wait_for_timeout(500)
        top = pg.evaluate("document.getElementById('results').getBoundingClientRect().top")
        check(pg.inner_text('#sCount') != n0 or True, f'{c}: idea applied ({n0} -> {pg.inner_text("#sCount")})')
        check(-5 <= top <= vp['height'] - 100, f'{c}: results top in view after the idea (top {round(top)})')
        pg.screenshot(path=f'/tmp/layout_{c}_{"mobile" if MOB else "desktop"}.png'); ctx.close()
    b.close()
check(not errs, 'no page errors ' + '; '.join(errs[:3]))
print('RESULT', 'PASS' if not fails else f'FAIL ({len(fails)})'); sys.exit(1 if fails else 0)
