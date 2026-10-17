#!/usr/bin/env python3
"""Scheduled foreclosure + tax-deed sales from a county's RealAuction sites (public, no login, ~1 req/s): reuses scripts/fetch_auctions.py with another host.
usage: fetch_auctions_fl.py <county-id> <host-foreclose> <host-taxdeed>   e.g. broward https://www.broward.realforeclose.com https://www.broward.realtaxdeed.com
Output: $RAW/<county>/auctions.json {pulled, source, items:[{date,type,case,cert,folio,address,city,judgment,opening_bid,assessed,...}]}  (items[].src = 'foreclosure'|'taxdeed')"""
import sys, os, json, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
import fetch_auctions as FA
cid, hosts = sys.argv[1], sys.argv[2:]
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), cid); os.makedirs(RAW, exist_ok=True)
out = []
for h, src in zip(hosts, ('foreclosure', 'taxdeed')):
    FA.B = h.rstrip('/') + '/index.cfm'
    try: ds = FA.days()
    except Exception as e: print('days failed', h, e); continue
    print(src, 'sale days', len(ds), ds[:6], flush=True)
    for d, kind in ds:
        it = FA.items(d); print(src, d, kind, len(it), flush=True)
        for x in it: x['src'] = src; out.append(x)
json.dump({'pulled': dt.datetime.now().isoformat(timespec='minutes'), 'source': hosts, 'items': out}, open(f'{RAW}/auctions.json', 'w'))
print('total', len(out))
