#!/usr/bin/env python3
"""Recent arm's-length sales for the card value estimate -> data/comps.json.gz (lazy-loaded by app.js).
Source: Miami-Dade PA roll (RAW/pagis.parquet from fetch_pagis.py), sale slots DOS/PRICE/QU_FLG 1-3.
Kept: qualified (Q = arm's-length per the PA), price >= $1,000, recorded in the last MONTHS months, and not a multi-parcel deed
(sale 1 shares its OR book/page with another folio). Cash vs financed is not in the roll: cash = -1 (unknown) until Clerk
deed + mortgage records are joined (Clerk daily files are a paid subscription; see README).
usage: RAW=/workspace/raw build_comps.py data [MONTHS]
"""
import gzip, json, os, sys, datetime as dt
import pandas as pd, numpy as np

RAW = os.environ.get('RAW', '/workspace/raw'); OUT = sys.argv[1] if len(sys.argv) > 1 else 'data'
MONTHS = int(sys.argv[2]) if len(sys.argv) > 2 else 6
today = dt.date.today(); m = today.month - MONTHS; y = today.year + (m - 1) // 12; m = (m - 1) % 12 + 1
cut = int(dt.date(y, m, min(today.day, 28)).strftime('%Y%m%d'))
COMM_MONTHS = int(os.environ.get('COMM_MONTHS', 24))  # commercial / industrial (DOR 10xx-49xx) sell rarely: longer window
m = today.month - COMM_MONTHS; y = today.year + (m - 1) // 12; m = (m - 1) % 12 + 1
cutC = int(dt.date(y, m, min(today.day, 28)).strftime('%Y%m%d'))
cols = ['FOLIO', 'TRUE_SITE_ADDR', 'DOR_CODE_CUR', 'BUILDING_HEATED_AREA', 'LOT_SIZE', 'LAT', 'LON', 'REFERENCE_ONLY_FLAG',
        'DOS_1', 'PRICE_1', 'QU_FLG_1', 'OR_BK_1', 'OR_PG_1', 'DOS_2', 'PRICE_2', 'QU_FLG_2', 'DOS_3', 'PRICE_3', 'QU_FLG_3']
d = pd.read_parquet(f'{RAW}/pagis.parquet', columns=cols)
d['FOLIO'] = d.FOLIO.astype(str).str.zfill(13)
comm = pd.to_numeric(d.DOR_CODE_CUR.astype(str).str.zfill(4).str[:2], errors='coerce').between(10, 49)
d = d[d.LAT.between(24, 27) & d.LON.between(-82, -79)]
bp = d.OR_BK_1.astype(str) + '/' + d.OR_PG_1.astype(str)
multi = set(bp[bp.duplicated(keep=False) & d.OR_BK_1.notna()].index)
rows, drop = [], {'multi_parcel': 0}
for k in (1, 2, 3):
    s = d[[f'DOS_{k}', f'PRICE_{k}', f'QU_FLG_{k}']].copy(); s.columns = ['dos', 'price', 'q']
    s['dos'] = pd.to_numeric(s.dos, errors='coerce')
    ok = (s.q == 'Q') & (s.price >= 1000) & ((s.dos >= cut) | (comm & (s.dos >= cutC)))
    if k == 1: drop['multi_parcel'] += int((ok & s.index.isin(multi)).sum()); ok &= ~s.index.isin(multi)
    x = d[ok]; s = s[ok]
    for f, a, lu, sf, lot, la, lo, dos, pr in zip(x.FOLIO, x.TRUE_SITE_ADDR.fillna(''), x.DOR_CODE_CUR.astype(str).str.zfill(4), x.BUILDING_HEATED_AREA.fillna(0),
                                                  x.LOT_SIZE.fillna(0), x.LAT, x.LON, s.dos, s.price):
        rows.append([f, int(round(la * 1e5)), int(round(lo * 1e5)), int(dos), int(pr), int(sf), int(lot), lu, -1, 'R', a.strip()])
rows.sort(key=lambda r: (-r[3], r[0]))
seen, out = set(), []
for r in rows:
    k = (r[0], r[3])
    if k in seen: continue
    seen.add(k); out.append(r)
meta = {'built': today.isoformat(), 'cutoff': cut, 'months': MONTHS, 'commMonths': COMM_MONTHS, 'commCutoff': cutC, 'nComm': sum(1 for r in out if 10 <= int(r[7][:2]) <= 49), 'n': len(out), 'newest': out[0][3] if out else 0, 'dropped': drop,
        'source': 'Miami-Dade Property Appraiser roll qualified (arm\'s-length) sales', 'cash_known': 0,
        'cols': ['folio', 'lat5', 'lon5', 'date', 'price', 'sqft', 'lot', 'lu', 'cash', 'src', 'addr']}
json.dump({'meta': meta, 'rows': out}, gzip.open(os.path.join(OUT, 'comps.json.gz'), 'wt'), separators=(',', ':'))
print(json.dumps(meta), os.path.getsize(os.path.join(OUT, 'comps.json.gz')))
