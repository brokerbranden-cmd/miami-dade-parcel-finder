#!/usr/bin/env python3
"""Discover candidate city zoning FeatureServers for Broward (ArcGIS Online search) -> $RAW/broward/zoning_candidates.json (features, extent, fields)."""
import requests, json, os, re
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'broward')
CITIES = ['Fort Lauderdale','Hollywood','Pompano Beach','Coral Springs','Pembroke Pines','Miramar','Davie','Plantation','Sunrise','Deerfield Beach','Lauderhill','Weston','Coconut Creek','Margate','Tamarac','Oakland Park','Wilton Manors','Dania Beach','Hallandale Beach','Lauderdale Lakes','North Lauderdale','Cooper City','Parkland','Lighthouse Point','Lauderdale-by-the-Sea','Hillsboro Beach','Sea Ranch Lakes','Southwest Ranches','Pembroke Park','West Park','Oakland Park']
cand = {}
for c in CITIES:
    for q in (f'"{c}" zoning districts', f'{c} FL zoning'):
        try: r = requests.get('https://www.arcgis.com/sharing/rest/search', params={'q': q + ' type:"Feature Service"', 'num': 10, 'f': 'json'}, timeout=30).json()
        except Exception as e: print('ERR', q, e); continue
        for x in r.get('results', []):
            t = (x.get('title') or '') + ' ' + (x.get('snippet') or '') + ' ' + ' '.join(x.get('tags') or [])
            if 'zon' not in t.lower(): continue
            ext = x.get('extent') or []
            if ext and not (-80.6 < (ext[0][0] + ext[1][0]) / 2 < -79.9 and 25.8 < (ext[0][1] + ext[1][1]) / 2 < 26.45): continue
            cand.setdefault(x['url'], {'title': x['title'], 'owner': x['owner'], 'city_q': c, 'modified': x.get('modified'), 'url': x['url']})
print(len(cand))
out = []
for u, d in cand.items():
    try:
        j = requests.get(u + '?f=json', timeout=30).json()
        for l in j.get('layers', [])[:6]:
            lj = requests.get(f'{u}/{l["id"]}?f=json', timeout=30).json()
            cn = requests.get(f'{u}/{l["id"]}/query', params={'where': '1=1', 'returnCountOnly': 'true', 'f': 'json'}, timeout=30).json().get('count')
            e = lj.get('extent') or {}
            out.append({**d, 'layer': l['id'], 'lname': l['name'], 'geom': lj.get('geometryType'), 'count': cn, 'fields': [f['name'] for f in lj.get('fields', [])][:30], 'extent': [e.get('xmin'), e.get('ymin'), e.get('xmax'), e.get('ymax')], 'sr': (e.get('spatialReference') or {}).get('latestWkid')})
            print(d['city_q'], '|', d['title'], '|', l['name'], '|', cn, '|', lj.get('geometryType'), flush=True)
    except Exception as e: print('ERR', u, str(e)[:80])
json.dump(out, open(os.path.join(RAW, 'zoning_candidates.json'), 'w'), indent=0)
