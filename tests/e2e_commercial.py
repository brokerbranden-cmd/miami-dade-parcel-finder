"""Commercial: coverage of every Miami-Dade folio on the Commercial Data list (tests/commercial_expect.json, made from
/workspace/distressed_commercial/distressed_commercial.xlsx) with matching score / live tax / entity / gas fields,
Commercial distress + closed gas + owner entity filters, live tax payoff on card + drawer (with read date),
commercial land-use presets and the commercial $/sqft comps estimate. argv: URL [desktop|mobile]"""
import sys, json, os, re
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
BASE = URL.split('#')[0].split('?')[0]; Q = '?drive=0' if MOB else ''
EXP = json.load(open(os.path.join(os.path.dirname(__file__), 'commercial_expect.json')))
ENT = {'Active (Open': 'Active', 'Inactive - d': 'Dissolved', 'Inactive - F': 'Inactive', 'Not found (F': 'Not found', 'Active/Inact': 'Mixed'}
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
with sync_playwright() as pw:
    b = pw.chromium.launch(); vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB); pg = ctx.new_page(); pg.set_default_timeout(60000)
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    def boot(h=''):
        pg.goto(BASE + Q + h, timeout=180000)
        if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_function('window.PF_READY && PF.cmReady()', timeout=240000); pg.wait_for_timeout(800)
    def go(h): pg.evaluate(f"location.hash={json.dumps(h)}"); pg.wait_for_timeout(2500)
    def all_rows(): x = pg.evaluate('PF.sample(100000)'); return x['rows']
    def smp(k): return pg.evaluate(f'PF.sample({k})')['rows']
    def chip(t): pg.evaluate("t=>{ for(const b of document.querySelectorAll('#ideas .chip')) if(b.textContent.trim()===t){ b.click(); return; } }", t); pg.wait_for_timeout(2500)
    boot()
    fs = [e['f'] for e in EXP]
    miss = pg.evaluate('fs=>PF.cmMissing(fs)', fs)
    ok(not miss, f'coverage: {len(fs) - len(miss)}/{len(fs)} Miami-Dade folios on the commercial list are in the parcel packs' + (f' (missing e.g. {miss[:5]})' if miss else ''))
    got = pg.evaluate('fs=>fs.map(f=>PF.cmGet(f))', fs); bad = {'s': 0, 'due': 0, 'lpy': 0, 'chk': 0, 'gas': 0, 'ent': 0, 'absent': 0}
    for e, g in zip(EXP, got):
        if not g: bad['absent'] += 1; continue
        if g['s'] != e['s']: bad['s'] += 1
        if e['live']:
            if abs((g.get('due') or 0) - (e['due'] or 0)) > 0.01: bad['due'] += 1
            if (g.get('lpy') or '') != (e['lpy'] or ''): bad['lpy'] += 1
            if (g.get('chk') or '') != e['chk']: bad['chk'] += 1
        elif 'chk' in g: bad['chk'] += 1
        if bool(g['gas']) != e['gas']: bad['gas'] += 1
        if g['ent'] != ENT.get(e['ent'], ''): bad['ent'] += 1
    nlive = sum(e['live'] for e in EXP)
    # condo-pack folios only show when Condo units is picked; filter counts below are over the main pack
    CON = set(pg.evaluate("fs=>{ const p=PF.PACKS[1], s=new Set(fs), o=[]; if(p) for(let i=0;i<p.n;i++){ const f=PF.getStr(p,'folio',i); if(s.has(f)) o.push(f); } return o; }", fs))
    print(f'[{TAG}] {len(CON)} list folios are condo units (condo pack)'); EXP = [e for e in EXP if e['f'] not in CON]
    ok(not any(bad.values()), f'fields match the xlsx for all {len(EXP)} folios (score, live payoff on {nlive}, last paid year, read date, closed gas, entity status) mismatches={bad}')
    go('cm=35&sort=cm_d&gov=1'); rs = all_rows(); want = sum(e['s'] >= 35 for e in EXP)
    ok(len(rs) == want and all(r['cmd'] and r['cmd']['s'] >= 35 for r in rs), f'Commercial distress 35+: {len(rs)} results (xlsx {want})')
    sc = [r['cmd']['s'] for r in smp(50)]; ok(sc == sorted(sc, reverse=True), 'sorted by commercial distress score')
    ok('Comm. distress' in pg.inner_text('#cards .card >> nth=0'), 'card shows the commercial distress badge')
    go('cgas=1&gov=1'); rs = all_rows(); want = sum(e['gas'] for e in EXP)
    ok(len(rs) == want and want > 0, f'Closed gas station filter: {len(rs)} (xlsx {want})'); ok('Closed gas station' in pg.inner_text('#cards'), 'closed gas station tag on cards')
    go('cent=in&gov=1'); rs = all_rows(); want = sum(ENT.get(e['ent']) in ('Inactive', 'Dissolved') for e in EXP)
    ok(len(rs) == want, f'Owner entity inactive/dissolved: {len(rs)} (xlsx {want})')
    tgt = next(e for e in sorted(EXP, key=lambda e: -(e['due'] or 0)) if e['live'] and e['due'])
    pg.goto('about:blank'); boot(('&' if Q else '?') + f'folio={tgt["f"]}'); pg.wait_for_selector('.drawer', timeout=60000); pg.wait_for_timeout(800); dt = pg.inner_text('.drawer')
    ok('Live tax' in dt and 'Payoff $' in dt and 'read ' in dt and 'Last paid year' in dt, f'drawer shows live payoff, last paid year and read date for {tgt["f"]}')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    go(f'q={tgt["f"]}&gov=1'); card = pg.locator(f'#cards .card[data-folio="{tgt["f"]}"]')
    ok(card.count() == 1 and re.search(r'Tax payoff.*\$[\d,.]+ due.*read \w+ \d+, \d{4}', card.inner_text(), re.S) is not None, 'card shows the tax payoff line with its read date')
    for name, word in (('Gas stations', 'SERVICE STATION'), ('Warehouses & industrial', None), ('Retail stores & centers', None), ('Office buildings', None)):
        chip(name); rs = smp(300); lus = {r['lu'][:2] for r in rs}
        ok(len(rs) > 10 and all(10 <= int(r['lu'][:2]) <= 49 for r in rs) and (word is None or all(word in r['lu'].upper() for r in rs)), f'preset {name}: {len(rs)} sampled, land uses {sorted(lus)}')
    chip('Retail stores & centers'); pg.wait_for_function('PF.compsReady()', timeout=180000); pg.wait_for_timeout(1500)
    rs = smp(200); e = [r for r in rs if r['comps'] and r['comps']['est']]
    ok(len(e) >= 0.3 * len(rs) and all(r['comps']['com'] and r['comps']['ppsf'] > 0 and r['comps']['rad'] <= 5 for r in e), f'retail: {len(e)}/{len(rs)} have a commercial $/sqft estimate (<=5 mi, 24 months)')
    pg.wait_for_timeout(1000); ok(re.search(r'\$[\d.]+/sf (bldg|lot)', pg.inner_text('#cards')) is not None, 'commercial card shows $/sf')
    b.close()
print(f'[{TAG}] ' + ('ALL PASS' if not errs else f'{len(errs)} FAIL: ' + '; '.join(errs[:8])))
sys.exit(1 if errs else 0)
