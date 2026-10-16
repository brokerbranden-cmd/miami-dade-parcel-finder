"""Multi-county smoke test: county switcher, Monroe packs, hidden layers, flood filter, per-county storage, share link.
usage: python3 tests/e2e_county.py [base_url]"""
import sys, json
from playwright.sync_api import sync_playwright
URL = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/').rstrip('/') + '/'
errs, fails = [], []
def check(ok, msg): print(('ok   ' if ok else 'FAIL ') + msg); ok or fails.append(msg)
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    ctx = b.new_context(viewport={'width': 1300, 'height': 900}, service_workers='block')
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(URL + '?county=monroe'); pg.wait_for_selector('#results:not([hidden])', timeout=120000)
    total = pg.evaluate('fetch("data/monroe/meta.json").then(r=>r.json()).then(m=>m.total)')
    check(pg.evaluate('PFCounty.id') == 'monroe', 'active county = monroe')
    check(pg.inner_text('header.top h1').lower().startswith('monroe'), 'header says Monroe: ' + pg.inner_text('header.top h1'))
    check(pg.input_value('#countySel') == 'monroe', 'switcher shows Monroe')
    check(pg.inner_text('#srcCount').replace(',', '') == str(total), f'source line count {pg.inner_text("#srcCount")} == meta {total}')
    for sel in ('.grp.distress', '.grp.permits', '.grp.vacancy', '#asmGrp', '.grp[data-need="zoning"]'):
        check(not pg.is_visible(sel), f'{sel} hidden')
    for sel in ('#mrGrp', '.grp[data-need="mzoning"]'):
        check(pg.is_visible(sel), f'{sel} visible for Monroe (zoning + buildability layers now exist)')
    check(pg.evaluate("PFCounty.has('monroe') && PFCounty.has('mzoning') && !PFCounty.has('zoning') && !PFCounty.has('distress')"), 'Monroe layer list')
    ideas = pg.eval_on_selector_all('#ideas .chip', 'n=>n.map(x=>x.textContent)')
    check(not any('Hottest' in t or 'Assemblage' in t or 'Commercial distress' in t for t in ideas), f'ideas without missing layers ({len(ideas)})')
    check(pg.inner_text('label[for="cra"]') == 'FEMA flood zone', 'flood zone filter label')
    opts = pg.eval_on_selector_all('#cra option', 'n=>n.map(x=>x.value)')
    ve = next((o for o in opts if o.startswith('VE')), None); check(bool(ve), f'flood options ({len(opts)})')
    pg.evaluate("document.getElementById('moreBox').open=true")
    s = pg.evaluate("PF.sample(50)"); s = s.get('rows', s.get('sample', [])) if isinstance(s, dict) else s; first = s[0] if s else {}
    check(bool(first.get('folio')), 'cards have folios')
    # all parcels via a fresh unfiltered state (hash) -> then VE filter
    pg.goto(URL + '?county=monroe#hg=0'); pg.wait_for_selector('#results:not([hidden])', timeout=120000)
    n0 = int(pg.inner_text('#sCount').replace(',', '') or 0)
    pg.select_option('#cra', ve); pg.wait_for_timeout(1200)
    n1 = int(pg.inner_text('#sCount').replace(',', '') or 0); check(0 < n1 < n0, f'flood filter {ve!r}: {n0} -> {n1}')
    check('county=monroe' in pg.url, 'URL carries ?county=monroe: ' + pg.url[:120])
    check(pg.query_selector('#cards .card') is not None, 'cards render')
    # per-county storage: save in Monroe, Miami-Dade key untouched
    pg.evaluate("localStorage.setItem('mdpf.saved.v1', JSON.stringify({'0000000000001':{folio:'0000000000001'}}))")
    pg.click('#cards .card .star') if pg.query_selector('#cards .card .star') else None
    pg.wait_for_timeout(500)
    keys = pg.evaluate("Object.keys(localStorage)")
    check('mdpf.v2.monroe' in keys, 'Monroe search state stored under mdpf.v2.monroe')
    md_saved = json.loads(pg.evaluate("localStorage.getItem('mdpf.saved.v1')"))
    check(list(md_saved) == ['0000000000001'], 'Miami-Dade saved list untouched by Monroe')
    check(pg.evaluate("PFCounty.key('pf.send.v1')") == 'pf.send.v1.monroe', 'send tags key per county')
    # switch to Miami-Dade via the header select
    pg.select_option('#countySel', 'miami-dade'); pg.wait_for_selector('#results:not([hidden])', timeout=180000)
    check(pg.evaluate('PFCounty.id') == 'miami-dade' and 'county=miami-dade' in pg.url, 'switched to Miami-Dade (URL ' + pg.url[:80] + ')')
    check(pg.is_visible('.grp.distress'), 'Miami-Dade shows distress filters')
    check(not pg.is_visible('#mrGrp') and pg.evaluate("!PFCounty.has('monroe')"), 'Miami-Dade hides the Monroe-only buildability group')
    check(pg.query_selector('#cards .card .mrb') is None, 'no Monroe buildability badges on Miami-Dade cards')
    check(not any('Buildable' in t or 'ROGO' in t for t in pg.eval_on_selector_all('#ideas .chip', 'n=>n.map(x=>x.textContent)')), 'no Monroe presets on Miami-Dade')
    check(pg.evaluate("localStorage.getItem('pf.county')") == 'miami-dade', 'choice remembered')
    b.close()
check(not errs, 'no page errors ' + '; '.join(errs[:3]))
print('RESULT', 'PASS' if not fails else f'FAIL ({len(fails)})'); sys.exit(1 if fails else 0)
