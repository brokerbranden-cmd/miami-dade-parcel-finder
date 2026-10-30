"""Headless e2e (also the live check after deploy): the owner names Branden reported under 'Individuals (not a company)' on Oct 30, 2026
are companies in the app, in the county that has them, and surname-only look-alikes stay individuals.
    python3 tests/e2e_orgname.py http://localhost:8080/ [desktop|mobile]"""
import sys, re
from urllib.parse import quote
from playwright.sync_api import sync_playwright
import legacy_ui  # noqa: F401
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'desktop'
CHECKS = {'broward': (['AMERICAN EXPRESS TRAVEL', 'SOUTHERN SHORES ACQUISITIONS', 'FLORIDA EASTERN ECCLESIASTICAL'], []),
          'miami-dade': (['VOLUNTEERS OF AMERICA', 'THE MOST REVEREND'], ['JOHN BANK'])}
errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + m)
    if not c: errs.append(m)
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={'width': 390, 'height': 844} if MODE == 'mobile' else {'width': 1360, 'height': 900}).new_page()
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    def hsearch(h):
        r0 = pg.evaluate('PF.runN()'); pg.evaluate(f"location.hash={h!r}")
        try: pg.wait_for_function(f'PF.runN()>{r0}', timeout=20000)
        except Exception: pass
        pg.wait_for_timeout(600); return pg.evaluate('PF.auditRows(5000)')
    for county, (companies, people) in CHECKS.items():
        pg.goto(URL + '?county=' + county); pg.wait_for_function('window.PF_READY', timeout=240000); pg.wait_for_timeout(1500)
        fx = pg.evaluate('PF.okFix()'); ok(fx[0] and fx[0]['fixed'] > 0, f'{county}: app reclassified {fx[0] and fx[0]["fixed"]} owner names on load')
        for q in companies:
            p_, c_ = hsearch('#owner=person&q=' + quote(q)), hsearch('#owner=corp&q=' + quote(q))
            ok(p_['n'] == 0 and c_['n'] > 0, f"{county} '{q}': Individuals={p_['n']} Companies&orgs={c_['n']}")
        for q in people:
            p_, a_ = hsearch('#owner=person&q=' + quote(q)), hsearch('#q=' + quote(q))
            ok(p_['n'] > 0 and p_['n'] == a_['n'], f"{county} '{q}': Individuals={p_['n']} all={a_['n']} (a person, stays an individual)")
    b.close()
print('ERRORS:', errs if errs else 'none'); sys.exit(1 if errs else 0)
