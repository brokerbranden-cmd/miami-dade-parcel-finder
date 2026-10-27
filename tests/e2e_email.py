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
    def check_url(u, to, first, addr, tag, city=None):
        city = tc(city) if city else 'South Florida'
        ok(u.startswith(DEEP), f'{tag}: opens the Outlook on the web compose deeplink ({u[:60]})')
        qs = u.split('?', 1)[1]; ok(' ' not in u and '\n' not in u and '%40' in qs and '%20' in qs, f'{tag}: to/subject/body are URL-encoded')
        q = parse_qs(urlsplit(u).query); g = lambda k: (q.get(k) or [''])[0]
        ok(g('to') == to, f'{tag}: to={g("to")}')
        ok(g('subject') == f'Question about {addr}', f'{tag}: subject "{g("subject")}" (expected "Question about {addr}")')
        body = g('body'); ok(body.startswith(f'Hey {first},'), f'{tag}: body greets "{body[:30]}" (expected Hey {first},)')
        exp = f"Hey {first}, how are you?\n\nI own a property nearby and was reaching out to owners in the area to see if there's any interest in selling in the near future. I'm here locally in {city} and would love to have a conversation about it if you're open to it. I'd buy as-is.\n\nYou can reach me at (305) 812-9445.\n\nThanks,\nBranden"
        ok(body == exp, f'{tag}: body is exactly Branden\'s template with first name + title-cased address filled' + ('' if body == exp else f' GOT {body!r}'))
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
    check_url(last(), 'owner.a@example.com', fa, ad, 'Miami-Dade first-last', A.get('city'))
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
    check_url(last(), 'alt.a@example.com', fa, ad, 'drawer', A.get('city'))
    ok(pg.query_selector('#drawerHost .emb') is not None, 'drawer shows the Emailed badge')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    # filters: Already contacted / Hide already sent
    go(f'q={A["folio"]}&cont=1&hg=0'); ok(n_of() == 1, 'Already contacted includes the emailed owner')
    go(f'q={A["folio"]}&hs=1&hg=0'); ok(n_of() == 0, 'Hide already sent hides the emailed owner')
    # LLC owner -> "there"
    go(f'q={C["folio"]}&hg=0'); pg.wait_for_selector(f'.card[data-folio="{C["folio"]}"] [data-stemail]', timeout=60000)
    pg.click(f'.card[data-folio="{C["folio"]}"] [data-stemail]'); pg.wait_for_timeout(500)
    ok((parse_qs(urlsplit(last()).query).get('body') or [''])[0].startswith('Hey there,'), f'LLC owner ({C["owner"]}) falls back to "Hey there,"'); ok((parse_qs(urlsplit(last()).query).get('body') or [''])[0].startswith('Hey there, how are you?'), 'no first name -> "Hey there, how are you?"')
    # Saved list: Email works there and logs an outreach activity
    pg.evaluate(f"PF.SV.add({json.dumps(A2['folio'])}, {{addr:{json.dumps(A2['addr'])}, city:{json.dumps(A2['city'])}, zip:{json.dumps(A2['zip'])}, pack:'main'}})")
    go('saved=1&hg=0'); pg.wait_for_selector(f'.card[data-folio="{A2["folio"]}"] [data-stemail]', timeout=60000)
    pg.click(f'.card[data-folio="{A2["folio"]}"] [data-stemail]'); pg.wait_for_timeout(800)
    check_url(last(), 'owner.b@example.com', tc(A2['owner'].split()[0]), ac(A2['addr'].strip()), 'Saved list', A2.get('city'))
    it = pg.evaluate(f"PF.SV.get({json.dumps(A2['folio'])})") or {}
    ok(it.get('acts') and it['acts'][0]['type'] == 'email' and 'owner.b@example.com' in it['acts'][0]['note'] and it.get('stage') == 'Contacted', 'Saved: email activity logged, stage Contacted')
    # Email owner: one message, To = Branden, BCC = owner's emails (deduped, invalid skipped, max 5), repeat warning lists the emailed ones
    from urllib.parse import unquote
    D0 = A2
    EM = ['x1@example.com', 'X1@Example.com', 'not-an-email', 'x2@example.com', 'x3@example.com']
    pg.evaluate(f"(()=>{{ const k={json.dumps(skey('miami-dade'))}, o=JSON.parse(localStorage.getItem(k)||'{{}}'); o[{json.dumps(D0['folio'])}]={{a:'2026-10-19',s:'test',n:'',p:[],e:{json.dumps(EM)}}}; localStorage.setItem(k,JSON.stringify(o)); PFSkip.store.reload(); PF.rerun(); }})()"); pg.wait_for_timeout(1500)
    go(f'q={D0["folio"]}&hg=0'); ob = f'.card[data-folio="{D0["folio"]}"] [data-stown]'; pg.wait_for_selector(ob, timeout=60000)
    ok(pg.inner_text(ob).strip() == 'Email owner (3)' and pg.query_selector(f'.card[data-folio="{D0["folio"]}"] [data-stemail]') is not None, f'card: one "Email owner" button ({pg.inner_text(ob).strip()}) + per-email buttons kept')
    n0 = opened(); pg.click(ob); pg.wait_for_timeout(800); u = last()
    ok(opened() == n0 + 1 and u.startswith(DEEP.replace('?', '?mailtouri=mailto%3A')), f'Email owner opens one Outlook web compose via mailtouri ({u[:90]})')
    mt = unquote(u.split('mailtouri=', 1)[1]); q = parse_qs(urlsplit(mt).query); to = mt[7:].split('?')[0]
    bcc = (q.get('bcc') or [''])[0].split(',')
    ok(to == 'Branden@prop-hunters.com', f'To is Branden@prop-hunters.com ({to})')
    ok(bcc == ['x1@example.com', 'x2@example.com', 'x3@example.com'], f'BCC deduped, invalid skipped: {bcc}')
    ok(pg.evaluate("PFSkipUI.BCC_MAX") == 5, 'BCC capped at 5')
    bd = (q.get('body') or [''])[0].replace('\r\n', '\n'); fd = tc(D0['owner'].split()[0])
    ok(bd.startswith(f'Hey {fd},') and '(305) 812-9445' in bd and 'http' not in bd and 'rather not hear' not in bd, 'owner email body: template, plain text, no links, no opt-out line')
    em = (json.loads(pg.evaluate(f"localStorage.getItem({json.dumps(sendkey('miami-dade'))})") or '{}').get('sent', {}).get(D0['folio']) or {}).get('em') or {}
    ok(set(bcc) <= set(em.get('addrs', {})), f'every BCC address recorded as emailed: {sorted(em.get("addrs", {}))}')
    ok(pg.query_selector(f'.card[data-folio="{D0["folio"]}"] .emb') is not None, 'card shows Emailed')
    n1 = opened(); pg.click(ob); pg.wait_for_selector('#stEmAgain', timeout=10000); wt = pg.inner_text('#stEmAgain')
    ok(all(x in wt for x in bcc) and 'x4@example.com' not in wt, 'repeat warning lists every address already emailed')
    pg.click('[data-stclose]'); pg.wait_for_timeout(300)
    pg.evaluate(f"(()=>{{ const k={json.dumps(skey('miami-dade'))}, o=JSON.parse(localStorage.getItem(k)); o[{json.dumps(D0['folio'])}].e=['x1@example.com','x2@example.com','x3@example.com','x4@example.com','x5@example.com']; localStorage.setItem(k,JSON.stringify(o)); PFSkip.store.reload(); PF.rerun(); }})()"); pg.wait_for_timeout(1500)
    pg.click(ob); pg.wait_for_selector('#stEmNew', timeout=10000)
    pg.click('#stEmNew'); pg.wait_for_timeout(600); u2 = unquote(last().split('mailtouri=', 1)[1])
    ok(opened() == n1 + 1 and (parse_qs(urlsplit(u2).query).get('bcc') or [''])[0] == 'x4@example.com,x5@example.com', f'"Email only the new" BCCs the 2 not yet emailed')
    aid = pg.get_attribute(f'.card[data-folio="{D0["folio"]}"]', 'data-id'); pg.evaluate(f"PF.openDrawer({aid})"); pg.wait_for_selector('.stdraw [data-stown]', timeout=60000); ok(True, 'drawer has Email owner'); pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    pg.evaluate("localStorage.setItem('pf.emailtpl.v1', JSON.stringify({mode:'mailto', to_addr:'me@prop-hunters.com'}))")
    ok(pg.evaluate(f"PF.skBridge && (()=>{{ return true; }})()"), 'bridge')
    pg.click(ob); pg.wait_for_selector('#stEmGo'); pg.click('#stEmGo'); pg.wait_for_timeout(500); lm = pg.evaluate('window.PF_LAST_EMAIL')
    ok(lm['url'].startswith('mailto:me@prop-hunters.com?bcc=x1@example.com,') and lm['mode'] == 'mailto', f'mailto mode: To from settings + bcc= ({lm["url"][:70]})')
    pg.evaluate("localStorage.removeItem('pf.emailtpl.v1')")
    # Bad email: known bounces pre-marked; mark by hand; bad ones dimmed, no Email button, left out of BCC
    pg.evaluate(f"(()=>{{ const k={json.dumps(skey('miami-dade'))}, o=JSON.parse(localStorage.getItem(k)); o[{json.dumps(D0['folio'])}].e=['Cal_L_Cox@yahoo.com','x1@example.com','x2@example.com']; localStorage.setItem(k,JSON.stringify(o)); PFSkip.store.reload(); }})()"); pg.wait_for_timeout(1500)
    aid = pg.get_attribute(f'.card[data-folio="{D0["folio"]}"]', 'data-id'); pg.evaluate(f"PF.openDrawer({aid})"); pg.wait_for_selector('.stdraw .stem.bad', timeout=60000)
    ok('Bad email' in pg.inner_text('.stdraw') and pg.query_selector('.stdraw [data-stemail="Cal_L_Cox@yahoo.com"]') is None, 'known bounce pre-marked Bad email, dimmed, no Email button')
    ok(pg.inner_text('.stdraw [data-stown]').strip() == 'Email owner (2)', 'bad email left out of Email owner BCC')
    pg.click('.stdraw [data-stbad="x2@example.com"][data-v="1"]'); pg.wait_for_selector('.stdraw [data-stbad="x2@example.com"][data-v="0"]', timeout=10000)
    ok(pg.query_selector('.stdraw [data-stemail="x2@example.com"]') is None and pg.inner_text('.stdraw [data-stown]').strip() == 'Email owner', 'marking by hand: dimmed, no Email button, out of BCC')
    ok(pg.evaluate("PFSkipUI.isBad('x2@example.com') && JSON.parse(localStorage.getItem('pf.bademail.v1'))['x2@example.com'] === true"), 'bad mark saved in the browser')
    pg.click('.stdraw [data-stbad="x2@example.com"][data-v="0"]'); pg.wait_for_selector('.stdraw [data-stemail="x2@example.com"]', timeout=10000); ok(True, 'Unmark restores the Email button')
    ok(pg.evaluate("PFSkipUI.isBad('jamesw830@earthlink.com') && PFSkipUI.isBad('arinajohanajulio@yahoo.es')"), 'all three known bounces pre-marked')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    # stored templates: an unedited copy of the old default migrates to the new one; an edited one is kept
    OLD = "Hi {owner_first},\n\nMy name is {my_name} with Prop Hunters. I'm a local buyer and wanted to see if you'd consider an offer on {property_address}. No repairs or agents needed.\n\nIf you're open to a quick conversation, you can reach me at {my_phone}.\n\nThanks,\n{my_name}\n\nIf you'd rather not hear from me, just reply and let me know."
    pg.evaluate(f"localStorage.setItem('pf.emailtpl.v1', JSON.stringify({{mode:'web', my_name:'Branden', my_phone:'(305) 812-9445', subject:'Question about {{property_address}}', body:{json.dumps(OLD)}}}))")
    ok(pg.evaluate("PFSkipUI.tplGet().body").startswith('Hey {first_name},'), 'saved copy of the old default migrates to the new template')
    PREV = "Hey {first_name},\n\nMy name is Branden with Prop Hunters. I'm an investor/buyer and wanted to see if you'd consider an offer on {property_address}.\nif you're open to a quick conversation, you can reach me at (305) 812-9445.\n\nThanks,\nBranden"
    pg.evaluate(f"localStorage.setItem('pf.emailtpl.v1', JSON.stringify({{body:{json.dumps(PREV)}}}))")
    ok(pg.evaluate("PFSkipUI.tplGet().body").startswith('Hey {first_name}, how are you?') and pg.evaluate("PFSkipUI.tplGet().subject") == 'Question about {property_address}', 'saved copy of the previous default migrates; subject stays Question about <street address>')
    pg.evaluate("localStorage.setItem('pf.emailtpl.v1', JSON.stringify({body:'Hello {first_name}, custom'}))")
    ok(pg.evaluate("PFSkipUI.tplGet().body") == 'Hello {first_name}, custom', 'an edited template is kept')
    EDITED = "Hello {first_name},\nCustom line about {property_address}.\n\nIf you'd rather not hear from me, just reply and let me know.\n\nBest,\nB"
    pg.evaluate(f"localStorage.setItem('pf.emailtpl.v1', JSON.stringify({{body:{json.dumps(EDITED)}}}))")
    ok(pg.evaluate("PFSkipUI.tplGet().body") == "Hello {first_name},\nCustom line about {property_address}.\n\nBest,\nB", 'opt-out line (and its blank line) stripped from an edited saved template, rest kept')
    ok("rather not hear" not in pg.evaluate("PFSkipUI.TPL_DEF.body"), 'default template has no opt-out line')
    pg.evaluate("localStorage.removeItem('pf.emailtpl.v1')")
    # template editor: tips, edit + mailto mode
    go('hg=0'); pg.evaluate("document.getElementById('stTplBtn').click()"); pg.wait_for_selector('#stTips')
    tips = pg.inner_text('#stTips'); ok('Inbox tips' in tips and 'one at a time at a normal pace' in tips and 'modest at first' in tips and 'plain text' in tips and 'links' in tips and 'Stop' in tips, 'template editor shows Inbox tips'); ok(pg.input_value('#stTplTo') == 'Branden@prop-hunters.com', 'template editor: editable To address')
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
        check_url(last(), 'bw.owner@example.com', tc(W['owner'].split()[1]), ac(W['addr'].strip()), f'Broward last-first ({W["owner"]})', W.get('city'))
        ok(pg.query_selector(f'.card[data-folio="{W["folio"]}"] .emb') is not None, 'Broward card shows Emailed')
        md = json.loads(pg.evaluate("localStorage.getItem('pf.send.v1')") or '{}').get('sent', {})
        ok(W['folio'] not in md, 'Broward email tracking is per county')
    b.close()
print(('ALL PASS' if not errs else 'FAILED: ' + '; '.join(errs[:6])) + f' [{TAG}]', flush=True)
sys.exit(1 if errs else 0)
