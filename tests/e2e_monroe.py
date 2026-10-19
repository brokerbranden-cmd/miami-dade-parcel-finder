"""Monroe buildability screen + unpaid-tax layer (filters, badges, drawer, preset, hash, export columns unchanged): group, rating chips, filters, preset, card badge, drawer reasons + disclaimer, absentee label, qPublic link, hash round trip.
usage: python3 tests/e2e_monroe.py [base_url] [desktop|mobile]"""
import sys, re
from playwright.sync_api import sync_playwright
URL = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/').rstrip('/') + '/'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'desktop'
errs, fails = [], []
def check(ok, msg): print(('ok   ' if ok else 'FAIL ') + msg); ok or fails.append(msg)
MOB = MODE == 'mobile'
cnt = lambda pg: int(pg.inner_text('#sCount').replace(',', '') or 0)
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    vp = {'width': 390, 'height': 800} if MODE == 'mobile' else {'width': 1300, 'height': 900}
    ctx = b.new_context(viewport=vp, service_workers='block', is_mobile=MODE == 'mobile', has_touch=MODE == 'mobile')
    pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(URL + '?county=monroe#hg=0'); pg.wait_for_selector('#results:not([hidden])', timeout=120000); pg.wait_for_selector('#cards .card', timeout=60000)
    sheet = lambda: (pg.click('#filtersBtn'), pg.wait_for_timeout(400)) if MOB and not pg.is_visible('#panel') else None
    check(pg.evaluate("PFCounty.has('monroe')"), 'Monroe has the monroe layer'); sheet()
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
        pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    # absentee wording
    sheet()
    check('outside the Keys' in pg.inner_text('body') or pg.evaluate("document.getElementById('ow_absz')&&document.getElementById('ow_absz').closest('label,div').innerText").lower().count('outside the keys') > 0, 'absentee label says outside the Keys')
    # hash round trip
    pg.goto(URL + '?county=monroe#bld=R&mtier=1'); pg.wait_for_selector('#results:not([hidden])', timeout=120000); pg.wait_for_timeout(1500); sheet()
    check(pg.eval_on_selector_all('#mrRate .chip.on', 'n=>n.map(x=>x.dataset.mr)') == ['rate:R'], 'rating restored from the URL')
    check(pg.eval_on_selector_all('#cards .card .mrb', 'n=>n.length>0 && n.every(x=>x.classList.contains("R"))'), 'URL filter shows only red')
    # sort option
    check('bld_a' in pg.eval_on_selector_all('#sortSel option', 'n=>n.map(x=>x.value)'), 'sort by best buildability available')
    # zoning code filter exists for Monroe
    pg.goto(URL + '?county=monroe#hg=0'); pg.wait_for_selector('#cards .card', timeout=120000); sheet()
    check(pg.is_visible('.grp[data-need="mzoning"]'), 'city zoning code filter group visible')
    pg.click('.grp[data-need="mzoning"] .gtog'); pg.wait_for_timeout(300); check(pg.is_visible('#mzq') and pg.is_visible('#mzCities'), 'zoning code box + by-city list open')
    pg.goto(URL + '?county=monroe#code=R1'); pg.wait_for_selector('#cards .card', timeout=120000); pg.wait_for_timeout(1500); nzz = cnt(pg); check(0 < nzz < 20000, f'zoning code R1 (Islamorada) filter -> {nzz}')
    # ---- unpaid property taxes (Tax Collector report, as of Oct 16, 2026)
    pg.goto(URL + '?county=monroe#hg=0'); pg.wait_for_selector('#cards .card', timeout=120000); sheet(); n0 = cnt(pg)
    check(pg.is_visible('#mtGrp'), 'unpaid-taxes group visible for Monroe')
    tch = pg.eval_on_selector_all('#mtChips .chip', 'n=>n.map(x=>x.dataset.mr)'); check(tch == ['tax:any', 'tax:y2', 'tax:y3', 'tax:cert', 'tax:county'], f'tax chips {tch}')
    pg.click('#mtChips .chip[data-mr="tax:any"]'); pg.wait_for_timeout(900); t1 = cnt(pg); check(1000 < t1 < 2000, f'tax delinquent filter {n0} -> {t1}')
    check(pg.eval_on_selector_all('#cards .card', 'n=>n.length>0 && n.every(c=>c.querySelector(".taxb"))'), 'every visible card carries the tax-delinquent badge')
    check('mtax=any' in pg.evaluate('location.hash'), 'hash carries mtax=any')
    pg.click('#mtChips .chip[data-mr="tax:y2"]'); pg.wait_for_timeout(900); t2 = cnt(pg); check(300 < t2 < t1, f'2+ years {t1} -> {t2}')
    pg.click('#mtChips .chip[data-mr="tax:y3"]'); pg.wait_for_timeout(900); t3 = cnt(pg); check(20 < t3 < t2, f'3+ years {t2} -> {t3}')
    check(pg.eval_on_selector_all('#cards .card .taxb', 'n=>n.length>0 && n.every(x=>/(\\d+) yrs/.test(x.textContent) && +RegExp.$1>=3)'), 'cards under 3+ years show 3+ yrs')
    pg.click('#clrMt'); pg.wait_for_timeout(700); check(cnt(pg) == n0, 'tax Clear restores the count')
    pg.select_option('#mtMin', '10000'); pg.wait_for_timeout(900); tb = cnt(pg); check(0 < tb < t1, f'balance $10,000+ -> {tb}'); check('mtmin=10000' in pg.evaluate('location.hash'), 'hash carries mtmin')
    pg.click('#mtChips .chip[data-mr="tax:y3"]'); pg.wait_for_timeout(900); tb3 = cnt(pg); check(0 < tb3 <= min(tb, t3), f'3+ years and $10,000+ -> {tb3} (combined filters AND)')
    pg.click('#clrMt'); pg.wait_for_timeout(500)
    pg.click('#mtChips .chip[data-mr="tax:county"]'); pg.wait_for_timeout(900); check(cnt(pg) == 4, f'county-held certificates -> {cnt(pg)} (4 in the held list)')
    pg.click('#clrMt'); pg.wait_for_timeout(500)
    # preset (Monroe only)
    sheet()
    pr = pg.query_selector('.chip:text-is("Tax delinquent 2+ years")')
    if pr is not None and not pr.is_visible():
        mi = pg.query_selector('#moreIdeas')
        if mi: mi.click(); pg.wait_for_timeout(400)
    check(pr is not None, 'preset "Tax delinquent 2+ years" present for Monroe')
    if pr:
        pr.click(); pg.wait_for_timeout(1500); check(pg.eval_on_selector_all('#mtChips .chip.on', 'n=>n.map(x=>x.dataset.mr)') == ['tax:y2'], 'preset selects 2+ years'); check(cnt(pg) == t2, f'preset count {cnt(pg)} == filter count {t2}')
        check('tx_d' == pg.eval_on_selector('#sortSel', 'e=>e.value'), 'preset sorts by most unpaid tax years')
        pg.click('#cards .card h3'); pg.wait_for_selector('.drawer', timeout=30000); pg.wait_for_timeout(1500)
        d = pg.locator('.drawer section.dsec').filter(has=pg.locator('.dtog', has_text='Unpaid property taxes')).first; txt = d.inner_text()
        check('Years delinquent' in txt and 'Total balance' in txt and 'Tax certificate' in txt, 'drawer tax section has years, balance, certificate')
        check('197.432(13)' in txt and 'certificate holder' in txt.lower(), 'drawer states the FS 197.432(13) certificate-holder contact rule')
        check('May 2027' in txt, "drawer states Monroe's next certificate sale (May 2027)")
        check('Oct 16, 2026' in txt and 'county-taxes.net' in txt, 'drawer labels the data source and as-of date')
        check(pg.locator('.drawer .mrb:has-text("Tax delinquent")').count() >= 1, 'drawer tax badge')
        pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    # hash round trip
    pg.goto(URL + '?county=monroe#mtax=y3&mtmin=5000'); pg.wait_for_selector('#cards .card', timeout=120000); pg.wait_for_timeout(1500); sheet()
    check(pg.eval_on_selector_all('#mtChips .chip.on', 'n=>n.map(x=>x.dataset.mr)') == ['tax:y3'] and pg.eval_on_selector('#mtMin', 'e=>e.value') == '5000', 'tax filter restored from the URL')
    # other counties never show the tax layer or preset
    check(pg.query_selector('.chip:text-is("Tax deed auction upcoming")') is None and 'td_a' not in pg.eval_on_selector_all('#sortSel option', 'n=>n.map(x=>x.value)'), 'Monroe has no Broward-only tax-deed auction chip / preset / sort')
    pg.goto(URL + '?county=broward#hg=0'); pg.wait_for_selector('#cards .card', timeout=180000)
    check(pg.evaluate("PFCounty.has('mtax') && PFCounty.has('mtdeed')") and pg.query_selector('.chip:text-is("Tax deed auction upcoming")') is not None, 'Broward has its own tax layer (separate county data)')
    pg.goto(URL + '?county=miami-dade#hg=0'); pg.wait_for_selector('#cards .card', timeout=120000)
    check(not pg.is_visible('#mtGrp') and pg.query_selector('.chip:text-is("Tax delinquent 2+ years")') is None and 'tx_d' not in pg.eval_on_selector_all('#sortSel option', 'n=>n.map(x=>x.value)'), 'Miami-Dade has no tax group / preset / sort')
    # export columns unchanged (Monroe, tax filter on)
    c2 = b.new_context(viewport=vp, service_workers='block', is_mobile=MODE == 'mobile', has_touch=MODE == 'mobile', accept_downloads=True); p2 = c2.new_page(); p2.set_default_timeout(120000)
    p2.goto(URL + '?county=monroe#mtax=y3'); p2.wait_for_selector('#cards .card', timeout=120000); p2.wait_for_timeout(1500)
    with p2.expect_download(timeout=240000) as dl: p2.evaluate("document.getElementById('exportBtn').click()")
    import csv as _csv
    rows = list(_csv.reader(open(dl.value.path(), encoding='utf-8-sig'))); check(rows and rows[0] == ['Owner Name', 'Property Address', 'Property City', 'Property State', 'Property Zip', 'Property County', 'Mailing Address', 'Mailing City', 'Mailing State', 'Mailing Zip', 'Folio'], f'export header unchanged: {rows[0] if rows else None}')
    check(len(rows) > 20 and not any('tax' in h.lower() for h in rows[0]) and all(r[5] == 'Monroe' for r in rows[1:]) and sum(1 for r in rows[1:] if re.fullmatch(r'\d{5}', r[4])) >= 0.95 * (len(rows) - 1) and all(not r[9] or re.fullmatch(r'\d{5}(-\d{4})?', r[9]) for r in rows[1:]), f'export has {len(rows)-1} Monroe rows, no tax columns, Property Zip + Mailing Zip 5-digit text')
    b.close()
check(not errs, 'no page errors ' + '; '.join(errs[:3]))
print('RESULT', 'PASS' if not fails else f'FAIL ({len(fails)})'); sys.exit(1 if fails else 0)
