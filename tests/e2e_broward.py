"""Broward County: switcher, packs, hidden layers, flood filter, buildability screen, city zoning filter, auction signals, drawer, per-county storage, CSV County column.
usage: python3 tests/e2e_broward.py [base_url] [desktop|mobile]"""
import sys, re, json, csv, io
from playwright.sync_api import sync_playwright
URL = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/').rstrip('/') + '/'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'desktop'
MOB = MODE == 'mobile'
errs, fails = [], []
def check(ok, msg): print(('ok   ' if ok else 'FAIL ') + msg); ok or fails.append(msg)
cnt = lambda pg: int(pg.inner_text('#sCount').replace(',', '') or 0)
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    vp = {'width': 390, 'height': 800} if MOB else {'width': 1300, 'height': 900}
    ctx = b.new_context(viewport=vp, service_workers='block', is_mobile=MOB, has_touch=MOB, accept_downloads=True)
    pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(URL + '?county=broward#hg=0'); pg.wait_for_selector('#results:not([hidden])', timeout=180000); pg.wait_for_selector('#cards .card', timeout=60000)
    sheet = lambda: (pg.click('#filtersBtn'), pg.wait_for_timeout(400)) if MOB and not pg.is_visible('#panel') else None
    total = pg.evaluate('fetch("data/broward/meta.json").then(r=>r.json()).then(m=>m.total)')
    check(pg.evaluate('PFCounty.id') == 'broward', 'active county = broward')
    check(pg.inner_text('header.top h1').lower().startswith('broward'), 'header says Broward: ' + pg.inner_text('header.top h1'))
    check(pg.input_value('#countySel') == 'broward', 'switcher shows Broward')
    check(pg.inner_text('#srcCount').replace(',', '') == str(total) and total > 500000, f'source line count {pg.inner_text("#srcCount")} == meta {total}')
    sheet()
    for sel in ('.grp.distress', '.grp.permits', '.grp.vacancy', '#asmGrp', '.grp[data-need="zoning"]'):
        check(not pg.is_visible(sel), f'{sel} hidden (layer missing)')
    check(pg.is_visible('#mrGrp') and pg.is_visible('.grp[data-need="mzoning"]'), 'buildability + city zoning groups visible')
    check(pg.evaluate("PFCounty.has('broward') && PFCounty.has('mscreen') && !PFCounty.has('rogo') && !PFCounty.has('distress')"), 'Broward layer list')
    check(not pg.is_visible('#mrTier') and not pg.is_visible('#mrRogo'), 'Monroe-only Tier / ROGO rows hidden')
    check('Broward' not in pg.inner_text('#mrGrp') or 'Monroe' not in pg.inner_text('#mrGrp'), 'no Monroe wording in the screen group')
    check('Monroe' not in pg.inner_text('#mrGrp'), 'screen group has no Monroe text')
    sigs = pg.eval_on_selector_all('#mrSig .chip', 'n=>n.map(x=>x.textContent)')
    check(not any('ROGO' in s or 'Probate' in s or 'Code case' in s for s in sigs), f'signal chips limited to what Broward has {sigs}')
    ideas = pg.eval_on_selector_all('#ideas .chip', 'n=>n.map(x=>x.textContent)')
    check(not any(k in t for t in ideas for k in ('Hottest', 'Assemblage', 'Commercial distress', 'ROGO')), f'ideas without missing layers ({len(ideas)})')
    check(pg.inner_text('label[for="cra"]') == 'FEMA flood zone', 'flood zone filter label')
    n0 = cnt(pg); check(n0 > 400000, f'all parcels (default view hides condos / government) {n0}')
    check(pg.query_selector('#cards .card .mrb') is not None, 'cards show a buildability badge')
    # flood
    opts = pg.eval_on_selector_all('#cra option', 'n=>n.map(x=>x.value)'); ve = next((o for o in opts if o.startswith('VE')), None) or next((o for o in opts if o.startswith('AE')), None)
    check(bool(ve), f'flood options ({len(opts)})')
    pg.evaluate("document.getElementById('moreBox').open=true")
    pg.select_option('#cra', ve); pg.wait_for_timeout(1200); n1 = cnt(pg); check(0 < n1 < n0, f'flood filter {ve!r}: {n0} -> {n1}')
    pg.select_option('#cra', ''); pg.wait_for_timeout(800)
    # rating chips
    pg.click('#mrRate .chip[data-mr="rate:G"]'); pg.wait_for_timeout(900); ng = cnt(pg); check(0 < ng < n0, f'green filter {n0} -> {ng}')
    check(pg.eval_on_selector_all('#cards .card .mrb', 'n=>n.length>0 && n.every(x=>x.classList.contains("G"))'), 'all visible cards are green')
    pg.click('#clrMr'); pg.wait_for_timeout(800); check(cnt(pg) == n0, 'clear restores count')
    pg.click('#mrZt .chip[data-mr="zt:duplex"]') if pg.query_selector('#mrZt .chip[data-mr="zt:duplex"]') else None; pg.wait_for_timeout(800); nd = cnt(pg); check(0 < nd < n0, f'duplex zoning type {nd}')
    pg.click('#clrMr'); pg.click('#mrZt .chip[data-mr="zt:sf"]'); pg.wait_for_timeout(800); nz = cnt(pg); check(0 < nz < n0, f'single-family zoning {nz}')
    pg.click('#clrMr'); pg.click('#mrAvoid .chip[data-mr="avoid:ve"]'); pg.wait_for_timeout(800); nv = cnt(pg); check(0 < nv <= n0, f'leave out VE {n0} -> {nv}')
    pg.click('#clrMr'); pg.click('#mrSig .chip[data-mr="sig:fc_open"]'); pg.wait_for_timeout(800); nf = cnt(pg); check(0 < nf < 2000, f'foreclosure auction signal {nf}')
    pg.click('#clrMr'); pg.click('#mrSig .chip[data-mr="sig:vacant"]'); pg.wait_for_timeout(800); nvac = cnt(pg); check(0 < nvac < n0, f'vacant signal {nvac}')
    pg.click('#clrMr'); pg.wait_for_timeout(600)
    # preset + drawer
    preset = pg.query_selector('#ideas .chip:text-is("Buildable lots")'); check(preset is not None, 'Buildable lots preset present')
    if preset:
        preset.click(); pg.wait_for_timeout(1500); npst = cnt(pg); check(0 < npst < n0, f'preset applies ({npst})')
        pg.click('#cards .card h3'); pg.wait_for_selector('.drawer', timeout=30000); txt = pg.inner_text('.drawer')
        check('buildability screen' in txt.lower() and 'not a determination' in txt.lower(), 'drawer shows the screen + disclaimer')
        check('Monroe' not in txt and 'ROGO' not in txt, 'drawer has no Monroe wording')
        check('auctions & legal notices' in txt.lower(), 'drawer has the auctions & legal notices section')
        check('not loaded' in pg.evaluate("document.querySelector('.drawer').textContent").lower(), 'drawer states what public data is not loaded')
        href = pg.get_attribute('.drawer a:has-text("Property Appraiser page")', 'href') or ''
        check(bool(re.search(r'bcpa\.net/RecInfo\.asp\?URL_Folio=\d{12}$', href)), 'BCPA link uses the folio: ' + href[-45:])
        pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    # absentee wording
    sheet(); check('outside Broward' in pg.inner_text('body'), 'absentee label says outside Broward')
    # city zoning filter group
    pg.click('.grp[data-need="mzoning"] .gtog'); pg.wait_for_timeout(300); check(pg.is_visible('#mzq') and pg.is_visible('#mzCities'), 'zoning code box + by-city list open')
    # owner name order + per-county storage
    check(pg.evaluate("PFCounty.cfg.nameOrder") == 'last-first', 'skip trace nameOrder last-first')
    check(pg.evaluate("PFCounty.key('pf.send.v1')") == 'pf.send.v1.broward', 'send tags key per county')
    pg.evaluate("localStorage.setItem('mdpf.saved.v1', JSON.stringify({'0000000000001':{folio:'0000000000001'}}))")
    pg.wait_for_timeout(400); keys = pg.evaluate("Object.keys(localStorage)"); check('mdpf.v2.broward' in keys, 'Broward search state under mdpf.v2.broward')
    check(list(json.loads(pg.evaluate("localStorage.getItem('mdpf.saved.v1')"))) == ['0000000000001'], 'Miami-Dade saved list untouched')
    # hash round trip
    pg.goto(URL + '?county=broward#bld=R'); pg.wait_for_selector('#results:not([hidden])', timeout=180000); pg.wait_for_timeout(1500); sheet()
    check(pg.eval_on_selector_all('#mrRate .chip.on', 'n=>n.map(x=>x.dataset.mr)') == ['rate:R'], 'rating restored from the URL')
    check('bld_a' in pg.eval_on_selector_all('#sortSel option', 'n=>n.map(x=>x.value)'), 'sort by best buildability available')
    # CSV export: County column = Broward, 12-char folios, address never blank
    pg.goto(URL + '?county=broward#type=vacant&gov=1'); pg.wait_for_selector('#cards .card', timeout=180000); pg.wait_for_timeout(1500)
    if MOB and not pg.is_visible('#exportBtn'):
        m = pg.query_selector('#moreBtn, .mmore, [data-more]')
        if m: m.click(); pg.wait_for_timeout(300)
    with pg.expect_download(timeout=240000) as dl: pg.evaluate("document.querySelector('#exportBtn').click()")
    rows = list(csv.reader(io.StringIO(open(dl.value.path(), encoding='utf-8').read())))
    check(rows[0] == ['Address', 'Owner Name', 'Mailing Address', 'Folio', 'County', 'City', 'State'], 'export header: 7 contact columns')
    body = rows[1:]; check(len(body) > 1000 and all(len(r) == 7 and r[4] == 'Broward' and r[6] == 'FL' for r in body), f'export {len(body)} rows, County column = Broward')
    check(all(re.fullmatch(r'\d{6}[0-9A-Z]{2}\d{4}|\d{12}', r[3]) for r in body), 'export folios are 12 characters')
    check(all(r[0].strip() for r in body), 'export: Address never blank')
    # switch to Monroe and back keeps data separate
    pg.goto(URL + '?county=monroe#hg=0'); pg.wait_for_selector('#results:not([hidden])', timeout=180000)
    check(pg.evaluate("PFCounty.id") == 'monroe' and cnt(pg) < 100000 and pg.evaluate("PFCounty.has('rogo')"), 'Monroe unaffected (own pack, ROGO rows)')
    b.close()
check(not errs, 'no page errors ' + '; '.join(errs[:3]))
print('RESULT', 'PASS' if not fails else f'FAIL ({len(fails)})'); sys.exit(1 if fails else 0)
