"""Headless e2e: owner portfolios (grouping badge, filters, presets, sort, owner panel with stats/map/list/star,
back navigation, show-all table/map with persistent hash, CSV export, institution exclusion). Screenshots -> shots/owners_*.png"""
import sys, time, csv, io
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
SHOTS = sys.argv[2] if len(sys.argv) > 2 else '/workspace/parcel-finder/shots/'
errs = []
def ok(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg)
    if not cond: errs.append('assert: ' + msg)
cnt = lambda pg: int(pg.inner_text('#sCount').replace(',', ''))
def watch(pg, tag):
    pg.on('console', lambda m: m.type == 'error' and errs.append(f'{tag} console: ' + m.text))
    pg.on('pageerror', lambda e: errs.append(f'{tag} pageerror: ' + str(e)))
with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 1360, 'height': 900}, accept_downloads=True)
    pg = ctx.new_page(); watch(pg, 'main')
    pg.goto(URL); pg.wait_for_selector('#results:not([hidden])', timeout=180000); pg.wait_for_timeout(800)
    ok('owners hold 2+ properties' in pg.inner_text('#ogSrc'), 'owner stats line: ' + pg.inner_text('#ogSrc')[:120])
    # preset: multi-property motivated owners
    chip = pg.query_selector('#ideas .chip[data-i="4"]'); ok('motivated' in chip.inner_text(), 'preset chip present: ' + chip.inner_text())
    chip.click(); pg.wait_for_timeout(1500)
    n_mot = cnt(pg); ok(n_mot > 1000 and pg.input_value('#sortSel') == 'ogd_d' and pg.is_checked('#ogDist'), f'Multi-property motivated owners -> {n_mot} parcels, sorted by owner distressed count')
    badges = [x.inner_text() for x in pg.query_selector_all('#cards .card .pf')[:6]]
    ok(len(badges) >= 6 and all('distressed' in x for x in badges), 'cards show owner badges: ' + badges[0])
    pg.evaluate("window.scrollTo(0,document.querySelector('.grp .ogrow').getBoundingClientRect().top+window.scrollY-260)"); time.sleep(0.3)
    pg.screenshot(path=SHOTS + 'owners_01_filters.png')
    # owners-with-N filter + institutions
    pg.click('#resetBtn'); pg.wait_for_timeout(800)
    pg.select_option('#ogMin', '25'); pg.wait_for_timeout(1500); a = cnt(pg)
    pg.check('#ogInst'); pg.wait_for_timeout(1500); bb = cnt(pg)
    ok(0 < a < bb, f'owners with 25+: {a} parcels without institutions, {bb} with banks/government/large holders')
    pg.uncheck('#ogInst'); pg.select_option('#ogMin', '0'); pg.wait_for_timeout(800)
    # owner panel from a parcel drawer
    pg.click('#ideas .chip[data-i="4"]'); pg.wait_for_timeout(1500)
    pg.click('#cards .card'); pg.wait_for_selector('#ownerOpen', timeout=60000)
    pg.click('#ownerOpen'); pg.wait_for_selector('.ogdrawer .ogitem', timeout=120000); pg.wait_for_timeout(2500)
    stats = pg.inner_text('.ogdrawer .ogstats'); n_own = int(stats.split('\n')[1].replace(',', ''))
    items = len(pg.query_selector_all('.ogdrawer .ogitem')); ok(items == min(n_own, 400), f'owner panel lists {items} of {n_own} properties')
    ok(pg.query_selector('#ogMap.leaflet-container') is not None and len(pg.query_selector_all('#ogMap path.leaflet-interactive, #ogMap canvas')) > 0, 'owner map renders holdings')
    txt = pg.inner_text('.ogdrawer'); ok('DISTRESS ACROSS THE PORTFOLIO' in txt.upper() and 'AVG YEARS HELD' in txt.upper(), 'stats: distressed, avg years held, signals across portfolio')
    pg.screenshot(path=SHOTS + 'owners_02_panel.png')
    # star from the owner list, open a parcel and come back
    pg.click('.ogdrawer .ogitem:nth-child(2) .star'); pg.wait_for_timeout(300); ok(pg.inner_text('#savedCount') == '1', 'star in owner list saves the property')
    pg.click('.ogdrawer .ogitem:nth-child(3) .ogopen'); pg.wait_for_selector('.drawer:not(.ogdrawer) .btn.back', timeout=60000)
    pg.click('.drawer .btn.back'); pg.wait_for_selector('.ogdrawer .ogitem', timeout=60000); ok(True, 'parcel -> "Owner portfolio" back button returns to owner panel')
    # CSV from owner panel
    with pg.expect_download(timeout=180000) as dl: pg.click('#ogCsv')
    rows = list(csv.reader(io.StringIO(open(dl.value.path(), encoding='utf-8').read()))); ok(len(rows) - 1 == n_own, f'owner CSV rows {len(rows)-1} == {n_own}')
    # show all in table + hash persistence
    pg.click('#ogTblBtn'); pg.wait_for_timeout(2000)
    ok(cnt(pg) == n_own and 'ogf=' in pg.evaluate('location.hash') and 'Only properties of' in pg.inner_text('#ogLabel'), f'Show all in table -> {cnt(pg)} rows, owner chip: ' + pg.inner_text('#ogLabel'))
    pg.evaluate("document.getElementById('results').scrollIntoView()"); time.sleep(0.3); pg.screenshot(path=SHOTS + 'owners_03_table.png')
    h = pg.evaluate('location.hash'); pg.goto(URL + h); pg.reload(); pg.wait_for_selector('#results:not([hidden])', timeout=180000); pg.wait_for_timeout(2000)
    ok(cnt(pg) == n_own, f'reload with #ogf link restores the owner filter ({cnt(pg)})')
    pg.click('#vMap'); pg.wait_for_function("document.getElementById('mapHint').textContent.includes('on the map')", timeout=180000); pg.wait_for_timeout(2500)
    pg.evaluate("document.getElementById('results').scrollIntoView()"); time.sleep(0.3); pg.screenshot(path=SHOTS + 'owners_04_map.png')
    pg.click('#clrOg'); pg.wait_for_timeout(1500); ok(cnt(pg) > n_own, 'removing the owner chip clears the filter')
    pg.click('#vCards'); pg.select_option('#sortSel', 'og_d'); pg.wait_for_timeout(1500)
    first = pg.inner_text('#cards .card .pf') if pg.query_selector('#cards .card .pf') else ''; ok(first.startswith('Owner has'), 'sort by owner portfolio size (institutions ranked last): ' + first)
    # flagged institution in drawer
    pg.check('#ogInst'); pg.fill('#q', 'LENNAR HOMES LLC'); pg.wait_for_timeout(1500); pg.click('#cards .card'); pg.wait_for_selector('#ownerOpen', timeout=60000)
    ok('Large holder' in pg.inner_text('.drawer'), 'big builder flagged as large holder in the drawer')
    pg.keyboard.press('Escape')
    # mobile owner panel
    m = b.new_page(viewport={'width': 390, 'height': 844}); watch(m, 'mobile')
    m.goto(URL + '#ogn=2&ogd=1&sort=ogd_d'); m.wait_for_selector('#results:not([hidden])', timeout=180000); m.wait_for_timeout(1500)
    m.click('#cards .card'); m.wait_for_selector('#ownerOpen', timeout=60000); m.click('#ownerOpen'); m.wait_for_selector('.ogdrawer .ogitem', timeout=120000); m.wait_for_timeout(2000)
    m.screenshot(path=SHOTS + 'owners_05_mobile_panel.png')
    print('ERRORS:', errs if errs else 'none')
    b.close(); sys.exit(1 if errs else 0)
