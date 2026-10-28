"""Power / water cut filter, every county (Miami-Dade, Broward, Monroe): data file sanity, the select (+ counts), hash link, every result
carries the picked signal bit, card tag shows strength + source + month, drawer line, CSV 'Power / water cut' column appended last
(after Waterfront) then 'Utility shut off date' / 'Utility shut off source', the 'Shut off within' days filter, the map 'Utility shut off'
ring layer, the 'No utility shutoff data yet' note for counties with no list, Clear resets. argv: URL [desktop|mobile] [SHOTS_DIR]"""
import sys, json, gzip, csv, io, os, urllib.request, datetime as dt
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8117/'
MOB = len(sys.argv) > 2 and sys.argv[2] == 'mobile'; TAG = 'mobile' if MOB else 'desktop'
SHOTS = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shots', 'utility'); os.makedirs(SHOTS, exist_ok=True)
BASE = URL.split('#')[0].split('?')[0]
HDR = ['Owner Name', 'Property Address', 'Property City', 'Property State', 'Property Zip', 'Property County', 'Mailing Address', 'Mailing City', 'Mailing State', 'Mailing Zip', 'Folio']
COUNTIES = [('miami-dade', '', 'Miami-Dade'), ('broward', 'broward/', 'Broward'), ('monroe', 'monroe/', 'Monroe')]
MASK = {'any': 15, 'list': 1, 'case': 2, 'rc': 4, 'uv': 8}; KEYC = {'list': 'list', 'case': 'case', 'rc': 'rc', 'uv': 'uv'}
SRCW = {1: 'shutoff list', 2: 'code case', 4: 'permit', 8: 'open case'}
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + f'[{TAG}] ' + m, flush=True)
    if not c: errs.append(m)
with sync_playwright() as pw:
    b = pw.chromium.launch(); vp = {'width': 390, 'height': 844} if MOB else {'width': 1440, 'height': 900}
    ctx = b.new_context(viewport=vp, is_mobile=MOB, has_touch=MOB, service_workers='block', accept_downloads=True); pg = ctx.new_page(); pg.set_default_timeout(120000)
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    def pick(v):
        pg.select_option('#utSel', v) if pg.is_visible('#utSel') else pg.evaluate(f"(()=>{{const e=document.getElementById('utSel'); e.value='{v}'; e.dispatchEvent(new Event('change'))}})()")
        pg.wait_for_timeout(2500)
    for cid, d, name in COUNTIES:
        raw = urllib.request.urlopen(BASE + 'data/' + d + 'utility.json.gz', timeout=60).read()
        W = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw); c = W['counts']; R = W['rows']
        ok(W['county'] == cid and c['any'] == len(R) > 0, f"{name}: utility file {c['any']:,} parcels (list {c['list']:,}, case {c['case']:,}, reconnect {c['rc']:,}, unsafe/vacant {c['uv']:,})")
        ok(all(c[k] == sum(1 for r in R.values() if r[0] & MASK[k]) for k in KEYC), f'{name}: per-signal counts match the rows')
        ok(all(r[0] & r[1] and r[1] == next(bt for bt in (1, 2, 4, 8) if r[0] & bt) for r in R.values()), f'{name}: best signal = most accurate bit present')
        q = '?county=' + cid + ('&drive=0' if MOB else '')
        def boot(h):
            pg.goto('about:blank'); pg.goto(BASE + q + '#' + h, timeout=180000)
            if MOB and pg.query_selector('#drive:not([hidden])'): pg.click('#dExit')
            pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_function('window.PFUT && PFUT.data', timeout=90000); pg.wait_for_timeout(2500)
        boot('gov=1&ut=any')
        s = pg.evaluate('PF.sample(3000)'); n = s['n']
        ok(n > 0 and all(r['ut'] & 15 for r in s['rows']), f'{name}: #ut=any -> {n:,} results, every sampled row has a signal')
        ok(all(r['folio'] in R for r in s['rows']), f'{name}: sampled folios are in the utility file')
        ok(pg.evaluate("document.getElementById('utSel').value") == 'any', f'{name}: select reflects the link')
        opt = pg.evaluate("[...document.getElementById('utSel').options].map(o=>o.textContent)")
        ok(len(opt) == 6 and all('(' in t for t in opt[1:]) and 'Utility shutoff list' in opt[2], f'{name}: every option shows a count {opt}')
        ok(name in pg.inner_text('#utSrc'), f"{name}: source line {pg.inner_text('#utSrc')[:120]!r}")
        if pg.locator('#cards .card').count():
            t0 = pg.inner_text('#cards .card .tt.ut >> nth=0'); fol = pg.get_attribute('#cards .card >> nth=0', 'data-folio'); r0 = R.get(fol)
            if r0 is not None and r0[1] == 1:   # list badge: 'Water shut off 2026-09-09 (Pompano Beach cut list)'
                plc = (W.get('short') or {}).get(r0[4]) or r0[4].split(' water')[0].split(' open')[0]
                ok(t0.startswith(r0[3].replace(' (open)', '')) and r0[2] in t0 and '(' + plc + ')' in t0, f'{name}: list card tag {t0!r} = label + date + place')
            else: ok(r0 is not None and SRCW[r0[1]] in t0 and (not r0[2] or r0[2][:7] in t0), f'{name}: card tag {t0!r} = signal + source + month')
        pg.screenshot(path=os.path.join(SHOTS, f'ut_{cid}_{TAG}.png'))
        for v in ['case', 'rc', 'uv', 'list']:
            pick(v); s2 = pg.evaluate('PF.sample(1500)')
            ok(all(r['ut'] & MASK[v] for r in s2['rows']) and ('ut=' + v) in pg.evaluate('location.hash') and (s2['n'] > 0) == (c[v] > 0) and s2['n'] <= c[v],
               f"{name}: ut={v} -> {s2['n']:,} (file {c[v]:,}), all rows match, hash updated")
        pick('any')
        if pg.locator('#cards .card').count():
            pg.locator('#cards .card').first.click(); pg.wait_for_timeout(2500)
            t = pg.inner_text('body'); ok('Power / water cut' in t and 'signal' in t, f'{name}: drawer shows the Power / water cut line')
            pg.keyboard.press('Escape'); pg.wait_for_timeout(600)
        if not MOB:
            with pg.expect_download(timeout=240000) as dl: pg.evaluate("document.querySelector('#exportBtn').click()")
            rows = list(csv.reader(io.StringIO(open(dl.value.path(), encoding='utf-8').read())))
            ok(rows[0][:11] == HDR and rows[0][-4:] == ['Waterfront', 'Power / water cut', 'Utility shut off date', 'Utility shut off source'], f'{name}: CSV header = 11 fixed columns, ..., Waterfront, Power / water cut, Utility shut off date / source last ({rows[0][11:]})')
            ok(len(rows) > 1 and all(r[-3] and len(r) == len(rows[0]) for r in rows[1:]), f'{name}: every exported row has a Power / water cut value ({len(rows) - 1:,} rows, e.g. {rows[1][-3]!r})')
            FI = rows[0].index('Folio'); lr = [r for r in rows[1:] if (R.get(r[FI].replace('-', '')) or R.get(r[FI]) or [0, 0])[1] == 1]
            ok(all(r[-2] and r[-1] for r in lr) and all(not r[-2] for r in rows[1:] if r not in lr) and (len(lr) > 0) == (c['list'] > 0), f'{name}: shut off date / source filled exactly for listed parcels ({len(lr):,}, e.g. {lr[0][-2:] if lr else None})')
            pg.evaluate("document.querySelector('[data-view=table], #viewTable, button[data-v=table]') && document.querySelector('[data-view=table], #viewTable, button[data-v=table]').click()")
        # 'Shut off within' (days) + map ring layer + no-data note
        dis = pg.evaluate("document.getElementById('utDays').disabled"); note = pg.inner_text('#utListNote') if pg.is_visible('#utListNote') else pg.evaluate("document.getElementById('utListNote').textContent")
        if c['list']:
            ok(not dis and 'Utility shutoff lists on file' in note, f'{name}: days filter enabled, list note {note[:140]!r}')
            pg.evaluate("(()=>{const e=document.getElementById('utDays'); e.value='60'; e.dispatchEvent(new Event('change'))})()"); pg.wait_for_timeout(3000)
            s3 = pg.evaluate('PF.sample(2000)'); cut = (dt.date.today() - dt.timedelta(days=60)).isoformat()
            exp = sum(1 for r in R.values() if r[1] == 1 and not r[3].startswith('Utility lien') and r[2] and r[2] >= cut)
            ok(all(r['ut'] & 1 and r['utr'] and r['utr'][2] >= cut for r in s3['rows']) and 'utd=60' in pg.evaluate('location.hash') and 0 < s3['n'] <= exp if exp else s3['n'] == 0,
               f"{name}: shut off within 60 days -> {s3['n']:,} results (file {exp:,} since {cut}), all dated in range, hash utd=60")
            if pg.locator('#cards .card').count():
                t1 = pg.inner_text('#cards .card .tt.ut >> nth=0'); r1 = R.get(pg.get_attribute('#cards .card >> nth=0', 'data-folio'))
                ok(r1 and t1.startswith(r1[3].replace(' (open)', '')) and r1[2] in t1 and t1.endswith(')'), f'{name}: listed card badge {t1!r}')
            boot('gov=1&ut=any&utd=60'); ok(pg.evaluate("document.getElementById('utDays').value") == '60' and pg.evaluate('PF.sample(5)')['n'] == s3['n'], f"{name}: utd link restores the days filter ({pg.evaluate('PF.sample(5)')['n']} vs {s3['n']})")
        else:
            ok(dis and 'No utility shutoff data yet for this county' in note, f'{name}: no list -> days filter disabled + note {note!r}')
        pg.evaluate("document.getElementById('vMap').click()"); pg.wait_for_function("document.getElementById('mapHint').textContent.includes('on the map') || document.getElementById('mapHint').textContent.includes('Nothing')", timeout=180000)
        pg.evaluate("(()=>{const e=document.getElementById('mapUt'); if(!e.checked){ e.checked=true; e.dispatchEvent(new Event('change')); }})()"); pg.wait_for_timeout(3000)
        hint = pg.inner_text('#mapHint'); leg = pg.evaluate("document.getElementById('mapLegend').textContent")
        ok(('utility shut off in view' in hint and 'Utility shut off' in leg) if c['list'] else ('No utility shutoff data yet for this county' in hint), f'{name}: map layer hint {hint!r} legend {leg[-60:]!r}')
        pg.screenshot(path=os.path.join(SHOTS, f'ut_map_{cid}_{TAG}.png'))
        pg.evaluate("(()=>{const e=document.getElementById('mapUt'); e.checked=false; e.dispatchEvent(new Event('change'));})()"); pg.evaluate("document.getElementById('vCards').click()"); pg.wait_for_timeout(800)
        pg.evaluate("document.getElementById('clrUt').click()"); pg.wait_for_timeout(2500)
        ok(pg.evaluate("document.getElementById('utSel').value") == '' and pg.evaluate("document.getElementById('utDays').value") == '' and 'ut=' not in pg.evaluate('location.hash') and 'utd=' not in pg.evaluate('location.hash') and pg.evaluate('PF.sample(10)')['n'] >= n, f'{name}: Clear removes the filter')
    b.close()
print(('FAILED: ' + '; '.join(errs[:8])) if errs else f'ALL PASS [{TAG}]')
sys.exit(1 if errs else 0)
