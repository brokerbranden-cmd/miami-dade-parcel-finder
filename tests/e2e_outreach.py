"""Outreach tracking: log activities in the drawer, stage + next follow-up, Due/overdue filter + badge, Pipeline view,
JSON backup round-trip (merge by activity id), Send to 'Mark as sent' logging on saved leads. argv: URL [desktop|mobile]"""
import sys, re, json, datetime as dt
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
BASE = URL.split('#')[0].split('?')[0]; Q = '?drive=0' if MOB else ''
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
TODAY = dt.date.today().isoformat(); PAST = (dt.date.today() - dt.timedelta(days=3)).isoformat(); FUT = (dt.date.today() + dt.timedelta(days=5)).isoformat()
with sync_playwright() as pw:
    b = pw.chromium.launch(); vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, accept_downloads=True); pg = ctx.new_page(); pg.set_default_timeout(60000)
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    def boot(h=''):
        pg.goto(BASE + Q + h, timeout=180000)
        if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(800)
    def open_card(f):
        c = pg.locator(f'#cards .card[data-folio="{f}"]'); c.scroll_into_view_if_needed(); c.locator('.facts').click(); pg.wait_for_selector('#outBox')
        pg.evaluate("document.getElementById('outBox').scrollIntoView({block:'center'})")
    def close(): pg.click('#closeD'); pg.wait_for_timeout(300)
    boot(); folios = pg.eval_on_selector_all('#cards .card', 'e=>e.slice(0,3).map(x=>x.dataset.folio)'); f1, f2, f3 = folios
    # log on an unsaved property -> saved, stage New -> Contacted
    open_card(f1); ok(pg.input_value('#outStage') == 'New', 'new lead starts at stage New')
    pg.select_option('#actType', 'call'); pg.select_option('#actOutcome', 'Left voicemail'); pg.fill('#actNote', 'first try'); pg.click('#actAdd'); pg.wait_for_timeout(300)
    sv = pg.evaluate(f'PF.SV.get("{f1}")'); ok(sv and sv['stage'] == 'Contacted' and len(sv['acts']) == 1 and sv['acts'][0]['outcome'] == 'Left voicemail', 'logging a call saves the lead and moves it to Contacted')
    pg.select_option('#actType', 'text'); pg.fill('#actDate', PAST); pg.click('#actAdd'); pg.wait_for_timeout(300)
    ok(pg.locator('#outBox .actlist li').count() == 2 and 'Call' in pg.inner_text('#outBox .actlist li >> nth=0'), 'activity list newest first (call today above text 3 days ago)')
    pg.fill('#outNext', PAST); pg.dispatch_event('#outNext', 'change'); pg.wait_for_timeout(300)
    ok('Overdue 3d' in pg.inner_text('#outBox'), 'drawer shows the overdue badge'); close()
    card = pg.locator(f'#cards .card[data-folio="{f1}"]')
    ok('Overdue 3d' in card.inner_text() and re.search(r'Contacted · last call \w+ \d+ · next', card.locator('.outline').inner_text()) is not None, 'card shows stage, last touch, next follow-up and the badge')
    # second lead: due today, stage Offer via outcome; third lead: future follow-up (not due)
    open_card(f2); pg.select_option('#actType', 'door'); pg.select_option('#actOutcome', 'Offer made'); pg.click('#actAdd'); pg.wait_for_timeout(300)
    pg.fill('#outNext', TODAY); pg.dispatch_event('#outNext', 'change'); pg.wait_for_timeout(300)
    ok(pg.input_value('#outStage') == 'Offer' and 'Due today' in pg.inner_text('#outBox'), "outcome 'Offer made' moves it to Offer; due today"); close()
    open_card(f3); pg.select_option('#outStage', 'Follow-up'); pg.dispatch_event('#outStage', 'change'); pg.fill('#outNext', FUT); pg.dispatch_event('#outNext', 'change'); pg.wait_for_timeout(300); close()
    # delete an activity
    open_card(f1); dl = pg.locator('#outBox [data-actdel] >> nth=1'); dl.evaluate("e=>e.scrollIntoView({block:'center'})"); pg.wait_for_timeout(400); r = dl.bounding_box(); pg.mouse.click(r['x'] + r['width'] / 2, r['y'] + r['height'] / 2); pg.wait_for_timeout(300); ok(len(pg.evaluate(f'PF.SV.get("{f1}")')['acts']) == 1, 'delete removes one activity'); close()
    # due filter
    pg.evaluate("document.getElementById('dueOnly').click()"); pg.wait_for_timeout(1200)
    s = pg.evaluate('PF.sample(50)'); ok(s['n'] == 2 and {r['folio'] for r in s['rows']} == {f1, f2}, f'Due today/overdue filter shows the 2 due leads ({s["n"]})')
    ok('due=1' in pg.evaluate('location.hash') and '(2)' in pg.inner_text('#dueCount'), 'due filter in the link; count (2)')
    pg.evaluate("document.getElementById('dueOnly').click()"); pg.wait_for_timeout(800)
    pg.evaluate("const s=document.getElementById('stageSel'); s.value='Follow-up'; s.dispatchEvent(new Event('change'))"); pg.wait_for_timeout(1000)
    s = pg.evaluate('PF.sample(50)'); ok(s['n'] == 1 and s['rows'][0]['folio'] == f3, 'stage filter = Follow-up -> the third lead')
    pg.evaluate("const s=document.getElementById('stageSel'); s.value=''; s.dispatchEvent(new Event('change'))"); pg.wait_for_timeout(800)
    # pipeline view
    pg.click('#vPipe'); pg.wait_for_selector('#pipebox:not([hidden])')
    cols = {s_: pg.locator(f'.pcol[data-stage="{s_}"] .pitem').count() for s_ in ('Contacted', 'Offer', 'Follow-up', 'New')}
    ok(cols == {'Contacted': 1, 'Offer': 1, 'Follow-up': 1, 'New': 0}, f'pipeline columns {cols}')
    ok('2 follow-ups due' in pg.inner_text('#pipeInfo'), 'pipeline header counts due follow-ups')
    ok(pg.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'pipeline: no page-level horizontal scroll')
    pg.click(f'.pitem[data-pipe="{f2}"]'); pg.wait_for_selector('#outBox'); ok(pg.get_attribute('#outBox', 'data-folio') == f2, 'clicking a pipeline item opens its details'); close()
    ok('view=pipe' in pg.evaluate('location.hash'), 'pipeline view is in the link')
    # backup + restore
    with pg.expect_download() as dl: pg.click('#pipeExport')
    data = json.load(open(dl.value.path())); it = {x['folio']: x for x in data['items']}
    ok(data['version'] == 2 and len(it[f1]['acts']) == 1 and it[f2]['stage'] == 'Offer' and it[f3]['next'] == FUT, 'JSON backup carries stage, next and activity logs')
    it[f1]['acts'].append({'id': 'imported1', 'd': PAST, 'type': 'mailer', 'outcome': '', 'note': 'postcard', 'at': PAST + 'T12:00:00.000Z'})
    p2 = ctx.browser.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB).new_page()
    p2.goto(BASE + Q, timeout=180000)
    if MOB and p2.query_selector('#drive:not([hidden])'): p2.click('#dExit')
    p2.wait_for_function('window.PF_READY', timeout=240000)
    p2.set_input_files('#svImport', files=[{'name': 'b.json', 'mimeType': 'application/json', 'buffer': json.dumps(data).encode()}]); p2.wait_for_timeout(800)
    g = p2.evaluate(f'PF.SV.get("{f1}")'); ok(g and len(g['acts']) == 2 and g['stage'] == 'Contacted', 'restore into a fresh browser: stages + both activities')
    p2.context.close()
    pg.set_input_files('#svImport', files=[{'name': 'b.json', 'mimeType': 'application/json', 'buffer': json.dumps(data).encode()}]); pg.wait_for_timeout(800)
    ok(len(pg.evaluate(f'PF.SV.get("{f1}")')['acts']) == 2, 'merge into this browser adds the new activity by id (no duplicates)')
    # send to: mark as sent logs on saved leads
    pg.click('#vCards'); pg.wait_for_timeout(600)
    pg.evaluate(f"""()=>{{ const b=document.querySelector('#cards .card[data-folio="{f3}"] [data-sendtag="cc"]'); b.click(); }}"""); pg.wait_for_timeout(400)
    pg.evaluate("""()=>{ const g=document.querySelector('#sendGrp'); if(g&&g.classList.contains('closed')) g.querySelector('.gtog').click(); }""")
    if MOB and not pg.is_visible('#sendExp-cc'): pg.click('#filtersBtn'); pg.wait_for_timeout(300)
    pg.evaluate("document.getElementById('sendExp-cc').scrollIntoView({block:'center'})")
    with pg.expect_download(): pg.click('#sendExp-cc')
    pg.wait_for_selector('#sendBar [data-sendmark="1"]'); pg.click('#sendBar [data-sendmark="1"]'); pg.wait_for_timeout(500)
    a = pg.evaluate(f'PF.SV.get("{f3}")')['acts']; ok(a and a[0]['outcome'] == 'Sent to list' and a[0]['type'] == 'call' and pg.evaluate(f'PF.SV.get("{f3}")')['stage'] == 'Follow-up', 'Mark as sent logs a Sent to list call on the saved lead (stage kept)')
    ok(pg.is_disabled('#sendExp-cc'), 'mark as sent still empties the call center list')
    if MOB and pg.is_visible('#sheetDone'): pg.click('#sheetDone')
    b.close()
ok(not [x for x in errs if x.startswith('page')], 'no page errors')
print(f'\n[{TAG}] ' + ('ALL PASS' if not errs else f'{len(errs)} FAILED')); sys.exit(1 if errs else 0)
