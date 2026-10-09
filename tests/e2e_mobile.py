"""Headless e2e for the phone 'Drive for dollars' mode + PWA: auto-open on a phone, mocked GPS, dots around you,
tap a parcel -> bottom sheet (address / owner / score / signals), one-tap Save + status + quick note + 'looks vacant',
'Save where I am' (nearest parcel), Full details drawer, exit + preference, manifest + icons, service worker, offline reload.
Screenshots -> SHOTS/mobile_*.png"""
import sys, json
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
SHOTS = sys.argv[2] if len(sys.argv) > 2 else '/workspace/parcel-finder/shots/'
GPS = {'latitude': 25.79905, 'longitude': -80.21695}     # residential block in Allapattah, Miami
errs = []
def ok(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg)
    if not cond: errs.append('assert: ' + msg)
def watch(pg, tag):
    pg.on('console', lambda m: m.type == 'error' and 'net::ERR_INTERNET_DISCONNECTED' not in m.text and 'Failed to load resource' not in m.text and errs.append(f'{tag} console: ' + m.text))
    pg.on('pageerror', lambda e: errs.append(f'{tag} pageerror: ' + str(e)))
with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
                        geolocation=GPS, permissions=['geolocation'], user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148')
    pg = ctx.new_page(); watch(pg, 'phone')
    pg.goto(URL); pg.wait_for_selector('#drive:not([hidden])', timeout=180000)
    ok(True, 'drive mode opens automatically on a phone-width screen')
    pg.wait_for_function("document.getElementById('dGps').textContent.startsWith('GPS')", timeout=60000); pg.wait_for_timeout(2500)
    ok('GPS ±' in pg.inner_text('#dGps'), 'GPS fix shown: ' + pg.inner_text('#dGps'))
    ok(pg.is_hidden('#dHint'), 'parcel dots drawn around the GPS position (no "zoom in"/"no parcels" hint)')
    sizes = pg.evaluate("['dHere','dLocate','dExit'].map(id=>{const r=document.getElementById(id).getBoundingClientRect();return [id,Math.round(r.width),Math.round(r.height)]})")
    ok(all(w >= 44 and h >= 44 for _, w, h in sizes), f'touch targets >= 44px: {sizes}')
    pg.screenshot(path=SHOTS + 'mobile_01_drive_map.png')
    # tap the parcel nearest the GPS dot (map is centered on it)
    pt = pg.evaluate('PFDrive.nearestPoint()'); pg.touchscreen.tap(pt['x'], pt['y']); pg.wait_for_timeout(600)
    ok(pg.is_visible('#dSheet'), 'tap a parcel -> bottom sheet')
    t = pg.inner_text('#dSheet'); ok('OWNER' in t.upper() and ('distress score' in t or 'No distress records' in t), 'sheet shows owner + score line')
    addr1 = pg.inner_text('#dSheet h2')
    pg.click('#dSave'); pg.wait_for_selector('#dStatus')
    folio1 = pg.get_attribute('#dSave', 'data-folio')
    ok(pg.evaluate(f"PFSaved.has('{folio1}')"), f'one-tap Save: {addr1} ({folio1})')
    pg.select_option('#dStatus', 'Researching'); pg.check('#dVacant'); pg.fill('#dNote', 'Tall grass, mail piling up'); pg.wait_for_timeout(900)
    it = pg.evaluate(f"PFSaved.get('{folio1}')")
    ok(it['status'] == 'Researching' and it['vacant'] and it['note'] == 'Tall grass, mail piling up', 'status + vacant + quick note stored')
    pg.screenshot(path=SHOTS + 'mobile_02_parcel_sheet.png')
    # full details drawer over the map
    pg.click('#dDetails'); pg.wait_for_selector('.drawer'); pg.wait_for_timeout(800)
    ok(addr1.upper() in pg.inner_text('.drawer h2').upper(), 'Full details opens the drawer for that parcel')
    pg.click('#closeD'); pg.wait_for_timeout(300)
    pg.click('#dSheetClose'); pg.wait_for_timeout(300); ok(pg.is_hidden('#dSheet'), 'sheet closes')
    # Save where I am: move GPS a bit and save the nearest parcel
    ctx.set_geolocation({'latitude': GPS['latitude'] + 0.0007, 'longitude': GPS['longitude'] + 0.0004}); pg.wait_for_timeout(2500)
    n0 = pg.evaluate('PFSaved.count()')
    pg.click('#dHere'); pg.wait_for_timeout(800)
    ok(pg.evaluate('PFSaved.count()') == n0 + 1 and 'nearest to you' in pg.inner_text('#dSheet'), "'Save where I am' saved the nearest parcel: " + pg.inner_text('#dSheet h2'))
    pg.screenshot(path=SHOTS + 'mobile_03_save_where_i_am.png')
    pg.click('#dSheetClose')
    # PWA: manifest, icons, service worker
    man = pg.evaluate("fetch(document.querySelector('link[rel=manifest]').href).then(r=>r.json())")
    ok(man['display'] == 'standalone' and len(man['icons']) >= 3 and any(i.get('purpose') == 'maskable' for i in man['icons']), 'manifest: standalone, 3 icons incl. maskable')
    st = pg.evaluate("Promise.all(%s.map(i=>fetch(i.src).then(r=>r.status)))" % json.dumps(man['icons']))
    ok(all(s == 200 for s in st), f'icons load {st}')
    pg.evaluate('navigator.serviceWorker.ready.then(()=>1)')
    pg.reload(); pg.wait_for_selector('#drive:not([hidden])', timeout=180000); pg.wait_for_timeout(4000)
    ok(pg.evaluate('!!navigator.serviceWorker.controller'), 'service worker controls the page')
    caches = pg.evaluate("caches.keys().then(async ks=>{const o={};for(const k of ks){o[k]=(await (await caches.open(k)).keys()).length}return o})")
    ok(any(k.startswith('pf-shell') for k in caches) and caches.get('pf-data', 0) >= 1, f'caches: {caches}')
    # offline reload
    ctx.set_offline(True)
    pg.reload(); pg.wait_for_selector('#drive:not([hidden])', timeout=60000)
    pg.wait_for_function("document.getElementById('dGps').textContent.startsWith('GPS')", timeout=30000); pg.wait_for_timeout(2500)
    ok(pg.is_hidden('#dHint'), 'offline: app shell + packs load from cache, parcels drawn')
    pt = pg.evaluate('PFDrive.nearestPoint()'); pg.touchscreen.tap(pt['x'], pt['y']); pg.wait_for_timeout(600)
    ok(pg.is_visible('#dSheet'), 'offline: tap a parcel still works')
    pg.screenshot(path=SHOTS + 'mobile_04_offline.png')
    ctx.set_offline(False)
    # exit -> list view; preference remembered
    pg.click('#dSheetClose') if pg.is_visible('#dSheetClose') else None
    pg.click('#dExit'); pg.wait_for_timeout(500)
    ok(pg.is_hidden('#drive') and pg.is_visible('#results'), 'exit -> list & filters')
    pg.goto(URL.rstrip('/') + '/'); pg.wait_for_selector('#results:not([hidden])', timeout=180000); pg.wait_for_timeout(800)
    ok(pg.is_hidden('#drive'), 'after exiting, the next visit opens the list (preference remembered)')
    pg.screenshot(path=SHOTS + 'mobile_05_list_header.png')
    pg.click('#driveBtn'); pg.wait_for_selector('#drive:not([hidden])'); ok(True, 'header Drive button opens drive mode')
    ctx.close()
    # ?drive=1 start URL (installed app) + desktop doesn't auto-open
    d = b.new_context(viewport={'width': 1360, 'height': 900}); dp = d.new_page(); watch(dp, 'desktop')
    dp.goto(URL); dp.wait_for_selector('#results:not([hidden])', timeout=180000); dp.wait_for_timeout(500)
    ok(dp.is_hidden('#drive'), 'desktop does not auto-open drive mode')
    dp.goto(URL + '?drive=1'); dp.wait_for_selector('#drive:not([hidden])', timeout=60000); ok(True, '?drive=1 (PWA start URL) opens drive mode')
    d.close(); b.close()
print('ERRORS', errs if errs else 'none')
sys.exit(1 if errs else 0)
