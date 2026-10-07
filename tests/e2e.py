"""End-to-end smoke test of the local site with headless Chromium (playwright)."""
import sys, time, json
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
SHOTS = '/workspace/parcel-finder/shots/'
errs = []
def num(page, sel): return int(page.inner_text(sel).replace(',', '') or 0)
with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 1360, 'height': 900}, accept_downloads=True)
    page = ctx.new_page()
    page.on('console', lambda m: m.type in ('error',) and errs.append('console: ' + m.text))
    page.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    t = time.time(); page.goto(URL); page.wait_for_selector('#results:not([hidden])', timeout=120000)
    print('loaded in %.1fs' % (time.time() - t), 'count', page.inner_text('#sCount'), '|', page.inner_text('#summary'))
    print('subtitle:', page.inner_text('#srcLine'))
    page.screenshot(path=SHOTS + '01_top_filters.png')
    page.evaluate("document.getElementById('results').scrollIntoView()"); time.sleep(0.5)
    page.screenshot(path=SHOTS + '02_cards.png')
    page.evaluate("window.scrollTo(0,0)")
    ideas = page.query_selector_all('#ideas .chip')
    for k in range(len(ideas)):
        page.click(f'#ideas .chip[data-i="{k}"]'); page.wait_for_timeout(1200)
        print('preset', page.inner_text(f'#ideas .chip[data-i="{k}"]'), '->', page.inner_text('#sCount'), '| first card:', (page.inner_text('#cards .card h3') if page.query_selector('#cards .card h3') else '-'))
    # filters: city + zoning code + owner kind
    page.click('#ideas .chip[data-i="0"]'); page.wait_for_timeout(800)
    page.select_option('#city', 'Miami'); page.wait_for_timeout(800); print('vacant infill + Miami', page.inner_text('#sCount'))
    page.click('#mzMiami .chip[data-mz="T6"]'); page.wait_for_timeout(800); print('+ T6', page.inner_text('#sCount'), 'mzq=', page.input_value('#mzq'))
    page.click('#ownerKind button[data-k="corp"]'); page.wait_for_timeout(800); print('+ LLCs', page.inner_text('#sCount'))
    print('hash:', page.evaluate('location.hash'))
    # sorts
    for v in ['mv_a', 'held_d', 'sold_d', 'addr_a', 'ppl_a']:
        page.select_option('#sortSel', v); page.wait_for_timeout(500); print('sort', v, '->', page.inner_text('#cards .card h3'))
    # drawer
    page.click('#cards .card'); page.wait_for_selector('.drawer', timeout=60000); page.wait_for_timeout(800)
    print('drawer:', page.inner_text('.drawer h2'), '|', page.inner_text('.drawer .dl').split('\n')[:8])
    print('PA link:', page.get_attribute('.drawer .links a', 'href'))
    page.screenshot(path=SHOTS + '04_detail_drawer.png')
    page.keyboard.press('Escape')
    # table view
    page.click('#vTable'); page.wait_for_timeout(800)
    page.evaluate("document.getElementById('results').scrollIntoView()"); time.sleep(0.3)
    page.screenshot(path=SHOTS + '05_table.png'); print('table rows', len(page.query_selector_all('#tbody tr[data-id]')))
    # export CSV
    with page.expect_download(timeout=120000) as dl:
        page.click('#exportBtn')
    d = dl.value; path = SHOTS + '../tests/export_sample.csv'; d.save_as(path)
    lines = open(path).read().split('\n'); print('CSV', d.suggested_filename, len(lines) - 2, 'rows; header cols', len(lines[0].split(',')))
    print('CSV row1:', lines[1][:300])
    # map view
    page.click('#vMap'); page.wait_for_function("document.getElementById('mapHint').textContent.includes('on the map')", timeout=120000); page.wait_for_timeout(2500)
    print('map hint:', page.inner_text('#mapHint'))
    page.evaluate("document.getElementById('results').scrollIntoView()"); time.sleep(0.5)
    page.screenshot(path=SHOTS + '06_map.png')
    # click the first result's dot
    box = page.query_selector('#map').bounding_box()
    hit = page.evaluate("""() => { const c=document.querySelector('.dotlayer'); return null; }""")
    # whole county map with all vacant land
    page.click('#ideas .chip[data-i="0"]'); page.select_option('#city', ''); page.wait_for_timeout(2500)
    print('map all vacant:', page.inner_text('#mapHint'))
    page.screenshot(path=SHOTS + '07_map_county.png')
    # hash restore in new page
    h = page.evaluate('location.href'); p2 = ctx.new_page(); p2.on('pageerror', lambda e: errs.append('p2 pageerror: ' + str(e)))
    p2.goto(URL + '#type=mf29&city=Hialeah&o_homestead=no&sort=un_d'); p2.wait_for_selector('#results:not([hidden])', timeout=120000); p2.wait_for_timeout(1000)
    print('hash restore (2-9 units, Hialeah, non-homestead):', p2.inner_text('#sCount'), 'city=', p2.input_value('#city'), 'sort=', p2.input_value('#sortSel'))
    # condo + search
    p2.goto(URL + '#q=BRICKELL&type=condo'); p2.reload(); p2.wait_for_selector('#results:not([hidden])', timeout=120000); p2.wait_for_timeout(4000)
    print('condo search BRICKELL:', p2.inner_text('#sCount'))
    p2.goto(URL + '#q=01-0200-010-1100&gov=1'); p2.reload(); p2.wait_for_selector('#results:not([hidden])', timeout=120000); p2.wait_for_timeout(1500)
    print('folio search:', p2.inner_text('#sCount'), p2.inner_text('#cards .card h3') if p2.query_selector('#cards .card h3') else '-')
    page.set_viewport_size({'width': 1360, 'height': 900})
    print('ERRORS:', errs if errs else 'none')
    b.close()
