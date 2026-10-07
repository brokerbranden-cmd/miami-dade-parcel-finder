#!/usr/bin/env python3
"""Scheduled foreclosure and tax-deed sales from the Miami-Dade online auction site (RealAuction).

Source: https://www.miamidade.realforeclose.com  (public, no login; Miami-Dade runs BOTH foreclosure and tax-deed
sales on this one site, miamidade.realtaxdeed.com answers 403). Scraped politely: the calendar page for the current
month + 3 ahead, then each sale day's preview list (the page's own AJAX 'UPDATE/LOAD' JSON), ~1 request/second.
Output: RAW/auctions.json  [{date, type, case, cert, folio, address, city, judgment, opening_bid, assessed, status, aid, url}]
"""
import json, re, sys, time, html, datetime as dt, requests

B = 'https://www.miamidade.realforeclose.com/index.cfm'
RAW = sys.argv[1] if len(sys.argv) > 1 else '/workspace/raw'
s = requests.Session(); s.headers['User-Agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0 Safari/537.36 (parcel-finder; weekly refresh)'
# the item HTML is compressed with @-codes the site's JS expands
CODES = {'@A': '<div class="', '@B': '</div>', '@C': 'class="', '@D': '<div>', '@E': 'AUCTION', '@F': '</th><td', '@G': '</td></tr>', '@H': '<tr><th ', '@I': 'table', '@J': 'p_back="NextCheck='}

def expand(t):
    for k, v in CODES.items(): t = t.replace(k, v)
    return t

def get(params):
    for i in range(3):
        try:
            r = s.get(B, params=params, timeout=40); r.raise_for_status(); time.sleep(1.0); return r.text
        except Exception as e:
            print('retry', params, e); time.sleep(5)
    return ''

def days():
    out = set(); m = dt.date.today().replace(day=1)
    for i in range(4):
        t = get({'zaction': 'USER', 'zmethod': 'CALENDAR', 'selCalDate': m.strftime('%m/%d/%Y')})
        for d, kind in re.findall(r"dayid='(\d\d/\d\d/\d{4})'\s*>.*?CALTEXT'>([^<]+)<", t, re.S):
            out.add((d, kind.strip()))
        m = (m + dt.timedelta(days=32)).replace(day=1)
    return sorted(out, key=lambda x: dt.datetime.strptime(x[0], '%m/%d/%Y'))

def items(day):
    get({'zaction': 'AUCTION', 'Zmethod': 'PREVIEW', 'AUCTIONDATE': day})
    res = []
    for area in ('W', 'C'):  # W = waiting/scheduled, C = closed/canceled
        seen = set(); pagedir = 0
        for page in range(60):
            t = get({'zaction': 'AUCTION', 'Zmethod': 'UPDATE', 'FNC': 'LOAD', 'AREA': area, 'PageDir': pagedir, 'doR': 1 if pagedir == 0 else 0, 'tx': int(time.time() * 1000), 'bypassPage': 0})
            try: j = json.loads(t.strip())
            except Exception: break
            h = expand(j.get('retHTML') or '')
            blocks = re.split(r'(?=<div id="AITEM_)', h)
            new = 0
            for b in blocks:
                m = re.match(r'<div id="AITEM_(\d+)"', b)
                if not m or m.group(1) in seen: continue
                seen.add(m.group(1)); new += 1
                f = {}
                for lab, val in re.findall(r'<th [^>]*>([^<]*):?</th><td[^>]*>(.*?)</td></tr>', b, re.S):
                    f[lab.strip().rstrip(':')] = html.unescape(re.sub(r'<[^>]+>', '', val)).strip()
                cityrow = re.findall(r'scope="row"></th><td[^>]*>(.*?)</td>', b)
                st = [x for x in re.findall(r'ASTAT_MSG[BD] Astat_DATA">(.*?)</div>', b) if x.strip()]
                folio = re.sub(r'\D', '', f.get('Parcel ID', ''))
                res.append({'date': day, 'type': f.get('Auction Type', ''), 'case': f.get('Case #', ''), 'cert': f.get('Certificate #', ''),
                            'folio': folio, 'address': f.get('Property Address', ''), 'city': cityrow[0].strip() if cityrow else '',
                            'judgment': f.get('Final Judgment Amount', ''), 'opening_bid': f.get('Opening Bid', ''), 'assessed': f.get('Assessed Value', ''),
                            'status': 'scheduled' if area == 'W' else (re.sub('<[^>]+>', '', st[0]).strip() if st else 'closed'),
                            'aid': m.group(1), 'url': f'{B}?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={day}'})
            if not new: break
            pagedir = 1
    return res

if __name__ == '__main__':
    ds = days(); print('sale days', ds)
    out = []
    for d, kind in ds:
        it = items(d); print(d, kind, len(it), flush=True); out += it
    json.dump({'pulled': dt.datetime.now().isoformat(timespec='minutes'), 'source': 'https://www.miamidade.realforeclose.com', 'items': out}, open(f'{RAW}/auctions.json', 'w'))
    print('total', len(out))
