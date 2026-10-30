"""Headless e2e: owner-type classification. Utilities, banks, associations and institutions must be hidden by the 'Individuals' owner filter
(they are 'Companies & organizations'), and water-management districts / federal / county owners by 'Hide government-owned'.
Persons whose surname looks like a company word must stay individuals."""
import sys, os, json
from playwright.sync_api import sync_playwright
import legacy_ui  # noqa: F401  (simplified UI in legacy mode, see legacy_ui.py)
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'desktop'
import re
# entity / church keywords that never belong to an individual (care-of lines, 'REM' remainder lines and person-marked lines skipped)
ENT = re.compile(r"\b(?:L ?L ?C|INC|INCORPORATED|CORP|CORPORATION|LTD|LLP|PLLC|MINISTRIES|MINISTRY|CONGREGATION|SYNAGOGUE|MOSQUE|TABERNACLE|DIOCESE|ARCHDIOCESE|CATHEDRAL|EVANGELICAL|FELLOWSHIP|ASSEMBLY OF GOD|BAPTIST CHURCH|CHURCH OF|ASSOCIATION|ASSN|FOUNDATION|SOCIETY|CLUB|TRUSTEES OF|HOUSING AUTHORITY|CITY OF|IGLESIA (?:DE|DEL|BAUTISTA|EVANGELICA|CRISTIANA))\b")
PERS = re.compile(r"&\s?[WH]\b|\bH ?/ ?E\b|\bLE\b|\bETAL\b|\bJTRS\b")
def entity(o):
    for l in str(o).upper().split('|'):
        l = l.strip()
        if re.match(r'(C ?/ ?O\b|%|ATTN\b|CARE OF)', l): break
        if l.startswith('REM '): continue
        l = re.sub(r'\s+', ' ', re.sub(r"[^A-Z0-9&/]+", ' ', l.replace('.', '').replace("'", ''))).strip()
        if ENT.search(l) and not PERS.search(l): return True
    return False
errs = []
def ok(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg)
    if not cond: errs.append('assert: ' + msg)
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={'width': 390, 'height': 844} if MODE == 'mobile' else {'width': 1360, 'height': 900}).new_page()
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    pg.goto(URL); pg.wait_for_selector('#results:not([hidden])', timeout=180000); pg.wait_for_timeout(800)
    ok('Companies' in pg.inner_text('#ownerKind'), 'owner filter label: ' + pg.inner_text('#ownerKind').replace('\n', ' | ')[:80])
    cnt = lambda: int(pg.inner_text('#sCount').replace(',', '') or 0)
    def count(q, kind='all', gov=True):
        pg.click('#resetBtn'); pg.wait_for_timeout(500)
        if not gov: pg.uncheck('#hideGov')
        pg.click(f'#ownerKind button[data-k="{kind}"]'); pg.fill('#q', q); pg.wait_for_timeout(1500); return cnt()
    # companies / utilities / banks: found under 'all' and 'corp', hidden under 'person'
    for q in ['FLORIDA POWER & LIGHT', 'BANK OF AMERICA', 'WELLS FARGO', 'TELEPHONE', 'CONDOMINIUM ASSOCIATION', 'ARCHDIOCESE OF MIAMI']:
        a, c, p = count(q, 'all'), count(q, 'corp'), count(q, 'person')
        ok(a > 0 and c > 0 and p == 0, f'{q}: all={a} companies&orgs={c} individuals={p}')
    # government: visible only when 'Hide government-owned' is off; never under companies
    for q in ['SOUTH FLA WATER M', 'US ARMY CORPS', 'MIAMI-DADE COUNTY', 'SCHOOL BOARD', 'EXPRESSWAY AUTHORITY', 'HOUSING AUTHORITY', 'COMM DEV DIST']:
        hid, shown, corp = count(q, 'all', True), count(q, 'all', False), count(q, 'corp', True)
        # residue < 5% (HOUSING AUTHORITY: a few LLC / lessee names that merely mention it):
        # residue < 1%: e.g. 'MIAMI-DADE COUNTY | DADELAND VISTA LTD LESSEE' (a company leasing county land) or '% C & S FLOOD CONTROL DIST' mailing lines
        ok(shown > 0 and hid * 100 <= shown * 5 and corp * 100 <= shown * 5, f'{q}: hidden-gov={hid} shown-gov={shown} under companies={corp}')
    # person names containing company-like words stay individuals
    for q in ['MARIA POWER', 'JOHN BANK']:
        a = count(q, 'all'); p = count(q, 'person')
        ok(a == p, f'{q}: all={a} individuals={p}')
    # regression (Oct 19, 2026): 'Recert overdue' + 'Individuals' listed churches and companies. Individuals must never hold an entity name,
    # with RC, with other signals, and in all three counties; the owner-kind counts must add up to 'All owners'.
    def hsearch(h):
        r0 = pg.evaluate('PF.runN()'); pg.evaluate(f"location.hash={h!r}")
        try: pg.wait_for_function(f'PF.runN()>{r0}', timeout=20000)
        except Exception: pass
        pg.wait_for_timeout(600); return pg.evaluate('PF.auditRows(5000)')
    def kinds():
        t = pg.inner_text('#ownerKind'); return [int(x.replace(',', '')) for x in re.findall(r'(?<![\d.])(\d[\d,]*)(?![\d.KM])', t)]
    def person_check(county, h, need=True):
        r = hsearch(h); bad = [x['owner'] for x in r['rows'] if entity(x['owner'])]
        ok(not bad and (r['n'] > 0 or not need), f"{county} {h}: individuals={r['n']} entity-named={len(bad)} {bad[:5]}")
        return r
    r = person_check('miami-dade', '#sig=RC&owner=person')
    ok(all(x['folio'] != '0141110010350' for x in r['rows']), "RC + Individuals: 'IGLESIA DEL DIOS VIVO COLUMNA & APOYO...' (0141110010350) is not an individual")
    k = kinds(); ok(len(k) == 4 and k[0] == k[1] + k[2] + k[3] and k[1] == r['n'], f"RC owner-kind counts add up and match the results: {k} n={r['n']}")
    rc = hsearch('#sig=RC&owner=corp'); ok(any(x['folio'] == '0141110010350' for x in rc['rows']), 'RC + Companies & organizations includes IGLESIA DEL DIOS VIVO')
    for sg in ['LP', 'TD', 'TC', 'US', 'BV', 'CC', 'LN', 'PR', 'DC', 'FC']: person_check('miami-dade', f'#sig={sg}&owner=person', need=False)
    person_check('miami-dade', '#owner=person&type=condo'); person_check('miami-dade', '#owner=person&ds=50', need=False)
    for county, names in [('monroe', ['C O D SUPPLIES', 'HABITAT FOR HUMANITY', 'IGLESIA BAUTISTA']), ('broward', ['ATT RESIDENCE 1', 'IGLESIA DE DIOS', 'GOLF & TENNIS CLUB', 'CATHEDRAL OF PRAISE', 'AMERICAN EXPRESS TRAVEL', 'SOUTHERN SHORES ACQUISITIONS', 'FLORIDA EASTERN ECCLESIASTICAL'])]:
        pg.goto(URL + '?county=' + county); pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(1500)
        for h in ['#owner=person', '#owner=person&mtax=any', '#owner=person&o_oos=yes', '#owner=person&o_absz=yes', '#owner=person&x_life=yes', '#owner=person&td=basic']:
            person_check(county, h, need=h in ('#owner=person', '#owner=person&mtax=any'))
        k = kinds(); ok(len(k) == 4 and k[0] == k[1] + k[2] + k[3], f'{county} owner-kind counts add up: {k}')
        for q in names:
            from urllib.parse import quote
            p_ = hsearch('#owner=person&q=' + quote(q)); c_ = hsearch('#owner=corp&q=' + quote(q))
            ok(p_['n'] == 0 and c_['n'] > 0, f"{county} '{q}': individuals={p_['n']} companies&orgs={c_['n']}")
        fx = pg.evaluate('PF.okFix()'); print(county, 'reclassified', fx); 
        twin = pg.evaluate(f"fetch('data/{county}/meta.json').then(r=>r.json()).then(m=>!!m.ownerKind)")
        if twin:   # pack classified at build time by owner_kind.py (hard rules only): the app adds the given-name-aware business-word rules on load;
                   # it must reclassify exactly what the Python twin org_name(name, org_given(pack)) does (tests/unit_orgname.py checks every row)
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
            import unit_orgname as UO
            d0 = UO.parse(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', county, json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', county, 'meta.json')))['packs'][0]['files'][0]))
            want = len(UO.py_fixed(d0, UO.org_given(d0['owner'], d0['flags'])))
            ok(fx[0]['fixed'] == want, f"{county}: app reclassified {fx[0]['fixed']} names on load, Python twin with the pack's given names: {want} (must match)")
        else:      # older pack built before the twin: the app-side reclassification must kick in
            ok(fx[0]['fixed'] > 0, f'{county}: app reclassified some owner names')
    b.close()
print('ERRORS:', errs if errs else 'none'); sys.exit(1 if errs else 0)
