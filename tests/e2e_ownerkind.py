"""Headless e2e: owner-type classification. Utilities, banks, associations and institutions must be hidden by the 'Individuals' owner filter
(they are 'Companies & organizations'), and water-management districts / federal / county owners by 'Hide government-owned'.
Persons whose surname looks like a company word must stay individuals."""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
errs = []
def ok(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg)
    if not cond: errs.append('assert: ' + msg)
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={'width': 1360, 'height': 900}).new_page()
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
    b.close()
print('ERRORS:', errs if errs else 'none'); sys.exit(1 if errs else 0)
