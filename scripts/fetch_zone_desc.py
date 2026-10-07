#!/usr/bin/env python3
"""Look up the Property Appraiser's description for every PRIMARY_ZONE code on the roll.
The GIS layer only carries the 4-digit code, so for each distinct code we ask the PA's public
property-search service about ONE sample folio (about 270 polite, sequential requests)."""
import json, os, sys, time, requests, pandas as pd
RAW = sys.argv[1] if len(sys.argv) > 1 else '/workspace/raw'
API = 'https://apps.miamidadepa.gov/PApublicServiceProxy/PaServicesProxy.ashx'
out_fn = f'{RAW}/zone_desc.json'
out = json.load(open(out_fn)) if os.path.exists(out_fn) else {}
df = pd.read_parquet(f'{RAW}/pagis.parquet', columns=['FOLIO', 'PRIMARY_ZONE'])
df = df[df.FOLIO.notna() & df.PRIMARY_ZONE.notna()]
samples = df.groupby('PRIMARY_ZONE').FOLIO.apply(lambda s: list(s.head(3)))
for code, folios in samples.items():
    if code in out: continue
    for f in folios:
        try:
            d = requests.get(API, params={'Operation': 'GetPropertySearchByFolio', 'clientAppName': 'PropertySearch', 'folioNumber': f},
                             headers={'User-Agent': 'Mozilla/5.0 (parcel-finder data build)'}, timeout=30).json()
            pi = d.get('PropertyInfo') or {}
            if pi.get('PrimaryZone') == code and pi.get('PrimaryZoneDescription') is not None:
                out[code] = pi['PrimaryZoneDescription'].strip(); break
        except Exception as e:
            print('err', code, f, e)
        time.sleep(0.3)
    print(code, out.get(code), flush=True)
    json.dump(out, open(out_fn, 'w'), indent=0)
print('done', len(out), 'of', len(samples))
