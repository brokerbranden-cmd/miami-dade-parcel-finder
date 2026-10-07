"""Headless end-to-end test of the distress-deal features: signal chips, min score, Hottest leads preset, score sort,
card badges, table columns, drawer breakdown + source links, CSV columns, map coloring by score. Screenshots -> shots/distress_*.png"""
import sys, time, csv, io
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
SHOTS = '/workspace/parcel-finder/shots/'
errs = []
def ok(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg)
    if not cond: errs.append('assert: ' + msg)
with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 1360, 'height': 900}, accept_downloads=True)
    page = ctx.new_page()
    page.on('console', lambda m: m.type == 'error' and errs.append('console: ' + m.text))
    page.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    t = time.time(); page.goto(URL); page.wait_for_selector('#results:not([hidden])', timeout=180000)
    print('loaded in %.1fs' % (time.time() - t))
    chips = page.query_selector_all('#dsigs .chip'); ok(len(chips) == 12, f'{len(chips)} distress chips')
    print('chip counts:', ' | '.join(c.inner_text().replace('\n', ' ') for c in chips))
    page.screenshot(path=SHOTS + 'distress_01_filters.png')
    # Hottest leads preset
    page.click('#ideas .chip[data-i="0"]'); page.wait_for_timeout(1500)
    n = int(page.inner_text('#sCount').replace(',', '')); ok(n > 0, f'Hottest leads -> {n} parcels')
    ok(page.input_value('#sortSel') == 'ds_d', 'sorted by distress score')
    scores = [int(x.inner_text()) for x in page.query_selector_all('#cards .card .dscore')[:20]]
    ok(scores == sorted(scores, reverse=True) and min(scores) >= 50, f'card scores descending >=50: {scores[:8]}')
    page.evaluate("document.getElementById('results').scrollIntoView()"); time.sleep(0.4)
    page.screenshot(path=SHOTS + 'distress_02_hottest_cards.png')
    # drawer
    page.click('#cards .card'); page.wait_for_selector('.drawer .dbreak', timeout=60000); page.wait_for_timeout(600)
    txt = page.inner_text('.drawer'); ok('Distress score' in txt, 'drawer shows score breakdown')
    links = page.query_selector_all('.drawer .dlist a'); ok(len(links) > 0, f'{len(links)} source links in drawer, first: ' + (links[0].get_attribute('href') if links else '-'))
    print('drawer breakdown:', page.inner_text('.drawer .dbreak').replace('\n', ' / ')[:400])
    page.screenshot(path=SHOTS + 'distress_03_drawer.png')
    page.keyboard.press('Escape')
    # signal chip + min score
    page.click('#clrDs'); page.wait_for_timeout(800)
    page.click('#dsigs .chip[data-sig="US"]'); page.wait_for_timeout(1200)
    n_us = int(page.inner_text('#sCount').replace(',', '')); ok(n_us > 0, f'Unsafe structure chip -> {n_us}')
    page.select_option('#dsMin', '35'); page.wait_for_timeout(1200)
    n_us35 = int(page.inner_text('#sCount').replace(',', '')); ok(0 < n_us35 <= n_us, f'+ min score 35 -> {n_us35}')
    print('hash:', page.evaluate('location.hash'))
    # table
    page.select_option('#sortSel', 'ds_d'); page.click('#vTable'); page.wait_for_timeout(1000)
    heads = page.inner_text('#thead').upper(); ok('SCORE' in heads and 'SIGNALS' in heads, 'table has Score + Signals columns')
    page.evaluate("document.getElementById('results').scrollIntoView()"); time.sleep(0.3)
    page.screenshot(path=SHOTS + 'distress_04_table.png')
    # CSV
    with page.expect_download(timeout=180000) as dl: page.click('#exportBtn')
    raw = open(dl.value.path(), encoding='utf-8').read(); rows = list(csv.reader(io.StringIO(raw)))
    hdr = rows[0]; ok(all(c in hdr for c in ['Distress Score', 'Distress Signals', 'Signal Details', 'Signal Sources']), 'CSV has distress columns')
    r1 = dict(zip(hdr, rows[1])); print('CSV row1:', r1['Folio'], r1['Distress Score'], r1['Distress Signals'], '|', r1['Signal Details'][:160])
    ok(len(rows) - 1 == n_us35, f'CSV rows {len(rows)-1} == results {n_us35}')
    # map colored by score
    page.click('#ideas .chip[data-i="0"]'); page.wait_for_timeout(1200)
    page.click('#vMap'); page.wait_for_function("document.getElementById('mapHint').textContent.includes('on the map')", timeout=180000)
    page.select_option('#mapColor', 'score'); page.wait_for_timeout(2500)
    ok('Distress score' in page.inner_text('#mapLegend'), 'map legend switched to distress score')
    page.evaluate("document.getElementById('results').scrollIntoView()"); time.sleep(0.5)
    page.screenshot(path=SHOTS + 'distress_05_map_score.png')
    # wider map: every parcel scoring 20+
    page.goto(URL + '#ds=20&sort=ds_d&view=map'); page.reload(); page.wait_for_function("document.getElementById('mapHint').textContent.includes('on the map')", timeout=180000); page.wait_for_timeout(3000)
    print('map 20+:', page.inner_text('#mapHint'))
    page.evaluate("document.getElementById('results').scrollIntoView()"); time.sleep(0.5)
    page.screenshot(path=SHOTS + 'distress_06_map_county.png')
    # mobile
    m = b.new_page(viewport={'width': 390, 'height': 844}); m.on('pageerror', lambda e: errs.append('mobile pageerror: ' + str(e)))
    m.goto(URL + '#ds=50&sort=ds_d'); m.wait_for_selector('#results:not([hidden])', timeout=180000); m.wait_for_timeout(1500)
    m.click('#cards .card'); m.wait_for_selector('.drawer .dbreak', timeout=60000); m.wait_for_timeout(500)
    m.screenshot(path=SHOTS + 'distress_07_mobile_drawer.png')
    print('ERRORS:', errs if errs else 'none')
    b.close()
    sys.exit(1 if errs else 0)
