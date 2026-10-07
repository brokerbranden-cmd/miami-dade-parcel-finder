#!/usr/bin/env python3
"""Top new / high-score distress leads since a date -> CSV + simple HTML email body.

Usage: python3 scripts/top_leads.py --since 2026-10-01 [--min 40] [--limit 50] [--out out/leads]
A lead is "new" when one of its signal records has an event date >= since, or was first seen by
build_distress.py on/after since (records present at the very first build don't count as new).
Use --all to ignore newness and just rank by score. Nothing is sent; it only writes files.
"""
import argparse, gzip, html, json, os, sys
import pandas as pd
ap = argparse.ArgumentParser()
ap.add_argument('--since', required=True); ap.add_argument('--min', type=int, default=40)
ap.add_argument('--limit', type=int, default=50); ap.add_argument('--out', default='out/top_leads')
ap.add_argument('--all', action='store_true')
o = ap.parse_args()
RAW = os.environ.get('RAW', '/workspace/raw'); ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(gzip.open(f'{ROOT}/data/distress.json.gz'))
names = {s[0]: s[1] for s in d['sig']}; fb = d.get('firstBuild', '')
sc = pd.read_parquet(f'{RAW}/scores.parquet'); sc['FOLIO'] = sc['FOLIO'].astype(str)
sc = sc[sc.dscore >= o.min]
rows = []
for f, s in zip(sc.FOLIO, sc.dscore):
    recs = d['recs'].get(f, [])
    new = [r for r in recs if (r[1] or '') >= o.since or ((r[7] or '') >= o.since and (r[7] or '') > fb)]
    if not o.all and not new: continue
    rows.append((f, int(s), recs, new))
rows.sort(key=lambda r: (-r[1], -len(r[3])))
rows = rows[:o.limit]
pa = pd.read_parquet(f'{RAW}/pagis.parquet', columns=['FOLIO','TRUE_SITE_ADDR','TRUE_SITE_UNIT','TRUE_SITE_CITY','TRUE_SITE_ZIP_CODE','TRUE_OWNER1','TOTAL_VAL_CUR'])
pa['FOLIO'] = pa['FOLIO'].astype(str); pa = pa[pa.FOLIO.isin([r[0] for r in rows])].set_index('FOLIO')
out = []
for f, s, recs, new in rows:
    p = pa.loc[f] if f in pa.index else None
    addr = '' if p is None else ' '.join(str(x) for x in [p.TRUE_SITE_ADDR, p.TRUE_SITE_UNIT] if isinstance(x,str) and x).strip()
    out.append({'Address': addr, 'City': '' if p is None else p.TRUE_SITE_CITY, 'Zip': '' if p is None else p.TRUE_SITE_ZIP_CODE,
        'Folio': f, 'Score': s, 'Signals': '; '.join(sorted({names.get(r[0], r[0]) for r in recs})),
        'New since': '; '.join(f"{r[0]} {r[1]} {r[4]}" for r in new),
        'Value': '' if p is None else int(p.TOTAL_VAL_CUR or 0), 'Owner': '' if p is None else p.TRUE_OWNER1,
        'PA link': f'https://apps.miamidadepa.gov/propertysearch/#/?folio={f}',
        'Source links': ' '.join(list(dict.fromkeys(r[5] for r in sorted(recs,key=lambda r:r[0] not in {x[0] for x in new}) if r[5]))[:5])})
os.makedirs(os.path.dirname(o.out) or '.', exist_ok=True)
pd.DataFrame(out).to_csv(o.out + '.csv', index=False)
e = html.escape
tr = ''.join(f"<tr><td><b>{x['Score']}</b></td><td><a href='{e(x['PA link'])}'>{e(x['Address'])}</a><br><small>{e(str(x['City']))} · {x['Folio']}</small></td>"
             f"<td>{e(x['Signals'])}<br><small>{e(x['New since'])}</small></td><td>${x['Value']:,}</td><td>{e(str(x['Owner']))}</td></tr>" for x in out if True)
body = (f"<html><body style='font-family:Arial,sans-serif'><h2>Top distress leads since {e(o.since)}</h2>"
        f"<p>{len(out)} parcels, score ≥ {o.min}. Data built {e(d.get('built',''))}.</p>"
        "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;font-size:13px'>"
        f"<tr><th>Score</th><th>Property</th><th>Signals (new)</th><th>Value</th><th>Owner</th></tr>{tr}</table>"
        "<p><a href='https://brokerbranden-cmd.github.io/miami-dade-parcel-finder/#ds=50&sort=ds_d'>Open Hottest leads in Parcel Finder</a></p></body></html>")
open(o.out + '.html', 'w').write(body)
print(f'{len(out)} leads -> {o.out}.csv / {o.out}.html')
