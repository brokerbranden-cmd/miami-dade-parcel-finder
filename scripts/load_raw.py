#!/usr/bin/env python3
"""Combine raw PaGis chunks into one parquet file (raw/pagis.parquet)."""
import glob, json, sys, pandas as pd
RAW = sys.argv[1] if len(sys.argv) > 1 else '/workspace/raw'
rows = []
for fn in sorted(glob.glob(f'{RAW}/pagis/chunk_*.json')):
    for f in json.load(open(fn)):
        a = f['attributes']; g = f.get('geometry') or {}
        a['LON'] = g.get('x'); a['LAT'] = g.get('y'); rows.append(a)
df = pd.DataFrame(rows)
print(len(df), df.FOLIO.nunique())
df.to_parquet(f'{RAW}/pagis.parquet', index=False)
