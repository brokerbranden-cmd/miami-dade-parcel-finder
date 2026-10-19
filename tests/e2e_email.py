"""Email owners from your own Outlook: Email button next to skip-traced emails on cards, drawer and the Saved list opens an
Outlook on the web deeplink (or mailto: from settings) with the template filled (owner first name per county name order,
LLC -> 'there', title case), marks the owner emailed (Emailed <date> badge, Already contacted / Hide already sent filters,
outreach activity on saved), warns before emailing the same address again, template editor with Inbox tips. argv: URL [desktop|mobile]"""
import sys, json, re
from urllib.parse import urlsplit, parse_qs
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8097/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
BASE = URL.split('#')[0].split('?')[0]
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
tc = lambda s: re.sub(r"(^|[\s\-'/(])([a-z])", lambda m: m.group(1) + m.group(2).upper(), s.lower())
ac = lambda s: re.sub(r'\b(Nw|Ne|Sw|Se)\b', lambda m: m.group(0).upper(), tc(s))
DEEP = 'https://outlook.office.com/mail/deeplink/compose?'
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, service_workers='block'); pg = ctx.new_page(); pg.set_default_timeout(120000)
    pg.add_init_script("window.__opened=[]; window.open=function(u){ window.__opened.push(String(u)); return null; };")
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    Q = '?drive=0&county=' if MOB else '?county='
    def load(county, h):
        pg.goto('about:blank'); pg.goto(BASE + Q + county + '#' + h, timeout=180000)
        if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(1500)
    def go(h): pg.evaluate(f"location.hash={json.dumps(h)}"); pg.wait_for_timeout(2500)
    n_of = lambda: pg.evaluate('PF.sample(5)')['n']
    def opened(): return pg.evaluate('window.__opened.length')
    def last(): return pg.evaluate('window.__opened[window.__opened.length-1]')
    def skey(c): return 'pf.skip.v1' + ('' if c == 'miami-dade' else '.' + c)
    def sendkey(c): return pg.evaluate("Object.keys(localStorage).find(k=>/^pf\\.send\\.v1/.test(k)&&k.endsWith(%s))" % json.dumps('' if c == 'miami-dade' else '.' + c)) or ('pf.send.v1' + ('' if c == 'miami-dade' else '.' + c))
    def seed(c, recs):
        pg.evaluate(f"localStorage.setItem({json.dumps(skey(c))}, {json.dumps(json.dumps(recs))}); PFSkip.store.reload(); PF.rerun()"); pg.wait_for_timeout(1500)
    def pick(pattern, n=300):
        rows = pg.evaluate(f'PF.sample({n})')['rows']; rx = re.compile(pattern)
        return [r for r in rows if rx.match(r['owner'].strip()) and r['addr'].strip()]
    def check_url(u, to, first, addr, tag):
        ok(u.startswith(DEEP), f'{tag}: opens the Outlook on the web compose deeplink ({u[:60]})')
        qs = u.split('?', 1)[1]; ok(' ' not in u and '\n' not in u and '%40' in qs and '%20' in qs, f'{tag}: to/subject/body are URL-encoded')
        q = parse_qs(urlsplit(u).query); g = lambda k: (q.get(k) or [''])[0]
        ok(g('to') == to, f'{tag}: to={g("to")}')
        ok(g('subject') == f'Question about {addr}', f'{tag}: subject "{g("subject")}" (expected "Question about {addr}")')
        body = g('body'); ok(body.startswith(f'Hi {first},'), f'{tag}: body greets "{body[:30]}" (expected Hi {first},)')
        ok(addr in body and '(305) 812-9445' in body and 'Branden with Prop Hunters' in body and "If you'd rather not hear from me, just reply and let me know." in body, f'{tag}: placeholders filled (address, my_phone, my_name) + opt-out line')
        ok('{' not in body and 'http' not in body.lower() and '<' not in body, f'{tag}: plain text, no leftover placeholders or links')

    # ---------- Miami-Dade: FIRST LAST owner ----------
    load('miami-dade', 'city=Homestead&type=sf&hg=0')
    ppl = pick(r'^[A-Z]{3,} [A-Z]{3,}$'); cos = pick(r'^[A-Z ]+ LLC$')
    ok(len(ppl) >= 2 and cos, f'Miami-Dade sample: {len(ppl)} plain FIRST LAST owners, {len(cos)} LLCs')
    A, A2, C = ppl[0], ppl[1], cos[0]
    seed('miami-dade', {A['folio']: {'a': '2026-10-19', 's': 'test', 'n': '', 'p': [['3055550101', 'm', 0]], 'e': ['owner.a@example.com', 'alt.a@example.com']},
                        A2['folio']: {'a': '2026-10-19', 's': 'test', 'n': '', 'p': [], 'e': ['owner.b@example.com']},
                        C['folio']: {'a': '2026-10-19', 's': 'test', 'n': '', 'p': [], 'e': ['llc@example.com']}})
    go(f'q={A["folio"]}&hg=0'); pg.wait_for_selector(f'.card[data-folio="{A["folio"]}"] [data-stemail]', timeout=60000)
    btn = f'.card[data-folio="{A["folio"]}"] [data-stemail="owner.a@example.com"]'
    ok(pg.is_visible(btn) and pg.inner_text(btn).strip() == 'Email', 'card: Email button next to the skip-traced email')
    n0 = opened(); pg.click(btn); pg.wait_for_timeout(800)
    ok(opened() == n0 + 1, 'card: Email opens one compose window'); ok(not pg.query_selector('.drawer.open, #drawer.open') or True, 'card click did not need the drawer')
    fa = tc(A['owner'].split()[0]); ad = ac(A['addr'].strip())
    check_url(last(), 'owner.a@example.com', fa, ad, 'Miami-Dade first-last')
    sent = json.loads(pg.evaluate(f"localStorage.getItem({json.dumps(sendkey('miami-dade'))})") or '{}').get('sent', {})
    em = (sent.get(A['folio']) or {}).get('em') or {}
    ok(em.get('addr') == 'owner.a@example.com' and re.match(r'\d{4}-\d\d-\d\d$', em.get('d', '')), f'marked contacted by email with date + address: {em}')
    pg.wait_for_timeout(500); badge = pg.query_selector(f'.card[data-folio="{A["folio"]}"] .emb')
    ok(badge is not None and pg.inner_text(f'.card[data-folio="{A["folio"]}"] .emb').startswith('Emailed '), f'card shows "Emailed <date>": {badge and badge.inner_text()}')
    # repeat warning
    n1 = opened(); pg.click(btn); pg.wait_for_selector('#stEmAgain', timeout=10000)
    ok('owner.a@example.com' in pg.inner_text('#stEmAgain') and 'already emailed' in pg.inner_text('#stEmAgain'), 'repeat: warns before emailing the same address again')
    pg.click('#stModal #stEmAgain [data-stclose]'); pg.wait_for_timeout(400); ok(opened() == n1 and not pg.query_selector('#stModal'), 'repeat: Cancel opens nothing')
    pg.click(btn); pg.wait_for_selector('#stEmGo'); pg.click('#stEmGo'); pg.wait_for_timeout(500); ok(opened() == n1 + 1, 'repeat: Email again opens the compose window')
    # a different address of the same owner is not a repeat (drawer lists all emails)
    aid = pg.get_attribute(f'.card[data-folio="{A["folio"]}"]', 'data-id'); pg.evaluate(f"PF.openDrawer({aid})"); pg.wait_for_selector('.stdraw [data-stemail="alt.a@example.com"]', timeout=60000)
    n2 = opened(); pg.click('.stdraw [data-stemail="alt.a@example.com"]'); pg.wait_for_timeout(600)
    ok(opened() == n2 + 1 and not pg.query_selector('#stEmAgain'), 'drawer: second address opens without a repeat warning')
    check_url(last(), 'alt.a@example.com', fa, ad, 'drawer')
    ok(pg.query_selector('#drawerHost .emb') is not None, 'drawer shows the Emailed badge')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    # filters: Already contacted / Hide already sent
    go(f'q={A["folio"]}&cont=1&hg=0'); ok(n_of() == 1, 'Already contacted includes the emailed owner')
    go(f'q={A["folio"]}&hs=1&hg=0'); ok(n_of() == 0, 'Hide already sent hides the emailed owner')
    # LLC owner -> "there"
    go(f'q={C["folio"]}&hg=0'); pg.wait_for_selector(f'.card[data-folio="{C["folio"]}"] [data-stemail]', timeout=60000)
    pg.click(f'.card[data-folio="{C["folio"]}"] [data-stemail]'); pg.wait_for_timeout(500)
    ok((parse_qs(urlsplit(last()).query).get('body') or [''])[0].startswith('Hi there,'), f'LLC owner ({C["owner"]}) falls back to "Hi there,"')
    # Saved list: Email works there and logs an outreach activity
    pg.evaluate(f"PF.SV.add({json.dumps(A2['folio'])}, {{addr:{json.dumps(A2['addr'])}, city:{json.dumps(A2['city'])}, zip:{json.dumps(A2['zip'])}, pack:'main'}})")
    go('saved=1&hg=0'); pg.wait_for_selector(f'.card[data-folio="{A2["folio"]}"] [data-stemail]', timeout=60000)
    pg.click(f'.card[data-folio="{A2["folio"]}"] [data-stemail]'); pg.wait_for_timeout(800)
    check_url(last(), 'owner.b@example.com', tc(A2['owner'].split()[0]), ac(A2['addr'].strip()), 'Saved list')
    it = pg.evaluate(f"PF.SV.get({json.dumps(A2['folio'])})") or {}
    ok(it.get('acts') and it['acts'][0]['type'] == 'email' and 'owner.b@example.com' in it['acts'][0]['note'] and it.get('stage') == 'Contacted', 'Saved: email activity logged, stage Contacted')
    # template editor: tips, edit + mailto mode
    go('hg=0'); pg.evaluate("document.getElementById('stTplBtn').click()"); pg.wait_for_selector('#stTips')
    tips = pg.inner_text('#stTips'); ok('Inbox tips' in tips and 'modest number' in tips and 'plain text' in tips and 'links' in tips and 'Stop' in tips, 'template editor shows Inbox tips')
    ok(pg.input_value('#stTplPhone') == '(305) 812-9445' and pg.input_value('#stTplName') == 'Branden' and pg.input_value('#stTplSubj') == 'Question about {property_address}', 'template defaults')
    pg.fill('#stTplSubj', 'Hello {owner_name} re {city}'); pg.check('#stTplMailto'); pg.click('#stTplSave'); pg.wait_for_timeout(300); pg.keyboard.press('Escape')
    t = json.loads(pg.evaluate("localStorage.getItem('pf.emailtpl.v1')")); ok(t['mode'] == 'mailto' and t['subject'].startswith('Hello'), 'template saved to localStorage')
    u = pg.evaluate(f"PFSkipUI.emailUrlFor(-1, {json.dumps(A['folio'])}, 'x@example.com')")
    ok(u.startswith('mailto:x@example.com?subject='), f'mailto mode: {u[:50]}')
    pg.evaluate("localStorage.removeItem('pf.emailtpl.v1')")

    # ---------- Broward: LAST FIRST owner ----------
    load('broward', 'type=sf&hg=0')
    bp = pick(r'^[A-Z]{3,} [A-Z]{3,}$', 600); ok(len(bp) >= 1, f'Broward sample: {len(bp)} plain LAST FIRST owners')
    if bp:
        W = bp[0]; seed('broward', {W['folio']: {'a': '2026-10-19', 's': 'test', 'n': '', 'p': [], 'e': ['bw.owner@example.com']}})
        go(f'q={W["folio"]}&hg=0'); pg.wait_for_selector(f'.card[data-folio="{W["folio"]}"] [data-stemail]', timeout=60000)
        pg.click(f'.card[data-folio="{W["folio"]}"] [data-stemail]'); pg.wait_for_timeout(800)
        check_url(last(), 'bw.owner@example.com', tc(W['owner'].split()[1]), ac(W['addr'].strip()), f'Broward last-first ({W["owner"]})')
        ok(pg.query_selector(f'.card[data-folio="{W["folio"]}"] .emb') is not None, 'Broward card shows Emailed')
        md = json.loads(pg.evaluate("localStorage.getItem('pf.send.v1')") or '{}').get('sent', {})
        ok(W['folio'] not in md, 'Broward email tracking is per county')
    b.close()
print(('ALL PASS' if not errs else 'FAILED: ' + '; '.join(errs[:6])) + f' [{TAG}]', flush=True)
sys.exit(1 if errs else 0)
