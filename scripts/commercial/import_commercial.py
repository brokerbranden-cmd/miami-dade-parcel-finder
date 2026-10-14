#!/usr/bin/env python3
"""Miami-Dade rows of the commercial distress list -> data/commercial.json.gz (keyed by 13-digit folio)."""
import sys, json, gzip, re, datetime
import pandas as pd
src, out = sys.argv[1], sys.argv[2]
d = pd.read_csv(src, dtype=str).fillna('')
d = d[d.county == 'Miami-Dade']
def num(v):
    try: return round(float(v), 2)
    except Exception: return None
def ent(s):
    if s.startswith('Active/Inactive'): return 'Mixed'
    if s.startswith('Active'): return 'Active'
    if s.startswith('Inactive - domestic'): return 'Dissolved'
    if s.startswith('Inactive'): return 'Inactive'
    if s.startswith('Not found'): return 'Not found'
    return ''
rows = {}
for r in d.itertuples():
    f = re.sub(r'\D', '', r.folio_parcel_id)
    if len(f) != 13: continue
    x = dict(s=int(float(r.distress_score or 0)), t=r.property_type, cat=r.signal_categories,
             gas=1 if 'Closed gas station' in r.all_signals else 0, ent=ent(r.owner_entity_status), entSrc=r.owner_entity_source[:200])
    if r.tax_data_basis.startswith('LIVE'):
        x.update(due=num(r.amount_due_now) or 0, lpy=r.last_paid_year or '', npo=num(r.not_payable_online_amount),
                 chk=(r.tax_status_checked_at or '')[:10], yrs=num(r.years_delinquent), certs=r.certificates_outstanding[:160],
                 tda=r.tax_deed_application[:120])
    rows[f] = x
meta = dict(built=datetime.date.today().isoformat(), n=len(rows), source='Commercial Data bot list (build3 scoring), live tax via county-taxes.net reader')
json.dump(dict(meta=meta, rows=rows), gzip.open(out, 'wt'), separators=(',', ':'))
print(f"commercial: {len(rows)} Miami-Dade folios, live tax {sum('chk' in v for v in rows.values())}, closed gas {sum(v['gas'] for v in rows.values())}, entity {sum(bool(v['ent']) for v in rows.values())}")
