"""Monroe city permits + code cases (Key West eTRAKiT, Islamorada CityView): signal chips, filter correctness against the pack bits,
drawer text, vacancy-hint points, hash round trip, Broward unaffected.
usage: python3 tests/e2e_monroe_city.py [base_url] [desktop|mobile]"""
import sys, re
from playwright.sync_api import sync_playwright
URL = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/').rstrip('/') + '/'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'desktop'
errs, fails = [], []
def check(ok, msg): print(('ok   ' if ok else 'FAIL ') + msg); ok or fails.append(msg)
MOB = MODE == 'mobile'
cnt = lambda pg: int(pg.inner_text('#sCount').replace(',', '') or 0)
# pack-side truth, decoded in Python from the served packs (same format as build_monroe.write_pack)
import gzip, json, urllib.request
import numpy as np
T = {'uint8': np.uint8, 'uint16': np.uint16, 'uint32': np.uint32}
def pack(name):
    raw = gzip.decompress(urllib.request.urlopen(URL + 'data/monroe/' + name, timeout=120).read()); h = int.from_bytes(raw[:4], 'little'); hdr = json.loads(raw[4:4 + h]); base = 4 + h; out = {}
    for c in hdr['cols']:
        if c['type'] in T: out[c['name']] = np.frombuffer(raw[base + c['offset']: base + c['offset'] + c['bytes']], dtype=T[c['type']])
    return out
PK = {n: pack(f'{n}.bin.gz') for n in ('main', 'condo')}
META = json.loads(urllib.request.urlopen(URL + 'data/monroe/meta.json', timeout=60).read())
def truth(bit): return [int(((PK[n]['sigm'].astype(np.int64) & bit) > 0).sum()) for n in ('main', 'condo')]
with sync_playwright() as pw:
    b = pw.chromium.launch(args=['--js-flags=--max-old-space-size=1024'])
    vp = {'width': 390, 'height': 800} if MOB else {'width': 1300, 'height': 900}
    ctx = b.new_context(viewport=vp, service_workers='block', is_mobile=MOB, has_touch=MOB)
    pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(URL + '?county=monroe#hg=0'); pg.wait_for_selector('#cards .card', timeout=120000); pg.wait_for_timeout(1000)
    sheet = lambda: (pg.click('#filtersBtn'), pg.wait_for_timeout(400)) if MOB and not pg.is_visible('#panel') else None
    sheet(); n0 = cnt(pg)
    def sec(title):
        d = pg.locator('.drawer section.dsec').filter(has=pg.locator('.dtog', has_text=title)).first
        if not d.count(): return ''
        if 'Nothing on record' not in d.inner_text() and len(d.inner_text()) < len(title) + 40: d.locator('.dtog').first.click(); pg.wait_for_timeout(500)
        return d.inner_text()
    meta = META.get('enrich') or {}
    cm = meta.get('city_matched') or {}; cp = meta.get('city_permits') or {}
    check(cp.get('kw_permits', 0) > 1000 and cp.get('isl_permits', 0) > 500, f"meta: city records loaded {cp}")
    check(cm.get('kw_permit_parcels', 0) > 500 and cm.get('isl_permit_parcels', 0) > 300 and cm.get('kw_code_parcels', 0) > 30 and cm.get('isl_code_parcels', 0) > 100, f'meta: parcels matched by RE {cm}')
    keys = pg.eval_on_selector_all('#mrSig .chip', 'n=>n.map(x=>x.dataset.mr)')
    for k in ('sig:code_open', 'sig:permit_open', 'sig:permit_recent', 'sig:code'): check(k in keys, f'chip {k} present')
    for k, bit, lo in (('code_open', 65536, 20), ('permit_open', 128, 200), ('permit_recent', 64, 500)):
        tm, tc = truth(bit)
        pg.click(f'#mrSig .chip[data-mr="sig:{k}"]'); pg.wait_for_timeout(1200); n = cnt(pg)
        check(lo <= n and 0.9 * tm <= n <= tm + tc and n < n0, f'{k}: filter {n} (pack bits: main {tm}, condo {tc})')
        check(f'msig={k}' in pg.evaluate('location.hash'), f'hash carries msig={k}')
        pg.click('#clrMr'); pg.wait_for_timeout(800)
    check(cnt(pg) == n0, 'clear restores the count')
    # drawer: open code case parcel shows the city case text + open count
    pg.goto(URL + '?county=monroe#msig=code_open'); pg.wait_for_selector('#cards .card', timeout=120000); pg.wait_for_timeout(1500); sheet()
    check(pg.eval_on_selector_all('#mrSig .chip.on', 'n=>n.map(x=>x.dataset.mr)') == ['sig:code_open'], 'open-code-case chip restored from the URL')
    pg.click('#cards .card h3'); pg.wait_for_selector('.drawer', timeout=30000); pg.wait_for_timeout(1500)
    txt = sec('Permits, code cases')
    check(re.search(r'\d+ open', txt) is not None and re.search(r'(Key West|Islamorada|county|Marathon)', txt) is not None, 'drawer shows open code cases: ' + (re.search(r'\d+ (Key West|Islamorada)[^\n]{0,80}', txt) or [''])[0])
    check('eTRAKiT' in txt and 'CityView' in txt, 'drawer coverage note names the Key West / Islamorada sources')
    pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
    # a Key West parcel with a recent permit: drawer has Last permit + permit text, vacancy hint shows the -15 recent-permit line
    pg.goto(URL + '?county=monroe#msig=permit_recent'); pg.wait_for_selector('#cards .card', timeout=120000); pg.wait_for_timeout(1500)
    nk = cnt(pg); check(nk > 100, f'parcels with a city permit in the last 2 yrs: {nk}')
    pg.click('#cards .card h3'); pg.wait_for_selector('.drawer', timeout=30000); pg.wait_for_timeout(1500); txt = sec('Permits, code cases')
    check('Last permit' in txt and re.search(r'\d+ (Key West|Islamorada) permits', txt) is not None, 'drawer lists the city permits with a last-permit date')
    hasb = True; rp = [0, 0]
    for nme in ('main', 'condo'):
        v = PK[nme]['vsig'].astype(np.int64); sgm = PK[nme]['sigm'].astype(np.int64); m = (v & (1 << 11)) > 0
        rp[0] += int(m.sum()); rp[1] += int((m & ((sgm & 64) == 0)).sum())
    check(hasb and rp[0] > 100 and rp[1] == 0, f'vacancy hint: {rp[0]} parcels carry the recent-permit bit, all with the permit_recent signal ({rp[1]} without)')
    vt = sec('Vacancy')
    check('Permit issued in the last 24 months' in vt or 'No building on record' in vt, 'vacancy section shows the recent-permit line (-15): ' + vt[:120].replace('\n', ' '))
    pg.keyboard.press('Escape')
    # Broward has none of the Monroe city chips
    pg.goto(URL + '?county=broward#hg=0'); pg.wait_for_selector('#cards .card', timeout=180000); pg.wait_for_timeout(800)
    bk = pg.eval_on_selector_all('#mrSig .chip', 'n=>n.map(x=>x.dataset.mr)')
    # Broward has its own 'Open code case' chip (sigm bit 128 from build_broward.py), so only the Monroe-only permit chips must be absent
    check(not any(k in bk for k in ('sig:permit_open', 'sig:permit_recent')), f'Broward has no Monroe city permit chips ({len(bk)} chips)')
    check(bk.count('sig:code_open') <= 1, 'Broward has at most its own one Open code case chip')
    b.close()
check(not errs, 'no page errors ' + '; '.join(errs[:3]))
print('RESULT', 'PASS' if not fails else f'FAIL ({len(fails)})'); sys.exit(1 if fails else 0)
