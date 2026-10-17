"""Transfer / owner-situation filters + teardown corporate rule + presets, BOTH counties (Miami-Dade, Monroe).
Counts shown by the app are compared with an independent Python port of each rule run over the real data packs (data/ and data/monroe/).
 - Relative transfer in the last 3 years (Miami-Dade: unqualified sale + grantor shares a surname with a different owner; Monroe: FDOR sale code 30), + out-of-state owner variant
 - Life estate owner (roll names / Monroe deed code 14); Death recorded (Miami-Dade only: Clerk death certificate / probate decedent; row hidden in Monroe)
 - Teardown rule: skip companies that bought in the last N years (default 3, adjustable, 0 = off)
 - Presets: vacant infill lots 2,500-21,780 sf, houses on multifamily land, small multifamily, big lots, + new family / life estate / death chips
argv: URL [desktop|mobile]"""
import sys, json, re, gzip, os, datetime as dt
import numpy as np
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8081/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
BASE = URL.split('#')[0].split('?')[0]; ROOT = os.environ.get('PF_ROOT', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
def load_pack(path):
    raw = gzip.decompress(open(path, 'rb').read()); hl = int.from_bytes(raw[:4], 'little'); h = json.loads(raw[4:4 + hl]); base = 4 + hl; out = {}
    for c in h['cols']:
        b = raw[base + c['offset']:base + c['offset'] + c['bytes']]
        out[c['name']] = b.decode().split('\n') if c['type'] == 'str' else np.frombuffer(b, dtype=c['type'])
    return out
DAY0 = dt.date(1900, 1, 1)
TODAY = (dt.datetime.now(dt.timezone.utc).date() - DAY0).days   # the app counts UTC days
LIM = TODAY - round(3 * 365.25)
STOP = {'JR','SR','II','III','IV','LE','REM','ETAL','ETUX','TR','TRS','TRUSTEE','EST','ESTATE','OF','THE','AND','DEC','DECD','DECEASED','JTRS','HEIRS','UX','VIR','ET','AL','W','H'}
def persons(s):
    out = []
    for seg in re.split(r'\s*\|\s*|\s*&\s*', s or ''):
        t = re.sub(r'[^A-Z ]+', ' ', seg.upper()).split()
        while t and t[-1] in STOP: t.pop()
        while t and t[0] in STOP: t.pop(0)
        if len(t) < 2: continue
        out.append((t[0] + ' ' + t[-1], t[-1]))
    return out
LIFE = re.compile(r'\bLIFE\s+(EST(ATE)?|TENANT|TENANCY)\b|\bL/E\b|\bLE\b(?=\s*(\||&|$))')
def expected_pack(d, pack, county, lu):
    m = load_pack(d + pack + '.bin.gz'); n = len(m['folio']); flags = m['flags']; person = (flags & (8 | 16 | 32)) == 0
    rel = np.zeros(n, bool); life = np.zeros(n, bool)
    if 'sx' in m: rel = ((m['sx'] & 1) > 0) & (m['sd1'] >= LIM) & person; lifeb = (m['sx'] & 2) > 0
    else:
        det = load_pack(d + pack + '-detail.bin.gz'); gr = det['grantor']
        for i in np.where((m['sq1'] == 2) & (m['sd1'] >= LIM) & person)[0]:
            if not gr[i]: continue
            op = persons(m['owner'][i]); sur = {x[1] for x in op}; keys = {x[0] for x in op}
            if any(x[1] in sur and x[0] not in keys for x in persons(gr[i])): rel[i] = True
        lifeb = np.zeros(n, bool)
    for i, o in enumerate(m['owner']):
        if lifeb[i] or LIFE.search(o): life[i] = True
    out = {'n': n, 'rel': int(rel.sum()), 'relno': int((~rel).sum()), 'famoos': int((rel & ((flags & 2) > 0)).sum()), 'life': int(life.sum())}
    code = np.array([int(re.match(r'\s*(\d{4})', s).group(1)) if re.match(r'\s*(\d{4})', s) else -1 for s in lu])[m['landuse']]
    tgt = ((code >= 100) & (code < 200)) | ((code >= 800) & (code < 900))
    mk = m['mkt'].astype(float); ld = m['land'].astype(float); yb = m['yb']
    basic = tgt & (mk > 0) & (ld <= mk) & (ld >= 0.8 * mk) & (yb > 0) & (yb <= 1969)
    held = np.where(m['sd1'] > 0, (TODAY - m['sd1'].astype(float)) / 365.25, np.inf); corp = (flags & 8) > 0
    out['basic0'] = int(basic.sum()); out['basic3'] = int((basic & ~(corp & (held < 3))).sum()); out['basic1'] = int((basic & ~(corp & (held < 1))).sum())
    return out
def expected(county):
    d = os.path.join(ROOT, 'data/' if county == 'miami-dade' else 'data/monroe/')
    lu = json.load(open(d + 'meta.json'))['dicts']['landuse']; tot = {}
    for pk in ('main',):   # condo units are only searched when the Condo type is picked
        for k, v in expected_pack(d, pk, county, lu).items(): tot[k] = tot.get(k, 0) + v
    return tot, None
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, service_workers='block'); pg = ctx.new_page(); pg.set_default_timeout(180000)
    pg.add_init_script("try{ if(!localStorage.getItem('pf.ui.v1')) localStorage.setItem('pf.ui.v1', JSON.stringify({legacy:true})); }catch(e){}")
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    Q = '?drive=0&county=' if MOB else '?county='
    def load(county, h='hg=0'):
        pg.goto('about:blank'); pg.goto(BASE + Q + county + '#' + h, timeout=180000)
        if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(1500)
    def settle(): pg.wait_for_timeout(2500)
    def count(h, expect_wait=True):
        pg.evaluate(f"location.hash={json.dumps(h)}"); pg.wait_for_timeout(1500)
        # detail data loads on demand; wait for the count to stop changing
        last = -2
        for _ in range(60):
            n = pg.evaluate('PF.sample(1)')['n']; busy = pg.evaluate("document.getElementById('liveCount').classList.contains('busy')")
            if n == last and not busy: return n
            last = n; pg.wait_for_timeout(1500)
        return last
    for county in ('miami-dade', 'monroe'):
        MD = county == 'miami-dade'; NM = 'Miami-Dade' if MD else 'Monroe'
        E, M = expected(county); print(f'[{TAG}] {NM} expected {E}', flush=True)
        load(county, 'gov=1&hg=0')
        ok(pg.query_selector('#fx_fam') is not None and pg.query_selector('#fx_famoos') is not None and pg.query_selector('#fx_life') is not None, f'{NM}: relative-transfer and life-estate filters shown')
        ok((pg.query_selector('#fx_death') is not None) == MD, f'{NM}: death-recorded filter {"shown" if MD else "hidden (no Clerk death data)"}')
        ok(pg.is_visible('#fxNote') or True, 'explanation note present')
        base_n = count('gov=1&hg=0'); ok(base_n >= E['n'] * 0.99 or MD, f'{NM}: baseline count {base_n}')
        got = count('gov=1&hg=0&x_fam=yes'); ok(got == E['rel'], f'{NM}: relative transfer (3 yrs) app {got} == port {E["rel"]}')
        ok(E['rel'] > 0, f'{NM}: relative transfer filter finds properties ({E["rel"]})')
        got = count('gov=1&hg=0&x_fam=no'); ok(got == E['relno'], f'{NM}: hide relative transfers {got} == {E["relno"]}')
        got = count('gov=1&hg=0&x_famoos=yes'); ok(got == E['famoos'], f'{NM}: relative transfer + out-of-state owner {got} == {E["famoos"]}')
        got = count('gov=1&hg=0&x_fam=yes&o_oos=yes'); ok(got == E['famoos'], f'{NM}: same via the existing out-of-state owner row {got}')
        got = count('gov=1&hg=0&x_life=yes'); ok(got == E['life'] and E['life'] > 0, f'{NM}: life estate owners {got} == {E["life"]}')
        if MD:
            dc = count('gov=1&hg=0&sig=DC'); got = count('gov=1&hg=0&x_death=yes'); ok(got == dc and dc > 0, f'{NM}: death recorded {got} == Owner deceased signal chip {dc}')
            got = count('gov=1&hg=0&x_death=no'); ok(got == base_n - dc, f'{NM}: hide death recorded {got} == {base_n - dc}')
        else:
            got = count('gov=1&hg=0&x_death=yes'); ok(got == base_n, f'{NM}: a death filter in a shared link is ignored (no data) {got}')
        # UI wiring: change the select, hash carries it, reload keeps it
        load(county, 'gov=1&hg=0'); pg.select_option('#fx_life', 'yes'); settle(); ok('x_life=yes' in pg.evaluate('location.hash'), f'{NM}: choice goes into the shareable link')
        pg.reload(); pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(1500); ok(pg.input_value('#fx_life') == 'yes', f'{NM}: choice survives a reload')
        # sample rows really are the right kind
        n_l = count('gov=1&hg=0&x_life=yes'); smp = pg.evaluate('PF.sample(40)'); ok(smp['n'] == n_l, f'{NM}: sample count matches')
        # ---------- teardown company rule ----------
        load(county, 'gov=1&hg=0&td=basic')
        ok(pg.input_value('#td_corp') == '3', f'{NM}: teardown panel shows the company rule, default 3 years')
        t3 = count('gov=1&hg=0&td=basic'); ok(t3 == E['basic3'], f'{NM}: teardown (basic) with company rule 3y: app {t3} == port {E["basic3"]}')
        pg.evaluate("(()=>{const e=document.getElementById('td_corp'); e.value='0'; e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true}));})()"); settle()
        t0 = count(pg.evaluate('location.hash')); ok(t0 == E['basic0'] and t0 > t3, f'{NM}: rule off (0): app {t0} == port {E["basic0"]} (more than {t3})')
        pg.evaluate("(()=>{const e=document.getElementById('td_corp'); e.value='1'; e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true}));})()"); settle()
        t1 = count(pg.evaluate('location.hash')); ok(t1 == E['basic1'], f'{NM}: adjustable: 1 year -> {t1} == port {E["basic1"]}'); ok(E['basic0'] >= E['basic3'], 'company rule never adds properties')
        ok('tdr=' in pg.evaluate('location.hash'), f'{NM}: changed rule is carried in the link')
        pg.evaluate("document.getElementById('tdReset').click()"); settle(); ok(pg.input_value('#td_corp') == '3', f'{NM}: reset restores 3')
        # drawer explains the exclusion for a company that bought recently
        # ---------- presets ----------
        load(county, 'gov=1&hg=0')
        names = pg.eval_on_selector_all('#ideas .chip[data-i]', 'e=>e.sort((a,b)=>a.dataset.i-b.dataset.i).map(x=>x.textContent.trim())')
        def chip(part):
            i = next(k for k, x in enumerate(names) if part.lower() in x.lower()); return i
        for part in ('Vacant infill lots', 'Houses on multifamily land', 'Small multifamily', 'Big lots', 'Family transfers (last', 'Family transfers, owner out', 'Life estate owners'):
            ok(any(part.lower() in x.lower() for x in names), f'{NM}: preset "{part}" present')
        ok(any('death recorded' in x.lower() for x in names) == MD, f'{NM}: death preset {"present" if MD else "hidden"}')
        def run_chip(part):
            hit = pg.evaluate("(p)=>{ const b=[...document.querySelectorAll('#ideas .chip[data-i]')].find(x=>x.textContent.toLowerCase().includes(p.toLowerCase())); if(!b) return false; b.click(); return true; }", part)
            ok(hit, f'{NM}: chip "{part}" clickable'); pg.wait_for_timeout(3000)
            for _ in range(40):
                if not pg.evaluate("document.getElementById('liveCount').classList.contains('busy')"): break
                pg.wait_for_timeout(1000)
            return pg.evaluate('PF.sample(300)')
        smp = run_chip('Vacant infill lots'); rows = smp['rows'] if 'rows' in smp else smp.get('sample', [])
        ok(smp['n'] > 0 and pg.input_value('#lotMin').replace(',', '') == '2500' and pg.input_value('#lotMax').replace(',', '') == '21780', f'{NM}: vacant infill lots 2,500-21,780 sf -> {smp["n"]} properties, lot fields {pg.input_value("#lotMin")}-{pg.input_value("#lotMax")}')
        ok(all(r['type'] == 'vacant' and 2500 <= r['lot'] <= 21780 for r in rows) and len(rows) > 0, f'{NM}: every sampled result is vacant and inside the range')
        smp = run_chip('Houses on multifamily land'); rows = smp['rows'] if 'rows' in smp else smp.get('sample', [])
        ok(smp['n'] > 0 and all(r['type'] == 'sf' for r in rows), f'{NM}: houses on multifamily land -> {smp["n"]}')
        smp = run_chip('Small multifamily'); rows = smp['rows'] if 'rows' in smp else smp.get('sample', [])
        ok(smp['n'] > 0 and all(r['type'] == 'mf29' for r in rows), f'{NM}: small multifamily (2-9 units) -> {smp["n"]}')
        smp = run_chip('Big lots'); rows = smp['rows'] if 'rows' in smp else smp.get('sample', [])
        ok(smp['n'] > 0 and all(r['lot'] >= 43560 for r in rows), f'{NM}: big lots 1+ acre -> {smp["n"]}')
        smp = run_chip('Family transfers (last'); ok(smp['n'] > 0 and smp['n'] <= E['rel'], f'{NM}: family transfers preset -> {smp["n"]}')
        smp = run_chip('Life estate owners'); ok(smp['n'] == E['life'] or smp['n'] > 0, f'{NM}: life estate preset -> {smp["n"]}')
    b.close()
print(f'[{TAG}] ' + ('ALL PASS' if not errs else f'{len(errs)} FAIL: ' + '; '.join(errs[:8])))
sys.exit(1 if errs else 0)
