#!/usr/bin/env python3
"""Pull Miami-Dade Clerk Official Records (public Standard Search -> Name/Document) by document type and date.

Source: https://onlineservices.miamidadeclerk.gov/officialrecords/  (no login needed for Name/Document search)
There is no public bulk API: the site's JSON endpoints (api/home/standardsearch -> api/SearchResults/getStandardRecords)
only answer a search submitted from the page itself (per-search reCAPTCHA/Turnstile header), so this drives the real
page with headless Chrome (Playwright), one search at a time, and saves the JSON the page loads.
Results are capped at 500 rows per search, so ranges that hit the cap are split in half until they fit.
Each finished (doctype, range) is cached in RAW/clerk/<code>/<from>_<to>.json, so reruns only fetch new days.

usage: fetch_clerk.py RAW [--days N] [--types LIS,CLP,...]
"""
import json, os, sys, time, argparse
from datetime import date, timedelta
from playwright.sync_api import sync_playwright

URL = "https://onlineservices.miamidadeclerk.gov/officialrecords/"
TYPES = {  # code -> (label in the dropdown, default look-back days, initial chunk days)
    'LIS': ('LIS PENDENS - LIS', 540, 1),
    'CLP': ('CANCELLATION OF LIS PENDENS - CLP', 540, 3),
    'FTL': ('FEDERAL TAX LIEN - FTL', 540, 14),
    'LIE': ('LIEN - LIE', 365, 3),
    'PAD': ('PROBATE & ADMINISTRATION - PAD', 540, 14),
    'DCE': ('DEATH CERTIFICATE (EST OF) - DCE', 540, 14),
}
CAP = 500

def run_search(browser, label, a, b):
    ctx = browser.new_context(viewport={"width": 1300, "height": 900},
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
    pg = ctx.new_page(); pg.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    pg.set_default_timeout(60000)
    got = {'rec': None, 'std': None}
    def on_resp(r):
        try:
            if 'getStandardRecords' in r.url: got['rec'] = r.json()
            elif 'standardsearch' in r.url: got['std'] = r.json()
        except Exception: pass
    try:
        pg.on('response', on_resp)
        pg.goto(URL, wait_until="domcontentloaded", timeout=90000); time.sleep(1)
        pg.locator("text=Name/Document").first.click(); pg.wait_for_selector("#documentType")
        pg.select_option("#documentType", label=label)
        pg.fill("#dateRangeFrom", a.isoformat()); pg.fill("#dateRangeTo", b.isoformat())
        pg.locator("button:has-text('SEARCH')").first.click()
        t0 = time.time()
        while time.time() - t0 < 45:
            if got['rec'] is not None: break
            if got['std'] is not None and (not got['std'].get('isValidSearch') or 'No results found' in pg.inner_text('body')): break
            time.sleep(0.4)
        if got['rec'] is not None:
            return got['rec'].get('recordingModels') or []
        if got['std'] is not None and 'No results found' in pg.inner_text('body'):
            return []
        pg.screenshot(path='/tmp/clerk_fail.png')
        raise RuntimeError(f'search failed {label} {a}..{b}: {got["std"]} | ' + pg.inner_text('body')[:300].replace(chr(10),' '))
    finally:
        ctx.close()

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('raw'); ap.add_argument('--days', type=int); ap.add_argument('--types', default=','.join(TYPES))
    ap.add_argument('--until', default=None, help='last day (default: today)')
    o = ap.parse_args()
    end = date.fromisoformat(o.until) if o.until else date.today()
    with sync_playwright() as p:
        br = p.chromium.launch(headless=not os.environ.get('DISPLAY'), executable_path="/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None,
                               args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"])
        for code in o.types.split(','):
            label, back, chunk = TYPES[code]
            d = os.path.join(o.raw, 'clerk', code); os.makedirs(d, exist_ok=True)
            start = end - timedelta(days=back if o.days is None else o.days)
            todo = []; a = start
            while a <= end:
                todo.append((a, min(a + timedelta(days=chunk - 1), end))); a += timedelta(days=chunk)
            fails = 0
            while todo:
                a, b = todo.pop(0)
                if chunk == 1 and a.weekday() >= 5: continue  # recorder is closed on weekends
                f = os.path.join(d, f'{a}_{b}.json')
                recent = (end - b).days < 7  # re-pull the last week (index lags a few days)
                if os.path.exists(f) and not recent: continue
                try:
                    m = run_search(br, label, a, b)
                except Exception as e:
                    print('  fail', code, a, b, str(e)[:150], flush=True); fails += 1
                    if fails > 25: print('too many failures, stopping', code); break
                    time.sleep(5); continue
                if len(m) >= CAP and b > a:
                    mid = a + (b - a) // 2
                    todo[:0] = [(a, mid), (mid + timedelta(days=1), b)]; print(f'  split {code} {a}..{b}', flush=True); continue
                json.dump({'code': code, 'from': str(a), 'to': str(b), 'capped': len(m) >= CAP, 'n': len(m), 'pulled': time.strftime('%Y-%m-%d %H:%M'), 'models': m}, open(f, 'w'))
                print(f'{code} {a}..{b} n={len(m)}', flush=True)
                time.sleep(1.5)  # be polite
        br.close()

if __name__ == '__main__':
    main()
