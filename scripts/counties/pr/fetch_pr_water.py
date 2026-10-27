#!/usr/bin/env python3
"""Puerto Rico waterfront inputs (public ODbL OpenStreetMap data):
 1. marine water: osmdata.openstreetmap.de water-polygons-split-4326 (OSM coastline) clipped to PR -> OUT/marine_pr.gpkg
    (reuses a cached zip from $WATERZIP when present, otherwise downloads it)
 2. inland water: OSM natural=water / landuse=reservoir / waterway=riverbank polygons and waterway=river|canal|stream|drain|ditch
    lines from the Overpass API -> OUT/inland_pr.json"""
import os, sys, json, time, requests
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
BBOX = (-68.0, 17.85, -65.2, 18.6); H = {'User-Agent': 'parcel-finder/1.0 (public data research)'}
z = os.environ.get('WATERZIP', '/workspace/raw/water/water-polygons-split-4326.zip')
if not os.path.exists(z):
    z = os.path.join(OUT, 'water-polygons-split-4326.zip')
    if not os.path.exists(z):
        with requests.get('https://osmdata.openstreetmap.de/download/water-polygons-split-4326.zip', headers=H, stream=True, timeout=900) as r:
            r.raise_for_status()
            with open(z + '.tmp', 'wb') as fh:
                for b in r.iter_content(1 << 20): fh.write(b)
        os.replace(z + '.tmp', z)
import geopandas as gpd
mp = os.path.join(OUT, 'marine_pr.gpkg')
if not os.path.exists(mp):
  g = gpd.read_file(f'zip://{z}!water-polygons-split-4326/water_polygons.shp', bbox=BBOX); g.to_file(mp); print('marine polygons', len(g), flush=True)
q = f"""[out:json][timeout:600];(way["natural"="water"]({BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]});relation["natural"="water"]({BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]});
way["landuse"="reservoir"]({BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]});way["waterway"~"^(riverbank|river|canal|stream|drain|ditch)$"]({BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]}););out geom;"""
EP = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter', 'https://overpass.private.coffee/api/interpreter']
for a in range(9):
    try:
        r = requests.post(EP[a % len(EP)], data={'data': q}, headers=H, timeout=900); r.raise_for_status(); d = r.json(); break
    except Exception as e: print('retry', a, e, flush=True); time.sleep(20)
else: raise SystemExit('overpass failed')
json.dump(d, open(os.path.join(OUT, 'inland_pr.json'), 'w')); print('inland elements', len(d.get('elements', [])), flush=True); print('DONE water', flush=True)
