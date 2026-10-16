"""Monroe buildability screen: group, rating chips, filters, preset, card badge, drawer reasons + disclaimer, absentee label, qPublic link, hash round trip.
usage: python3 tests/e2e_monroe.py [base_url] [desktop|mobile]"""
import sys, re
from playwright.sync_api import sync_playwright
URL = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/').rstrip('/') + '/'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'desktop'
errs, fails = [], []
def check(ok, msg): print(('ok   ' if ok else 'FAIL ') + msg); ok or fails.append(msg)
cnt = lambda pg: int(pg.inner_text('#sCount').replace(',', '') or 0)
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    vp = {'width': 390, 'height': 800} if MODE == 'mobile' else {'width': 1300, 'height': 900}
    ctx = b.new_context(viewport=vp, service_workers='block', is_mobile=MODE == 'mobile', has_touch=MODE == 'mobile')
    pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(URL + '?county=monroe#hg=0'); pg.wait_for_selector('#results:not([hidden])', timeout=120000); pg.wait_for_selector('#cards .card', timeout=60000)
    check(pg.evaluate("PFCounty.has('monroe')"), 'Monroe has the monroe layer')
    check(pg.is_visible('#mrGrp'), 'buildability group visible'); check('Screening tool' in pg.inner_text('#mrGrp') or 'screening tool' in pg.inner_text('#mrGrp').lower(), 'group labelled screening tool')
    chips = pg.eval_on_selector_all('#mrRate .chip', 'n=>n.map(x=>x.textContent)'); check(len(chips) == 3 and 'Green' in chips[0], f'rating chips {chips}')
    n0 = cnt(pg)
    # card badge
    check(pg.query_selector('#cards .card .mrb') is not None, 'card shows a buildability badge')
    # filter: green
    pg.click('#mrRate .chip[data-mr="rate:G"]'); pg.wait_for_timeout(900); ng = cnt(pg)
    check(0 < ng < n0, f'green filter {n0} -> {ng}')
    check(pg.eval_on_selector_all('#cards .card .mrb', 'n=>n.length>0 && n.every(x=>x.classList.contains("G"))'), 'all visible cards are green')
    check('bld=G' in pg.evaluate('location.hash'), 'hash carries bld=G: ' + pg.evaluate('location.hash')[:80])
    pg.click('#mrRate .chip[data-mr="rate:Y"]'); pg.wait_for_timeout(800); ngy = cnt(pg); check(ngy > ng, f'green+yellow {ng} -> {ngy}')
    pg.click('#clrMr'); pg.wait_for_timeout(800); check(cnt(pg) == n0, 'clear restores count')
    # tier + ROGO + signals + leave out
    pg.click('#mrTier .chip[data-mr="tier:1"]'); pg.wait_for_timeout(800); nt = cnt(pg); check(0 < nt < n0, f'Tier I filter {nt}')
    pg.click('#clrMr'); pg.click('#mrRogo .chip[data-mr="rogo:1"]'); pg.wait_for_timeout(800); nr = cnt(pg); check(0 < nr < 1000, f'ROGO awarded {nr}')
    pg.click('#clrMr'); pg.click('#mrAvoid .chip[data-mr="avoid:ve"]'); pg.wait_for_timeout(800); nv = cnt(pg); check(0 < nv < n0, f'leave out flood VE {n0} -> {nv}')
    pg.click('#clrMr'); pg.click('#mrZt .chip[data-mr="zt:sf"]'); pg.wait_for_timeout(800); nz = cnt(pg); check(0 < nz < n0, f'zoning type single-family {nz}')
    pg.click('#clrMr'); pg.click('#mrSig .chip[data-mr="sig:fc_open"]'); pg.wait_for_timeout(800); nf = cnt(pg); check(0 < nf < 500, f'open foreclosure case signal {nf}')
    pg.click('#clrMr'); pg.wait_for_timeout(600)
    # preset
    preset = pg.query_selector('#ideas .chip:text-is("Buildable lots")'); check(preset is not None, 'Buildable lots preset present')
    if preset:
        preset.click(); pg.wait_for_timeout(1500); npst = cnt(pg); check(0 < npst < n0, f'preset applies ({npst})')
        check(pg.eval_on_selector_all('#mrRate .chip.on', 'n=>n.length') == 2, 'preset selects Green + Yellow')
        check(pg.eval_on_selector_all('#cards .card .mrb', 'n=>n.length>0 && n.every(x=>!x.classList.contains("R"))'), 'preset cards contain no red')
        # drawer
        pg.click('#cards .card h3'); pg.wait_for_selector('.drawer', timeout=30000)
        txt = pg.inner_text('.drawer')
        check('buildability screen' in txt.lower(), 'drawer has buildability screen'); check('not a determination' in txt.lower() and 'confirm with' in txt.lower(), 'drawer disclaimer (screening, confirm with planning)')
        check(pg.locator('.drawer .mrlist li:visible').count() >= 3, f'drawer lists reasons ({pg.locator(".drawer .mrlist li:visible").count()})')
        href = pg.get_attribute('.drawer a:has-text("Property Appraiser page")', 'href') or ''
        check(bool(re.search(r'KeyValue=\d{8}-\d{6}$', href)), 'qPublic link uses RE number: ' + href[-40:])
        pg.keyboard.press('Escape'); pg.click('#resetBtn'); pg.wait_for_timeout(800)
    # absentee wording
    check('outside the Keys' in pg.inner_text('body') or pg.evaluate("document.getElementById('ow_absz')&&document.getElementById('ow_absz').closest('label,div').innerText").lower().count('outside the keys') > 0, 'absentee label says outside the Keys')
    # hash round trip
    pg.goto(URL + '?county=monroe#bld=R&mtier=1'); pg.wait_for_selector('#results:not([hidden])', timeout=120000); pg.wait_for_timeout(1500)
    check(pg.eval_on_selector_all('#mrRate .chip.on', 'n=>n.map(x=>x.dataset.mr)') == ['rate:R'], 'rating restored from the URL')
    check(pg.eval_on_selector_all('#cards .card .mrb', 'n=>n.length>0 && n.every(x=>x.classList.contains("R"))'), 'URL filter shows only red')
    # sort option
    check('bld_a' in pg.eval_on_selector_all('#sortSel option', 'n=>n.map(x=>x.value)'), 'sort by best buildability available')
    # zoning code filter exists for Monroe
    check(pg.is_visible('.grp[data-need="mzoning"]'), 'city zoning code filter group visible')
    pg.click('.grp[data-need="mzoning"] .gtog'); pg.wait_for_timeout(300); check(pg.is_visible('#mzq') and pg.is_visible('#mzCities'), 'zoning code box + by-city list open')
    pg.goto(URL + '?county=monroe#code=R1'); pg.wait_for_selector('#cards .card', timeout=120000); pg.wait_for_timeout(1500); nzz = cnt(pg); check(0 < nzz < 20000, f'zoning code R1 (Islamorada) filter -> {nzz}')
    b.close()
check(not errs, 'no page errors ' + '; '.join(errs[:3]))
print('RESULT', 'PASS' if not fails else f'FAIL ({len(fails)})'); sys.exit(1 if fails else 0)
