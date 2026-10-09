"""Headless e2e for the vacancy & condition hint: chips with counts, min-score filter, sort, preset, card badge, table column,
drawer breakdown + aerial thumbnail + Street View / satellite links, saved 'looks vacant / damaged' flag + condition note
(persists, filters, exported in JSON/CSV), hash round-trip. Screenshots -> SHOTS/vacancy_*.png"""
import sys, json, csv, io
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
SHOTS = sys.argv[2] if len(sys.argv) > 2 else '/workspace/parcel-finder/shots/'
errs = []
def ok(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg)
    if not cond: errs.append('assert: ' + msg)
cnt = lambda pg: int(pg.inner_text('#sCount').replace(',', ''))
with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 1360, 'height': 900}, accept_downloads=True)
    pg = ctx.new_page()
    pg.on('console', lambda m: m.type == 'error' and 'arcgisonline' not in m.text and errs.append('console: ' + m.text))
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    pg.goto(URL); pg.wait_for_selector('#results:not([hidden])', timeout=180000); pg.wait_for_timeout(1000)
    meta = pg.evaluate("fetch('data/meta.json').then(r=>r.json())")
    ok(meta.get('vacancy') and meta['vacancy']['ge40'] > 0, f"meta.vacancy: {meta['vacancy']['ge40']} parcels 40+, {meta['vacancy']['ge60']} 60+")
    chips = pg.query_selector_all('#vsigs .chip'); ok(len(chips) == 12, f'{len(chips)} vacancy chips')
    ok('40+' in pg.inner_text('#vsSrc'), 'source line: ' + pg.inner_text('#vsSrc'))
    # preset
    chip = pg.query_selector('#ideas .chip[data-i="4"]'); ok('vacant' in chip.inner_text().lower(), 'preset: ' + chip.inner_text())
    chip.click(); pg.wait_for_timeout(1500)
    n40 = cnt(pg); ok(n40 > 50, f'preset (hint 40+) -> {n40} results')
    ok(pg.input_value('#sortSel') == 'vs_d' and pg.input_value('#vsMin') == '40', 'preset sets sort vs_d and min 40')
    first = pg.inner_text('#cards .card:nth-of-type(1) .ob .vac'); ok('Likely vacant' in first, 'first card badge: ' + first)
    scores = [int(x.split('·')[-1]) for x in pg.eval_on_selector_all('#cards .card .ob .vac', 'els=>els.map(e=>e.textContent)')[:30]]
    ok(scores == sorted(scores, reverse=True) and min(scores) >= 40, f'cards sorted by hint desc: {scores[:8]}…')
    ok('vs=40' in pg.evaluate('location.hash') and 'sort=vs_d' in pg.evaluate('location.hash'), 'hash has vs=40 & sort=vs_d')
    pg.screenshot(path=SHOTS + 'vacancy_01_filter_cards.png')
    # chip counts sum check / chip filter
    ng = pg.query_selector('#vsigs .chip[data-vs="NG"]'); n_ng = int(ng.inner_text().split('\n')[-1].replace(',', '').replace('K', '000') or 0)
    ng.click(); pg.wait_for_timeout(900)
    ok(cnt(pg) == n_ng and cnt(pg) > 0, f'neglect-case chip count {n_ng} == results {cnt(pg)}')
    ok('vsig=NG' in pg.evaluate('location.hash'), 'hash has vsig=NG')
    # drawer
    pg.click('#cards .card:nth-of-type(1)'); pg.wait_for_selector('.drawer'); pg.wait_for_timeout(2500)
    d = pg.inner_text('.drawer')
    ok('vacancy & condition' in d.lower() and 'neglect-type code case' in d.lower(), 'drawer shows vacancy breakdown with neglect case')
    ok('Vacancy / neglect hint' in d, 'distress breakdown includes the capped vacancy soft signal')
    ok(pg.query_selector('.drawer .aerial img') is not None, 'aerial thumbnail present')
    nat = pg.eval_on_selector('.drawer .aerial img', 'i=>i.complete?i.naturalWidth:0'); ok(nat > 0, f'aerial image loaded (width {nat})')
    ok(pg.query_selector('.drawer .vlinks a[href*="map_action=pano"]') and pg.query_selector('.drawer .vlinks a[href*="basemap=satellite"]'), 'Street View + satellite links')
    pg.query_selector('.drawer .vlinks').scroll_into_view_if_needed(); pg.wait_for_timeout(300)
    pg.screenshot(path=SHOTS + 'vacancy_02_drawer.png')
    # save + mark vacant + condition note
    folio = pg.get_attribute('#savedBox', 'data-folio')
    pg.click('#savedBox .svsave'); pg.wait_for_selector('#svVacant')
    pg.check('#svVacant'); pg.wait_for_timeout(300)
    pg.fill('#svCond', 'Boarded front window, tall grass'); pg.wait_for_timeout(900)
    it = pg.evaluate(f"PFSaved.get('{folio}')")
    ok(it['vacant'] is True and it['cond'] == 'Boarded front window, tall grass', 'saved item stores vacant flag + condition note')
    pg.query_selector('#savedBox').scroll_into_view_if_needed(); pg.screenshot(path=SHOTS + 'vacancy_03_saved_condition.png')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
    card = pg.query_selector(f'#cards .card[data-folio="{folio}"]'); ok(card and 'Looks vacant (you)' in card.inner_text(), 'card shows "Looks vacant (you)"')
    # reload persistence + "marked by me" filter
    pg.reload(); pg.wait_for_selector('#results:not([hidden])', timeout=180000); pg.wait_for_timeout(800)
    ok(pg.evaluate(f"PFSaved.get('{folio}').vacant") is True, 'vacant flag persists after reload')
    pg.click('#clrVs'); pg.check('#vsMine'); pg.wait_for_timeout(1200)
    ok(cnt(pg) == 1 and pg.get_attribute('#cards .card', 'data-folio') == folio, 'filter "marked vacant by me" -> exactly that parcel')
    pg.uncheck('#vsMine'); pg.wait_for_timeout(500)
    # exports
    with pg.expect_download() as dl:
        pg.click('#savedBtn'); pg.wait_for_timeout(600); pg.click('#svExportJson')
    j = json.load(open(dl.value.path())); x = [i for i in j['items'] if i['folio'] == folio][0]
    ok(x['vacant'] and x['cond'].startswith('Boarded'), 'JSON export carries vacant + cond')
    with pg.expect_download() as dl: pg.click('#svExportCsv')
    rows = list(csv.DictReader(io.StringIO(open(dl.value.path()).read())))
    ok(rows[0]['Marked Vacant/Damaged'] == 'Y' and rows[0]['Condition Note'].startswith('Boarded') and rows[0]['Vacancy Hint'] != '', 'saved CSV has vacancy columns')
    with pg.expect_download() as dl: pg.click('#exportBtn')
    rows = list(csv.DictReader(io.StringIO(open(dl.value.path()).read())))
    ok(rows and rows[0]['Vacancy Hint'] and rows[0]['Vacancy Signals'] and rows[0]['Marked Vacant/Damaged'] == 'Y', 'results CSV has Vacancy Hint/Signals/Marked columns')
    pg.click('#svBack'); pg.wait_for_timeout(500)
    # import merges flag into a fresh context
    ctx2 = b.new_context(viewport={'width': 1360, 'height': 900}); p2 = ctx2.new_page()
    p2.goto(URL); p2.wait_for_selector('#results:not([hidden])', timeout=180000)
    p2.set_input_files('#svImport', files=[{'name': 's.json', 'mimeType': 'application/json', 'buffer': json.dumps(j).encode()}]); p2.wait_for_timeout(800)
    ok(p2.evaluate(f"PFSaved.get('{folio}') && PFSaved.get('{folio}').vacant") is True, 'import into fresh browser keeps the vacant flag')
    ctx2.close()
    # table column + sort header
    pg.goto(URL + '#vs=60&sort=vs_d&view=table'); pg.wait_for_timeout(2000)
    n60 = cnt(pg); ok(n60 == meta['vacancy']['ge60'] or n60 > 0, f'hint 60+ -> {n60} (meta {meta["vacancy"]["ge60"]})')
    ok(pg.query_selector('#thead th[data-s="vs_d"].sorted') is not None, 'table: Vacancy column sorted')
    pg.screenshot(path=SHOTS + 'vacancy_04_table.png')
    # negative signal: recent permit chip present with count
    pg.goto(URL + '#vsig=RP'); pg.wait_for_timeout(1500); ok(cnt(pg) > 1000, f'recent-permit chip filter -> {cnt(pg)}')
    # mobile drawer
    m = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True); mp = m.new_page()
    mp.on('pageerror', lambda e: errs.append('mobile pageerror: ' + str(e)))
    mp.goto(URL + '#vs=40&sort=vs_d'); mp.wait_for_selector('#results:not([hidden])', timeout=180000); mp.wait_for_timeout(1000)
    mp.click('#cards .card:nth-of-type(1)'); mp.wait_for_selector('.drawer'); mp.wait_for_timeout(2500)
    mp.query_selector('.drawer .aerial').scroll_into_view_if_needed(); mp.wait_for_timeout(500)
    mp.screenshot(path=SHOTS + 'vacancy_05_mobile_drawer.png')
    b.close()
print('ERRORS', errs if errs else 'none')
sys.exit(1 if errs else 0)
