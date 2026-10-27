"""One-click skip trace through BatchData (Cloudflare Worker MOCKED, no network, no credits): access code prompt + validation, plan counts
(dedupe, exclusions, daily cap), chunking + progress + cancel, summary, results in the per-county skip store (same shape as CSV import), Has phone filter,
Text list excludes DNC, per-card and per-drawer 'Skip trace' button with results appearing immediately, no-match / error / daily cap handling,
reload persistence, Monroe separation, no secrets in the page. argv: URL [desktop|mobile]"""
import sys, json, re, csv, io, time
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
BASE = URL.split('#')[0].split('?')[0]
CODE = 'TEST-ACCESS-CODE'; errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
# ---- mocked Worker ----
M = {'calls': [], 'status_calls': 0, 'remaining': 500, 'cap': 500, 'force': {}, 'delay': 0, 'fail_after': None, 'bad_code_status': False, 'n_post': 0}
def result_for(it):
    f = it['id']
    if f in M['force']: return dict(M['force'][f], id=f)
    dg = re.sub(r'\D', '', f); d = sum(map(int, dg)) % 6; n = int(dg[-4:] or 0)
    if d == 0: return {'id': f, 'status': 'nomatch'}
    if d == 1: return {'id': f, 'status': 'error', 'error': 'provider_error'}
    if d == 2: return {'id': f, 'status': 'match', 'name': 'Test Owner', 'phones': [['30555%05d' % (n % 100000 + 10000), 'm', 1], ['78655%05d' % (n % 100000 + 20000), 'l', 0]], 'emails': []}
    return {'id': f, 'status': 'match', 'name': 'Test Owner', 'phones': [['30555%05d' % (n % 100000 + 30000), 'm', 0], ['78655%05d' % (n % 100000 + 40000), 'l', 0]], 'emails': ['o%d@example.com' % n]}
CORS = {'access-control-allow-origin': '*', 'access-control-allow-headers': 'content-type, x-access-code', 'access-control-allow-methods': 'GET, POST, OPTIONS'}
def handler(route):
    r = route.request; u = r.url
    if r.method == 'OPTIONS': return route.fulfill(status=204, headers=CORS)
    code = r.headers.get('x-access-code', '')
    jf = lambda o, s=200: route.fulfill(status=s, headers={**CORS, 'content-type': 'application/json'}, body=json.dumps(o))
    if code != CODE: return jf({'error': 'bad_access_code'}, 401)
    if u.endswith('/status'):
        M['status_calls'] += 1; return jf({'ok': True, 'dailyCap': M['cap'], 'usedToday': M['cap'] - M['remaining'], 'remainingToday': M['remaining'], 'maxPerRequest': 50})
    body = r.post_data_json; items = body['items']; M['calls'].append(items); M['n_post'] += 1
    if M['fail_after'] is not None and M['n_post'] > M['fail_after']: return jf({'error': 'daily_cap', 'remainingToday': 0}, 429)
    if M['delay']: pg.wait_for_timeout(int(M['delay'] * 1000))
    res = [result_for(i) for i in items]; M['remaining'] -= sum(1 for x in res if x['status'] in ('match', 'nocontact'))
    jf({'ok': True, 'results': res, 'meta': {'sent': len(items)}, 'remainingToday': M['remaining'], 'dailyCap': M['cap']})
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, accept_downloads=True, service_workers='block'); pg = ctx.new_page(); pg.set_default_timeout(120000)
    ctx.route(re.compile(r'https://parcel-skiptrace\.brokerbranden\.workers\.dev/.*'), handler)
    pg.add_init_script("try{ if(!localStorage.getItem('pf.ui.v1')) localStorage.setItem('pf.ui.v1', JSON.stringify({legacy:true})); }catch(e){}")
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    downloads = []; pg.on('download', lambda d: downloads.append(d))
    Q = '?drive=0&county=' if MOB else '?county='
    def load(county='miami-dade', h='hg=0'):
        pg.goto('about:blank'); pg.goto(BASE + Q + county + '#' + h, timeout=180000)
        if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(1200)
    def go(h): pg.evaluate(f"location.hash={json.dumps(h)}"); pg.wait_for_timeout(2500)
    n_of = lambda: pg.evaluate('PF.sample(5)')['n']
    def jsclick(sel): pg.evaluate(f"document.querySelector({json.dumps(sel)}).click()")
    def skey(county='miami-dade'): return 'pf.skip.v1' + ('' if county == 'miami-dade' else '.' + county)
    def store(county='miami-dade'): return json.loads(pg.evaluate(f"localStorage.getItem({json.dumps(skey(county))})") or '{}')
    def close_modal():
        if pg.query_selector('#stModal'): pg.evaluate("document.querySelector('#stModal [data-stclose]').click()"); pg.wait_for_timeout(300)
    def setmax(v):
        pg.fill('#skaMax', str(v)); pg.wait_for_function("(v)=>{const b=document.querySelector('#skaGo'); return b && !b.disabled && b.textContent.startsWith('Skip trace '+v+' ');}", arg=v, timeout=120000)
    def open_bulk():
        jsclick('#stApiBtn'); pg.wait_for_selector('#skaCounts b, #skCode', timeout=120000)
    digits = lambda s: re.sub(r'\D', '', s)

    load('miami-dade', 'city=Homestead&q=SW 2&hg=0')
    ok(pg.evaluate("localStorage.getItem('pf.skapi.code.v1')") is None, 'fresh browser: no access code stored')
    ok(pg.is_visible('#stApiBtn') and 'Skip trace these' in pg.inner_text('#stApiBtn'), "panel has the 'Skip trace these' button")
    pg.wait_for_selector('#cards .card'); N = n_of()
    ok(len(pg.query_selector_all('#cards .card [data-stgo]')) > 0, "every card has its own 'Skip trace' button")
    ok(pg.evaluate("document.querySelector('#cards [data-stgo]').getBoundingClientRect().height") >= 28, 'card button is tap sized')

    # ---------- access code prompt ----------
    jsclick('#stApiBtn'); pg.wait_for_selector('#skCode'); ok('access code' in pg.inner_text('#stModal').lower(), 'first use asks for the access code')
    pg.fill('#skCode', 'WRONG'); jsclick('#skCodeGo'); pg.wait_for_selector('#skCodeMsg:not([hidden])'); ok('not accepted' in pg.inner_text('#skCodeMsg'), 'wrong code rejected with a message')
    ok(pg.evaluate("localStorage.getItem('pf.skapi.code.v1')") is None, 'wrong code is not stored')
    pg.fill('#skCode', CODE); pg.keyboard.press('Enter'); pg.wait_for_selector('#skaCounts b', timeout=120000)
    ok(pg.evaluate("localStorage.getItem('pf.skapi.code.v1')") == CODE, 'right code stored on this device (localStorage)')
    ok('check your BatchData pricing' in pg.inner_text('#skaCost'), 'cost line says to check BatchData pricing (no invented price)')
    ok(re.search(r'500\s+of\s+500\s+left', pg.inner_text('#skaCost')) is not None, 'daily limit shown (500 of 500 left)')
    cnt = pg.inner_text('#skaCounts'); lookups = int(re.search(r'([\d,]+)\s+lookups?', cnt).group(1).replace(',', ''))
    ok(lookups >= 1 and lookups <= N, f'plan: {lookups} lookups for {N} properties (one per owner)')
    ok(pg.is_checked('#skaDedupe') and pg.is_checked('#skaTraced') and pg.is_checked('#skaContacted'), 'dedupe / skip traced / skip contacted are on by default')

    # ---------- run 8 lookups ----------
    take = min(8, lookups); setmax(take); M['calls'].clear(); jsclick('#skaGo')
    pg.wait_for_selector('#skaReport', timeout=180000)
    items = [i for c in M['calls'] for i in c]
    ok(len(items) == take and len(M['calls']) == 1, f'{len(items)} items in {len(M["calls"])} request(s)')
    it0 = items[0]; ok(set(it0.keys()) >= {'id', 'first', 'last', 'company', 'street', 'city', 'state', 'zip', 'mailStreet', 'mailCity', 'mailState', 'mailZip'} and it0['state'] == 'FL' and it0['street'], f'request item has name / address / mailing fields')
    ok(len({i['id'] for i in items}) == len(items), 'one lookup per owner (unique ids)')
    exp = [result_for(i) for i in items]; M['remaining'] = 500 - sum(1 for x in exp if x['status'] in ('match', 'nocontact'))
    e_ph = {q[0] for x in exp if x['status'] == 'match' for q in x['phones']}; e_em = {e for x in exp if x['status'] == 'match' for e in x['emails']}; e_dnc = {q[0] for x in exp if x['status'] == 'match' for q in x['phones'] if q[2]}
    e_nm = sum(1 for x in exp if x['status'] == 'nomatch'); e_er = sum(1 for x in exp if x['status'] == 'error'); e_f = sum(1 for x in exp if x['status'] == 'match')
    rep = {k: pg.inner_text('#' + k) for k in ('skrFound', 'skrPhones', 'skrEmails', 'skrDnc', 'skrNoMatch', 'skrErr', 'skrProps')}
    ok(int(rep['skrFound']) == e_f and rep['skrPhones'].startswith(str(len(e_ph))) and int(rep['skrEmails']) == len(e_em) and int(rep['skrDnc']) == len(e_dnc) and int(rep['skrNoMatch']) == e_nm and int(rep['skrErr']) == e_er, f'summary matches results {rep}')
    S = store(); folios_done = {k for k in S}
    ok(len(S) >= take - e_er and pg.evaluate("localStorage.getItem('pf.skip.v1.monroe')") is None, f'{len(S)} properties written to the Miami-Dade store only')
    anyp = next(v for v in S.values() if v['p']); ok(re.fullmatch(r'\d{10}', anyp['p'][0][0]) and anyp['p'][0][1] in 'mlv' and anyp['s'] == 'BatchData API' and re.fullmatch(r'\d{4}-\d\d-\d\d', anyp['a']), f"store record has the CSV-import shape {anyp['p'][0]} {anyp['s']}")
    ok(any(q[2] == 1 for v in S.values() for q in v['p']) == bool(e_dnc), 'DNC flag stored (1)')
    ok(any((not v['p']) and (not v['e']) for v in S.values()) == (e_nm > 0), 'no-match owners stored as traced with nothing found')
    errf = [i['id'] for i, x in zip(items, exp) if x['status'] == 'error']; ok(all(f not in S for f in errf), 'error rows are not saved (can be retried)')
    jsclick('#skaShow'); pg.wait_for_timeout(2500)
    ok('ph=1' in pg.evaluate('location.hash') and n_of() >= 1, f'Show properties with phones -> {n_of()}'); ok(pg.evaluate("document.getElementById('stInfo').textContent").startswith(str(len(S))), 'panel info updated')
    # Text list excludes DNC + landline numbers
    jsclick('#stTextBtn'); pg.wait_for_selector('#sttCounts b', timeout=120000)
    with pg.expect_download(timeout=120000) as d: jsclick('#sttGo')
    txt = open(d.value.path(), encoding='utf-8').read(); ok(len(e_dnc) == 0 or not any(p in txt for p in e_dnc), 'Text list leaves DNC numbers out'); ok('78655' not in txt, 'Text list leaves landlines out')
    pg.wait_for_timeout(500); close_modal()

    # ---------- second run excludes the already traced ----------
    go('city=Homestead&q=SW 2&hg=0'); M['calls'].clear(); open_bulk(); t1 = pg.inner_text('#skaCounts')
    ok(re.search(r'([\d,]+)\s+already skip traced', t1) is not None and int(re.search(r'([\d,]+)\s+already skip traced', t1).group(1).replace(',', '')) >= take - e_er, 'second plan leaves out already skip traced: ' + t1.split('\n')[-1])
    pg.evaluate("(()=>{const c=document.getElementById('skaTraced'); c.checked=false; c.dispatchEvent(new Event('change',{bubbles:true}));})()"); pg.wait_for_timeout(1500)
    pg.wait_for_function("!document.querySelector('#skaGo').disabled"); t2 = int(re.search(r'([\d,]+)\s+lookups?', pg.inner_text('#skaCounts')).group(1).replace(',', ''))
    ok(t2 > int(re.search(r'([\d,]+)\s+lookups?', t1).group(1).replace(',', '')) or lookups <= take, f'unchecking skip traced brings them back ({t2})')
    close_modal()

    # ---------- chunking, progress, cancel ----------
    load('miami-dade', 'hg=0&q=SW'); M['calls'].clear(); M['delay'] = 1.2; open_bulk()
    big = int(re.search(r'([\d,]+)\s+lookups?', pg.inner_text('#skaCounts')).group(1).replace(',', '')); ok(big >= 120, f'broad filter has {big} lookups')
    setmax(120); pg.click('#skaGo'); ok('Yes, skip trace' in pg.inner_text('#skaGo'), 'more than 25 lookups needs a second confirming click')
    pg.click('#skaGo'); pg.wait_for_function("document.querySelector('#skaProgTxt') && /\\d+ of 120 done/.test(document.querySelector('#skaProgTxt').textContent) && !/^0 of/.test(document.querySelector('#skaProgTxt').textContent)", timeout=120000)
    ok(pg.is_visible('#skaProg'), 'progress bar shown'); pg.click('#skaCancel'); pg.wait_for_selector('#skaReport', timeout=180000); M['delay'] = 0
    ok(1 <= len(M['calls']) < 3 and all(len(c) <= 50 for c in M['calls']), f'cancel stopped further chunks ({len(M["calls"])} request(s) of {[len(c) for c in M["calls"]]})')
    ok('Cancelled' in pg.inner_text('#skaReport') and len(store()) > len(folios_done), 'cancelled report; finished batch kept in the store')
    close_modal()

    # ---------- daily cap ----------
    pg.wait_for_timeout(3000); M['remaining'] = 3; load('miami-dade', 'hg=0&q=SW'); open_bulk(); ok(re.search(r'\b3\s+of\s+500', pg.inner_text('#skaCost')) is not None, 'low remaining shown')
    ok(int(re.search(r'([\d,]+)\s+lookups?', pg.inner_text('#skaCounts')).group(1)) == 3 and not pg.is_hidden('#skaWarn'), 'plan is cut to the daily limit with a warning')
    close_modal(); M['remaining'] = 500; M['fail_after'] = 1; M['n_post'] = 0; load('miami-dade', 'hg=0&q=SW'); open_bulk(); setmax(120); pg.click('#skaGo'); pg.click('#skaGo'); pg.wait_for_selector('#skaReport', timeout=180000)
    ok('limit' in pg.inner_text('#skaReport').lower() and 'Stopped' in pg.inner_text('#skaReport'), 'server daily cap mid-run: run stops, earlier batch saved'); close_modal(); M['fail_after'] = None

    # ---------- bad stored code -> re-prompt ----------
    pg.evaluate("localStorage.setItem('pf.skapi.code.v1','OLD')"); load('miami-dade', 'city=Homestead&q=SW 2&hg=0'); jsclick('#stApiBtn'); pg.wait_for_selector('#skCode')
    ok('not accepted' in pg.inner_text('#stModal').lower() and pg.evaluate("localStorage.getItem('pf.skapi.code.v1')") is None, 'a no-longer-valid saved code is dropped and asked for again'); close_modal()
    pg.evaluate(f"localStorage.setItem('pf.skapi.code.v1','{CODE}')")

    # ---------- single property: card button ----------
    load('miami-dade', 'city=Homestead&q=SW 2&hg=0&ph=0'); pg.wait_for_selector('#cards .card')
    cards = pg.evaluate("[...document.querySelectorAll('#cards .card')].filter(c=>c.querySelector('[data-stgo]')).slice(0,6).map(c=>c.dataset.folio)")
    ok(len(cards) >= 3, f'{len(cards)} untraced cards visible')
    fA, fB, fC = cards[0], cards[1], cards[2]
    M['force'][fA] = {'status': 'match', 'name': 'Ana Perez', 'phones': [['3055559001', 'm', 0], ['3055559002', 'm', 1]], 'emails': ['ana@example.com']}
    M['force'][fB] = {'status': 'nomatch'}; M['force'][fC] = {'status': 'error', 'error': 'provider_error'}
    M['calls'].clear(); sc = pg.evaluate("window.scrollY"); pg.evaluate(f"document.querySelector('#cards .card[data-folio=\"{fA}\"] [data-stgo]').click()")
    pg.wait_for_selector(f'#cards .card[data-folio="{fA}"] a[href="tel:+13055559001"]', timeout=60000)
    ok(len(M['calls']) == 1 and len(M['calls'][0]) == 1 and M['calls'][0][0]['id'] == fA, 'one click sent exactly one record (no prompt: code already saved)')
    ok(pg.evaluate("document.getElementById('drawerHost').children.length") == 0, 'clicking the button does not open the drawer')
    cardA = f'#cards .card[data-folio="{fA}"]'
    ok(pg.query_selector(f'{cardA} a[href^="sms:+13055559001?&body="]') is not None and pg.query_selector(f'{cardA} [data-stgo]') is None, 'phone appears on the card at once with Call + Text links; button gone')
    ok(pg.query_selector(f'{cardA} .dncb') is None and 'DNC' not in pg.inner_text(cardA) and pg.query_selector(f'{cardA} a[href="tel:+13055559002"]') is not None and pg.query_selector(f'{cardA} a[href^="sms:+13055559002?&body="]') is not None, 'DNC number shows plain with Call + Text, no badge')
    ok('ana@example.com' in pg.inner_text(cardA) and pg.query_selector(f'{cardA} a[href="mailto:ana@example.com"]') is not None, 'email shown as a mailto link')
    ok(store()[fA]['p'][0][:2] == ['3055559001', 'm'] and store()[fA]['s'] == 'BatchData API', 'saved in the county store')
    one = pg.evaluate('window.PF_LAST_SKAPI_ONE'); ok(one and one['folio'] == fA and one['phones'] == 2 and one['emails'] == 1 and one['dnc'] == 1, f'single-run summary (found 2 phones, 1 email, 1 DNC) {one}')
    # no match
    pg.evaluate(f"document.querySelector('#cards .card[data-folio=\"{fB}\"] [data-stgo]').click()"); pg.wait_for_function(f"document.querySelector('#cards .card[data-folio=\"{fB}\"] .stnone')", timeout=60000)
    ok('no phone found' in pg.inner_text(f'#cards .card[data-folio="{fB}"]').lower() and fB in store(), 'no match: card says traced, no phone found (and will not be run again by default)')
    # error: stays untraced, message shown, button usable again
    pg.evaluate(f"document.querySelector('#cards .card[data-folio=\"{fC}\"] [data-stgo]').click()"); pg.wait_for_function(f"(()=>{{const b=document.querySelector('#cards .card[data-folio=\"{fC}\"] [data-stgo]'); return b && !b.disabled && b.textContent.trim()==='Skip trace';}})()", timeout=60000)
    ok(fC not in store(), 'error: not saved, button available to retry')
    # reload: results persist
    load('miami-dade', 'city=Homestead&q=SW 2&hg=0&ph=1'); pg.wait_for_selector(f'#cards .card[data-folio="{fA}"] a[href="tel:+13055559001"]'); ok(True, 'after reload the card still shows the phone')

    # ---------- single property: drawer button ----------
    load('miami-dade', 'city=Homestead&q=SW 2&hg=0&ph=0'); pg.wait_for_selector('#cards .card')
    fD = pg.evaluate("[...document.querySelectorAll('#cards .card')].filter(c=>c.querySelector('[data-stgo]'))[0].dataset.folio")
    M['force'][fD] = {'status': 'match', 'name': 'Dee Lee', 'phones': [['3055559101', 'm', 0], ['3055559102', 'm', 2]], 'emails': []}
    pg.evaluate(f"document.querySelector('#cards .card[data-folio=\"{fD}\"]').click()"); pg.wait_for_selector('.drawer .stdraw [data-stgo]')
    ok('Skip trace this owner' in pg.inner_text('.drawer .stdraw'), "drawer has 'Skip trace this owner'"); M['calls'].clear()
    pg.evaluate("document.querySelector('.drawer .stdraw [data-stgo]').click()"); pg.wait_for_selector('.drawer .stdraw a[href="tel:+13055559101"]', timeout=60000)
    ok(len(M['calls']) == 1 and pg.query_selector('.drawer .stdraw .dncb') is None and 'Litigator' not in pg.inner_text('.drawer .stdraw'), 'drawer shows phones at once, no litigator badge')
    pg.evaluate("document.getElementById('closeD').click()"); pg.wait_for_timeout(300)
    ok(pg.query_selector(f'#cards .card[data-folio="{fD}"] a[href="tel:+13055559101"]') is not None, 'the card behind the drawer shows the phone too')

    # ---------- single trace without a code asks first, then continues ----------
    pg.evaluate("localStorage.removeItem('pf.skapi.code.v1')"); load('miami-dade', 'city=Homestead&q=SW 2&hg=0&ph=0'); pg.wait_for_selector('#cards .card')
    fE = pg.evaluate("[...document.querySelectorAll('#cards .card')].filter(c=>c.querySelector('[data-stgo]'))[0].dataset.folio"); M['force'][fE] = {'status': 'match', 'name': 'E', 'phones': [['3055559201', 'm', 0]], 'emails': []}
    pg.evaluate(f"document.querySelector('#cards .card[data-folio=\"{fE}\"] [data-stgo]').click()"); pg.wait_for_selector('#skCode'); pg.fill('#skCode', CODE); jsclick('#skCodeGo')
    pg.wait_for_selector(f'#cards .card[data-folio="{fE}"] a[href="tel:+13055559201"]', timeout=60000); ok(True, 'card button asks for the code once, then runs the lookup')

    # ---------- no secrets in the page / sources ----------
    allsrc = pg.evaluate("Promise.all(['skiptrace-api.js','skiptrace-ui.js','app.js','index.html'].map(f=>fetch(f).then(r=>r.text()))).then(a=>a.join('\\n'))")
    ok('Bearer' not in allsrc, 'no bearer token / key in the site code')
    ok('api.batchdata.com' not in allsrc, 'browser never calls BatchData directly')
    # ---------- Monroe stays separate ----------
    load('monroe', 'hg=0&city=Key West&q=College'); pg.wait_for_selector('#cards .card')
    fM = pg.evaluate("[...document.querySelectorAll('#cards .card')].filter(c=>c.querySelector('[data-stgo]'))[0].dataset.folio"); M['force'][fM] = {'status': 'match', 'name': 'Key West Owner', 'phones': [['3055559301', 'm', 0]], 'emails': []}; M['calls'].clear()
    pg.evaluate(f"document.querySelector('#cards .card[data-folio=\"{fM}\"] [data-stgo]').click()"); pg.wait_for_selector(f'#cards .card[data-folio="{fM}"] a[href="tel:+13055559301"]', timeout=60000)
    ok(M['calls'][0][0]['state'] == 'FL' and fM in store('monroe') and fM not in store(), 'Monroe result goes to the Monroe store only')
    load('miami-dade', 'city=Homestead&q=SW 2&hg=0'); ok(fM not in store() and pg.evaluate("PFSkip.store.key") == 'pf.skip.v1', 'Miami-Dade store untouched by the Monroe lookup')
    b.close()
print(f'[{TAG}] ' + ('ALL PASS' if not errs else f'{len(errs)} FAIL: ' + '; '.join(errs[:8])))
sys.exit(1 if errs else 0)
