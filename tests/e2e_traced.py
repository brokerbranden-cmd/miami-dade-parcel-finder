"""Skip traced view: lists every property in this county's skip store (imports + BatchData Worker results), owner / address / traced date /
phones with DNC + litigator flags / emails, Email + Call/Text buttons, Emailed / contacted status, row opens the drawer, search, sort,
CSV export (standard columns + traced date, phones, emails), per county. argv: URL [desktop|mobile]"""
import sys, json, re, csv, io
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8097/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
BASE = URL.split('#')[0].split('?')[0]
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
STD = ['Owner Name', 'Property Address', 'Property City', 'Property State', 'Property Zip', 'Property County', 'Mailing Address', 'Mailing City', 'Mailing State', 'Mailing Zip', 'Folio']
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, accept_downloads=True, service_workers='block'); pg = ctx.new_page(); pg.set_default_timeout(120000)
    pg.add_init_script("window.__opened=[]; window.open=function(u){ window.__opened.push(String(u)); return null; };")
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    Q = '?drive=0&county=' if MOB else '?county='
    def load(county, h='hg=0'):
        pg.goto('about:blank'); pg.goto(BASE + Q + county + '#' + h, timeout=180000)
        if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(1500)
    def skey(c): return 'pf.skip.v1' + ('' if c == 'miami-dade' else '.' + c)
    def seed(c, recs): pg.evaluate(f"localStorage.setItem({json.dumps(skey(c))}, {json.dumps(json.dumps(recs))}); PFSkip.store.reload()"); pg.wait_for_timeout(800)
    def tv(): pg.evaluate("document.getElementById('vTraced').click()"); pg.wait_for_selector('#trbox:not([hidden])'); pg.wait_for_timeout(1200)
    rows_of = lambda: pg.eval_on_selector_all('#trList [data-trow]', 'e=>e.map(x=>x.dataset.trow)')

    load('miami-dade', 'city=Homestead&type=sf&hg=0')
    S = [r for r in pg.evaluate('PF.sample(300)')['rows'] if re.match(r'^[A-Z]{3,} [A-Z]{3,}$', r['owner'].strip()) and r['addr'].strip()][:3]
    ok(len(S) == 3, 'picked 3 Miami-Dade owners')
    A, B2, C = S
    seed('miami-dade', {A['folio']: {'a': '2026-10-12', 's': 'BatchData API', 'n': '', 'p': [['3055550101', 'm', 0], ['3055550102', 'l', 1]], 'e': ['a.owner@example.com']},
                        B2['folio']: {'a': '2026-10-18', 's': 'BatchData API', 'n': '', 'p': [['3055550201', 'm', 2]], 'e': []},
                        C['folio']: {'a': '2026-10-15', 's': 'Import', 'n': '', 'p': [], 'e': []}})
    ok(pg.is_visible('#vTraced') and pg.inner_text('#vTraced').strip() == 'Skip traced', 'Skip traced tab in the view switch')
    tv(); r = rows_of()
    ok(sorted(r) == sorted([A['folio'], B2['folio'], C['folio']]), f'lists every traced property ({len(r)})')
    ok(r == [B2['folio'], C['folio'], A['folio']], 'default sort: newest traced first')
    txt = pg.inner_text(f'[data-trow="{A["folio"]}"]')
    ok(A['addr'].strip().split()[0] in txt and A['owner'].split()[0] in txt.upper() and '2026-10-12' in txt, 'row shows address, owner, traced date')
    ok('(305) 555-0101' in txt and 'DNC' not in txt and 'a.owner@example.com' in txt, 'row shows phones (no DNC label) + emails')
    ok('Litigator' not in pg.inner_text(f'[data-trow="{B2["folio"]}"]') and 'Flagged' not in pg.inner_text('#trList'), 'no litigator / flagged label')
    ok(pg.query_selector(f'[data-trow="{A["folio"]}"] a[href="tel:+13055550101"]') and pg.query_selector(f'[data-trow="{A["folio"]}"] a[href="sms:+13055550101"]') and pg.query_selector(f'[data-trow="{A["folio"]}"] a[href="tel:+13055550102"]'), 'Call / Text on every number, DNC one included')
    ok('Not contacted' in txt, 'status: Not contacted before emailing')
    # Email from the view
    pg.click(f'[data-trow="{A["folio"]}"] [data-stemail]'); pg.wait_for_timeout(900)
    ok(pg.evaluate('window.__opened.length') == 1 and pg.evaluate('window.__opened[0]').startswith('https://outlook.office.com/mail/deeplink/compose?to=a.owner%40example.com'), 'Email button opens the Outlook compose deeplink')
    ok(not pg.query_selector('#drawerHost .stdraw') or not pg.is_visible('#drawerHost .stdraw'), 'Email click does not open the drawer')
    st = pg.inner_text(f'[data-trow="{A["folio"]}"] .trstat'); ok(st.startswith('Emailed ') and 'Not contacted' not in st, f'status updates to Emailed: "{st}"')
    # sort + search
    pg.select_option('#trSort', 'phones'); pg.wait_for_timeout(300); ok(rows_of()[0] == A['folio'], 'sort Most phones')
    pg.select_option('#trSort', 'new'); pg.wait_for_timeout(300); ok(rows_of()[-1] == A['folio'], 'sort Not contacted first')
    pg.select_option('#trSort', 'date_a'); pg.wait_for_timeout(300); ok(rows_of()[0] == A['folio'], 'sort Oldest traced')
    pg.fill('#trQ', '555-0201'); pg.wait_for_timeout(300); ok(rows_of() == [B2['folio']], 'search by phone')
    pg.fill('#trQ', 'a.owner@'); pg.wait_for_timeout(300); ok(rows_of() == [A['folio']], 'search by email')
    pg.fill('#trQ', C['addr'].strip().lower()); pg.wait_for_timeout(300); ok(C['folio'] in rows_of(), 'search by address')
    pg.fill('#trQ', ''); pg.wait_for_timeout(300)
    # CSV
    with pg.expect_download(timeout=60000) as d: pg.click('#trExport')
    rows = list(csv.reader(io.StringIO(open(d.value.path(), encoding='utf-8').read())))
    ok(rows[0][:11] == STD and rows[0][11] == 'Traced Date' and 'Phone 1' in rows[0] and not any('Flags' in c for c in rows[0]) and 'Email 1' in rows[0], f'CSV header: standard columns + traced date / phones / emails ({len(rows[0])} cols)')
    ok(len(rows) == 4, f'CSV has the 3 traced properties ({len(rows)-1})')
    h = rows[0]; ra = next(x for x in rows[1:] if x[10].replace('-', '') == A['folio'])
    ok(ra[h.index('Phone 1')] == '3055550101' and ra[h.index('Phone 2')] != '' and ra[h.index('Email 1')] == 'a.owner@example.com' and ra[h.index('Traced Date')] == '2026-10-12', 'CSV row carries phones (plain), email, date')
    # row click -> drawer
    pg.click(f'[data-trow="{C["folio"]}"] .traddr'); pg.wait_for_selector('#savedBox', timeout=60000)
    ok(pg.get_attribute('#savedBox', 'data-folio') == C['folio'], 'clicking a row opens the drawer for that property')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    # per county
    seed('monroe', {'1234567': {'a': '2026-10-10', 's': 'x', 'n': 'Monroe Owner', 'p': [], 'e': ['m@example.com']}})
    tv(); ok('1234567' not in rows_of() and len(rows_of()) == 3, 'Miami-Dade view ignores another county\'s results')
    load('broward'); tv(); ok(rows_of() == [] and 'No skip traced properties in Broward' in pg.inner_text('#trInfo'), 'Broward has its own (empty) list')
    pg.evaluate("document.getElementById('vCards').click()"); pg.wait_for_timeout(500)
    b.close()
print(('ALL PASS' if not errs else 'FAILED: ' + '; '.join(errs[:6])) + f' [{TAG}]', flush=True)
sys.exit(1 if errs else 0)
