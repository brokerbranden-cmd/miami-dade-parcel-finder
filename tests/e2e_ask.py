"""Ask box: plain-English requests -> the app's own filters. Each ask is checked against the same filters applied by hand (URL hash),
plus chips / hint / recent / examples, address + folio jumps, owner-name search (first-last vs last-first counties), county switch,
chip removal. argv: URL [desktop|mobile]"""
import sys, json, re
from urllib.parse import quote
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8097/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
BASE = URL.split('#')[0].split('?')[0]
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
MD = [  # ask, hand-applied hash
    ('Hialeah teardowns under 500k owned 20+ years by individuals', 'city=Hialeah&td=basic&mvMax=500000&hdMin=20&owner=person'),
    ('teardowns in hialeah owned over 20 years by private owners under $500,000', 'city=Hialeah&td=basic&mvMax=500000&hdMin=20&owner=person'),
    ('recert overdue in Little Havana', 'zip=33135,33130&sig=RC'),
    ('Little Havana recertification overdue', 'zip=33135,33130&sig=RC'),
    ('vacant lots over 10,000 sqft', 'type=vacant&lotMin=10000'),
    ('empty lots bigger than 10k sq ft', 'type=vacant&lotMin=10000'),
    ('lis pendens in Miami Gardens', 'city=Miami Gardens&sig=LP'),
    ('houses between $300k and $450k in Miami Gardens built before 1970', 'type=sf&city=Miami Gardens&mvMin=300000&mvMax=450000&ybMax=1969'),
    ('llc owned duplexes in Miami Beach', 'owner=corp&type=mf29&city=Miami Beach'),
    ('out of state owners in Homestead owned 15+ years', 'o_oos=yes&city=Homestead&hdMin=15'),
    ('tired landlords in hialeah', 'type=sf,th,mf29&hdMin=20&o_homestead=no&o_absz=yes&city=Hialeah'),
    ('probate and code violations in Opa-locka', 'sig=PR,CC&city=Opa-locka'),
    ('tax delinquent homes in Miami', 'sig=TX&type=sf&city=Miami'),
    ('condos in Doral under 300k', 'type=condo&city=Doral&mvMax=300000'),
    ('lots over half an acre in Homestead owned by trusts', 'type=vacant&lotMin=21780&city=Homestead&owner=trust'),
    ('2-9 units in North Miami no homestead', 'unMin=2&unMax=9&city=North Miami&o_homestead=no'),
]
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, service_workers='block'); pg = ctx.new_page(); pg.set_default_timeout(120000)
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    Q = '?drive=0&county=' if MOB else '?county='
    def load(county, h='hg=0'):
        pg.goto('about:blank'); pg.goto(BASE + Q + county + '#' + h, timeout=180000)
        if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(1500)
    def go(h): pg.evaluate(f"location.hash={json.dumps(h)}"); pg.wait_for_timeout(2500)
    n_of = lambda: pg.evaluate('PF.sample(5)')['n']
    def ask(t, wait=3000):
        pg.fill('#askQ', t); pg.press('#askQ', 'Enter'); pg.wait_for_timeout(wait)
    def hand(h):
        go('hg=0'); go(h + '&hg=0'); return n_of()
    def chips(): return pg.eval_on_selector_all('#askChips .askc:not(.off) > span', 'e=>e.map(x=>x.textContent)')

    load('miami-dade')
    ok(pg.is_visible('#askQ') and pg.is_visible('#askGo'), 'Ask box visible')
    ok(len(pg.query_selector_all('#askEx [data-ask]')) >= 3, 'example prompts shown')
    for t, h in MD:
        ask(t); a = n_of(); c = chips(); hint = pg.inner_text('#askHint') if pg.is_visible('#askHint') else ''
        n = hand(h); ok(a == n and n > 0, f'"{t}" -> {a} results = by hand ({h}) {n}; chips {c}' + (f'; hint {hint!r}' if hint else ''))
        ok(not hint or "Didn't understand" not in hint, f'"{t}" fully understood')
    # chip removal -> same as hand without that filter
    ask(MD[0][0]); pg.click('#askChips .askc:has-text("Individuals") .askdel'); pg.wait_for_timeout(2500); a = n_of()
    ok(a == hand('city=Hialeah&td=basic&mvMax=500000&hdMin=20'), f'removing the Individuals chip = filters without it ({a})')
    # unknown words -> hint
    ask('hialeah purple unicorns'); hint = pg.inner_text('#askHint')
    ok('purple unicorns' in hint and 'Hialeah' in chips(), f'unknown words get a hint: {hint!r}')
    # recent + example chips
    ok('hialeah purple unicorns' in pg.inner_text('#askRecent'), 'recent asks list')
    pg.click('#askEx [data-ask]:first-child') if False else pg.evaluate("document.querySelector('#askEx [data-ask]').click()"); pg.wait_for_timeout(3000)
    ok(pg.input_value('#askQ') == pg.get_attribute('#askEx [data-ask]', 'data-ask') and len(chips()) >= 2, 'tapping an example runs it')
    # address + folio jump
    go('city=Homestead&type=sf&hg=0'); rows = pg.evaluate('PF.sample(60)')['rows']
    cand = [r for r in rows if re.match(r'^\d+ (SW|NW|NE|SE) \d+ (ST|AVE|TER|CT|PL|RD|DR)$', r['addr'].strip())]
    picked = None
    for r in cand[:15]:
        go('q=' + quote(r['addr'].strip()) + '&hg=0')
        if n_of() == 1: picked = r; break
    ok(picked is not None, 'found a unique address to ask for')
    if picked:
        parts = picked['addr'].strip().split(); suf = {'ST': 'street', 'AVE': 'avenue', 'TER': 'terrace', 'CT': 'court', 'PL': 'place', 'RD': 'road', 'DR': 'drive'}[parts[-1]]
        n2 = int(parts[2]); ordn = str(n2) + ('th' if 10 <= n2 % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n2 % 10, 'th'))
        spoken = f'{parts[0]} {parts[1].lower()} {ordn} {suf}'
        ask(spoken, 4000); pg.wait_for_selector('#savedBox', timeout=60000)
        ok(pg.get_attribute('#savedBox', 'data-folio') == picked['folio'], f'address "{spoken}" opens that property')
        pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
        f = picked['folio']; dashed = f'{f[:2]}-{f[2:6]}-{f[6:9]}-{f[9:]}'
        ask(dashed, 5000); pg.wait_for_selector('#savedBox', timeout=60000)
        ok(pg.get_attribute('#savedBox', 'data-folio') == f, f'folio {dashed} jumps to the property')
        pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    # owner name (Miami-Dade first-last)
    go('city=Homestead&type=sf&hg=0'); ow = [r['owner'].strip() for r in pg.evaluate('PF.sample(80)')['rows'] if re.match(r'^[A-Z]{3,} [A-Z]{4,}$', r['owner'].strip())]
    if ow:
        first, last = ow[0].split(); ask(f'properties owned by {first.title()} {last.title()}'); a = n_of()
        ok(a >= 1 and a == hand('q=' + quote(f'{first} {last}')), f'"owned by {first.title()} {last.title()}" = owner search {first} {last} ({a})')
    # Broward from Miami-Dade: switches county, last-first owner names, closest-filter hint
    ask('tax delinquent 2+ years in Broward with lis pendens', 1000)
    pg.wait_for_function("location.search.includes('county=broward') && window.PF_READY", timeout=240000); pg.wait_for_timeout(4000)
    hint = pg.inner_text('#askHint'); a = n_of()
    ok('2+ years unpaid' in chips() and 'Lis pendens' in hint, f'Broward ask after switching county: chips {chips()}, hint {hint!r}')
    ok(a == hand('mtax=y2') and a > 0, f'Broward tax delinquent 2+ years = by hand ({a})')
    go('city=Hollywood&type=sf&hg=0'); bw = [r['owner'].strip() for r in pg.evaluate('PF.sample(80)')['rows'] if re.match(r'^[A-Z]{3,} [A-Z]{4,}$', r['owner'].strip())]
    if bw:
        last, first = bw[0].split(); ask(f'properties owned by {first.title()} {last.title()}'); a = n_of()
        ok(a >= 1 and a == hand('q=' + quote(f'{last} {first}')), f'Broward "owned by {first.title()} {last.title()}" searches {last} {first} ({a})')
    ask('Fort Lauderdale houses under 400k owned 20+ years'); a = n_of()
    ok(a == hand('city=Fort Lauderdale&type=sf&mvMax=400000&hdMin=20') and a > 0, f'Broward city + type + value + years ({a})')
    # Monroe
    load('monroe'); ask('vacant lots in Key West'); a = n_of()
    ok(a == hand('type=vacant&city=Key West') and a > 0, f'Monroe vacant lots in Key West ({a})')
    b.close()
print(('ALL PASS' if not errs else 'FAILED: ' + '; '.join(errs[:6])) + f' [{TAG}]', flush=True)
sys.exit(1 if errs else 0)
