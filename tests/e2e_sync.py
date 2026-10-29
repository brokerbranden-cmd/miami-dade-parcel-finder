"""Team sync e2e (sync.js + sync-worker) on a local stand-in for app.prop-hunters.com: sync-worker/test/harness.mjs runs the real Worker in
`wrangler dev` (local D1) behind a fake Cloudflare Access (signed test tokens), and serves the app on the same origin with /sync-api forwarded.
Two browser contexts = two devices / two team members (separate localStorage). Checks: data already in a browser goes up on its first sync and
nothing is lost; the other device gets saved properties, folders, notes, status, Send-to tags and skip trace phones/emails; who edited is kept;
edits both ways; offline edits wait and catch up; last edit wins; deletes travel; counties stay apart; a real UI save syncs; no Access login
-> nothing syncs and the page says sign in; the public copy (no sync) shows the "sign in at app.prop-hunters.com" note and never calls the API;
backup file from the public copy restores on the app and syncs. argv: [appPort]"""
import sys, json, subprocess, os, time, signal
from playwright.sync_api import sync_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8231
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + m, flush=True)
    if not c: errs.append(m)
h = subprocess.Popen(['node', 'sync-worker/test/harness.mjs', str(PORT)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, start_new_session=True)
try:
    H = json.loads(h.stdout.readline() or '{}')
    if not H.get('ready'): print('FAIL harness did not start', H.get('log', '')[-800:]); sys.exit(1)
    BASE = H['app']; TOK = H['tokens']
    F1, F2, B1 = '3059010010010', '3059010010020', '504201010010'
    SEED = {
        'mdpf.saved.v1': {F1: {'folio': F1, 'savedAt': '2026-09-01T12:00:00.000Z', 'updatedAt': '2026-09-01T12:00:00.000Z', 'status': 'Researching', 'note': 'pre-sync note', 'addr': '1 TEST ST', 'city': 'Miami', 'zip': '33101', 'pack': 'main', 'stage': 'New', 'next': '', 'acts': [], 'folders': ['default', 'fhot']},
                          F2: {'folio': F2, 'savedAt': '2026-09-02T12:00:00.000Z', 'updatedAt': '2026-09-02T12:00:00.000Z', 'status': 'New', 'note': 'second', 'addr': '2 TEST ST', 'city': 'Miami', 'zip': '33101', 'pack': 'main', 'stage': 'New', 'next': '', 'acts': [], 'folders': ['default']}},
        'mdpf.folders.v1': [{'id': 'default', 'name': 'My saved'}, {'id': 'fhot', 'name': 'Hot leads'}],
        'pf.skip.v1': {F1: {'a': '2026-09-01', 's': 'BatchData', 'n': 'JOHN DOE', 'p': [['3055550101', 'm', 0]], 'e': ['jd@example.com']}},
        'pf.send.v1': {'tags': {F1: {'em': 1}}, 'sent': {}},
        'mdpf.saved.v1.broward': {B1: {'folio': B1, 'savedAt': '2026-09-03T12:00:00.000Z', 'updatedAt': '2026-09-03T12:00:00.000Z', 'status': 'New', 'note': 'broward one', 'addr': '3 TEST ST', 'city': 'Hollywood', 'zip': '33020', 'pack': 'main', 'stage': 'New', 'next': '', 'acts': [], 'folders': ['default']}},
    }
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
        def dev(tok, seed=None, sync=True):
            ctx = b.new_context(viewport={'width': 1440, 'height': 900}, service_workers='block', accept_downloads=True, extra_http_headers={'Cf-Access-Jwt-Assertion': tok} if tok else {})
            js = ("localStorage.setItem('pf.sync.test','1');" if sync else '') + (f"if(!localStorage.getItem('t.seeded')){{const S={json.dumps(seed)};for(const k in S)localStorage.setItem(k,JSON.stringify(S[k]));localStorage.setItem('t.seeded','1');}}" if seed else '')
            ctx.add_init_script("try{" + js + "}catch(e){}"); pg = ctx.new_page(); pg.set_default_timeout(120000)
            pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
            calls = []; pg.on('request', lambda r: calls.append(r.url) if '/sync-api/' in r.url else None); pg._calls = calls
            return ctx, pg
        def load(pg, county='miami-dade', h='hg=0'):
            pg.goto('about:blank'); pg.goto(BASE + '?county=' + county + '#' + h, timeout=180000); pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(800)
        def sync(pg):
            return pg.evaluate("""async()=>{ for(let i=0;i<3;i++){ await PFSync.syncNow(); await new Promise(r=>setTimeout(r,250)); }
              for(let i=0;i<80&&(PFSync.state!=='ok'||PFSync.pending);i++) await new Promise(r=>setTimeout(r,250)); return PFSync.status(); }""")
        sv = lambda pg, f: pg.evaluate(f'PFSaved.get("{f}")')
        ls = lambda pg, k: pg.evaluate(f'JSON.parse(localStorage.getItem({json.dumps(k)})||"null")')

        # device A: Branden's browser that already had data before sync existed
        ca, A = dev(TOK['a'], SEED); load(A)
        s = sync(A); ok(s['state'] == 'ok' and s['pending'] == 0 and s['user'] == 'branden@prop-hunters.com', f'A first sync ok, all pushed, signed in as Branden: {s}')
        ok(sv(A, F1)['note'] == 'pre-sync note' and A.evaluate('PFSaved.count()') == 2, 'A keeps what was already saved on the first sync')
        ok(A.is_visible('#syncPill') and 'Synced' in A.inner_text('#syncPill'), 'A shows the sync status pill: ' + A.inner_text('#syncPill'))
        # device B: a teammate on a new computer
        cb, B = dev(TOK['b']); load(B); sync(B)
        x = sv(B, F1) or {}
        ok(x.get('note') == 'pre-sync note' and x.get('status') == 'Researching' and 'fhot' in x.get('folders', []), f'B gets saved property, note, status and folder: {x}')
        ok(B.evaluate('PFSaved.count()') == 2 and any(f['name'] == 'Hot leads' for f in B.evaluate('PFSaved.folders()')), 'B gets both saved properties and the Hot leads folder')
        k = B.evaluate(f'PFSkip.store.get("{F1}")') or {}
        ok(k.get('p', [[None]])[0][0] == '3055550101' and k.get('e') == ['jd@example.com'], f'B gets the skip trace phones / emails: {k}')
        ok((ls(B, 'pf.send.v1') or {}).get('tags', {}).get(F1) == {'em': 1}, 'B gets the Send-to tag')
        ok(B1 not in (ls(B, 'mdpf.saved.v1') or {}) and B1 in (ls(B, 'mdpf.saved.v1.broward') or {}), 'counties never mixed: the Broward save lands in the Broward store only')
        # edits B -> A, with who
        B.evaluate(f'PFSaved.update("{F1}",{{note:"called, left VM",status:PFSaved.STATUSES[2]}})'); B.evaluate(f'PFSaved.logActivity("{F1}",{{type:"call",d:"2026-10-29",outcome:"Left voicemail",note:"vm"}})'); sync(B); sync(A)
        x = sv(A, F1)
        ok(x['note'] == 'called, left VM' and x['status'] == A.evaluate('PFSaved.STATUSES[2]') and x.get('noteBy') == 'teammate@prop-hunters.com' and x.get('statusBy') == 'teammate@prop-hunters.com', f'A sees B\'s note + status, marked as by the teammate: {x["note"]!r} {x.get("noteBy")} {x.get("statusBy")}')
        ok(x['acts'] and x['acts'][0].get('by') == 'teammate@prop-hunters.com', 'outreach log entry synced with who logged it')
        # A -> B, skip trace result added on A
        A.evaluate(f"""(()=>{{const o=JSON.parse(localStorage.getItem('pf.skip.v1'));o['{F2}']={{a:'2026-10-29',s:'BatchData',n:'JANE ROE',p:[['3055550202','m',0]],e:[]}};localStorage.setItem('pf.skip.v1',JSON.stringify(o));PFSkip.store.reload();}})()""")
        sync(A); sync(B); ok((B.evaluate(f'PFSkip.store.get("{F2}")') or {}).get('n') == 'JANE ROE', 'new skip trace result on A shows up on B')
        # offline on A, then catch up
        ca.set_offline(True); A.evaluate(f'PFSaved.update("{F2}",{{note:"offline note"}})'); s = sync(A)
        ok(s['state'] == 'offline' and s['pending'] >= 1 and 'Offline' in A.inner_text('#syncPill'), f'A offline: change waits ({s["state"]}, {s["pending"]} pending)')
        sync(B); ok(sv(B, F2)['note'] == 'second', 'B does not have it yet')
        ca.set_offline(False); s = sync(A); sync(B)
        ok(s['state'] == 'ok' and s['pending'] == 0 and sv(B, F2)['note'] == 'offline note', 'back online: A catches up and B gets the offline edit')
        # survives reload on A (outbox / meta persisted) and last edit wins
        A.evaluate(f'PFSaved.update("{F2}",{{note:"A older"}})'); A.wait_for_timeout(50); B.evaluate(f'PFSaved.update("{F2}",{{note:"B newer"}})')
        sync(B); sync(A); sync(B)
        ok(sv(A, F2)['note'] == 'B newer' and sv(B, F2)['note'] == 'B newer', 'last edit wins on both devices')
        # delete travels
        B.evaluate(f'PFSaved.remove("{F2}")'); sync(B); sync(A); ok(sv(A, F2) is None and A.evaluate('PFSaved.count()') == 1, 'unsave on B removes it on A')
        # a real UI save on A shows up on B, with who saved it in B's drawer
        R = A.evaluate('PF.sample(30)')['rows'][0]; f = R['folio']
        A.evaluate(f"location.hash='q={f}&hg=0'"); A.wait_for_timeout(2500); A.click(f'#cards .card[data-folio="{f}"] [data-star]'); A.wait_for_timeout(800)
        if A.query_selector('#svPick'): A.click('#svPick [data-pdone]'); A.wait_for_timeout(500)
        ok(A.evaluate(f'PFSaved.has("{f}")'), 'A saves a property from the card star'); sync(A); sync(B)
        ok(B.evaluate(f'PFSaved.has("{f}")'), 'B sees the property A saved in the UI')
        B.evaluate(f"location.hash='q={f}&hg=0'"); B.wait_for_timeout(2500); B.click(f'#cards .card[data-folio="{f}"]'); B.wait_for_selector('.drawer #svNote', timeout=60000)
        ok('by branden' in B.inner_text('.drawer .svhead'), 'B\'s drawer says who saved it: ' + B.inner_text('.drawer .svhead')[:120])
        B.fill('#svNote', 'typed on B'); B.wait_for_timeout(1200); sync(B); sync(A); ok(sv(A, f)['note'] == 'typed on B', 'note typed in B\'s drawer reaches A')
        ok(all(c.startswith(BASE + 'sync-api/') for c in A._calls + B._calls), 'sync only talks to the same-origin /sync-api')
        # no Access login: nothing syncs, the page asks to sign in, local data stays
        cc, C = dev(None, SEED); load(C); s = sync(C)
        ok(s['state'] == 'signin' and C.evaluate('PFSaved.count()') == 2 and 'Sign in' in C.inner_text('#syncPill'), f'no Access login -> sign-in state, local data kept: {s["state"]}')
        # public copy (no sync): note + backup; then restore on the app
        cp, P = dev(None, {**SEED, 'mdpf.saved.v1': {'3059010010030': {**SEED['mdpf.saved.v1'][F1], 'folio': '3059010010030', 'note': 'from public site'}}}, sync=False); load(P, h='saved=1&hg=0')
        t = P.inner_text('#svSyncNote'); ok('app.prop-hunters.com' in t and P.is_hidden('#syncPill') if P.query_selector('#syncPill') else 'app.prop-hunters.com' in t, 'public copy: shows the sign in at app.prop-hunters.com note, no sync pill')
        P.wait_for_timeout(1500); ok(not P._calls, 'public copy never calls the sync API')
        with P.expect_download() as d: P.click('#svSyncNote [data-pfsync=backup]')
        path = d.value.path(); bk = json.load(open(path)); ok(bk.get('kind') == 'browser-backup' and 'pf.skip.v1' in bk['stores'] and 'mdpf.saved.v1.broward' in bk['stores'], 'public copy: backup file holds every store, all counties')
        A.evaluate("location.hash='saved=1&hg=0'"); A.wait_for_timeout(1500)
        with A.expect_file_chooser() as fc: A.click('#svSyncNote [data-pfsync=restore]')
        fc.value.set_files(path); A.wait_for_timeout(1500); sync(A); sync(B)
        ok(sv(A, '3059010010030') and sv(B, '3059010010030')['note'] == 'from public site', 'backup restored on the app syncs to the team')
        ok(sv(B, F1)['note'] == 'called, left VM', 'restoring an older backup does not overwrite newer edits')
        ok(not [e for e in errs if e.startswith('pageerror')], 'no page errors: ' + '; '.join(e for e in errs if e.startswith('pageerror'))[:300])
        b.close()
finally:
    try: os.killpg(h.pid, signal.SIGTERM)
    except Exception: pass
    try: h.wait(20)
    except Exception: pass
print(('FAILED ' + str(len(errs))) if errs else 'ALL PASS')
sys.exit(1 if errs else 0)
