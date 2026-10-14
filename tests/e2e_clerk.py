"""Seeker-gap features: folio deep links, auction max bid, open pre-foreclosure filter + tag, probate filed (+ match confidence),
comps value estimate on cards (cross-checked against data/comps.json.gz in Python). argv: URL [desktop|mobile] [SHOTS_DIR]"""
import sys, re, gzip, json, math, os, urllib.request
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
SHOTS = sys.argv[3] if len(sys.argv) > 3 else '/workspace/parcel-finder/shots/clerk/'
os.makedirs(SHOTS, exist_ok=True)
BASE = URL.split('#')[0].split('?')[0]; Q = '?drive=0&' if MOB else '?'
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
def gz(name):
    raw = urllib.request.urlopen(BASE + 'data/' + name, timeout=60).read()
    return json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
SIG = gz('signals.json.gz'); CPD = gz('comps.json.gz')
PF = {r[0]: r for r in SIG['pf']}; PB = {r[0]: r for r in SIG['pb']}; AU = {r[0] for r in SIG['au']}
ok(len(PF) > 100 and len(PB) > 50 and len(AU) > 20, f"signals file: {len(PF)} open pre-foreclosures, {len(PB)} probate, {len(AU)} auction folios")
ok(all(r[4] in 'HM' for r in SIG['pb']), 'probate rows are high or medium confidence only')
ok(all(len(r) == 8 for r in SIG['au']) and all(r[6] > 0 or r[7] in (1, 0, -1) for r in SIG['au']), 'auction rows carry max bid (amount or hidden flag)')
cut = CPD['meta']['cutoff']; cutC = CPD['meta'].get('commCutoff', cut); com = lambda r: 10 <= int(r[7][:2]) <= 49
ok(CPD['meta']['months'] == 6 and all(r[4] >= 1000 and r[3] >= (cutC if com(r) else cut) for r in CPD['rows']), f"comps: {len(CPD['rows']):,} sales >= $1,000, residential since {cut}, commercial/industrial since {cutC}")
def boot(pg, url):
    pg.goto(url, timeout=180000)
    if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
    pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(800)
with sync_playwright() as pw:
    b = pw.chromium.launch(); vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB); pg = ctx.new_page()
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    # 1. deep links
    f = sorted(PF)[len(PF) // 2]; fd = f'{f[:2]}-{f[2:6]}-{f[6:9]}-{f[9:]}'
    boot(pg, BASE + Q + 'folio=' + fd); pg.wait_for_selector('.drawer', timeout=60000)
    ok(fd in pg.inner_text('.drawer'), f'?folio={fd} opens that property')
    ok(pg.locator(f'.card.flash[data-folio="{f}"]').count() == 1, 'its card is highlighted in the results')
    ok(pg.locator('#copyLink').count() == 1, 'drawer has Copy link')
    pg.keyboard.press('Escape')
    condo = next((r[0] for r in CPD['rows'] if r[7] == '0407'), None)
    if condo:
        boot(pg, BASE + Q.rstrip('&?') + '#folio=' + condo); pg.wait_for_selector('.drawer', timeout=90000)
        ok(f'{condo[:2]}-{condo[2:6]}' in pg.inner_text('.drawer'), f'#folio= for a condo unit ({condo}) loads the condo pack and opens it')
    boot(pg, BASE + Q + 'folio=0000000000009'); pg.wait_for_timeout(1500)
    ok(pg.locator('.drawer').count() == 0, 'unknown folio: no drawer (toast instead)')
    # 2. pre-foreclosure
    boot(pg, BASE + Q.rstrip('&?') + '#pf=1&gov=1'); s = pg.evaluate('PF.sample(400)')
    ok(s['n'] > 0 and all(r['folio'] in PF for r in s['rows']), f"#pf=1: {s['n']:,} results, all open pre-foreclosures")
    ok(s['n'] <= len(PF), 'never more than the open set')
    ok(pg.evaluate("document.getElementById('pfOnly').checked"), 'checkbox reflects the link')
    t = pg.get_attribute('#cards .card .pfb', 'title') or ''
    ok('Lis pendens recorded' in t and 'Verify with the Clerk' in t, 'card tag tooltip gives record date / case / CFN')
    ok(pg.evaluate("(document.querySelector('.cgrp .gact:not([hidden])')||{}).textContent") is not None, 'group shows an active-filter badge')
    # 3. probate
    boot(pg, BASE + Q.rstrip('&?') + '#pb=h&gov=1'); s = pg.evaluate('PF.sample(400)')
    ok(s['n'] > 0 and all(PB.get(r['folio'], [0] * 5)[4] == 'H' for r in s['rows']), f"#pb=h: {s['n']:,} results, all high-confidence probate")
    nh = s['n']; boot(pg, BASE + Q.rstrip('&?') + '#pb=hm&gov=1'); s = pg.evaluate('PF.sample(400)')
    ok(s['n'] >= nh and all(r['folio'] in PB for r in s['rows']), f"#pb=hm: {s['n']:,} >= high only {nh:,}")
    # 4. auction max bid
    boot(pg, BASE + Q.rstrip('&?') + '#sig=FC&gov=1'); pg.wait_for_selector('#cards .auline', timeout=60000)
    t = pg.inner_text('#cards .auline'); ok(re.search(r'max bid (Hidden|\$|Not posted|n/a)', t) is not None, f'card auction line: {t.strip()[:80]}')
    # 5. comps value estimate
    boot(pg, BASE + Q.rstrip('&?') + '#type=sf'); pg.wait_for_function('PF.compsReady()', timeout=180000); pg.wait_for_timeout(800)
    s = pg.evaluate('PF.sample(300)'); e = [r for r in s['rows'] if r['comps'] and r['comps']['est']]
    ok(len(e) >= 0.8 * len(s['rows']), f"{len(e)}/{len(s['rows'])} single-family results have an estimate")
    lat = {r[0]: (r[1] / 1e5, r[2] / 1e5) for r in CPD['rows']}
    geo = pg.evaluate("rs=>rs.map(f=>{ for(const p of PF.PACKS){ if(!p||!p.geo) continue; const c=PF.getStr; for(let i=0;i<p.n;i++) if(c(p,'folio',i)===f) return [p.geo.lat[i],p.geo.lon[i],PF.D.landuse[p.c.landuse[i]].slice(0,4),p.c.lot[i]]; } return null; })", [r['folio'] for r in e[:12]])
    good = 0
    for r, g in zip(e[:12], geo):
        if not g: continue
        c = r['comps']; la, lo, lu = g[:3]
        mi = lambda a, b: math.hypot((a - la) * 69.05, (b - lo) * 69.05 * math.cos(la * math.pi / 180))
        pool = [x for x in CPD['rows'] if x[7] == lu and x[0] != r['folio'] and (x[5] if c['useB'] else x[6]) > 0 and mi(x[1] / 1e5, x[2] / 1e5) <= c['rad']
                and 1 / c['band'] <= (x[5] if c['useB'] else x[6]) / c['size'] <= c['band']]
        if not c['useB']: pool = [x for x in pool if x[5] == 0]
        else: pool = [x for x in pool if not (g[3] > 0 and x[6] > 0) or 1 / (2 * c['band']) <= x[6] / g[3] <= 2 * c['band']]
        good += (c['n'] <= len(pool) and (c['sameCn'] or c['n'] == len(pool)) and c['lo'] <= c['est'] <= c['hi'])
    ok(good == sum(1 for g in geo if g), f'estimates match an independent recount of comps.json ({good}/{sum(1 for g in geo if g)})')
    boot(pg, BASE + Q.rstrip('&?') + '#type=sf&zip=33155&sort=sold_d'); pg.wait_for_function('PF.compsReady()', timeout=180000); pg.wait_for_timeout(800)
    pg.evaluate("document.querySelector('#cards .card:has(.cpline b)').scrollIntoView({block:'center'})"); pg.wait_for_timeout(300)
    card = pg.locator('#cards .card:has(.cpline b)').first
    ok(re.search(r'\$[\d.]+[KM]?–\$[\d.]+[KM]?', card.locator('.cpline').inner_text()) is not None, 'card shows the estimate range')
    card.screenshot(path=f'{SHOTS}card_value_estimate_{TAG}.png')
    card.locator('.facts').click(); pg.wait_for_selector('.drawer', timeout=60000); pg.wait_for_timeout(800)
    ok(pg.locator('.drawer .cpt tbody tr').count() >= 3 and 'Not an appraisal' in pg.inner_text('.drawer'), 'drawer lists the comparable sales')
    ok(pg.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'no horizontal scroll')
    b.close()
ok(not [x for x in errs if x.startswith('page')], 'no page errors')
print(f'\n[{TAG}] ' + ('ALL PASS' if not errs else f'{len(errs)} FAILED'))
sys.exit(1 if errs else 0)
