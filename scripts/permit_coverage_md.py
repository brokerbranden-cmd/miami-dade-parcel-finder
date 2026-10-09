#!/usr/bin/env python3
"""Rewrite the per-city permit / code coverage tables in README.md (between the PERMIT_COVERAGE markers) from RAW/permit_index.json + permit_catalog.py."""
import json, os, re, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import permit_lib
RAW = sys.argv[1] if len(sys.argv) > 1 else '/workspace/raw'
cov, idx = permit_lib.coverage(RAW)
src = {}
for r in idx['sources']: src.setdefault((r['muni'], r['kind']), []).append(r)
lv = {'full': '8+ yrs', 'half': '5-8 yrs', 'recent': '<5 yrs', 'none': 'none'}
L = ['| City | Permits | Code cases | Records ingested (permits / code) | Folio+address match | Source |', '|---|---|---|---|---|---|']
def agg(m, kind):
    rs = src.get((m, kind), []); n = sum(r['records'] for r in rs); mt = sum(r['matched_folio'] + r['matched_address'] for r in rs)
    return n, (mt / n if n else 0)
for m, c in sorted(cov.items(), key=lambda x: x[1]['city']):
    if c['status'] != 'api': continue
    pn, pr = agg(m, 'permit'); cn, cr = agg(m, 'code')
    pt = f"since {c['permit_from'][:4]} ({lv[c['permit_level']]})" if c['permit_from'] else 'none usable'
    ct = f"since {c['code_from'][:4]}" if c['code_from'] else 'none usable'
    L.append(f"| {c['city']} | {pt} | {ct} | {pn:,} / {cn:,} | {pr:.0%} / {cr:.0%} | [{c['tech'].split(' (')[0]}]({c['portal']}) |")
api = '\n'.join(L)
L = ['| City | Why not ingested | Portal |', '|---|---|---|']
for m, c in sorted(cov.items(), key=lambda x: x[1]['city']):
    if c['status'] == 'api': continue
    L.append(f"| {c['city']} | {c['reason']} | {('[' + c['tech'] + '](' + c['portal'] + ')') if c['portal'] else c['tech']} |")
none = '\n'.join(L)
body = f"<!-- PERMIT_COVERAGE -->\nBuilt {idx.get('built','')}. Window = first year from which the source holds >= 40% of its recent yearly volume.\n\n**Ingested**\n\n{api}\n\n**No machine-readable public source** (not scored, shown in the drawer and the coverage table)\n\n{none}\n<!-- /PERMIT_COVERAGE -->"
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'README.md'); s = open(p).read()
s = re.sub(r'<!-- PERMIT_COVERAGE -->.*?<!-- /PERMIT_COVERAGE -->', lambda m: body, s, flags=re.S) if '<!-- PERMIT_COVERAGE -->' in s else s
open(p, 'w').write(s); print(body)
