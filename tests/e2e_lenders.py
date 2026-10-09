"""Headless e2e for lender tracking: empty state, add lenders (form validation), save properties and link deals (from the
Lenders page and from the property drawer), pipeline stage changes, dashboard math (needed counts each property once),
lender filters/search, 'contacted today', JSON + CSV export, JSON + CSV import into a fresh browser, persistence, delete,
privacy note, phone layout. Screenshots -> SHOTS/lenders_*.png"""
import sys, json, csv, io
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
SHOTS = sys.argv[2] if len(sys.argv) > 2 else '/workspace/parcel-finder/shots/'
errs = []
def ok(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg)
    if not cond: errs.append('assert: ' + msg)
def watch(pg, tag):
    pg.on('console', lambda m: m.type == 'error' and errs.append(f'{tag} console: ' + m.text))
    pg.on('pageerror', lambda e: errs.append(f'{tag} pageerror: ' + str(e)))
kpi = lambda pg, k: pg.inner_text(f'.kpi:nth-child({k}) b')
def add_lender(pg, **f):
    pg.click('[data-act="add-lender"] >> nth=0'); pg.wait_for_selector('#lfForm')
    for k, v in f.items():
        sel = {'name': '#lfName', 'company': '#lfCompany', 'phone': '#lfPhone', 'email': '#lfEmail', 'rate': '#lfRate', 'maxLoan': '#lfMax', 'geography': '#lfGeo', 'terms': '#lfTerms', 'notes': '#lfNotes', 'last': '#lfLast'}.get(k)
        if k == 'status': pg.select_option('#lfStatus', v)
        else: pg.fill(sel, v)
    pg.click('#lfForm button[type=submit]'); pg.wait_for_timeout(300)
with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 1360, 'height': 900}, accept_downloads=True); pg = ctx.new_page(); watch(pg, 'main')
    pg.on('dialog', lambda d: d.accept())
    pg.goto(URL + '#ds=50&sort=ds_d'); pg.wait_for_selector('#results:not([hidden])', timeout=180000); pg.wait_for_timeout(800)
    # save three properties
    folios = [pg.get_attribute(f'#cards .card:nth-of-type({k})', 'data-folio') for k in (1, 2, 3)]
    for k in (1, 2, 3): pg.click(f'#cards .card:nth-of-type({k}) .star'); pg.wait_for_timeout(150)
    ok(pg.evaluate('PFSaved.count()') == 3, 'saved 3 properties')
    pg.click('#lendersBtn'); pg.wait_for_selector('#lendersPage:not([hidden])')
    ok('stored only in this browser' in pg.inner_text('.lp-priv') and 'Supabase' in pg.inner_text('.lp-priv'), 'privacy note (local only, Supabase later)')
    ok(pg.query_selector('.lpempty') is not None, 'empty dashboard prompts to add a lender')
    # validation
    pg.click('[data-act="add-lender"] >> nth=0'); pg.click('#lfForm button[type=submit]'); pg.wait_for_timeout(200)
    ok('needs a name' in pg.inner_text('#lfErr'), 'form validation: ' + pg.inner_text('#lfErr'))
    pg.click('#lfForm [data-act="cancel"]')
    add_lender(pg, name='Ana Ruiz', company='Bay Capital Lending', phone='305-555-0142', email='ana@example.com', rate='11%, 2 pts', maxLoan='750,000',
               geography='Miami-Dade, Broward', terms='12-mo interest-only, 70% ARV', notes='Prefers SFR flips under $600K', status='Active', last='2026-09-28')
    pg.click('[data-tab="lenders"]'); pg.wait_for_timeout(200)
    add_lender(pg, name='Marcus Lee', company='Sunrise Private Money', phone='786-555-0199', rate='12%, 3 pts', maxLoan='400000', geography='Miami-Dade', status='Prospect')
    add_lender(pg, company='Coastal Hard Money', rate='10.5%, 2 pts', maxLoan='2000000', geography='South Florida', status='Paused')
    ok(len(pg.query_selector_all('.lcard')) == 3, '3 lender cards')
    ok(pg.inner_text('#lendersCount') == '3', 'header Lenders badge = 3')
    pg.fill('#lpSearch', 'broward'); pg.wait_for_timeout(200); ok(len(pg.query_selector_all('.lcard')) == 1, 'search "broward" -> 1 lender')
    pg.fill('#lpSearch', ''); pg.click('[data-act="lstatus"][data-st="Prospect"]'); ok(len(pg.query_selector_all('.lcard')) == 1, 'status filter Prospect -> 1')
    pg.click('[data-act="lstatus"][data-st=""]')
    marcus = pg.evaluate("PFLenders.lenders().find(l=>l.name==='Marcus Lee').id")
    pg.click(f'.lcard[data-id="{marcus}"] [data-act="contacted"]'); pg.wait_for_timeout(200)
    ok('today' in pg.inner_text(f'.lcard[data-id="{marcus}"]'), '"Contacted today" logs the date')
    pg.screenshot(path=SHOTS + 'lenders_02_lenders.png')
    # deals from the page
    ana = pg.evaluate("PFLenders.lenders().find(l=>l.name==='Ana Ruiz').id")
    def add_deal(folio, lender, req, com, stage, note=''):
        pg.click('[data-act="add-deal"] >> nth=0'); pg.wait_for_selector('#dfForm')
        pg.select_option('#dfProp', folio); pg.select_option('#dfLender', lender); pg.fill('#dfReq', req); pg.fill('#dfCom', com); pg.select_option('#dfStage', stage); pg.fill('#dfNote', note)
        pg.click('#dfForm button[type=submit]'); pg.wait_for_timeout(300)
    pg.click('[data-tab="deals"]')
    add_deal(folios[0], ana, '300000', '200000', 'Term sheet', 'Needs appraisal')
    add_deal(folios[0], marcus, '300000', '100000', 'Interested')
    add_deal(folios[1], ana, '450000', '450000', 'Funded')
    ok(len(pg.query_selector_all('#lpBody tbody tr')) == 3, '3 deals listed')
    # deal from the property drawer
    pg.click('#lpClose'); pg.click(f'#cards .card[data-folio="{folios[2]}"]'); pg.wait_for_selector('.drawer'); pg.wait_for_timeout(600)
    ok('No lender linked yet' in pg.inner_text('#finBox'), 'drawer Financing section on a saved property')
    pg.click('#finBox [data-finadd]'); pg.wait_for_selector('#dfForm')
    ok(pg.input_value('#dfProp') == folios[2], 'drawer "+ Add lender / deal" pre-selects that property')
    pg.select_option('#dfLender', marcus); pg.fill('#dfReq', '250000'); pg.select_option('#dfStage', 'Contacted'); pg.click('#dfForm button[type=submit]'); pg.wait_for_timeout(300)
    # stage change inline
    d3 = pg.evaluate(f"PFLenders.dealsFor('{folios[2]}')[0].id")
    pg.select_option(f'select.dstage[data-id="{d3}"]', 'Interested'); pg.wait_for_timeout(200)
    ok(pg.evaluate(f"PFLenders.deal('{d3}').stage") == 'Interested', 'inline stage change saved')
    pg.screenshot(path=SHOTS + 'lenders_03_deals.png')
    # dashboard math: needed = 300k + 450k + 250k = 1.0M; committed = min(300k, 300k) + 450k + 0 = 750k; offered 750k+... ; funded 450k
    pg.click('[data-tab="dash"]'); pg.wait_for_timeout(200)
    s = pg.evaluate('PFLenders.summary()')
    ok(s['needed'] == 1000000 and s['committed'] == 750000 and s['gap'] == 250000 and s['funded'] == 450000, f"summary needed {s['needed']} committed {s['committed']} gap {s['gap']} funded {s['funded']}")
    ok(kpi(pg, 1) == '$1M' and kpi(pg, 2) == '$750K' and kpi(pg, 3) == '$250K' and kpi(pg, 4) == '$450K', f'KPI cards {[kpi(pg, k) for k in (1, 2, 3, 4)]}')
    ok(len(pg.query_selector_all('.lppipe .pst')) == 5 and pg.inner_text('.pst.st-interested b') == '2', 'pipeline: 5 stages, Interested = 2')
    rows = pg.eval_on_selector_all('#lpBody table >> nth=0 >> tbody tr', 'r=>r.map(x=>x.innerText)')
    ok(any('Ana Ruiz' in r and '$650,000' in r for r in rows), 'by-lender: Ana Ruiz committed $650,000')
    pg.set_viewport_size({'width': 1360, 'height': 1250}); pg.screenshot(path=SHOTS + 'lenders_01_dashboard.png'); pg.set_viewport_size({'width': 1360, 'height': 900})
    # drawer shows linked deals
    pg.click(f'[data-act="open-prop"][data-folio="{folios[0]}"] >> nth=0'); pg.wait_for_selector('.drawer'); pg.wait_for_timeout(400)
    fin = pg.inner_text('#finBox'); ok('Needed $300,000' in fin and 'committed $300,000' in fin and 'Term sheet' in fin, 'drawer Financing lists the deals with totals')
    pg.query_selector('#finBox').scroll_into_view_if_needed(); pg.screenshot(path=SHOTS + 'lenders_04_drawer_financing.png')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
    # persistence
    pg.reload(); pg.wait_for_selector('#results:not([hidden])', timeout=180000)
    ok(pg.evaluate('PFLenders.lenders().length') == 3 and pg.evaluate('PFLenders.deals().length') == 4, 'lenders + deals persist after reload')
    # exports
    pg.click('#lendersBtn')
    with pg.expect_download() as dl: pg.click('#lpExportJson')
    j = json.load(open(dl.value.path())); ok(len(j['lenders']) == 3 and len(j['deals']) == 4 and j['kind'] == 'lender-tracking', 'JSON export: 3 lenders, 4 deals')
    with pg.expect_download() as dl: pg.click('#lpExportLCsv')
    ltext = open(dl.value.path()).read(); lrows = list(csv.DictReader(io.StringIO(ltext)))
    ok(len(lrows) == 3 and {'Name', 'Company', 'Phone', 'Email', 'Rate', 'Terms', 'Max Loan', 'Geography', 'Status', 'Last Contacted', 'Notes'} <= set(lrows[0]), 'lenders CSV columns')
    with pg.expect_download() as dl: pg.click('#lpExportDCsv')
    dtext = open(dl.value.path()).read(); drows = list(csv.DictReader(io.StringIO(dtext)))
    ok(len(drows) == 4 and drows[0]['Lender'] and drows[0]['Amount Requested'], 'deals CSV with lender names + amounts')
    # import into a fresh browser: CSV lenders, then JSON (merge, no dupes)
    c2 = b.new_context(viewport={'width': 1360, 'height': 900}); p2 = c2.new_page(); watch(p2, 'fresh')
    p2.goto(URL + '#ds=50'); p2.wait_for_selector('#results:not([hidden])', timeout=180000); p2.click('#lendersBtn')
    p2.set_input_files('#lpImport', files=[{'name': 'l.csv', 'mimeType': 'text/csv', 'buffer': ltext.encode()}]); p2.wait_for_timeout(500)
    ok(p2.evaluate('PFLenders.lenders().length') == 3, 'CSV import (lenders) into a fresh browser')
    p2.set_input_files('#lpImport', files=[{'name': 'd.csv', 'mimeType': 'text/csv', 'buffer': dtext.encode()}]); p2.wait_for_timeout(500)
    ok(p2.evaluate('PFLenders.deals().length') == 4, 'CSV import (deals) keeps lender links')
    p2.set_input_files('#lpImport', files=[{'name': 'x.json', 'mimeType': 'application/json', 'buffer': json.dumps(j).encode()}]); p2.wait_for_timeout(500)
    ok(p2.evaluate('PFLenders.lenders().length') == 3 and p2.evaluate('PFLenders.deals().length') == 4, 'JSON import merges by id (no duplicates)')
    c2.close()
    # delete lender -> deals kept as "No lender yet"
    pg.click('[data-tab="lenders"]'); pg.click(f'.lcard[data-id="{marcus}"] [data-act="edit-lender"]'); pg.click('#lfForm [data-act="del-lender"]'); pg.wait_for_timeout(300)
    ok(pg.evaluate('PFLenders.lenders().length') == 2 and pg.evaluate("PFLenders.deals().filter(d=>!d.lenderId).length") == 2, 'delete lender keeps their deals as "No lender yet"')
    # phone layout
    m = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True); mp = m.new_page(); watch(mp, 'phone')
    mp.goto(URL + '?drive=0&page=lenders'); mp.wait_for_selector('#lendersPage:not([hidden])', timeout=180000)
    mp.evaluate(f"PFLenders.importJSON({json.dumps(j)})"); mp.wait_for_timeout(400)
    ok(mp.evaluate('document.documentElement.scrollWidth') <= 392, 'phone: no horizontal overflow')
    mp.set_viewport_size({'width': 390, 'height': 1500}); mp.screenshot(path=SHOTS + 'lenders_05_mobile_dashboard.png')
    m.close(); b.close()
print('ERRORS', errs if errs else 'none')
sys.exit(1 if errs else 0)
