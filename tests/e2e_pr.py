"""Puerto Rico (4th county): dropdown order, PR loads only data/pr/<municipio>/ (no Florida data), municipio switch, coverage panel
(every feature listed, unavailable ones greyed), flood / waterfront / assemblage layers, export header = Florida contact columns
unchanged + PR columns last, mobile layout. argv: URL [desktop|mobile]"""
import sys, csv, io
from playwright.sync_api import sync_playwright
URL = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/').split('#')[0].split('?')[0].rstrip('/') + '/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
HDR = ['Owner Name', 'Property Address', 'Property City', 'Property State', 'Property Zip', 'Property County', 'Mailing Address', 'Mailing City', 'Mailing State', 'Mailing Zip', 'Folio']
PRH = ['Municipio', 'Barrio', 'Zoning Code', 'Zoning District', 'Zoning Overlays', 'Lot Sq Ft']
fails, errs, reqs = [], [], []
def check(c, m): print(('ok   ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True); c or fails.append(m)
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    vp = {'width': 390, 'height': 844} if MOB else {'width': 1366, 'height': 860}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, accept_downloads=True, service_workers='block'); pg = ctx.new_page(); pg.set_default_timeout(180000)
    pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('request', lambda r: reqs.append(r.url))
    pg.goto(URL + '?county=pr&muni=ponce' + ('&drive=0' if MOB else '')); pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(1500)
    opts = pg.eval_on_selector_all('#countySel option', 'o=>o.map(x=>[x.value,x.textContent.trim()])')
    check([o[0] for o in opts] == ['miami-dade', 'broward', 'monroe', 'pr'] or [o[0] for o in opts][:3] != [] and len(opts) == 4 and opts[-1][0] == 'pr', f'4 county options, Puerto Rico last: {opts}')
    check(pg.input_value('#countySel') == 'pr' and pg.evaluate('PFCounty.id') == 'pr', 'switcher shows Puerto Rico')
    check(pg.input_value('#muniSel') == 'ponce' and pg.eval_on_selector_all('#muniSel option', 'o=>o.length') >= 70, f"municipio picker on Ponce ({pg.eval_on_selector_all('#muniSel option', 'o=>o.length')} municipios)")
    data = [u for u in reqs if '/data/' in u]
    check(data and all('/data/pr/' in u for u in data), f'only Puerto Rico data requested ({len(data)} data requests, Florida: {[u for u in data if "/data/pr/" not in u][:2]})')
    tot = pg.evaluate('fetch("data/pr/ponce/meta.json").then(r=>r.json()).then(m=>m.total)'); n = pg.evaluate('PF.sample(1)')['n']
    check(tot > 10000 and n == tot, f'Ponce loads every parcel ({n} of {tot})')
    gaps = pg.eval_on_selector_all('#prGaps li', 'l=>l.map(x=>[x.className, x.textContent])')
    na = [g for g in gaps if g[0] == 'prna']
    check(len(gaps) >= 15 and na and all('Not public in PR' in g[1] or 'Not available' in g[1] for g in na), f'coverage panel lists {len(gaps)} features, {len(na)} greyed with a reason')
    check(all(any(k in g[1] for g in gaps if g[0] == 'prok') for k in ('Waterfront', 'Assemblages', 'flood zone')), 'waterfront, assemblages and flood zone available for PR')
    check(pg.evaluate("PFCounty.has('flood') && PFCounty.has('asm') && !PFCounty.has('distress') && !PFCounty.has('owners')"), 'PR layer list')
    fo = pg.eval_on_selector_all('#cra option', 'o=>o.map(x=>x.value)')
    check(any(v.startswith(('AE', 'VE', 'A ')) for v in fo), f'FEMA flood options ({len(fo)})')
    wf = pg.evaluate("PFWF.load ? PFWF.p.then(o=>o.counts.any) : 0") if pg.evaluate('!!(window.PFWF&&PFWF.p)') else pg.evaluate("PFWF.data ? PFWF.data.counts.any : -1")
    check(wf and wf > 0, f'waterfront parcels in Ponce: {wf}')
    ag = pg.evaluate("(async()=>{ const o=await fetch('data/pr/ponce/asm.json.gz').then(r=>r.ok); return o; })()")
    check(ag, 'assemblage file served for Ponce')
    na_ideas = pg.eval_on_selector_all('#ideas .chip[data-na]', 'n=>n.map(x=>[x.disabled, /not available for this county yet/.test(x.textContent)])')
    check(na_ideas and all(d and t for d, t in na_ideas), f'{len(na_ideas)} owner / sale ideas greyed "not available for this county yet"')
    # export: Florida contact columns unchanged, PR columns last
    if MOB and not pg.is_visible('#exportBtn'):
        m = pg.query_selector('#moreBtn, .mmore, [data-more]')
        if m: m.click(); pg.wait_for_timeout(300)
    pg.evaluate("location.hash='q=&lot=0'"); pg.wait_for_timeout(1500)
    with pg.expect_download(timeout=240000) as dl: pg.evaluate("document.querySelector('#exportBtn').click()")
    rows = list(csv.reader(io.StringIO(open(dl.value.path(), encoding='utf-8').read())))
    h = rows[0]
    check(h[:11] == HDR and h[-6:] == PRH and set(h[11:-6]) <= {'Waterfront'}, f'export header: 11 contact columns in order, PR columns last ({h})')
    body = rows[1:]
    check(body and all(r[3] == 'PR' and r[5] == 'Puerto Rico' and r[2] == 'Ponce' and r[-6] == 'Ponce' and r[10] for r in body[:500]), f'export rows say PR / Ponce with a catastro number ({len(body)} rows)')
    # municipio switch
    if MOB and pg.is_visible('#sheetDone'): pg.click('#sheetDone')
    pg.select_option('#muniSel', 'san-juan'); pg.wait_for_function("window.PF_READY && new URLSearchParams(location.search).get('muni')==='san-juan'", timeout=240000); pg.wait_for_timeout(1500)
    t2 = pg.evaluate('fetch("data/pr/san-juan/meta.json").then(r=>r.json()).then(m=>m.total)')
    check(pg.evaluate('PF.sample(1)')['n'] == t2 and 'San Juan' in pg.inner_text('#srcLine'), f'switched to San Juan ({t2} parcels)')
    sw = pg.evaluate('document.documentElement.scrollWidth'); check(sw <= vp['width'] + 1, f'no horizontal overflow ({sw})')
    pg.evaluate('window.scrollTo(0,0)'); pg.screenshot(path=f'/tmp/e2e_pr_{TAG}.png')
    b.close()
check(not errs, 'no page errors ' + '; '.join(errs[:3]))
print('RESULT', 'PASS' if not fails else f'FAIL ({len(fails)})'); sys.exit(1 if fails else 0)
