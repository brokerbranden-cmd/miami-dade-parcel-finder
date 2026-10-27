#!/usr/bin/env python3
"""Fort Lauderdale permits from LauderBuild (Accela Citizen Access, public record search, no login) -> $RAW/broward/permits/ftl_accela/<YYMM>.csv
Why: the city's ArcGIS BuildingPermits layer stopped updating on 2026-03-16 (still served, frozen at the source). LauderBuild record numbers
embed YYMM (BLD-ROOF-26100001), so a record-number search '%-YYMM%' + the grid's 'Download results' gives one month per export (~1 min).
Usage: fetch_ftl_lauderbuild.py [YYMM ...]   default = previous + current month (weekly), and any month since 2603 not yet saved.
Headless Chromium (ACA rejects plain HTTP posts as CSRF). Broward only."""
import os, sys, time, datetime as dt
from playwright.sync_api import sync_playwright
OUT = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'broward', 'permits', 'ftl_accela'); os.makedirs(OUT, exist_ok=True)
U = 'https://aca-prod.accela.com/FTL/Cap/CapHome.aspx?module=Permits&TabName=Permits'
def months():
    t = dt.date.today(); p = (t.replace(day=1) - dt.timedelta(days=1))
    m = {t.strftime('%y%m'), p.strftime('%y%m')}; d = dt.date(2026, 3, 1)
    while d <= t:
        if not os.path.exists(f'{OUT}/{d:%y%m}.csv'): m.add(f'{d:%y%m}')
        d = (d + dt.timedelta(days=32)).replace(day=1)
    return sorted(m)
todo = sys.argv[1:] or months(); errs = 0
with sync_playwright() as p:
    b = p.chromium.launch()
    for ym in todo:
        for tr in range(3):
            try:
                pg = b.new_page(accept_downloads=True); pg.goto(U, timeout=120000)
                pg.fill('#ctl00_PlaceHolderMain_generalSearchForm_txtGSPermitNumber', f'%-{ym}%')
                pg.click('#ctl00_PlaceHolderMain_btnNewSearch'); pg.wait_for_load_state('networkidle', timeout=120000)
                with pg.expect_download(timeout=600000) as d:
                    pg.click('#ctl00_PlaceHolderMain_dgvPermitList_gdvPermitList_gdvPermitListtop4btnExport')
                d.value.save_as(f'{OUT}/{ym}.csv.part'); os.replace(f'{OUT}/{ym}.csv.part', f'{OUT}/{ym}.csv'); pg.close()
                print(ym, 'ok', sum(1 for _ in open(f'{OUT}/{ym}.csv')) - 1, 'rows', flush=True); break
            except Exception as e:
                print(ym, 'try', tr, 'failed', str(e)[:200], flush=True); time.sleep(30 * (tr + 1))
        else: errs += 1
    b.close()
sys.exit(1 if errs else 0)
