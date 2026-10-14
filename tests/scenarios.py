"""Investor scenarios, end to end, against any URL (default: the LIVE site). argv: URL [desktop|mobile] [SHOTS_DIR]
Each scenario drives the UI like a user, then cross-checks the results against the raw data via a sample of the result set
(window.PF.sample: evenly spaced rows of the current results with the fields the filters use)."""
import sys, re, csv, io, json, time, traceback
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'https://brokerbranden-cmd.github.io/miami-dade-parcel-finder/'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'desktop'
SHOTS = sys.argv[3] if len(sys.argv) > 3 else '/workspace/parcel-finder/shots/scenarios/'
MOB = MODE == 'mobile'
BASE = URL.split('#')[0] + ('?drive=0' if MOB else '')
results, cur, errs = [], {'name': '', 'fails': []}, []
FLAG = dict(homestead=1, oos=2, absz=4, corp=8, trust=16, govt=32, estate=64, senior=128)
def ok(c, m):
    if not c: cur['fails'].append(m)
    print(('  ok   ' if c else '  FAIL ') + m, flush=True)
cnt = lambda: int(pg.inner_text('#sCount').replace(',', ''))
def settle(ms=900):
    pg.wait_for_timeout(ms)
    for _ in range(40):
        a = pg.inner_text('#sCount'); pg.wait_for_timeout(250)
        if a == pg.inner_text('#sCount'): break
def go(hash_='', reload=False):
    if reload: pg.goto(BASE + ('#' + hash_ if hash_ else ''), timeout=180000); boot()
    else: pg.evaluate(f"location.hash={json.dumps(hash_)}"); pg.evaluate("window.dispatchEvent(new HashChangeEvent('hashchange'))") if False else None
    settle(1200)
def boot():
    if MOB and pg.query_selector('#drive:not([hidden])'): click('#dExit')
    pg.wait_for_selector('#results:not([hidden])', timeout=240000); pg.wait_for_function('window.PF_READY', timeout=120000)
def reset():
    pg.keyboard.press('Escape')
    if pg.query_selector('#lendersPage:not([hidden])'): click('#lpClose')
    if pg.query_selector('#savedBar:not([hidden])'): click('#svBack'); settle(600)
    if not pg.is_disabled('#resetBtn'): click('#resetBtn')
    if 'on' not in (pg.get_attribute('#vCards', 'class') or ''): click('#vCards')
    settle(1000)
def sample(k=300): return pg.evaluate(f'PF.sample({k})')
def bit(s, sig): return (s['dsig'] >> s['_dbit'][sig]) & 1
def rows(k=300):
    s = sample(k); [r.__setitem__('_dbit', s['dbit']) for r in s['rows']]; return s['n'], s['rows']
def preset(name_part):
    names = pg.eval_on_selector_all('#ideas .chip[data-i]', 'e=>e.sort((a,b)=>a.dataset.i-b.dataset.i).map(x=>x.textContent.trim())')
    i = next(k for k, x in enumerate(names) if name_part.lower() in x.lower())
    click(f'#ideas .chip[data-i="{i}"]', force=True); settle(1500); return names[i]
def money(sel, v):
    fill(sel, v); pg.press(sel, 'Tab'); settle(1000)
def csv_of(click_sel):
    with pg.expect_download(timeout=180000) as dl: click(click_sel)
    return list(csv.DictReader(io.StringIO(open(dl.value.path(), encoding='utf-8-sig').read())))
def shot(n):
    pg.screenshot(path=f'{SHOTS}{MODE}_{n}.png')

# ---- simplified UI: reveal a control like a user would (open the phone filter sheet, expand its group,
#      open "More ideas", or open a card's ⋯ menu) before using it
REVEAL_JS = """s=>{ const e=document.querySelector(s); if(!e) return null; const ds=e.closest('.dsec.closed'); if(ds){ ds.querySelector('.dtog').click(); } const card=e.closest('.card'), g=e.closest('.cgrp.closed'), m=e.closest('#ideasMore');
  return {panel:!!e.closest('#panel'), g:g?g.dataset.g:null, more:!!(m&&m.hidden), menu:card&&e.closest('.sendtools')&&!card.classList.contains('menu-open')?card.dataset.folio:null,
          sheet:document.body.classList.contains('sheet-open'), phoneSheet:getComputedStyle(document.getElementById('filtersBtn')||document.body).display!=='none' && !!document.getElementById('filtersBtn')} }"""
def reveal(sel):
    if '>>' in sel: return
    for _ in range(4):
        try: i = pg.evaluate(REVEAL_JS, sel)
        except Exception: return
        if not i: return
        if i['panel']:
            if i['phoneSheet'] and not i['sheet']: pg.click('#filtersBtn'); pg.wait_for_timeout(250); continue
            if i['g']: pg.click(f'.cgrp[data-g="{i["g"]}"] .gtog'); pg.wait_for_timeout(150); continue
            if i['more']: pg.click('#moreIdeas'); pg.wait_for_timeout(150); continue
            return
        if i['sheet']: pg.click('#sheetClose'); pg.wait_for_timeout(250); continue
        if i['menu']: pg.click(f'.card[data-folio="{i["menu"]}"] .cmore'); pg.wait_for_timeout(150); continue
        return
def click(sel, **k): reveal(sel); pg.click(sel, **k)
def fill(sel, v): reveal(sel); pg.fill(sel, v)
def select(sel, v): reveal(sel); pg.select_option(sel, v)
def check(sel): reveal(sel); pg.check(sel)
def uncheck(sel): reveal(sel); pg.uncheck(sel)
TOTAL = {}
SC = []
def scenario(f): SC.append(f); return f

# ---------------------------------------------------------------- scenarios
@scenario
def s01_every_preset():
    names = pg.eval_on_selector_all('#ideas .chip[data-i]', 'e=>e.sort((a,b)=>a.dataset.i-b.dataset.i).map(x=>x.textContent.trim())')
    ok(len(names) >= 20, f'{len(names)} presets')
    for i, nm in enumerate(names):
        click(f'#ideas .chip[data-i="{i}"]', force=True); settle(1300); n = cnt()
        ok(0 < n < TOTAL['all'], f'preset "{nm}" -> {n:,}')
        ok(pg.get_attribute(f'#ideas .chip[data-i="{i}"]', 'class').find('on') >= 0, f'preset "{nm}" highlighted')
@scenario
def s02_preset_content():
    checks = [('Pre-foreclosure', lambda r: bit(r, 'LP') or bit(r, 'FC'), 'LP/foreclosure signal'),
              ('Tax deeds', lambda r: bit(r, 'TD') or bit(r, 'TX') or bit(r, 'TC'), 'tax deed / delinquent signal'),
              ('Unsafe structures', lambda r: bit(r, 'US'), 'unsafe structure signal'),
              ('Vacant infill', lambda r: r['type'] == 'vacant', 'vacant land'),
              ('Out-of-state owners', lambda r: r['flags'] & 2, 'out-of-state flag'),
              ('Estates and heirs', lambda r: r['flags'] & 64, 'estate flag'),
              ('Small multifamily', lambda r: r['type'] == 'mf29', '2-9 units type'),
              ('Big lots', lambda r: r['lot'] >= 43560, 'lot >= 1 acre'),
              ('Strong teardowns', lambda r: r['tier'] == 2, 'strong tier'),
              ('Teardowns', lambda r: r['tier'] >= 1, 'teardown tier'),
              ('Assemblages with', lambda r: r['asm'] and r['asm']['upside'], 'assemblage w/ upside'),
              ('Hottest leads', lambda r: r['dscore'] >= 1, 'has distress score')]
    for nm, f, what in checks:
        reset(); preset(nm); n, rs = rows(200)
        bad = [r['folio'] for r in rs if not f(r)]
        ok(n > 0 and not bad, f'"{nm}": {n:,} results, sampled {len(rs)} all {what}' + (f' (bad {bad[:3]})' if bad else ''))
        ok(not any(r['flags'] & 32 for r in rs), f'"{nm}": no government owners (hide government on)')
@scenario
def s03_strong_teardowns_miami_t4_t5_under_500k():
    reset(); click('#tierSeg button[data-tier="strong"]'); settle()
    fill('#mzq', 'T4, T5'); settle(1200); money('#mvMax', '500k')
    n, rs = rows()
    ok(n > 0, f'{n:,} strong teardowns in T4/T5 under $500K')
    ok(all(r['tier'] == 2 for r in rs), 'all strong tier')
    ok(all(re.match(r'T[45]', r['mzCode'].upper()) for r in rs), 'all zoned T4*/T5* ' + str({r['mzCode'] for r in rs}))
    ok(all(r['mzJur'] == 'Miami' for r in rs), 'all in the City of Miami')
    ok(all(r['mkt'] <= 500000 for r in rs), f"all <= $500K (max {max((r['mkt'] for r in rs), default=0):,})")
    h = pg.evaluate('location.hash'); ok('td=strong' in h and 'mvMax=500000' in h and 'code=T4' in h, 'hash: ' + h)
    shot('03_strong_t4t5')
@scenario
def s04_lp_absentee_high_distress():
    reset(); go('sig=LP&o_absz=yes&ds=50'); n, rs = rows()
    ok(n > 0, f'{n:,} LP + absentee + distress 50+')
    ok(all(bit(r, 'LP') for r in rs) and all(r['flags'] & 4 for r in rs) and all(r['dscore'] >= 50 for r in rs), 'every sample: LP, mails elsewhere, score >= 50')
    ok(pg.input_value('#dsMin') == '50' and 'on' in pg.get_attribute('#dsigs .chip[data-sig="LP"]', 'class'), 'UI reflects the link (LP chip on, min score 50)')
@scenario
def s05_tax_delinquent_estates():
    reset(); click('#dsigs .chip[data-sig="TX"]'); settle(); pg.evaluate("document.getElementById('moreBox').open=true")
    select('#ow_estate', 'yes'); settle(1200); n, rs = rows()
    ok(n > 0, f'{n:,} tax-delinquent estates')
    ok(all(bit(r, 'TX') and r['flags'] & 64 for r in rs), 'every sample: delinquent taxes + estate/heirs')
@scenario
def s06_assemblages_upside_miami_beach():
    reset(); select('#city', 'Miami Beach'); settle(); click('#asmOn'); settle(2500); check('#asmUp'); settle(1500)
    n, rs = rows()
    ok(n > 0, f'{n:,} assemblage parcels with upside in Miami Beach')
    ok(all(r['asm'] and r['asm']['upside'] for r in rs) and all(r['city'] == 'Miami Beach' for r in rs), 'every sample: upside group, Miami Beach')
    ok(rs == [] or pg.evaluate('PF.sample(1)')['sort'] == 'asm_d', 'sorted by assemblage score')
    shot('06_asm_miami_beach')
@scenario
def s07_money_shorthand():
    reset()
    for v, want in [('1.2m', 1200000), ('500K', 500000), ('$750,000', 750000), ('2.5k', 2500)]:
        money('#mvMax', v); n, rs = rows(150)
        ok(f'mvMax={want}' in pg.evaluate('location.hash') and all(r['mkt'] <= want for r in rs), f'max "{v}" -> {want:,}: {n:,}, all under')
    money('#mvMax', '1.2m'); money('#mvMin', '500k'); n, rs = rows(150)
    ok(all(500000 <= r['mkt'] <= 1200000 for r in rs), f'500k-1.2m range: {n:,}')
    for v in ('', '0', 'abc', '-'):
        money('#mvMin', v); money('#mvMax', v); n = cnt()
        ok(n == TOTAL['all'], f'"{v}" means no limit ({n:,})')
        ok('mvMax' not in pg.evaluate('location.hash'), f'"{v}" not put in link')
    money('#mvMax', 'abc'); ok(pg.get_attribute('#mvMax', 'aria-invalid') == 'true', 'invalid amount is flagged on the box')
    money('#mvMax', '')
@scenario
def s08_zoning_prefix():
    reset()
    for q, rx in [('T6', r'^T6'), ('RU-1', r'^RU-1'), ('rs-', r'^RS-'), ('T3-R, T4-R', r'^(T3-R|T4-R)')]:
        fill('#mzq', q); settle(1200); n, rs = rows(200)
        ok(n > 0 and all(re.match(rx, r['mzCode'].upper()) for r in rs), f'code "{q}": {n:,}, all match {rx}')
    fill('#mzq', 'ZZZ9'); settle(1000); ok(cnt() == 0, 'unknown code -> 0 results')
    ok(pg.is_visible('#empty'), 'empty state shown for zero results')
    click('#clrMz'); settle(); ok(cnt() == TOTAL['all'], 'clear zoning')
@scenario
def s09_teardown_rules_and_reset():
    reset(); click('#tierSeg button[data-tier="basic"]'); settle(); n0 = cnt()
    fill('#td_land', '90'); pg.press('#td_land', 'Tab'); settle(1500); n1 = cnt()
    ok(n1 < n0, f'land share 80% -> 90% shrinks teardowns {n0:,} -> {n1:,}')
    fill('#td_yb', '1950'); pg.press('#td_yb', 'Tab'); settle(1500); n2 = cnt(); _, rs = rows(150)
    ok(n2 < n1 and all(0 < r['yb'] <= 1950 for r in rs) and all(r['land'] >= .9 * r['mkt'] for r in rs), f'built <= 1950 and land >= 90%: {n2:,}')
    ok('tdr=' in pg.evaluate('location.hash'), 'custom rules in link')
    click('#tdReset'); settle(1500)
    ok(cnt() == n0 and pg.input_value('#td_land') == '80' and pg.input_value('#td_yb') == '1969' and 'tdr=' not in pg.evaluate('location.hash'), 'Reset restores defaults and count')
@scenario
def s10_send_to():
    reset(); preset('Strong teardowns')
    f1, f2 = (pg.get_attribute(f'#cards .card:nth-of-type({k})', 'data-folio') for k in (1, 2))
    for f in (f1, f2): click(f'#cards .card[data-folio="{f}"] [data-sendtag="cc"]')
    click(f'#cards .card[data-folio="{f1}"] [data-sendtag="dk"]'); pg.wait_for_timeout(400)
    ok(pg.query_selector('.drawer') is None, 'tagging does not open the drawer')
    click('#sendChips .chip[data-send="cc"]'); settle(); ok(cnt() == 2, 'Send to: call center filter shows the 2 tagged')
    fill('#listName-cc', 'Scenario list'); rs = csv_of('#sendExp-cc')
    ok({r['Folio'] for r in rs} == {f1, f2} and rs and list(rs[0].keys()) == ['Address', 'Owner Name', 'Mailing Address', 'Folio', 'County', 'City'], 'Send to export: the 2 folios, 6 contact columns only')
    click('#sendBar [data-sendmark="1"]'); pg.wait_for_timeout(500)
    ok(pg.is_disabled('#sendExp-cc'), 'after Mark as sent nothing new to export')
    click(f'#cards .card[data-folio="{f1}"] .resend[data-resend="cc"]'); pg.wait_for_timeout(400)
    rs = csv_of('#sendExp-cc'); ok([r['Folio'] for r in rs] == [f1], 'Re-send exports only the re-sent parcel')
    for f in (f1, f2): click(f'#cards .card[data-folio="{f}"] [data-sendtag="cc"]'); pg.wait_for_timeout(200)
    click('#clrSend'); settle()
@scenario
def s11_save_with_notes():
    reset(); preset('Unsafe structures'); f = pg.get_attribute('#cards .card:nth-of-type(1)', 'data-folio')
    click('#cards .card:nth-of-type(1)', position={'x': 8, 'y': 8}); pg.wait_for_selector('.drawer .svsave', timeout=60000)
    click('.drawer .svsave'); pg.wait_for_selector('#svStatusSel'); select('#svStatusSel', 'Called')
    fill('#svNote', 'Spoke to son, call back Friday'); pg.wait_for_timeout(1200); pg.keyboard.press('Escape')
    ok(int(pg.inner_text('#savedCount') or 0) >= 1, 'saved count badge')
    go('', reload=True); click('#savedBtn'); settle(1500)
    ok(pg.query_selector(f'#cards .card[data-folio="{f}"]') is not None, 'saved parcel listed in Saved view after reload')
    ok('Spoke to son' in pg.inner_text(f'#cards .card[data-folio="{f}"]') and 'Called' in pg.inner_text(f'#cards .card[data-folio="{f}"]'), 'card shows status and note')
    click('#svBack'); settle()
@scenario
def s12_lenders():
    click('#lendersBtn'); pg.wait_for_selector('#lendersPage:not([hidden])')
    click('[data-act="add-lender"] >> nth=0'); pg.wait_for_selector('#lfForm')
    fill('#lfName', 'Scenario Lender'); fill('#lfCompany', 'Test Capital'); fill('#lfMax', '500k'); select('#lfStatus', 'Active')
    click('#lfForm button[type=submit]'); pg.wait_for_timeout(400); click('[data-tab="lenders"]'); pg.wait_for_timeout(300)
    card = next((c for c in pg.query_selector_all('.lcard') if 'Scenario Lender' in c.inner_text()), None)
    ok(card is not None, 'lender card added'); ok(card is not None and '$500,000' in card.inner_text(), 'max loan "500k" saved as $500,000')
    ok(int(pg.inner_text('#lendersCount') or 0) >= 1, 'header lender badge')
    shot('12_lenders'); click('#lpClose'); pg.wait_for_timeout(300)
@scenario
def s13_owner_portfolio():
    reset(); check('#ogInst'); fill('#q', 'LENNAR HOMES LLC'); settle(1500)
    click('#cards .card', position={'x': 8, 'y': 8}); pg.wait_for_selector('.drawer .dsec', timeout=60000); click('#ownerOpen')
    pg.wait_for_selector('.ogdrawer .ogitem', timeout=120000); pg.wait_for_timeout(800)
    k = len(pg.query_selector_all('.ogdrawer .ogitem')); ok(k > 5, f'portfolio lists {k} properties'); shot('13_portfolio')
    click('#ogTblBtn'); settle(2000); n, rs = rows(100)
    ok(n >= k and len({r['og'] for r in rs}) == 1, f'portfolio table: {n} parcels, one owner group')
    pg.keyboard.press('Escape'); click('#clrOg'); uncheck('#ogInst'); fill('#q', ''); settle()
@scenario
def s14_map_many_and_zero():
    reset(); preset('Teardowns'); click('#vMap')
    pg.wait_for_function("document.getElementById('mapHint').textContent.includes('on the map')", timeout=180000); pg.wait_for_timeout(1500)
    ok(re.search(r'[\d,]+ on the map', pg.inner_text('#mapHint')) is not None, 'map: ' + pg.inner_text('#mapHint')[:80]); shot('14_map_many')
    fill('#mzq', 'ZZZ9'); settle(1500)
    ok(cnt() == 0 and 'Nothing matches' in pg.inner_text('#mapHint'), 'map with zero results: ' + pg.inner_text('#mapHint')[:60]); shot('14_map_zero')
    fill('#mzq', ''); click('#vCards'); settle()
@scenario
def s15_share_link_full_state():
    reset(); select('#city', 'Hialeah'); click('#types .chip[data-t="sf"]'); click('#dsigs .chip[data-sig="CC"]')
    money('#mvMax', '600k'); click('#ownerKind button[data-k="person"]'); click('#tierSeg button[data-tier="basic"]')
    select('#sortSel', 'mv_a'); click('#vTable'); settle(1500)
    h, n = pg.evaluate('location.hash'), cnt()
    p2 = ctx.new_page(); p2.goto(BASE + h, timeout=180000)
    if MOB and p2.query_selector('#drive:not([hidden])'): p2.click('#dExit')
    p2.wait_for_selector('#results:not([hidden])', timeout=240000); p2.wait_for_timeout(3000)
    ok(int(p2.inner_text('#sCount').replace(',', '')) == n, f'fresh tab from link shows the same {n:,}')
    ok(p2.input_value('#city') == 'Hialeah' and p2.input_value('#sortSel') == 'mv_a' and p2.input_value('#mvMax') == '600k' and not p2.is_hidden('#tablebox'), 'city, sort, money box and table view restored')
    ok(p2.evaluate('location.hash') == h, 'link unchanged after load'); p2.close()
@scenario
def s16_csv_columns():
    reset(); go('city=Miami%20Gardens&sig=TD&type=sf'); n = cnt(); ok(0 < n < 5000, f'{n} rows to export')
    rs = csv_of('#exportBtn'); hdr = list(rs[0].keys()) if rs else []
    ok(len(rs) == n, f'CSV rows {len(rs)} = results {n}')
    ok(hdr == ['Address', 'Owner Name', 'Mailing Address', 'Folio', 'County', 'City'], f'columns exactly Address, Owner Name, Mailing Address, Folio, County, City ({hdr})')
    ok(all(re.fullmatch(r'[\d-]{13,17}', r['Folio']) for r in rs), 'folios look right')
    ok(len({r['Folio'] for r in rs}) == len(rs), 'no duplicate rows')
    ok(all(r['City'] == 'Miami Gardens' for r in rs), 'city column matches filter')
    ok(all(r['County'] == 'Miami-Dade' and r['Owner Name'] for r in rs), 'county + owner filled')
    ok(sum(1 for r in rs if r['Mailing Address']) >= 0.9 * len(rs), 'mailing address present on most rows')
@scenario
def s17_sort_orders():
    reset(); go('type=sf&city=Doral')
    for k, f, d in [('lot_d', 'lot', -1), ('lot_a', 'lot', 1), ('mv_a', 'mkt', 1), ('mv_d', 'mkt', -1), ('held_d', 'sd1', 1), ('sold_d', 'sd1', -1), ('ds_d', 'dscore', -1), ('un_d', 'units', -1), ('yb_a', 'yb', 1), ('addr_a', 'addr', 1)]:
        select('#sortSel', k); settle(900); _, rs = rows(120)
        v = [r[f] for r in rs if (r[f] or f in ('dscore', 'units'))]
        good = v == sorted(v, reverse=d < 0)
        ok(good, f'sort {k} orders by {f}' + ('' if good else f' {v[:6]}'))
@scenario
def s18_hide_companies_and_institutions():
    reset(); click('#ownerKind button[data-k="person"]'); settle(); n, rs = rows(400)
    bad = [r['owner'] for r in rs if re.search(r'\b(LLC|INC|CORP|BANK|FPL|FLORIDA POWER|SFWMD|WATER MANAGEMENT|CITY OF|COUNTY|TRUST)\b', r['owner'])]
    ok(not bad, f'"Individuals": {n:,}, no companies / utilities / banks / government in sample' + (f' (saw {bad[:3]})' if bad else ''))
    reset(); _, rs = rows(800)
    bad = [r['owner'] for r in rs if r['flags'] & 32 or re.search(r'SFWMD|WATER MANAGEMENT DIST|MIAMI-DADE COUNTY|CITY OF MIAMI\b|STATE OF FLORIDA', r['owner'])]
    ok(not bad, 'default (hide government): no SFWMD / county / city / state owners' + (f' (saw {bad[:3]})' if bad else ''))
    reset(); select('#ogMin', '5'); settle(2500); _, rs = rows(500)
    bad = [r['owner'] for r in rs if re.search(r'\bBANK\b|FPL|FLORIDA POWER|SFWMD|WATER MANAGEMENT|HOUSING AUTHORITY', r['owner'])]
    ok(not bad, 'owners with 5+ parcels exclude banks, FPL, SFWMD & big institutions' + (f' (saw {bad[:3]})' if bad else ''))
    check('#ogInst'); settle(2000); _, rs2 = rows(800)
    ok(cnt() > 0, 'including institutions adds them back'); uncheck('#ogInst'); select('#ogMin', '0'); settle()
@scenario
def s19_clear_all():
    reset(); go('sig=LP&type=sf&city=Miami&td=basic&mvMax=900000&asm=1&o_oos=yes'); ok(cnt() < TOTAL['all'], 'many filters on')
    ok(int(re.sub(r'\D', '', pg.inner_text('#onCount') or '0') or 0) >= 5, 'filters-on badge counts them: ' + pg.inner_text('#onCount'))
    click('#resetBtn'); settle(1500)
    ok(cnt() == TOTAL['all'] and pg.evaluate('location.hash') in ('', '#'), 'Clear all -> every parcel, empty link')
    ok(pg.input_value('#city') == '' and pg.input_value('#mvMax') == '' and not pg.query_selector('#dsigs .chip.on') and not pg.is_checked('#asmUp'), 'all inputs cleared')
@scenario
def s20_back_forward():
    go('', reload=True); reset()
    click('#types .chip[data-t="vacant"]'); settle(); a = cnt()
    select('#city', 'Homestead'); settle(); b = cnt()
    ok(b < a, f'vacant {a:,} -> + Homestead {b:,}')
    pg.go_back(); settle(1500); ok(cnt() == a and pg.input_value('#city') == '', f'Back -> {cnt():,} (expected {a:,})')
    pg.go_forward(); settle(1500); ok(cnt() == b and pg.input_value('#city') == 'Homestead', f'Forward -> {cnt():,} (expected {b:,})')
@scenario
def s21_reload_persistence():
    reset(); go('type=mf29&city=Miami&sort=mv_a&view=table'); n = cnt()
    pg.reload(); boot(); settle(1500)
    ok(cnt() == n and pg.input_value('#sortSel') == 'mv_a', f'reload with link keeps {n:,} and sort')
    pg.goto(BASE, timeout=180000); boot(); settle(1500)
    ok(cnt() == n, f'reopening the site with no link restores the last search ({cnt():,})')
@scenario
def s22_drawer_and_table():
    reset(); preset('Hottest leads'); click('#vTable'); settle()
    ok(len(pg.query_selector_all('#tbody tr[data-id]')) > 10, 'table rows'); pg.locator('#tbody tr[data-id]').first.locator('td').nth(2).click(); pg.wait_for_selector('.drawer', timeout=60000); pg.wait_for_timeout(800)
    d = pg.inner_text('.drawer').lower(); ok('distress' in d and 'folio' in d, 'drawer opens from the table with distress section'); shot('22_drawer')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(300); ok(pg.query_selector('.drawer') is None, 'Esc closes drawer'); click('#vCards'); settle()
@scenario
def s23_area_and_zip():
    reset(); fill('#zips', '33133, 33146'); settle(1500); n, rs = rows()
    ok(n > 0 and all(r['zip'] in ('33133', '33146') for r in rs), f'two ZIPs: {n:,}')
    fill('#zips', ''); settle()
@scenario
def s24_search_box():
    reset(); fill('#q', 'BRICKELL AVE'); settle(1500); n, rs = rows(100)
    ok(n > 0 and all('BRICKELL AVE' in (r['addr'] + ' ' + r['owner']).upper() for r in rs), f'search "BRICKELL AVE": {n:,}')
    fill('#q', ''); settle()
@scenario
def s25_lot_and_construction_chips():
    reset(); click('#lotz .chip[data-lz="split"]'); settle(1500); n, rs = rows(150)
    ok(n > 0, f'lots that could be split: {n:,}')
    click('#lotz .chip[data-lz="split"]'); click('#lotz .chip[data-lz="below"]'); settle(1500); ok(cnt() > 0, f'under zone minimum: {cnt():,}')
    click('#lotz .chip[data-lz="below"]'); settle(); ok(cnt() == TOTAL['all'], 'lot chips cleared')
@scenario
def s26_adverse_possession():
    reset(); check('#apOnly'); settle(1500); n, rs = rows(150)
    ok(n > 0 and all(r['ap'] for r in rs), f'adverse possession: {n:,}'); uncheck('#apOnly'); settle()
@scenario
def s27_assemblage_group_flow():
    reset(); preset('🧩 Assemblages'); pg.wait_for_selector('#cards .card .asmb', timeout=60000); b = pg.locator('#cards .card .asmb').first
    lots = int(re.search(r'(\d+) lots', b.inner_text()).group(1)); b.click(); settle(1500)
    ok(cnt() == lots, f'Show group -> {cnt()} = {lots}'); click('#asmBack'); settle(1500); ok(cnt() > lots, 'All groups back')
@scenario
def s28_owner_flags_combo():
    reset(); go('o_homestead=no&o_oos=yes&type=sf&hdMin=20'); n, rs = rows()
    ok(n > 0 and all(not (r['flags'] & 1) and r['flags'] & 2 for r in rs), f'tired out-of-state landlords: {n:,}, flags agree')
    now = time.time() / 86400 + 25567; ok(all(r['sd1'] == 0 or now - r['sd1'] >= 20 * 365 - 5 for r in rs), 'held 20+ years')
@scenario
def s29_copy_link_and_folios():
    reset(); go('city=Bay%20Harbor%20Islands&type=sf'); pg.context.grant_permissions(['clipboard-read', 'clipboard-write']) if not MOB else None
    click('#copyBtn'); pg.wait_for_timeout(500); ok(True, 'Copy folios clicked without error')
    click('#linkBtn'); pg.wait_for_timeout(500); ok(True, 'Copy link clicked without error')
@scenario
def s30_condo_lazy_pack():
    reset(); click('#types .chip[data-t="condo"]'); settle(4000); n, rs = rows(100)
    ok(n > 1000 and all(r['type'] == 'condo' for r in rs), f'condo units load on demand: {n:,}')
@scenario
def s31_vacancy_signals():
    reset(); preset('Likely vacant'); n, rs = rows(150); ok(n > 0, f'likely vacant: {n:,}')
@scenario
def s34_folio_deep_link():
    reset(); check('#pfOnly'); settle(1500); f = sample(5)['rows'][0]['folio']; uncheck('#pfOnly'); settle()
    p2 = ctx.new_page(); p2.goto(BASE + ('&' if '?' in BASE else '?') + 'folio=' + f[:2] + '-' + f[2:6] + '-' + f[6:9] + '-' + f[9:], timeout=180000)
    if MOB and p2.query_selector('#drive:not([hidden])'): p2.click('#dExit')
    p2.wait_for_selector('.drawer', timeout=120000); t = p2.inner_text('.drawer')
    ok(re.sub(r'\D', '', t.split('\n')[1] if t.startswith('Close') else t)[:13] == f or f[:2] + '-' + f[2:6] in t, f'?folio= with dashes opens the drawer of {f}')
    ok(p2.locator('.card.flash').count() == 1, 'the deep-linked card is highlighted'); p2.close()
@scenario
def s35_pre_foreclosure_open_lp():
    reset(); check('#pfOnly'); settle(1500); n, rs = rows(150); c = int(re.sub(r'\D', '', pg.inner_text('#pfCount')) or 0)
    ok(n > 0 and n == c, f'pre-foreclosure filter {n:,} = its count {c:,}')
    ok(all(r['pf'] for r in rs), 'every sampled row has an open lis pendens')
    meta = pg.evaluate('PF.sigMeta()'); ok(all(r['pf'][1] >= meta['pf']['from'] for r in rs), 'recorded inside the covered period')
    ok(pg.locator('#cards .card .pfb').count() > 0 and 'Verify with the Clerk' in (pg.get_attribute('#cards .card .pfb', 'title') or ''), 'cards carry the Pre-foreclosure tag with the case/CFN tooltip')
    ok('pf=1' in pg.evaluate('location.hash'), 'filter is in the share link')
    go(pg.evaluate('location.hash').lstrip('#'), reload=True); ok(cnt() == n, 'share link restores it'); uncheck('#pfOnly'); settle()
@scenario
def s36_probate_filed_confidence():
    reset(); select('#pbSel', 'hm'); settle(1500); n1, r1 = rows(150); select('#pbSel', 'h'); settle(1500); n2, r2 = rows(150)
    ok(n1 > 0 and 0 < n2 <= n1, f'probate filed: high+medium {n1:,} >= high only {n2:,}')
    ok(all(r['pb'] for r in r1) and all(r['pb'][4] == 'H' for r in r2), 'rows match the chosen confidence')
    ok(pg.locator('#cards .card .pbb').count() > 0, 'cards carry the Probate filed tag'); select('#pbSel', ''); settle()
@scenario
def s37_auction_max_bid():
    reset(); go('sig=FC'); n, rs = rows(150); withau = [r for r in rs if r['au']]
    ok(n > 0 and len(withau) > 0, f'scheduled foreclosure sales carry auction rows ({len(withau)}/{len(rs)})')
    ok(pg.locator('#cards .auline').count() > 0 and 'max bid' in pg.inner_text('#cards .auline'), 'card shows the auction line with the max bid')
    pg.click('#cards .card:has(.auline)', position={'x': 8, 'y': 8}); pg.wait_for_selector('.drawer', timeout=60000); pg.wait_for_timeout(800); reveal('.drawer .aumax'); pg.wait_for_selector('.drawer .aumax', timeout=60000)
    ok('plaintiff max bid' in pg.inner_text('.drawer .aumax').lower(), 'drawer lists the plaintiff max bid'); pg.keyboard.press('Escape'); settle(400)
@scenario
def s38_comps_value_estimate():
    reset(); go('type=sf'); pg.wait_for_function('PF.compsReady()', timeout=180000); settle(800); n, rs = rows(200)
    e = [r for r in rs if r['comps'] and r['comps']['est']]
    ok(len(e) >= 0.8 * len(rs), f'single family: {len(e)}/{len(rs)} have a comps estimate')
    ok(all(r['comps']['n'] >= 3 and r['comps']['lo'] <= r['comps']['est'] <= r['comps']['hi'] and r['comps']['rad'] <= 2 for r in e), 'estimate sits in its range, 3+ comps within 2 mi')
    t = pg.inner_text('#cards .card .cpline:has(b)'); ok(re.search(r'\$[\d.]+[KM]?–\$[\d.]+[KM]?', t) is not None, f'card shows the value range ({t.strip()[:60]})')
    ok('last 6 months' in (pg.get_attribute('#cards .card .cpline:has(b) .v span', 'title') or ''), 'range tooltip explains radius / months / land use / financing')
    cl = pg.locator('#cards .card:has(.cpline b)').first; cl.scroll_into_view_if_needed(); cl.locator('.facts').click(); pg.wait_for_selector('.drawer', timeout=60000); pg.wait_for_timeout(800)
    reveal('.drawer .cpt'); ok(pg.locator('.drawer .cpt tbody tr').count() >= 3, 'drawer lists the comparable sales'); pg.keyboard.press('Escape'); settle(400)
@scenario
def s39_outreach_followups_due():
    reset(); go(''); settle(800); fs = pg.eval_on_selector_all('#cards .card', 'e=>e.slice(0,2).map(x=>x.dataset.folio)')
    pg.evaluate("([a,b])=>{const t=new Date(),y=new Date(t-2*864e5),p=d=>d.toISOString().slice(0,10);PF.SV.logActivity(a,{type:'call',d:p(t),outcome:'Talked'});PF.SV.update(a,{next:p(y)});PF.SV.logActivity(b,{type:'mailer',d:p(t)});PF.SV.update(b,{next:'2099-01-01'})}", fs)
    go('due=1'); settle(1500); cs = pg.eval_on_selector_all('#cards .card', 'e=>e.map(x=>x.dataset.folio)')
    ok(fs[0] in cs and fs[1] not in cs, f'Due/overdue filter shows only the overdue lead ({len(cs)} cards)')
    ok('Overdue' in pg.inner_text('#cards'), 'overdue badge on the card')
@scenario
def s40_outreach_pipeline():
    go('view=pipe'); settle(1500)
    ok(pg.locator('#pipeCols .pcol').count() == 7, 'pipeline has 7 stage columns')
    ok(pg.locator('#pipeCols .pcol[data-stage="Contacted"] .pitem').count() >= 2, 'contacted leads appear in the Contacted column')
@scenario
def s32_mobile_or_desktop_layout():
    reset(); w = pg.evaluate('document.documentElement.scrollWidth'); vw = pg.evaluate('innerWidth')
    ok(w <= vw + 1, f'no horizontal scroll ({w} <= {vw})'); shot('32_layout')
@scenario
def s32b_no_float_noise():
    reset(); preset('Houses on multifamily land'); txt = pg.inner_text('#cards')
    bad = re.findall(r'\d\.\d{4,}', txt); ok(not bad, 'card numbers are rounded' + (f' (saw {bad[:3]})' if bad else ''))
    click('#cards .card', position={'x': 8, 'y': 8}); pg.wait_for_selector('.drawer', timeout=60000); pg.wait_for_timeout(1200)
    bad = re.findall(r'\d\.\d{4,}', pg.inner_text('.drawer')); ok(not bad, 'drawer numbers are rounded' + (f' (saw {bad[:3]})' if bad else '')); pg.keyboard.press('Escape')
@scenario
def s33_no_console_errors():
    ok(not errs, 'no console errors / page errors during the whole run' + (f': {errs[:3]}' if errs else ''))

# ---------------------------------------------------------------- run
with sync_playwright() as pw:
    br = pw.chromium.launch()
    vp = {'width': 390, 'height': 844} if MOB else {'width': 1360, 'height': 900}
    ctx = br.new_context(viewport=vp, accept_downloads=True, is_mobile=MOB, has_touch=MOB)
    pg = ctx.new_page(); pg.set_default_timeout(90000); pg.on('dialog', lambda d: d.accept())
    pg.on('console', lambda m: m.type == 'error' and not re.search(r'arcgisonline|tile|ERR_|net::|Failed to load resource', m.text) and errs.append('console: ' + m.text))
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    pg.goto(BASE, timeout=180000); boot(); reset(); TOTAL['all'] = cnt(); print(f'[{MODE}] {URL} all parcels {TOTAL["all"]:,}')
    import os; only = [x for x in os.environ.get('ONLY', '').split(',') if x]
    for f in SC:
        if only and not any(f.__name__.startswith(o) for o in only) and f.__name__ != 's33_no_console_errors': continue
        cur = {'name': f.__name__, 'fails': []}; print(f'== {f.__name__}', flush=True); t = time.time()
        try: f()
        except Exception as e:
            loc = next((l.strip() for l in str(e).split('\n') if 'locator(' in l), ''); cur['fails'].append('exception: ' + str(e).split('\n')[0][:200] + ' ' + loc[:120]); print('  EXC', str(e).split('\n')[0][:300], loc[:200])
            try: pg.keyboard.press('Escape'); pg.evaluate("document.getElementById('lendersPage').hidden||document.getElementById('lpClose').click()")
            except Exception: pass
        results.append((f.__name__, cur['fails'], time.time() - t))
    br.close()
bad = [r for r in results if r[1]]
print(f'\nSUMMARY [{MODE}] {len(results) - len(bad)}/{len(results)} scenarios passed')
for n_, fl, _ in bad: print('  FAILED', n_, '|', '; '.join(fl)[:400])
sys.exit(1 if bad else 0)
