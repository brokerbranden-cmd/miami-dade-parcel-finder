#!/usr/bin/env python3
"""Miami-Dade Tax Collector public real-estate reports (Grant Street TaxSys "shared reports"), downloaded as CSV.

Source: https://miamidade.county-taxes.com/govhub/reports/real-estate  (also framed at county-taxes.net/fl-miamidade/reports/real-estate)
Public, no login, but there is no plain-URL export: each report is run in the page (headless Chrome) and its own
"Download CSV" button is used. 3 reports, one page load each.
  Public-Open Certificates wAddr   every outstanding (unredeemed) tax certificate: tax year, face amount, holder, address
  Public-unpaid accts non-cert     unpaid accounts not (yet) sold as certificates (current-year delinquents, deferrals)
  Public-Open Deeds                open tax-deed applications (applied / certified / scheduled sale date)
Output: RAW/tax/<report>.csv
"""
import os, sys, time
from playwright.sync_api import sync_playwright

RAW = sys.argv[1] if len(sys.argv) > 1 else '/workspace/raw'
URL = 'https://miamidade.county-taxes.com/govhub/reports/real-estate'
REPORTS = ['Public-Open Certificates wAddr', 'Public-unpaid accts non-cert', 'Public-Open Deeds']

def run(pg, name, out):
    pg.goto(URL, wait_until='networkidle', timeout=120000)
    pg.fill('#selected-report-filter', name); time.sleep(1)
    items = pg.locator('#selected-report-filter-menu a.dropdown-item')
    for i in range(items.count()):
        if items.nth(i).inner_text().strip() == name:
            items.nth(i).dispatch_event('mousedown'); break
    else:
        raise RuntimeError('report not listed: ' + name)
    pg.wait_for_load_state('networkidle'); time.sleep(2)
    pg.locator('button:has-text("Search")').last.click(); pg.wait_for_load_state('networkidle')
    pg.wait_for_selector('text=search results found', timeout=180000)
    with pg.expect_download(timeout=600000) as d:
        pg.evaluate('download_report()')  # default format is CSV
    d.value.save_as(out)

if __name__ == '__main__':
    os.makedirs(f'{RAW}/tax', exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, executable_path='/usr/bin/google-chrome' if os.path.exists('/usr/bin/google-chrome') else None, args=['--no-sandbox'])
        pg = b.new_page(accept_downloads=True, viewport={'width': 1300, 'height': 1000},
                        user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36')
        for name in REPORTS:
            out = f'{RAW}/tax/{name}.csv'
            try:
                run(pg, name, out); print(name, os.path.getsize(out), 'bytes', flush=True)
            except Exception as e:
                print('FAILED', name, str(e)[:200], '(keeping previous file if any)')
            time.sleep(3)
        b.close()
