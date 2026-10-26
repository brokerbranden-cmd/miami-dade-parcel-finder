#!/usr/bin/env python3
"""Waterfront layer inputs (all counties, one shared South Florida extent):
 1. marine water: OpenStreetMap coastline water polygons (osmdata.openstreetmap.de water-polygons-split-4326, rebuilt daily from the
    OSM coastline) clipped to South Florida -> $RAW/water/marine_sfl.gpkg. Re-downloaded when older than MAX_AGE_DAYS (default 28).
 2. inland water: OSM natural=water / waterway=riverbank / landuse=reservoir polygons + waterway=canal|river|stream|drain|ditch lines
    from Overture Maps base/water (OSM-derived, public S3) -> $RAW/water/overture/water_sfl.parquet (same max age).
Both are public ODbL data. Read-only; ~1 request every few seconds."""
import os, sys, time, json, zipfile, requests
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'water'); os.makedirs(os.path.join(RAW, 'osm'), exist_ok=True)
MAX_AGE = float(os.environ.get('MAX_AGE_DAYS', '28')) * 86400
BBOX = (-82.30, 24.30, -79.80, 26.45)   # Monroe (incl. Dry Tortugas side of Key West) .. north Broward
H = {'User-Agent': 'parcel-finder/1.0 (public data research)'}
fresh = lambda p: os.path.exists(p) and time.time() - os.path.getmtime(p) < MAX_AGE
def marine():
    out = os.path.join(RAW, 'marine_sfl.gpkg')
    if fresh(out): print('marine cached'); return
    z = os.path.join(RAW, 'water-polygons-split-4326.zip')
    if not fresh(z):
        with requests.get('https://osmdata.openstreetmap.de/download/water-polygons-split-4326.zip', headers=H, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(z + '.tmp', 'wb') as fh:
                for b in r.iter_content(1 << 20): fh.write(b)
        os.replace(z + '.tmp', z)
    import geopandas as gpd
    g = gpd.read_file(f'zip://{z}!water-polygons-split-4326/water_polygons.shp', bbox=BBOX)
    g.to_file(out + '.tmp.gpkg'); os.replace(out + '.tmp.gpkg', out); print('marine polygons', len(g))
OVERTURE = os.environ.get('OVERTURE_RELEASE', '')   # e.g. 2026-10-21.0; default = newest release in the public bucket
def latest_release():
    import re
    x = requests.get('https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/?list-type=2&prefix=release/&delimiter=/', headers=H, timeout=60).text
    rel = sorted(re.findall(r'<Prefix>release/(\d{4}-\d{2}-\d{2}\.\d+)/</Prefix>', x))
    if not rel: raise RuntimeError('no Overture releases listed')
    return rel[-1]
def inland():
    """Overture Maps base/water (OpenStreetMap lakes, ponds, canals, rivers, streams; ODbL), public S3, anonymous; bbox-filtered
    parquet read (~30K features, a few seconds) -> $RAW/water/overture/water_sfl.parquet"""
    import pyarrow.dataset as ds, pyarrow.fs as pfs, pyarrow.parquet as pq, pyarrow.compute as pc
    out = os.path.join(RAW, 'overture', 'water_sfl.parquet'); os.makedirs(os.path.dirname(out), exist_ok=True)
    if fresh(out): print('inland cached'); return
    rel = OVERTURE or latest_release()
    d = ds.dataset(f'overturemaps-us-west-2/release/{rel}/theme=base/type=water/', filesystem=pfs.S3FileSystem(anonymous=True, region='us-west-2'), format='parquet')
    f = (pc.field(('bbox', 'xmin')) < BBOX[2]) & (pc.field(('bbox', 'xmax')) > BBOX[0]) & (pc.field(('bbox', 'ymin')) < BBOX[3]) & (pc.field(('bbox', 'ymax')) > BBOX[1])
    tb = d.to_table(columns=['id', 'subtype', 'class', 'is_salt', 'geometry', 'bbox'], filter=f)
    if tb.num_rows < 5000: raise RuntimeError(f'only {tb.num_rows} Overture water features - refusing to replace the cache')
    tb = tb.replace_schema_metadata({**(tb.schema.metadata or {}), b'overture_release': rel.encode()})
    pq.write_table(tb, out + '.tmp'); os.replace(out + '.tmp', out); print('overture', rel, tb.num_rows, 'water features')
if __name__ == '__main__':
    marine(); inland(); print('water inputs ok')
