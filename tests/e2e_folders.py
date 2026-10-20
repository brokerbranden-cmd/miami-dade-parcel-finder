"""Saved folders: existing saved properties migrate to the default folder (nothing lost), create / rename / delete folders (per county),
'All saved' tab, a property in several folders chosen from the save button and from the Saved list, folder tabs filter the list,
per-folder CSV with the standard columns, deleting a folder keeps its properties saved. argv: URL [desktop|mobile]"""
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
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    Q = '?drive=0&county=' if MOB else '?county='
    def load(county, h='hg=0'):
        pg.goto('about:blank'); pg.goto(BASE + Q + county + '#' + h, timeout=180000)
        if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
        pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(1500)
    def go(h): pg.evaluate(f"location.hash={json.dumps(h)}"); pg.wait_for_timeout(2500)
    shown = lambda: pg.eval_on_selector_all('#cards .card', 'e=>e.map(x=>x.dataset.folio)')
    def tab(name): pg.click(f'#svFolders .chip:has-text("{name}")'); pg.wait_for_timeout(1500)

    load('miami-dade', 'city=Homestead&type=sf&hg=0')
    R = pg.evaluate('PF.sample(40)')['rows'][:5]; F = [r['folio'] for r in R]
    # legacy saved list (pre-folders item shape) -> migrates into the default folder
    legacy = {f: {'folio': f, 'savedAt': '2026-09-01T12:00:00.000Z', 'updatedAt': '2026-09-01T12:00:00.000Z', 'status': 'Researching', 'note': 'old note', 'addr': r['addr'], 'city': r['city'], 'zip': r['zip'], 'pack': 'main', 'stage': 'New', 'next': '', 'acts': []} for f, r in zip(F[:3], R[:3])}
    pg.evaluate(f"localStorage.setItem('mdpf.saved.v1', {json.dumps(json.dumps(legacy))}); localStorage.removeItem('mdpf.folders.v1')")
    load('miami-dade', 'city=Homestead&type=sf&hg=0')
    ok(pg.evaluate('PF.SV.count()') == 3 and all(pg.evaluate(f'PF.SV.get("{f}").folders') == ['default'] and pg.evaluate(f'PF.SV.get("{f}").note') == 'old note' for f in F[:3]), 'existing saved properties land in the default folder with notes kept')
    go('saved=1&hg=0'); ok(pg.is_visible('#svFolders'), 'Saved list shows folder tabs')
    t = pg.inner_text('#svFolders'); ok('All saved' in t and 'My saved' in t and '+ New folder' in t, f'tabs: {t!r}')
    # create two folders
    pg.click('#svfNew'); pg.fill('#svfName', 'Hot leads'); pg.click('#svfForm button[type=submit]'); pg.wait_for_timeout(1500)
    hot = pg.evaluate("PF.SV.folders().find(x=>x.name==='Hot leads').id"); ok(bool(hot), 'created folder Hot leads')
    pg.click('#svfNew'); pg.fill('#svfName', 'Probate'); pg.click('#svfForm button[type=submit]'); pg.wait_for_timeout(1500)
    pro = pg.evaluate("PF.SV.folders().find(x=>x.name==='Probate').id")
    ok(shown() == [], 'new folder starts empty')
    # Saved list: folder picker on a card -> put F[0] in Hot leads + Probate (one or more folders)
    tab('All saved'); pg.click(f'#cards .card[data-folio="{F[0]}"] [data-svfold]'); pg.wait_for_selector('#svPick')
    pg.check(f'#svPick [data-pf="{hot}"]'); pg.check(f'#svPick [data-pf="{pro}"]'); pg.click('#svPick [data-pdone]'); pg.wait_for_timeout(800)
    ok(sorted(pg.evaluate(f'PF.SV.get("{F[0]}").folders')) == sorted(['default', hot, pro]), 'Saved list picker: property in several folders')
    pg.click(f'#cards .card[data-folio="{F[1]}"] [data-svfold]'); pg.wait_for_selector('#svPick'); pg.check(f'#svPick [data-pf="{hot}"]'); pg.uncheck('#svPick [data-pf="default"]'); pg.click('#svPick [data-pdone]'); pg.wait_for_timeout(800)
    ok(pg.evaluate(f'PF.SV.get("{F[1]}").folders') == [hot], 'move a property out of the default folder')
    # save button: saving a new property from a folder tab puts it in that folder; the picker opens to pick more
    go('city=Homestead&type=sf&hg=0'); go(f'q={F[3]}&hg=0'); pg.click(f'#cards .card[data-folio="{F[3]}"] [data-star]'); pg.wait_for_selector('#svPick', timeout=10000)
    ok(pg.evaluate(f'PF.SV.get("{F[3]}").folders') == ['default'], 'save button: saved to the default folder')
    pg.check(f'#svPick [data-pf="{pro}"]'); pg.fill('#svPick .svpnew input', 'Call back'); pg.click('#svPick .svpnew button'); pg.wait_for_timeout(500)
    cb = pg.evaluate("PF.SV.folders().find(x=>x.name==='Call back').id"); fs = pg.evaluate(f'PF.SV.get("{F[3]}").folders')
    ok(cb and pro in fs and cb in fs, f'save button picker: chose Probate + a new folder ({fs})'); pg.click('#svPick [data-pdone]')
    ok(pg.query_selector('#svPick') is None, 'picker closes')
    # tabs filter
    go('saved=1&hg=0'); tab('All saved'); ok(sorted(shown()) == sorted([F[0], F[1], F[2], F[3]]), 'All saved shows everything')
    tab('Hot leads'); ok(sorted(shown()) == sorted([F[0], F[1]]), 'Hot leads tab filters')
    tab('My saved'); ok(sorted(shown()) == sorted([F[0], F[2], F[3]]), 'My saved tab filters')
    # saving while a folder tab is open puts it in that folder
    tab('Probate'); ok(sorted(shown()) == sorted([F[0], F[3]]), 'Probate tab filters')
    # per-folder CSV
    tab('Hot leads')
    with pg.expect_download(timeout=120000) as d: pg.click('#svfExport')
    rows = list(csv.reader(io.StringIO(open(d.value.path(), encoding='utf-8').read())))
    ok(rows[0] == STD, f'folder CSV header = standard columns'); ok(sorted(r[10].replace('-', '') for r in rows[1:]) == sorted([F[0], F[1]]), f'folder CSV has only that folder ({len(rows)-1} rows)')
    ok('Hot-leads' in d.value.suggested_filename, f'file name names the folder: {d.value.suggested_filename}')
    # rename
    pg.click('#svfRename'); pg.fill('#svfName', 'Hottest'); pg.click('#svfForm button[type=submit]'); pg.wait_for_timeout(1200)
    ok('Hottest' in pg.inner_text('#svFolders') and 'Hot leads' not in pg.inner_text('#svFolders') and pg.evaluate(f'PF.SV.inFolder("{F[0]}","{hot}")'), 'rename keeps the folder contents')
    ok('Hottest' in pg.inner_text(f'#cards .card[data-folio="{F[0]}"] .svfl'), 'card shows its folder names')
    # delete (two-step), properties stay saved
    pg.click('#svfDelete'); ok('Yes, delete' in pg.inner_text('#svfDelete'), 'delete asks to confirm'); pg.click('#svfDelete'); pg.wait_for_timeout(1500)
    ok(not pg.evaluate(f"PF.SV.folders().some(x=>x.id==='{hot}')") and pg.evaluate('PF.SV.count()') == 4, 'folder deleted, all 4 properties still saved')
    ok(pg.evaluate(f'PF.SV.get("{F[1]}").folders') == ['default'], 'property only in the deleted folder goes back to My saved')
    ok(pg.query_selector('#svfDelete') is None, 'back on All saved (no delete button)'); tab('My saved'); ok(pg.query_selector('#svfDelete') is None, 'default folder cannot be deleted')
    # drawer folder button
    pg.click(f'#cards .card[data-folio="{F[2]}"] .addr, #cards .card[data-folio="{F[2]}"] h3') if pg.query_selector(f'#cards .card[data-folio="{F[2]}"] h3') else pg.evaluate(f"PF.openDrawer(+document.querySelector('#cards .card[data-folio=\"{F[2]}\"]').dataset.id)")
    pg.wait_for_selector('#savedBox [data-svfold]', timeout=60000); ok(True, 'drawer has the folder picker')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400); pg.keyboard.press('Escape')
    # backup JSON carries folders
    ok(any(x['name'] == 'Probate' for x in pg.evaluate('PF.SV.exportJSON().folders')), 'saved backup JSON includes folders')
    # per county
    load('monroe'); ok([x['name'] for x in pg.evaluate('PF.SV.folders()')] == ['My saved'] and pg.evaluate('PF.SV.count()') == 0, 'Monroe has its own folders and saved list')
    b.close()
print(('ALL PASS' if not errs else 'FAILED: ' + '; '.join(errs[:6])) + f' [{TAG}]', flush=True)
sys.exit(1 if errs else 0)
