"""Headless e2e for Assemblages: lazy data load, filter + group count, upside-only, presets, sort by group score, card badge,
'Show group' (single group + back), drawer section (reason, members, links), map outlines (tiles load only in map mode),
CSV columns, hash round-trip. argv: URL [SHOTS_DIR] [mobile]"""
import sys, csv, io, re
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
SHOTS = sys.argv[2] if len(sys.argv) > 2 else '/workspace/parcel-finder/shots/'
MOBILE = len(sys.argv) > 3 and sys.argv[3] == 'mobile'
TAG = 'mobile' if MOBILE else 'desktop'
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m)
    if not c: errs.append(m)
cnt = lambda pg: int(pg.inner_text('#sCount').replace(',', ''))
with sync_playwright() as pw:
    b = pw.chromium.launch()
    vp = {'width': 390, 'height': 844} if MOBILE else {'width': 1360, 'height': 900}
    ctx = b.new_context(viewport=vp, accept_downloads=True, is_mobile=MOBILE, has_touch=MOBILE)
    pg = ctx.new_page(); reqs = []
    pg.on('request', lambda r: reqs.append(r.url))
    pg.on('console', lambda m: m.type == 'error' and 'arcgisonline' not in m.text and errs.append('console: ' + m.text))
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    pg.goto(URL + ('?drive=0' if MOBILE else ''), timeout=180000)
    if MOBILE and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
    pg.wait_for_selector('#results:not([hidden])', timeout=180000); pg.wait_for_timeout(800)
    pg.click('#resetBtn'); pg.wait_for_timeout(1200); total = cnt(pg)
    ok(not any('asm-polys' in u for u in reqs), 'no outline tiles fetched at start')
    pg.click('#asmOn'); pg.wait_for_function("document.querySelector('#asmSrc').textContent.includes('groups')", timeout=60000); pg.wait_for_timeout(1500)
    n_all = cnt(pg); ok(5000 < n_all < total, f'assemblage parcels {n_all} of {total}')
    ok(any('asm.json.gz' in u for u in reqs) and not any('asm-polys' in u for u in reqs), 'asm.json.gz loaded, outlines still not loaded')
    src = pg.inner_text('#asmSrc'); ok(re.search(r'[\d,]+ groups \([\d,]+ parcels\)', src) is not None, 'source line: ' + src)
    ok('asm=1' in pg.evaluate('location.hash'), 'hash has asm=1')
    import urllib.request, gzip as _gz, json as _js
    _raw = urllib.request.urlopen(URL.split('#')[0].split('?')[0] + 'data/asm.json.gz', timeout=120).read()
    _o = _js.loads(_gz.decompress(_raw) if _raw[:2] == b'\x1f\x8b' else _raw)
    top = [[_o['zones'][r[5]], r[6], r[1], None if r[7] < 0 else r[7], None if r[8] < 0 else r[8], r[12] == 1] for r in _o['g'][:200]]
    ok(not any(z.upper() in ('AU', 'GU', 'AG') for z, *_ in top), 'no agricultural zoning in the top 200 groups')
    ok(max(t[1] for t in top) <= 2 * 43560, f'top 200 groups are all <= 2 acres combined (max {max(t[1] for t in top) / 43560:.2f} ac)')
    ok(all(t[5] or (t[3] or 0) > (t[4] or 0) for t in top[:50]), 'top 50 groups clear the zone minimum or add units')
    ok([t[2] for t in top] == sorted([t[2] for t in top], reverse=True), 'groups ordered by score')
    first_cards = pg.eval_on_selector_all('#cards .card', 'e=>e.slice(0,10).map(x=>x.innerText)')
    ok(not any('Agricultur' in t for t in first_cards), 'first 10 cards are not agricultural')
    ok(pg.input_value('#sortSel') == 'asm_d', 'sort switched to assemblage score')
    ok('assemblage groups' in pg.inner_text('#summary') if pg.query_selector('#summary') else True, 'summary mentions groups')
    pg.click('#asmUp'); pg.wait_for_timeout(1500); n_up = cnt(pg)
    ok(0 < n_up < n_all, f'upside only {n_up} < {n_all}'); ok('asmup=1' in pg.evaluate('location.hash'), 'hash asmup=1')
    cards = pg.query_selector_all('#cards .card')[:12]
    badges = [c.query_selector('.asmb') for c in cards]
    ok(len(cards) > 5 and all(badges), 'every card has an assemblage badge')
    sc = [int(re.search(r'score (\d+)', x.inner_text()).group(1)) for x in badges if x]
    ok(sc == sorted(sc, reverse=True), f'sorted by group score desc: {sc[:8]}')
    ok(all('upside' in x.inner_text() for x in badges if x), 'upside-only badges say upside')
    pg.screenshot(path=f'{SHOTS}asm_{TAG}_cards.png')
    gid = re.search(r'#(\d+)', badges[0].inner_text()).group(1); nlots = int(re.search(r'(\d+) lots', badges[0].inner_text()).group(1))
    badges[0].click(); pg.wait_for_timeout(1500)
    ok(cnt(pg) == nlots, f'Show group #{gid} -> {cnt(pg)} parcels (badge says {nlots})')
    ok(f'asmg={gid}' in pg.evaluate('location.hash'), 'hash has asmg')
    ok(pg.is_visible('#asmRow') if not MOBILE else True, 'single-group row visible')
    # drawer
    pg.click('#cards .card:nth-of-type(1)', position={'x': 8, 'y': 8}); pg.wait_for_selector('.drawer', timeout=20000); pg.wait_for_timeout(800)
    d = pg.inner_text('.drawer'); dl = d.lower()
    ok(f'assemblage #{gid}' in dl and 'owners' in dl and 'combined' in dl, 'drawer assemblage section with reason')
    ok(len(pg.query_selector_all('.drawer .asmlist li')) == nlots, 'drawer lists every member')
    pg.screenshot(path=f'{SHOTS}asm_{TAG}_drawer.png')
    pg.click('.drawer [data-asmmap]'); pg.wait_for_timeout(1000)
    pg.wait_for_function("document.querySelectorAll('.asmpoly').length>0", timeout=90000); pg.wait_for_timeout(800)
    ok(any('asm-polys/' in u for u in reqs), 'outline tile fetched in map mode')
    tiles = len({u for u in reqs if 'asm-polys/' in u}); ok(tiles <= 2, f'only {tiles} outline tile(s) fetched')
    ok(len(pg.query_selector_all('.asmpoly')) == nlots, f"{len(pg.query_selector_all('.asmpoly'))} outlines for {nlots} lots")
    ok('Assemblage:' in pg.inner_text('#mapHint'), 'map hint: ' + pg.inner_text('#mapHint'))
    pg.screenshot(path=f'{SHOTS}asm_{TAG}_map.png')
    # back to all groups
    pg.click('#vCards'); pg.wait_for_timeout(600)
    pg.click('#asmBack'); pg.wait_for_timeout(1500); ok(cnt(pg) == n_up, f'All groups -> back to {cnt(pg)}')
    # CSV
    with pg.expect_download(timeout=120000) as dlv: pg.click('#exportBtn')
    rows = list(csv.DictReader(io.StringIO(open(dlv.value.path(), encoding='utf-8-sig').read())))
    ok(len(rows) == n_up, f'CSV rows {len(rows)}')
    ok(all(r['Assemblage Group'] and r['Assemblage Upside'] == 'Y' and int(r['Assemblage Parcels']) >= 2 and 'owners' in r['Assemblage Reason'] for r in rows[:200]), 'CSV assemblage columns filled')
    # presets + hash reload
    pg.click('#resetBtn'); pg.wait_for_timeout(1000)
    names = pg.eval_on_selector_all('#ideas .chip', 'e=>e.map(x=>x.textContent)')
    i = next(k for k, x in enumerate(names) if 'Assemblages with' in x); pg.click(f'#ideas .chip[data-i="{i}"]', force=True); pg.wait_for_timeout(1500)
    ok(cnt(pg) == n_up, f'preset Assemblages with upside -> {cnt(pg)}')
    i = next(k for k, x in enumerate(names) if x.strip().endswith('Assemblages')); pg.click(f'#ideas .chip[data-i="{i}"]', force=True); pg.wait_for_timeout(1500)
    ok(cnt(pg) == n_all, f'preset Assemblages -> {cnt(pg)}')
    pg.goto(URL.split('#')[0] + ('?drive=0' if MOBILE else '') + '#asm=1&asmg=' + gid); pg.reload(); pg.wait_for_selector('#results:not([hidden])', timeout=180000)
    pg.wait_for_function(f"+document.querySelector('#sCount').textContent.replace(/,/g,'')=={nlots}", timeout=60000); ok(True, 'hash asmg reload restores single group')
    b.close()
print('ERRORS', errs) if errs else print('ALL OK')
sys.exit(1 if errs else 0)
