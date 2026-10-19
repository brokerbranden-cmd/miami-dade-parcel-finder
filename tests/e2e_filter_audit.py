"""Filter-correctness audit (all three counties). Usage: python3 tests/e2e_filter_audit.py [URL] [desktop|mobile]

For a representative set of single filters, pairwise combinations and the 'More ideas' presets, every result row (up to CAP rows per
search, an evenly spaced sample beyond that) is re-checked against every active condition. The conditions are read from the URL hash
the app writes and evaluated here, in Python, from the row's own raw pack columns (PF.auditRows): the app's filter code is not reused.
It also checks that the count shown equals the number of results, and runs a name audit over every parcel of every pack: an owner name
with an entity / church keyword must never be classified as an individual ('person')."""
import sys, re, json, itertools
from urllib.parse import parse_qs
from playwright.sync_api import sync_playwright
import legacy_ui  # noqa: F401
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'desktop'
CAP = 3000
DSIG = ['FC', 'LP', 'TD', 'TC', 'TX', 'US', 'BV', 'CC', 'LN', 'RC', 'PR', 'DC']
FLAG = {'homestead': 1, 'oos': 2, 'absz': 4, 'corp': 8, 'trust': 16, 'govt': 32, 'estate': 64, 'senior': 128}
# entity / church keywords that never belong to an individual (lines from C/O, %, ATTN on and 'REM ...' remaindermen lines are skipped,
# as are lines with a person marker: '&W', 'H/E', 'LE', 'ETAL', 'JTRS')
ENT = (r"\b(?:L ?L ?C|INC|INCORPORATED|CORP|CORPORATION|LTD|LLP|PLLC|MINISTRIES|MINISTRY|CONGREGATION|SYNAGOGUE|MOSQUE|TABERNACLE|DIOCESE|"
       r"ARCHDIOCESE|CATHEDRAL|EVANGELICAL|FELLOWSHIP|ASSEMBLY OF GOD|BAPTIST CHURCH|CHURCH OF|ASSOCIATION|ASSN|FOUNDATION|SOCIETY|CLUB|"
       r"TRUSTEES OF|HOUSING AUTHORITY|CITY OF|IGLESIA (?:DE|DEL|BAUTISTA|EVANGELICA|CRISTIANA))\b")
ENT_RE = re.compile(ENT); PERS_RE = re.compile(r"&\s?[WH]\b|\bH ?/ ?E\b|\bLE\b|\bETAL\b|\bJTRS\b")
LIFE_RE = re.compile(r"\bLIFE\s+(EST(ATE)?|TENANT|TENANCY)\b|\bL/E\b|\bLE\b(?=\s*(\||&|$))")
FX_STOP = set('JR SR II III IV LE REM ETAL ETUX TR TRS TRUSTEE EST ESTATE OF THE AND DEC DECD DECEASED JTRS HEIRS UX VIR ET AL W H'.split())
errs = []; cover = []; unchecked = set()
def ok(cond, msg):
    if not cond: errs.append(msg); print('FAIL ' + msg)
    return cond
def name_lines(o):
    out = []
    for l in str(o or '').upper().split('|'):
        l = l.strip()
        if re.match(r"(C ?/ ?O\b|%|ATTN\b|CARE OF)", l): break
        if l.startswith('REM '): continue
        out.append(re.sub(r'\s+', ' ', re.sub(r"[^A-Z0-9&/]+", ' ', l.replace('.', '').replace("'", ''))).strip())
    return out
def entity_name(o): return any(ENT_RE.search(l) and not PERS_RE.search(l) for l in name_lines(o))
def surnames(s):
    out = set()
    for seg in re.split(r"\s*\|\s*|\s*&\s*", str(s or '')):
        t = [w for w in re.sub(r'[^A-Z ]+', ' ', seg.upper()).split()]
        while t and t[-1] in FX_STOP: t.pop()
        while t and t[0] in FX_STOP: t.pop(0)
        if len(t) >= 2: out.add(t[-1]); out.add(t[0])   # roll order differs by county (FIRST LAST / LAST FIRST): accept either end
    return out
def kind(r): f = r['flags']; return 'corp' if f & 8 else 'trust' if f & 16 else 'govt' if f & 32 else 'person'
def checks(h, today):
    """hash params -> list of (label, predicate(row))."""
    q = {k: v[0] for k, v in parse_qs(h.lstrip('#'), keep_blank_values=True).items()}
    C = []
    num = lambda k: float(q[k]) if k in q and q[k] != '' else None
    if q.get('gov') != '1': C.append(('hide government', lambda r: not (r['flags'] & 32) and r['type'] != 'gov'))
    if 'owner' in q:
        w = q['owner']; C.append((f'owner={w}', lambda r, w=w: kind(r) == w))
        if w == 'person': C.append(('person name has no entity keyword', lambda r: not entity_name(r['owner'])))
    if 'type' in q:
        ts = set(q['type'].split(',')); C.append((f'type in {sorted(ts)}', lambda r, ts=ts: r['type'] in ts))
    for col, a, b in [('mkt', 'mvMin', 'mvMax'), ('lot', 'lotMin', 'lotMax'), ('sqft', 'sfMin', 'sfMax'), ('units', 'unMin', 'unMax')]:
        lo, hi = num(a), num(b)
        if lo: C.append((f'{col}>={lo:g}', lambda r, c=col, lo=lo: r[c] >= lo))
        if hi: C.append((f'{col}<={hi:g}', lambda r, c=col, hi=hi: r[c] <= hi))
    lo, hi = num('ybMin'), num('ybMax')
    if lo: C.append((f'yb>={lo:g}', lambda r, lo=lo: r['yb'] and r['yb'] >= lo))
    if hi: C.append((f'yb<={hi:g}', lambda r, hi=hi: r['yb'] and r['yb'] <= hi))
    lo, hi = num('hdMin'), num('hdMax')
    held = lambda r: today - r['sd1'] if r['sd1'] else 99999
    if lo: C.append((f'held>={lo:g}y', lambda r, lo=lo: held(r) >= lo * 365.25))
    if hi: C.append((f'held<={hi:g}y', lambda r, hi=hi: held(r) <= hi * 365.25))
    if q.get('city'): C.append((f"city={q['city']}", lambda r, v=q['city']: r['city'] == v))
    if q.get('zip'):
        zs = {z.strip()[:5] for z in re.split(r'[\s,;]+', q['zip']) if z.strip()}; C.append((f'zip in {sorted(zs)}', lambda r, zs=zs: r['zip'] in zs))
    for k, bit in FLAG.items():
        v = q.get('o_' + k)
        if v == 'yes': C.append((f'{k}=yes', lambda r, b=bit: r['flags'] & b))
        if v == 'no': C.append((f'{k}=no', lambda r, b=bit: not (r['flags'] & b)))
    if 'sig' in q:
        m = sum(1 << DSIG.index(s) for s in q['sig'].split(',') if s in DSIG); C.append((f"signal any of {q['sig']}", lambda r, m=m: r['dsig'] & m))
    if num('ds'): C.append((f"dscore>={q['ds']}", lambda r, v=num('ds'): r['dscore'] >= v))
    if q.get('td') in ('basic', 'strong'):
        t = 2 if q['td'] == 'strong' else 1; C.append((f"teardown tier>={t}", lambda r, t=t: r['tier'] >= t))
    if 'mtax' in q:
        T = set(q['mtax'].split(',')); y = 3 if 'y3' in T else 2 if 'y2' in T else 1
        C.append((f'unpaid tax years>={y}', lambda r, y=y: r.get('txy', 0) >= y))
        if 'cert' in T: C.append(('investor certificate', lambda r: r.get('txf', 0) & 1))
        if 'county' in T: C.append(('county certificate', lambda r: r.get('txf', 0) & 2))
    if num('mtmin'): C.append((f"tax balance>={q['mtmin']}", lambda r, v=num('mtmin'): r.get('txb', 0) >= v))
    lim = today - round(3 * 365.25)
    def fam(r):
        if r['flags'] & 56 or r['sd1'] < lim: return False
        if 'sx' in r: return bool(r['sx'] & 1)
        return r.get('sq1') == 2 and r.get('grantor') is not None and bool(surnames(r['owner']) & surnames(r['grantor']))
    if q.get('x_fam') == 'yes': C.append(('relative transfer, 3 yrs', fam))
    if q.get('x_famoos') == 'yes': C.append(('relative transfer + out of state', lambda r: fam(r) and r['flags'] & 2))
    if q.get('x_life') == 'yes': C.append(('life estate', lambda r: LIFE_RE.search(r['owner'].upper()) or (r.get('sx', 0) & 2)))
    if q.get('x_death') == 'yes': C.append(('death recorded', lambda r: r['dsig'] & (1 << DSIG.index('DC'))))
    if q.get('hs') == '1': C.append(('hide sent', None))   # checked against the sent list below
    known = {'gov', 'owner', 'type', 'mvMin', 'mvMax', 'lotMin', 'lotMax', 'sfMin', 'sfMax', 'unMin', 'unMax', 'ybMin', 'ybMax', 'hdMin', 'hdMax', 'city', 'zip', 'sig', 'ds',
             'td', 'mtax', 'mtmin', 'x_fam', 'x_famoos', 'x_life', 'x_death', 'hs', 'sort', 'view', 'in'} | {'o_' + k for k in FLAG}
    for k in q:
        if k not in known: unchecked.add(k)
    return C
def audit(pg, county, label, h=None, click=None):
    r0 = pg.evaluate('PF.runN()')
    if click is not None:
        pg.evaluate(f"document.querySelector('#ideas button[data-i=\"{click}\"]').click()")
    else:
        pg.evaluate(f"location.hash={json.dumps(h)}")
    last = None
    try: pg.wait_for_function(f'PF.runN()>{r0}', timeout=20000)
    except Exception: pass   # same state as before (no re-run needed)
    for _ in range(60):   # settle: lazy packs (condo units, transfer detail) re-run the search when they arrive
        pg.wait_for_timeout(350); r = pg.evaluate(f"PF.auditRows({CAP})")
        key = (r['n'], r['shown'], pg.evaluate('location.hash'))
        if key == last and not pg.evaluate("!!document.querySelector('#liveCount.busy')"): break
        last = key
    hh = pg.evaluate('location.hash'); C = checks(hh, r['today']); sent = set(r['sent'])
    shown = int(re.sub(r'\D', '', r['shown']) or 0)
    ok(shown == r['n'], f"{county} | {label}: count shown {shown} != results {r['n']}")
    bad = 0
    for row in r['rows']:
        for lab, f in C:
            good = (row['folio'] not in sent) if f is None else bool(f(row))
            if not good:
                bad += 1
                if bad <= 5: ok(False, f"{county} | {label}: {row['folio']} '{row['owner'][:60]}' fails [{lab}] {hh}")
    if bad > 5: ok(False, f"{county} | {label}: {bad} violations in total")
    cover.append((county, label, r['n'], len(r['rows']), len(C)))
    print(f"{'PASS' if not bad else 'FAIL'} {county} | {label}: n={r['n']} checked={len(r['rows'])} conditions={len(C)}")
    return r
with sync_playwright() as pw:
    b = pw.chromium.launch()
    vp = {'width': 390, 'height': 844} if MODE == 'mobile' else {'width': 1360, 'height': 900}
    for county in ['miami-dade', 'monroe', 'broward']:
        ctx = b.new_context(viewport=vp, is_mobile=MODE == 'mobile', has_touch=MODE == 'mobile'); pg = ctx.new_page()
        pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
        pg.goto(URL + '?county=' + county); pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(1500)
        md = county == 'miami-dade'
        # seed 'sent' marks on a few parcels so 'Hide already sent' has something to hide
        base = audit(pg, county, 'baseline', '#sort=lot_d')
        seed = [x['folio'] for x in base['rows'][:5]]
        pg.evaluate("f=>{ const k=PFCounty.key('pf.send.v1'); const o=JSON.parse(localStorage.getItem(k)||'{}'); o.tags=o.tags||{}; o.sent=o.sent||{}; f.forEach(x=>o.sent[x]={cc:'2026-10-01'}); localStorage.setItem(k,JSON.stringify(o)); }", seed)
        pg.reload(); pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(1500)
        # pick a real city / zip from the data
        cities = {}; zips = {}
        for x in base['rows']: cities[x['city']] = cities.get(x['city'], 0) + 1; zips[x['zip']] = zips.get(x['zip'], 0) + 1
        city = max((c for c in cities if c), key=cities.get); zp = max((z for z in zips if z), key=zips.get)
        S = {'own_person': 'owner=person', 'own_corp': 'owner=corp', 'own_trust': 'owner=trust', 'gov_shown': 'gov=1',
             'type_sf': 'type=sf', 'type_vacant': 'type=vacant', 'type_mf29': 'type=mf29', 'type_condo': 'type=condo', 'type_com': 'type=com,mixed',
             'value': 'mvMin=200000&mvMax=600000', 'lot': 'lotMin=5000&lotMax=10000', 'year': 'ybMin=1950&ybMax=1980', 'city': 'city=' + city, 'zip': 'zip=' + zp,
             'absentee': 'o_absz=yes', 'oos': 'o_oos=yes', 'not_homestead': 'o_homestead=no', 'estate': 'o_estate=yes', 'fam': 'x_fam=yes', 'life': 'x_life=yes',
             'teardown': 'td=basic', 'teardown_strong': 'td=strong', 'hide_sent': 'hs=1'}
        if md:
            for s in DSIG: S['sig_' + s] = 'sig=' + s
            S['death'] = 'x_death=yes'; S['tax'] = 'sig=TX,TC'; S['ds50'] = 'ds=50'
        else:
            S['tax'] = 'mtax=any'; S['tax_y2_cert'] = 'mtax=y2,cert'
        for k, h in S.items(): audit(pg, county, k, '#' + h)
        # pairwise: every owner kind x every other filter, plus value/type/area/flag pairs
        others = [k for k in S if not k.startswith('own_')]
        for k in others: audit(pg, county, f'own_person + {k}', '#' + S['own_person'] + '&' + S[k])
        sub = [k for k in ['type_sf', 'type_condo', 'value', 'city', 'oos', 'tax', 'life', 'teardown', 'hide_sent', 'sig_RC', 'sig_LP', 'death'] if k in S]
        for ok_ in ['own_corp', 'own_trust']:
            for k in sub: audit(pg, county, f'{ok_} + {k}', '#' + S[ok_] + '&' + S[k])
        extra = [('type_sf', 'value'), ('type_vacant', 'lot'), ('city', 'year'), ('zip', 'absentee'), ('oos', 'not_homestead'), ('tax', 'absentee'),
                 ('teardown', 'type_sf'), ('life', 'oos'), ('fam', 'city'), ('hide_sent', 'type_sf'), ('estate', 'value'), ('tax', 'hide_sent')]
        if md: extra += [('sig_RC', 'type_condo'), ('sig_RC', 'city'), ('sig_LP', 'oos'), ('sig_TD', 'value'), ('death', 'type_sf'), ('ds50', 'teardown'), ('sig_PR', 'estate'), ('sig_CC', 'hide_sent')]
        for a, c in extra: audit(pg, county, f'{a} + {c}', '#' + S[a] + '&' + S[c])
        # presets ('More ideas'): click each one, then audit with the conditions the app wrote to the hash
        n_ideas = pg.evaluate("document.querySelectorAll('#ideas button[data-i]').length")
        for i in pg.evaluate("[...document.querySelectorAll('#ideas button[data-i]')].map(b=>[b.dataset.i,b.textContent.trim()])"):
            audit(pg, county, 'preset: ' + i[1], click=i[0])
        # owner-kind counts on the filter buttons add up
        pg.evaluate("location.hash='#sig=RC'" if md else "location.hash='#sort=lot_d'"); pg.wait_for_timeout(2500)
        t = pg.inner_text('#ownerKind'); nums = [int(x.replace(',', '')) for x in re.findall(r'(?<![\d.])(\d[\d,]*)(?![\d.KM])', t)]
        if len(nums) == 4: ok(nums[0] == nums[1] + nums[2] + nums[3], f"{county}: owner-kind counts add up {nums}")
        # name audit over every parcel of every loaded pack (main + condo units)
        pg.evaluate("PF.cmMissing([])") if md else None; pg.wait_for_timeout(1000)
        res = pg.evaluate("""([ent,pers])=>{ const E=new RegExp(ent), PR=new RegExp(pers), bad=[]; let n=0, persons=0;
            const lines=o=>{ const out=[]; for(let l of String(o||'').toUpperCase().split('|')){ l=l.trim(); if(/^(C ?\\/ ?O\\b|%|ATTN\\b|CARE OF)/.test(l)) break; if(l.startsWith('REM ')) continue; out.push(l.replace(/[.']/g,'').replace(/[^A-Z0-9&\\/]+/g,' ').replace(/\\s+/g,' ').trim()); } return out; };
            for(const p of PF.PACKS){ if(!p) continue; for(let i=0;i<p.n;i++){ n++; if(p.c.flags[i]&56) continue; persons++; const o=PF.getStr(p,'owner',i); if(lines(o).some(l=>E.test(l)&&!PR.test(l))) bad.push(PF.getStr(p,'folio',i)+' '+o); } }
            return {n, persons, bad:bad.slice(0,50), nbad:bad.length, fix:PF.okFix()}; }""", [ENT, PERS_RE.pattern])
        print(f"{county}: name audit over {res['n']} parcels ({res['persons']} individuals), app reclassified {res['fix']}")
        ok(res['nbad'] == 0, f"{county}: {res['nbad']} individuals with an entity/church name, e.g. {res['bad'][:10]}")
        ctx.close()
    b.close()
print(f"COVERAGE: {len(cover)} searches audited, {sum(c[3] for c in cover)} rows checked; params not re-checked (presets only): {sorted(unchecked)}")
print('ERRORS:', errs[:60] if errs else 'none', f'({len(errs)})' if errs else ''); sys.exit(1 if errs else 0)
