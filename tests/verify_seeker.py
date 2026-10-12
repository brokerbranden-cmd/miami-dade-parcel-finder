"""Manual-style verification of the Parcel Seeker features at desktop and phone widths, with screenshots.
usage: verify_seeker.py URL OUTDIR"""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
OUT = sys.argv[2] if len(sys.argv) > 2 else '/workspace/parcel-finder/shots/verify/'
res = []
def ok(c, m): res.append(('PASS ' if c else 'FAIL ') + m); print(res[-1])
cnt = lambda pg: int(pg.inner_text('#sCount').replace(',', ''))
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for tag, vp in [('desktop', {'width': 1360, 'height': 900}), ('mobile', {'width': 390, 'height': 844})]:
        ctx = b.new_context(viewport=vp, accept_downloads=True, is_mobile=tag == 'mobile', has_touch=tag == 'mobile')
        pg = ctx.new_page(); pg.set_default_timeout(90000)
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(URL + ('?drive=0' if tag == 'mobile' else ''), timeout=180000)
        if tag == 'mobile' and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_selector('#results:not([hidden])', timeout=240000); pg.wait_for_timeout(1500)
        pg.click('#resetBtn'); pg.wait_for_timeout(2000); tot = cnt(pg); ok(tot > 400000, f'{tag}: all {tot}')
        sh = lambda n, sel: (pg.query_selector(sel).scroll_into_view_if_needed(), pg.screenshot(path=f'{OUT}{tag}_{n}.png'))
        # presets
        names = pg.eval_on_selector_all('#ideas .chip', 'e=>e.map(x=>x.textContent)')
        for want in ['Teardowns', '💥 Strong teardowns', 'Lots that could be split']:
            i = names.index(want); pg.click(f'#ideas .chip[data-i="{i}"]'); pg.wait_for_timeout(2000); ok(cnt(pg) > 0, f'{tag}: preset {want} -> {cnt(pg)}')
        sh('01_preset', '#ideas')
        pg.click('#resetBtn'); pg.wait_for_timeout(1500)
        # zoning by city + prefix
        pg.click('#mzCities details[data-j="Hialeah"] > summary'); pg.wait_for_timeout(300)
        c = pg.query_selector('#mzCities details[data-j="Hialeah"] .chip'); c.click(); pg.wait_for_timeout(2000)
        ok(cnt(pg) > 0 and all('Hialeah' in x.inner_text() for x in pg.query_selector_all('#cards .card')[:8]), f'{tag}: city code {c.get_attribute("data-mzs")} -> {cnt(pg)}')
        sh('02_city_zoning', '#mzCities details[data-j="Hialeah"]'); pg.click('#clrMz'); pg.wait_for_timeout(1500)
        pg.fill('#mzq', 'T6'); pg.wait_for_timeout(2000); n6 = cnt(pg); ok(n6 > 1000, f'{tag}: prefix T6 -> {n6}'); pg.fill('#mzq', ''); pg.wait_for_timeout(1500)
        # zoning types
        pg.click('#zones .chip[data-z="mf"]'); pg.wait_for_timeout(2000); nm = cnt(pg); ok(0 < nm < tot, f'{tag}: zoning type Multifamily -> {nm}'); sh('03_zoning_type', '#zones'); pg.click('#clrZone'); pg.wait_for_timeout(1500)
        # money shorthand
        pg.fill('#mvMin', '500k'); pg.fill('#mvMax', '1.2m'); pg.wait_for_timeout(2500); h = pg.evaluate('location.hash')
        ok('mvMin=500000' in h and 'mvMax=1200000' in h and 0 < cnt(pg) < tot, f'{tag}: 500k-1.2m -> {cnt(pg)}'); sh('04_money', '#mvMin')
        pg.fill('#mvMin', ''); pg.fill('#mvMax', ''); pg.wait_for_timeout(1500)
        # teardown rules + reset
        pg.click('#tierSeg button[data-tier="strong"]'); pg.wait_for_timeout(2000); s0 = cnt(pg)
        pg.fill('#td_land', '60'); pg.wait_for_timeout(2500); s1 = cnt(pg); ok(s1 > s0, f'{tag}: strong {s0} -> land 60% {s1}')
        sh('05_teardown_rules', '#tdRules')
        pg.click('#tdReset'); pg.wait_for_timeout(2000); ok(cnt(pg) == s0 and pg.input_value('#td_land') == '80', f'{tag}: reset -> {cnt(pg)}')
        # send to
        f = pg.get_attribute('#cards .card:nth-of-type(1)', 'data-folio')
        pg.click(f'#cards .card[data-folio="{f}"] [data-sendtag="dk"]'); pg.wait_for_timeout(600)
        ok('1 ready' in pg.inner_text('#sendInfo-dk'), f'{tag}: tagged door knock')
        with pg.expect_download() as dl: pg.click('#sendExp-dk')
        ok(dl.value.suggested_filename.startswith('DoorKnock_'), f'{tag}: export {dl.value.suggested_filename}')
        pg.click('#sendBar [data-sendmark="1"]'); pg.wait_for_timeout(600); ok('Sent' in pg.inner_text(f'#cards .card[data-folio="{f}"]'), f'{tag}: marked sent')
        sh('06_send_card', f'#cards .card[data-folio="{f}"]'); sh('07_send_panel', '#sendGrp')
        ok(not errs, f'{tag}: no page errors {errs[:2]}')
        ctx.close()
    b.close()
print('ALL PASS' if all(r.startswith('PASS') for r in res) else 'SOME FAILED')
