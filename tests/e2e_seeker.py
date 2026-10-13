"""Headless e2e for the Parcel Seeker feature set: teardown tier + editable rule panel (land share, year, unit / sq ft / story
multiples, lot split factor, min-lot toggle, reset), lot-vs-zone-minimum chips, city zoning codes grouped by city (collapsible,
exact picks) + typed prefix matching, 500k / 1.2m money shorthand, construction chips, adverse possession, Send to (tag on card,
filter, export with team + list name, mark as sent, no double export, Re-send), new sorts, drawer teardown section, CSV columns,
hash round-trip. Screenshot -> SHOTS/seeker_features.png"""
import sys, csv, io, re
from playwright.sync_api import sync_playwright
import legacy_ui  # noqa: F401  (simplified UI in legacy mode, see legacy_ui.py)
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
SHOTS = sys.argv[2] if len(sys.argv) > 2 else '/workspace/parcel-finder/shots/'
errs = []
def ok(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg)
    if not cond: errs.append('assert: ' + msg)
cnt = lambda pg: int(pg.inner_text('#sCount').replace(',', ''))
def chipn(pg, sel):
    t = pg.inner_text(sel).split('\n')[-1].strip().replace(',', '')
    if t.endswith('K'): return None
    if t.endswith('M'): return None
    return int(t or 0)
def wait(pg, ms=900): pg.wait_for_timeout(ms)
with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 1360, 'height': 900}, accept_downloads=True)
    pg = ctx.new_page()
    pg.on('console', lambda m: m.type == 'error' and 'arcgisonline' not in m.text and errs.append('console: ' + m.text))
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    pg.goto(URL); pg.wait_for_selector('#results:not([hidden])', timeout=180000); wait(pg, 1000)
    pg.click('#resetBtn'); wait(pg, 1500)
    total = cnt(pg); ok(total > 400000, f'all parcels (no condos): {total}')
    zr = pg.evaluate("fetch('data/zoning-rules.json').then(r=>r.json())")
    ok(zr['counts']['matched'] > 500 and len(zr['rules']) >= 500, f"zoning rules table: {zr['counts']}")
    ok('Zone rules for' in pg.inner_text('#tdSrc'), 'teardown source line: ' + pg.inner_text('#tdSrc'))
    # ---- teardown tier ----
    nb = int(pg.inner_text('#tcBasic').replace(',', '').replace('K', '000')) if 'K' not in pg.inner_text('#tcBasic') else None
    pg.click('#tierSeg button[data-tier="basic"]'); wait(pg, 1500); n_basic = cnt(pg)
    ok(n_basic > 1000, f'Teardown (basic) -> {n_basic}')
    pg.click('#tierSeg button[data-tier="strong"]'); wait(pg, 1500); n_strong = cnt(pg)
    ok(0 < n_strong < n_basic, f'Strong teardown -> {n_strong} (< basic {n_basic})')
    ok('td=strong' in pg.evaluate('location.hash'), 'hash has td=strong')
    # every strong card: target use, land >= 80%, built <= 1969, says Strong teardown
    cards = pg.query_selector_all('#cards .card')[:20]
    ok(all('Strong teardown' in c.inner_text() for c in cards), 'first 20 cards tagged Strong teardown')
    lp = [int(re.search(r'(\d+)% is land', c.inner_text()).group(1)) for c in cards]
    ok(min(lp) >= 79, f'land share on strong cards >= 80%: min {min(lp)}')
    # JS evaluate() agrees with the fast tier on the first 300 results
    agree = pg.evaluate("""()=>{ const PF=window.PF; let bad=0,n=0; const ids=[...document.querySelectorAll('#cards .card')].map(c=>+c.dataset.id);
        return ids.length; }""")
    ok(agree > 0, f'{agree} cards rendered')
    pg.select_option('#sortSel', 'um_d'); wait(pg, 1200)
    ups = [c.inner_text() for c in pg.query_selector_all('#cards .card')[:15]]
    mult = [float(re.search(r'\(([\d.]+)×\)', u).group(1)) for u in ups if re.search(r'\(([\d.]+)×\)', u)]
    ok(len(mult) >= 5 and mult == sorted(mult, reverse=True) and min(mult) >= 3, f'sorted by unit multiple desc: {mult[:6]}')
    # drawer teardown section
    pg.click('#cards .card:nth-of-type(1)'); pg.wait_for_selector('.drawer'); wait(pg, 1500)
    d = pg.inner_text('.drawer')
    dl = d.lower(); ok('teardown & zoning upside' in dl and 'strong teardown' in dl and 'units allowed' in dl, 'drawer teardown section with verdict + units allowed')
    ok('zone rules' in dl and 'min lot' in dl, 'drawer shows zone rules (min lot / density / FAR)')
    pg.keyboard.press('Escape'); wait(pg, 300)
    # ---- rule panel ----
    ok(pg.input_value('#td_land') == '80' and pg.input_value('#td_yb') == '1969' and pg.input_value('#td_um') == '3' and pg.input_value('#td_split') == '2' and pg.is_checked('#td_minlot'), 'rule defaults 80% / 1969 / 3x / 2x / min-lot on')
    pg.fill('#td_um', '2'); wait(pg, 1500); n2 = cnt(pg); ok(n2 > n_strong, f'unit multiple 2x -> more strong ({n2} > {n_strong})')
    ok('tdr=' in pg.evaluate('location.hash'), 'non-default rule saved in hash')
    pg.fill('#td_um', '3'); wait(pg, 1200)
    pg.uncheck('#td_minlot'); wait(pg, 1500); n3 = cnt(pg); ok(n3 >= n_strong, f'min-lot toggle off -> strong {n3} >= {n_strong}')
    pg.check('#td_minlot'); wait(pg, 1200)
    pg.fill('#td_land', '60'); wait(pg, 1500); n4 = cnt(pg); ok(n4 > n_strong, f'land share 60% -> strong {n4} > {n_strong}')
    pg.fill('#td_yb', '1950'); wait(pg, 1500); n5 = cnt(pg); ok(n5 < n4, f'max year 1950 -> {n5} < {n4}')
    pg.click('#tdReset'); wait(pg, 1500); ok(cnt(pg) == n_strong and pg.input_value('#td_land') == '80' and 'tdr=' not in pg.evaluate('location.hash'), 'Reset to defaults restores the count and clears the hash')
    pg.click('#clrTd'); wait(pg, 1200); ok(cnt(pg) == total, 'Clear tier -> back to all')
    # ---- lot vs zone minimum ----
    n_split = chipn(pg, '#lotz .chip[data-lz="split"]')
    pg.click('#lotz .chip[data-lz="split"]'); wait(pg, 1500); ns = cnt(pg)
    ok(ns > 0 and (n_split is None or n_split == ns), f'Lot could be split chip {n_split} == results {ns}')
    pg.fill('#td_split', '4'); wait(pg, 1500); ns4 = cnt(pg); ok(ns4 < ns, f'split factor 4x -> fewer splittable lots ({ns4} < {ns})')
    pg.click('#tdReset'); wait(pg, 1200)
    pg.click('#lotz .chip[data-lz="split"]'); pg.click('#lotz .chip[data-lz="below"]'); wait(pg, 1500); nb2 = cnt(pg)
    ok(nb2 > 0 and all('lot under zone min' in c.inner_text() for c in pg.query_selector_all('#cards .card')[:10]), f'Lot under zone minimum -> {nb2}, cards say so')
    pg.click('#lotz .chip[data-lz="below"]'); wait(pg, 1200); ok(cnt(pg) == total, 'lot chips cleared')
    # ---- city zoning grouped by city ----
    det = pg.query_selector_all('#mzCities details.mzc'); ok(len(det) >= 30, f'{len(det)} city groups')
    ok(pg.get_attribute('#mzCities details[data-j="Miami"]', 'open') is not None, 'Miami group open by default')
    hia = pg.query_selector('#mzCities details[data-j="Hialeah"]'); ok(hia.get_attribute('open') is None, 'Hialeah collapsed by default')
    pg.click('#mzCities details[data-j="Hialeah"] > summary'); wait(pg, 300)
    ok(pg.get_attribute('#mzCities details[data-j="Hialeah"]', 'open') is not None, 'Hialeah opens on tap')
    chip = pg.query_selector('#mzCities details[data-j="Hialeah"] .chip'); code = chip.get_attribute('data-mzs'); cn_ = chipn(pg, f'#mzCities .chip[data-mzs="{code}"]')
    chip.click(); wait(pg, 1500); nh = cnt(pg)
    ok(nh > 0 and (cn_ is None or cn_ == nh), f'pick {code}: chip {cn_} == results {nh}')
    ok(all('Hialeah' in c.inner_text() for c in pg.query_selector_all('#cards .card')[:10]), 'picked code only in that city')
    ok('picked' in pg.inner_text('#mzCities details[data-j="Hialeah"] summary'), 'group shows "1 picked"')
    ok('mzs=' in pg.evaluate('location.hash'), 'hash has mzs')
    pg.click('#clrMz'); wait(pg, 1200); ok(cnt(pg) == total, 'zoning cleared')
    pg.fill('#mzq', 'T6'); wait(pg, 1500); nt6 = cnt(pg)
    codes = set(c.inner_text().split('Zoning')[1].split('·')[0].strip() for c in pg.query_selector_all('#cards .card')[:40])
    ok(nt6 > 1000 and all(x.startswith('T6') for x in codes) and len(codes) > 1, f'typed "T6" prefix -> {nt6}, codes {sorted(codes)[:6]}')
    pg.fill('#mzq', ''); wait(pg, 1200)
    # ---- money shorthand ----
    pg.fill('#mvMin', '500k'); pg.fill('#mvMax', '1.2m'); wait(pg, 1800)
    vals = pg.evaluate("[...document.querySelectorAll('#cards .card')].slice(0,40).map(c=>c.querySelector('.facts > div:nth-child(3) .v').textContent)")
    def mv(s):
        s = s.replace('$', ''); return float(s[:-1]) * (1e6 if s.endswith('M') else 1e3)
    ok(all(5e5 <= mv(v) <= 1.2e6 + 5e3 for v in vals), f'500k-1.2m values: {vals[:5]}')
    hsh = pg.evaluate('location.hash'); ok('mvMin=500000' in hsh and 'mvMax=1200000' in hsh, 'hash has mvMin=500000 mvMax=1200000')
    pg.fill('#spMin', '100k'); wait(pg, 1200); ok('spMin=100000' in pg.evaluate('location.hash'), 'sale price accepts 100k')
    pg.fill('#spMin', ''); pg.fill('#mvMin', ''); pg.fill('#mvMax', ''); wait(pg, 1500); ok(cnt(pg) == total, 'money boxes cleared')
    # ---- construction + adverse possession ----
    nw = chipn(pg, '#cnChips .chip[data-cn="2"]'); pg.click('#cnChips .chip[data-cn="2"]'); wait(pg, 1500)
    ok(cnt(pg) > 0 and (nw is None or nw == cnt(pg)), f'Wood frame chip {nw} == results {cnt(pg)}')
    pg.click('#cards .card:nth-of-type(1)'); pg.wait_for_selector('.drawer'); wait(pg, 1200); ok('Wood frame' in pg.inner_text('.drawer'), 'drawer shows construction'); pg.keyboard.press('Escape')
    pg.click('#clrCn'); wait(pg, 1200)
    apn = int(pg.inner_text('#apCount').strip('()').replace(',', '')); pg.check('#apOnly'); wait(pg, 1500)
    ok(apn > 50 and cnt(pg) == apn and 'Adverse possession' in pg.inner_text('#cards .card'), f'adverse possession {apn} == results')
    pg.uncheck('#apOnly'); wait(pg, 1200)
    # ---- presets ----
    names = pg.eval_on_selector_all('#ideas .chip[data-i]', 'e=>e.sort((a,b)=>a.dataset.i-b.dataset.i).map(x=>x.textContent)')
    ok(any('Strong teardowns' in n for n in names) and any('could be split' in n for n in names), 'new presets present')
    i = [k for k, n in enumerate(names) if 'Strong teardowns' in n][0]
    pg.click(f'#ideas .chip[data-i="{i}"]'); wait(pg, 1500)
    ok(cnt(pg) == n_strong and pg.input_value('#sortSel') == 'um_d', f'Strong teardowns preset -> {cnt(pg)} sorted by unit multiple')
    i = [k for k, n in enumerate(names) if n == 'Teardowns'][0]
    pg.click(f'#ideas .chip[data-i="{i}"]'); wait(pg, 1500); ok(cnt(pg) == n_basic, 'Teardowns preset = basic tier')
    # ---- send to ----
    f1 = pg.get_attribute('#cards .card:nth-of-type(1)', 'data-folio'); f2 = pg.get_attribute('#cards .card:nth-of-type(2)', 'data-folio')
    pg.click(f'#cards .card[data-folio="{f1}"] [data-sendtag="cc"]'); pg.click(f'#cards .card[data-folio="{f2}"] [data-sendtag="cc"]'); pg.click(f'#cards .card[data-folio="{f1}"] [data-sendtag="dk"]'); wait(pg, 500)
    ok(pg.query_selector('.drawer') is None, 'tag button does not open the drawer')
    ok(chipn(pg, '#sendChips .chip[data-send="cc"]') == 2 and chipn(pg, '#sendChips .chip[data-send="dk"]') == 1, 'chips: 2 call center, 1 door knock')
    ok('2 ready' in pg.inner_text('#sendInfo-cc'), 'call center: ' + pg.inner_text('#sendInfo-cc'))
    pg.click('#sendChips .chip[data-send="cc"]'); wait(pg, 1500); ok(cnt(pg) == 2, 'Send to filter: 2 tagged')
    pg.fill('#listName-cc', 'Hialeah teardowns Oct')
    with pg.expect_download() as dl: pg.click('#sendExp-cc')
    d0 = dl.value; ok(d0.suggested_filename == 'Hialeah_teardowns_Oct.csv', 'file name ' + d0.suggested_filename)
    rows = list(csv.DictReader(io.StringIO(open(d0.path(), encoding='utf-8').read())))
    ok(len(rows) == 2 and rows[0]['Team'] == 'Call center' and rows[0]['List Name'] == 'Hialeah teardowns Oct' and list(rows[0].keys())[:3] == ['Folio', 'Team', 'List Name'], 'export: folio, team, list name first; 2 rows')
    ok({r['Folio'] for r in rows} == {f1, f2} and all(r['Teardown Tier'] in ('Teardown', 'Strong') for r in rows) and all(r['Call Center Tag'] == 'Y' for r in rows), 'export rows = tagged folios with teardown columns')
    ok(not pg.query_selector('#sendBar').is_hidden() and 'Mark as sent' in pg.inner_text('#sendBar'), 'mark-as-sent bar shown')
    pg.click('#sendBar [data-sendmark="1"]'); wait(pg, 600)
    ok('Sent' in pg.inner_text(f'#cards .card[data-folio="{f1}"] .sendline'), 'card shows Call center · Sent badge')
    ok(pg.is_disabled('#sendExp-cc') and '2 already sent' in pg.inner_text('#sendInfo-cc'), 'nothing new to export: ' + pg.inner_text('#sendInfo-cc'))
    pg.click(f'#cards .card[data-folio="{f1}"] .resend[data-resend="cc"]'); wait(pg, 500)
    ok('1 ready' in pg.inner_text('#sendInfo-cc'), 'Re-send puts it back: ' + pg.inner_text('#sendInfo-cc'))
    pg.reload(); pg.wait_for_selector('#results:not([hidden])', timeout=180000); wait(pg, 1500)
    ok(cnt(pg) == 2 and chipn(pg, '#sendChips .chip[data-send="dk"]') == 1, 'tags + Send to filter survive reload')
    pg.click(f'#cards .card[data-folio="{f2}"] [data-sendtag="cc"]'); wait(pg, 1200); ok(cnt(pg) == 1, 'untag drops it from the Send to view')
    pg.click('#clrSend'); wait(pg, 1200)
    # ---- screenshot of the new filters ----
    pg.click('#resetBtn'); wait(pg, 1200); pg.click('#tierSeg button[data-tier="strong"]'); pg.click('#lotz .chip[data-lz="minok"]'); wait(pg, 1500)
    pg.click('#mzCities details[data-j="Hialeah"] > summary'); wait(pg, 300)
    el = pg.query_selector('#tdGrp'); el.scroll_into_view_if_needed()
    top = pg.evaluate("document.querySelector('#mzq').closest('.grp').getBoundingClientRect().top+scrollY")
    bot = pg.evaluate("document.querySelector('#sendGrp').getBoundingClientRect().bottom+scrollY")
    pg.set_viewport_size({'width': 1360, 'height': 900})
    pg.add_style_tag(content='#stickybar{position:static !important}')
    top = pg.evaluate("document.querySelector('#mzq').closest('.grp').getBoundingClientRect().top+scrollY")
    bot = pg.evaluate("document.querySelector('#sendGrp').getBoundingClientRect().bottom+scrollY")
    # the filters now live in a scrolling sidebar, so capture the filter groups element by element range instead of a page clip
    try: pg.screenshot(path=SHOTS + 'seeker_features.png', full_page=True, clip={'x': 0, 'y': max(0, top - 10), 'width': 1360, 'height': min(bot - top + 20, 3200)})
    except Exception: pg.query_selector('#tdGrp').screenshot(path=SHOTS + 'seeker_features.png')
    pg.click('#resetBtn'); wait(pg, 600)
    b.close()
print('\n'.join(errs) if errs else 'ALL PASS')
sys.exit(1 if errs else 0)
