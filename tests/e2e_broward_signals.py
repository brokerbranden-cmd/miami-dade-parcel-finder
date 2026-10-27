"""Broward permits / code cases / published foreclosure notices (build_broward.py sigm bits 2 / 32 / 64 / 128):
chips present with counts, each filter narrows the list and agrees with the pack, filters AND with city, hash round trip, card + drawer wording, CSV export.
usage: python3 tests/e2e_broward_signals.py [base_url] [desktop|mobile]"""
import sys, re, csv, io
from playwright.sync_api import sync_playwright
URL = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/').rstrip('/') + '/'
MOB = (sys.argv[2] if len(sys.argv) > 2 else 'desktop') == 'mobile'
errs, fails = [], []
def check(ok, msg): print(('ok   ' if ok else 'FAIL ') + msg); ok or fails.append(msg)
cnt = lambda pg: int(pg.inner_text('#sCount').replace(',', '') or 0)
BITS = {'fc_notice': 2, 'code': 32, 'dperm': 64, 'code_open': 128}
# parcels in the default view (main pack, no government) carrying a bit
PACKCOUNT = """(bit)=>{ let n=0; for(const p of PF.PACKS){ if(!p) continue; const c=p.c.sigm; for(let i=0;i<p.n;i++) if(c[i]&bit) n++; } return n; }"""   # every loaded pack, all parcels
SAMPLE = """(bit)=>{ const s=PF.sample(400).rows; return {n:s.length, all:s.every(r=>r.sigm&bit), cities:[...new Set(s.map(r=>r.city))]}; }"""
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    vp = {'width': 390, 'height': 800} if MOB else {'width': 1300, 'height': 900}
    ctx = b.new_context(viewport=vp, service_workers='block', is_mobile=MOB, has_touch=MOB, accept_downloads=True)
    pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e))); pg.set_default_timeout(180000)
    pg.goto(URL + '?county=broward#hg=0'); pg.wait_for_selector('#cards .card', timeout=180000); pg.wait_for_timeout(1500)
    sheet = lambda: (pg.click('#filtersBtn'), pg.wait_for_timeout(400)) if MOB and not pg.is_visible('#panel') else None
    def shut():
        if MOB and pg.is_visible('#sheetDone'): pg.click('#sheetDone'); pg.wait_for_timeout(400)
    sheet(); n0 = cnt(pg)
    meta = pg.evaluate('fetch("data/broward/meta.json").then(r=>r.json())')
    fn, pm = meta.get('fcNotices') or {}, meta.get('permits') or {}
    check(fn.get('cases', 0) > 100 and fn.get('matched', 0) > 50 and 0 < fn.get('match_rate_with_address', 0) <= 1, f"meta.fcNotices: {fn.get('cases')} cases, {fn.get('matched')} matched, rate {fn.get('match_rate_with_address')}")
    check(all(c in (pm.get('by_city') or {}) for c in ('Pembroke Pines', 'Sunrise', 'Oakland Park', 'Miramar', 'Fort Lauderdale')), f"meta.permits covers the 5 cities {sorted((pm.get('by_city') or {}).keys())}")
    chips = pg.eval_on_selector_all('#mrSig .chip', 'n=>n.map(x=>x.dataset.mr)')
    for k in BITS: check(f'sig:{k}' in chips, f'chip sig:{k} present')
    labels = pg.eval_on_selector_all('#mrSig .chip', 'n=>n.map(x=>x.textContent)')
    check(any(l.startswith('Foreclosure notice (published)') for l in labels), 'notice chip is labelled "Foreclosure notice (published)"')
    got = {}
    for k, bit in BITS.items():
        exp = pg.evaluate(PACKCOUNT, bit)
        pg.click(f'#mrSig .chip[data-mr="sig:{k}"]'); pg.wait_for_timeout(1200); got[k] = cnt(pg)
        sm = pg.evaluate(SAMPLE, bit)
        check(0 < got[k] < n0 and got[k] <= exp and sm['n'] > 0 and sm['all'], f'filter {k}: {n0} -> {got[k]} (loaded packs carry {exp}; every sampled result has bit {bit})')
        check(f'msig={k}' in pg.evaluate('decodeURIComponent(location.hash)'), f'hash carries msig={k}')
        if k == 'fc_notice':
            check(pg.eval_on_selector_all('#cards .card', 'n=>n.length>0 && n.every(c=>/Foreclosure notice \\(published\\)/.test(c.innerText))'), 'every notice card says "Foreclosure notice (published)"')
            shut(); pg.click('#cards .card h3'); pg.wait_for_selector('.drawer', timeout=30000); pg.wait_for_timeout(800)
            t = pg.evaluate("document.querySelector('.drawer').textContent")
            check('Foreclosure notice (published)' in t and re.search(r'(CACE|COCE|CONO|COSO|COWE|CACV)-\d{2}-\d{6}', t) is not None, 'drawer shows the published notice with a case number')
            check('floridapublicnotices.com' in t and 'not the recorded lis pendens' in t, 'drawer names the source and says it is not the recorded lis pendens')
            pg.keyboard.press('Escape'); pg.wait_for_timeout(400); sheet()
        if k == 'code_open': check(got[k] <= got['code'], f"open code cases {got[k]} <= code cases {got['code']}")
        pg.click('#clrMr'); pg.wait_for_timeout(900); check(cnt(pg) == n0, f'clear after {k} restores {n0}')
    # recorded lis pendens (AcclaimWeb exports, sigm bit 4): own chip, also counts as the distress LP signal, drawer shows the case + match confidence
    lm = meta.get('lisPendens') or {}
    if lm.get('lp_docs'):
        check(lm.get('matched', 0) == lm.get('matched_high', 0) + lm.get('matched_medium', 0) and lm['matched'] + lm.get('unmatched', 0) == lm['lp_docs'], f"meta.lisPendens adds up: {lm.get('lp_docs')} docs = {lm.get('matched')} matched + {lm.get('unmatched')} unmatched")
        exp = pg.evaluate(PACKCOUNT, 4)
        check('sig:lp_rec' in chips and 0 < exp <= lm['matched'], f'chip sig:lp_rec present; {exp} parcels carry bit 4 (<= {lm["matched"]} matched docs)')
        pg.click('#mrSig .chip[data-mr="sig:lp_rec"]'); pg.wait_for_timeout(1200); k4 = cnt(pg); sm = pg.evaluate(SAMPLE, 4)
        check(0 < k4 <= exp and sm['all'] and pg.eval_on_selector_all('#cards .card', 'n=>n.length>0 && n.every(c=>/Lis pendens \\(recorded\\)/.test(c.innerText))'), f'filter lp_rec: {k4} parcels, every card says "Lis pendens (recorded)"')
        shut(); pg.click('#cards .card h3'); pg.wait_for_selector('.drawer', timeout=30000); pg.wait_for_timeout(800)
        t = pg.evaluate("document.querySelector('.drawer').textContent")
        check('Lis pendens recorded' in t and re.search(r'(CACE|COCE|CONO|COSO|COWE|CACV)-\d{2}-\d{6}', t) is not None and re.search(r'match (high|medium)', t) is not None, 'drawer shows the recorded lis pendens with case number and match confidence')
        pg.keyboard.press('Escape'); pg.wait_for_timeout(400); sheet(); pg.click('#clrMr'); pg.wait_for_timeout(900)
        sc = pg.evaluate("""()=>{ let n=0,bad=0; for(const p of PF.PACKS){ if(!p||!p.c.dsig) continue; for(let i=0;i<p.n;i++) if(p.c.sigm[i]&4){ n++; if(!(p.c.dsig[i]&2)) bad++; } } return {n,bad}; }""")
        check(sc['bad'] == 0, f"every recorded-LP parcel carries the distress LP bit ({sc['n']} checked)")
    # AND with city: code cases in Pembroke Pines only
    pg.goto(URL + '?county=broward#msig=code'); pg.wait_for_selector('#cards .card', timeout=180000); pg.wait_for_timeout(2000); sheet()
    check(pg.eval_on_selector_all('#mrSig .chip.on', 'n=>n.map(x=>x.dataset.mr)') == ['sig:code'], 'code filter restored from the URL')
    cities = pg.evaluate(SAMPLE, 32)['cities']
    check(any('Pembroke Pines' in c for c in cities) and any('Sunrise' in c for c in cities) and any('Oakland Park' in c for c in cities), f'code cases come from the EnerGov cities ({len(cities)} cities)')
    shut(); pg.click('#cards .card h3'); pg.wait_for_selector('.drawer', timeout=30000); pg.wait_for_timeout(800)
    t = pg.evaluate("document.querySelector('.drawer').textContent")
    check('Code cases' in t and re.search(r'code cases? in 5 yrs', t) is not None, 'drawer lists the code cases')
    check('Pembroke Pines, Sunrise, Oakland Park and Miramar' in t, 'drawer coverage note names the cities')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    # distress permits: drawer text + Fort Lauderdale included
    pg.goto(URL + '?county=broward#msig=dperm'); pg.wait_for_selector('#cards .card', timeout=180000); pg.wait_for_timeout(2000)
    cities = pg.evaluate(SAMPLE, 64)['cities']
    check(any('Fort Lauderdale' in c for c in cities), 'distress permits include Fort Lauderdale')
    shut(); pg.click('#cards .card h3'); pg.wait_for_selector('.drawer', timeout=30000); pg.wait_for_timeout(800)
    t = pg.evaluate("document.querySelector('.drawer').textContent")
    check('Distress-type permits (24 mo)' in t, 'drawer shows the distress permits')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    # export keeps the 11 columns under a new filter
    pg.goto(URL + '?county=broward#msig=fc_notice'); pg.wait_for_selector('#cards .card', timeout=180000); pg.wait_for_timeout(2000)
    if MOB and not pg.is_visible('#exportBtn'):
        m = pg.query_selector('#moreBtn, .mmore, [data-more]')
        if m: m.click(); pg.wait_for_timeout(300)
    shut()
    with pg.expect_download(timeout=240000) as dl: pg.evaluate("document.getElementById('exportBtn').click()")
    rows = list(csv.reader(io.StringIO(open(dl.value.path(), encoding='utf-8-sig').read())))
    check(len(rows) - 1 == got['fc_notice'] and all(r[5] == 'Broward' for r in rows[1:]), f"export under the notice filter: {len(rows) - 1} rows == {got['fc_notice']}")
    # Miami-Dade unaffected: no Broward chips there
    pg.goto(URL + '?county=miami-dade#hg=0'); pg.wait_for_selector('#results:not([hidden])', timeout=180000); pg.wait_for_timeout(1000)
    check(pg.query_selector('#mrSig .chip[data-mr="sig:fc_notice"]') is None, 'Miami-Dade has no Broward notice chip')
    b.close()
check(not errs, 'no page errors ' + '; '.join(errs[:3]))
print('RESULT', 'PASS' if not fails else f'FAIL ({len(fails)})'); sys.exit(1 if fails else 0)
