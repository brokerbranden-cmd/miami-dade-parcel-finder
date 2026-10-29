"""Smarter Contact export: buttons in the filter panel (current results), the saved bar and the Skip traced view; CSV header is exactly
Smarter Contact's field names (PFSC.HEAD); one row per owner, phones best first, DNC / wrong numbers / no-phone rows left out; Mark as sent
to Smarter Contact stores the sent numbers + logs a Text outreach entry; re-export skips sent numbers unless "Include already sent";
per county (Miami-Dade, Broward, Monroe; Puerto Rico when its data is built). Fake 555-01xx numbers only. argv: URL [desktop|mobile]"""
import sys, json, re, csv, io, os
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8097/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
BASE = URL.split('#')[0].split('?')[0]
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
HEAD = ['First Name', 'Last Name'] + [f'Phone {k}' for k in range(1, 11)] + ['Email', 'Property Address', 'Property City', 'Property State', 'Property Zip',
        'Mailing Address', 'Mailing City', 'Mailing State', 'Mailing Zip', 'APN', 'Parcel County', 'Parcel State', 'Folio', 'Company', 'Owner Name', 'County', 'Properties', 'All Folios']
nf = lambda s: re.sub(r'\W', '', s or '')
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, accept_downloads=True, service_workers='block'); pg = ctx.new_page(); pg.set_default_timeout(120000)
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    Q = '?drive=0&county=' if MOB else '?county='
    def load(county, h='hg=0'):
        pg.goto('about:blank'); pg.goto(BASE + Q + county + '#' + h, timeout=180000)
        if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(1500)
    def seed(recs): pg.evaluate(f"localStorage.setItem(PFCounty.key('pf.skip.v1'), {json.dumps(json.dumps(recs))}); PFSkip.store.reload()"); pg.wait_for_timeout(800)
    def open_sc(sel):
        pg.evaluate(f"document.querySelector({json.dumps(sel)}).click()"); pg.wait_for_selector('#scModal #scCounts'); pg.wait_for_function("!/Preparing/.test(document.getElementById('scCounts').textContent)", timeout=120000)
    def recount(): pg.wait_for_timeout(300); pg.wait_for_function("!/Preparing/.test(document.getElementById('scCounts').textContent)", timeout=120000)
    def download():
        with pg.expect_download(timeout=60000) as d: pg.click('#scGo')
        name = d.value.suggested_filename; raw = open(d.value.path(), 'rb').read().decode('utf-8')
        return name, raw, list(csv.reader(io.StringIO(raw)))
    send = lambda: json.loads(pg.evaluate("localStorage.getItem(PFCounty.key('pf.send.v1'))") or '{}')
    def pick(n, pat=r'^[A-Z]{3,} [A-Z]{3,}$'):
        return [r for r in pg.evaluate('PF.sample(400)')['rows'] if re.match(pat, r['owner'].strip()) and r['addr'].strip()][:n]

    # ---------- Miami-Dade ----------
    load('miami-dade', 'city=Homestead&type=sf&hg=0')
    ok(pg.evaluate("typeof PFSC==='object' && typeof PFSC.open==='function'"), 'smartercontact.js loaded and wired')
    ok(pg.evaluate("JSON.stringify(PFSC.HEAD)") == json.dumps(HEAD, separators=(',', ':')), 'PFSC.HEAD is the Smarter Contact header')
    for sel, src in (('#scBtn', ''), ('#svScBtn', 'saved'), ('#trScBtn', 'traced')):
        el = pg.query_selector(sel); ok(el is not None and el.get_attribute('data-scexport') == src and 'Smarter Contact' in el.text_content(), f'{sel} button present (data-scexport="{src}")')
    A, B2, C = pick(3); co = pick(1, r'^[A-Z ]+ LLC$')
    ok(len(co) == 1, 'picked an LLC owner'); L = co[0]
    seed({A['folio']: {'a': '2026-10-20', 's': 'BatchData API', 'n': '', 'p': [['3055550102', 'm', 1], ['3055550101', 'm', 4], ['3055550103', 'l', 0], ['3055550104', 'm', 8]], 'e': ['a.owner@example.com']},
          B2['folio']: {'a': '2026-10-20', 's': 'BatchData API', 'n': '', 'p': [['3055550201', 'm', 0]], 'e': []},
          C['folio']: {'a': '2026-10-20', 's': 'Import', 'n': '', 'p': [], 'e': []},
          L['folio']: {'a': '2026-10-20', 's': 'BatchData API', 'n': '', 'p': [['3055550301', 'm', 0]], 'e': []}})
    open_sc('#scBtn')
    ok(pg.input_value('#scSrc') == 'results' and not pg.is_checked('#scSent'), 'filter-panel button: current results, Include already sent off')
    cnt = pg.inner_text('#scCounts'); ok('3 owners' in cnt and 'DNC' in cnt, f'counts: 3 owners, DNC left out ("{cnt}")')
    name, raw, rows = download()
    ok(re.match(r'^smarter-contact-miami-dade-3-\d{8}\.csv$', name) is not None, f'file name {name}')
    ok(rows[0] == HEAD, f'CSV header exactly Smarter Contact columns ({len(rows[0])})'); ok('\r\n' in raw, 'CRLF line ends')
    h = rows[0]; by = {nf(r[h.index('Folio')]): r for r in rows[1:]}
    ok(sorted(by) == sorted([nf(A['folio']), nf(B2['folio']), nf(L['folio'])]), 'one row per owner with a phone; no-phone property left out')
    ra = by.get(nf(A['folio'])) or [''] * len(h)
    ok([ra[h.index(f'Phone {k}')] for k in (1, 2, 3)] == ['3055550101', '3055550103', ''], f'A: best first (active mobile, then landline), DNC + disconnected left out {ra[2:5]}')
    ok(ra[h.index('First Name')] == A['owner'].split()[0].title() and ra[h.index('Last Name')] == A['owner'].split()[-1].title(), 'A: first / last name split')
    ok(ra[h.index('Email')] == 'a.owner@example.com' and ra[h.index('Property State')] == 'FL' and ra[h.index('County')] == 'Miami-Dade' and ra[h.index('Parcel County')] == 'Miami-Dade', 'A: email, state, county')
    ok(ra[h.index('Property Address')].strip() == A['addr'].strip() and ra[h.index('APN')] == ra[h.index('Folio')], 'A: property address, APN = folio')
    rl = by.get(nf(L['folio'])) or [''] * len(h)
    ok(rl[h.index('First Name')] == 'Owner' and rl[h.index('Last Name')].upper() == L['owner'].strip() and rl[h.index('Company')].upper() == L['owner'].strip(), f'LLC: First Name Owner, entity in Last Name + Company ({rl[:2]})')
    ok(all(re.fullmatch(r'\d{10}', r[h.index('Phone 1')]) for r in rows[1:]), 'phones are 10 digits')
    # mark as sent
    pg.wait_for_selector('#expBar:not([hidden])'); ok(pg.input_value('#expTeam') == 'sc', 'Mark as sent bar preselects Smarter Contact')
    pg.click('#expMark'); pg.wait_for_timeout(1500)
    s = send().get('sent', {}); sa = next((v for k, v in s.items() if nf(k) == nf(A['folio'])), {}).get('sc')
    ok(sa and sa.get('ph') == ['3055550101', '3055550103'] and sa.get('list', '').startswith('Smarter Contact'), f'sent record keeps the exported numbers ({sa})')
    it = pg.evaluate(f'PF.SV.get({json.dumps(A["folio"])})')
    ok(it and it['acts'] and it['acts'][0]['type'] == 'text' and it['acts'][0]['outcome'] == 'Sent to list' and 'Smarter Contact' in it['acts'][0]['note'], 'outreach history: Text, Sent to list, Smarter Contact')
    # re-export
    open_sc('#scBtn'); ok(pg.is_disabled('#scGo') and 'already sent to Smarter Contact' in pg.inner_text('#scCounts'), 'second export: everything already sent, nothing to download')
    pg.check('#scSent'); recount(); ok(not pg.is_disabled('#scGo') and '3 owners' in pg.inner_text('#scCounts'), 'Include already sent brings them back')
    pg.click('#scModal [data-scclose]')
    seed({A['folio']: {'a': '2026-10-21', 's': 'BatchData API', 'n': '', 'p': [['3055550101', 'm', 4], ['3055550105', 'm', 0], ['3055550103', 'l', 0]], 'e': []},
          B2['folio']: {'a': '2026-10-20', 's': 'BatchData API', 'n': '', 'p': [['3055550201', 'm', 0]], 'e': []}})
    open_sc('#scBtn'); name, raw, rows = download()
    ok(len(rows) == 2 and rows[1][2:4] == ['3055550105', ''], f'new number on a sent owner is exported, sent ones are not ({rows[1:]})')
    pg.click('#expSkip'); pg.wait_for_timeout(300)
    # Skip traced view + saved list sources
    pg.evaluate("document.getElementById('vTraced').click()"); pg.wait_for_selector('#trbox:not([hidden])'); pg.wait_for_timeout(1000)
    ok('Smarter Contact · Sent' in pg.inner_text(f'[data-trow="{A["folio"]}"]'), 'Skip traced row shows Smarter Contact · Sent')
    open_sc('#trScBtn'); ok(pg.input_value('#scSrc') == 'traced', 'Skip traced button exports the traced view')
    pg.check('#scSent'); recount(); ok('2 owners' in pg.inner_text('#scCounts'), 'traced view: 2 owners with phones')
    opts = pg.eval_on_selector_all('#scSrc option', 'e=>e.map(x=>x.value)'); ok(set(opts) == {'results', 'saved', 'traced'}, f'source choices {opts}')
    pg.select_option('#scSrc', 'saved'); recount(); ok('owner' in pg.inner_text('#scCounts') and not pg.is_disabled('#scGo'), f'saved list source (outreach-logged properties): {pg.inner_text("#scCounts")}')
    pg.click('#scModal [data-scclose]'); pg.evaluate("document.getElementById('vCards').click()"); pg.wait_for_timeout(500)
    seed({})

    # ---------- other counties: own store, own header values, never mixed ----------
    for cid, cname, area in (('broward', 'Broward', '954'), ('monroe', 'Monroe', '305')):
        load(cid)
        ok(pg.query_selector('#scBtn') is not None and pg.query_selector('#trScBtn') is not None, f'{cname}: buttons present')
        S = pick(1) or [r for r in pg.evaluate('PF.sample(80)')['rows'] if r['addr'].strip()][:1]
        f = S[0]['folio']; seed({f: {'a': '2026-10-20', 's': 'x', 'n': 'Pat Doe', 'p': [[area + '5550111', 'm', 0], [area + '5550112', 'm', 1]], 'e': []}})
        pg.evaluate("document.getElementById('vTraced').click()"); pg.wait_for_selector('#trbox:not([hidden])'); pg.wait_for_timeout(800)
        open_sc('#trScBtn'); name, raw, rows = download()
        ok(name.startswith(f'smarter-contact-{cid}-1-') and rows[0] == HEAD and len(rows) == 2, f'{cname}: file {name}, header, 1 row')
        r = rows[1] if len(rows) > 1 else [''] * len(HEAD)
        ok(r[2:4] == [area + '5550111', ''] and r[HEAD.index('County')] == cname and r[HEAD.index('Property State')] == 'FL' and nf(r[HEAD.index('Folio')]) == nf(f), f'{cname}: phone (DNC one left out), county, state, folio {r[2:4]} {r[HEAD.index("County")]}')
        pg.click('#expSkip'); seed({}); pg.evaluate("document.getElementById('vCards').click()"); pg.wait_for_timeout(300)
    # Puerto Rico (when built in this tree)
    if pg.evaluate("PFCounty.list.some(c=>c.id==='pr')") and os.path.isdir('data/pr'):
        load('pr'); ok(pg.evaluate("PFCounty.id") == 'pr', 'Puerto Rico loaded')
        SR = pg.evaluate('PF.sample(80)')['rows']; S = ([r for r in SR if r['addr'].strip()] or SR)[:1]
        ok(len(S) == 1, 'Puerto Rico: picked a parcel')
        if S:
            f = nf(S[0]['folio']); seed({f: {'a': '2026-10-20', 's': 'x', 'n': '', 'p': [['7875550111', 'm', 0]], 'e': []}})   # skip store keys are folio digits
            pg.evaluate("document.getElementById('vTraced').click()"); pg.wait_for_selector('#trbox:not([hidden])'); pg.wait_for_timeout(800)
            open_sc('#trScBtn'); name, raw, rows = download()
            ok(rows[0] == HEAD + ['Barrio'] and len(rows) == 2 and rows[1][HEAD.index('Property State')] == 'PR' and rows[1][0] == 'Owner' and rows[1][2] == '7875550111', f'Puerto Rico: Barrio last, state PR, Owner, 787 number ({name})')
            pg.click('#expSkip'); seed({})
    else: print(f'SKIP [{TAG}] Puerto Rico not built in this tree', flush=True)
    b.close()
print(('ALL PASS' if not errs else 'FAILED: ' + '; '.join(errs[:6])) + f' [{TAG}]', flush=True)
sys.exit(1 if errs else 0)
