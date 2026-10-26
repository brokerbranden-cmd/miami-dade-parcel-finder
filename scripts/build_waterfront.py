#!/usr/bin/env python3
"""Waterfront / oceanfront layer, built the same way for every county (no county has an official waterfront flag on its public roll:
Miami-Dade PA layer 5, the BCPA / FDOR NAL fields and the Monroe PA parcel layer were all checked).
  python3 scripts/build_waterfront.py miami-dade|broward|monroe     -> data/<dir>/water.json.gz
Method (parcel polygon vs mapped water, OpenStreetMap, see scripts/fetch_water.py):
  * marine water = OSM coastline water polygons. Its width decides the sub-type (morphological opening in metres, EPSG:3086):
      ocean / open water: part of water >= 2*R_OPEN (800 m) across - Atlantic, Gulf, Florida Bay, Biscayne Bay, Card / Barnes Sound
      bay: >= 2*R_BAY (100 m) across - Intracoastal Waterway, harbours, basins, river mouths, smaller bays
      canal: narrower marine water - finger canals, Keys canals, tidal creeks
  * inland water = OSM natural=water / reservoir / riverbank polygons (>= MIN_LAKE m2) and waterway lines (buffered by a typical half
    width): water=canal / waterway=canal|drain|ditch -> canal, everything else (lakes, ponds, quarry lakes, rivers) -> lake / other.
  * a parcel counts when its polygon is within TOL of that water (ocean: TOL_OCEAN, since beach / dune strips sit between many
    oceanfront lots and the mapped shoreline) and the gap is not taken by another built-on private lot (first-row check: 3 points on
    the shortest line to the water must not fall inside another parcel that is itself next to the water and has an improved use).
  * condo units / parcels without their own polygon take the class of the parcel polygon that contains their point.
Bits: 1 ocean, 2 bay, 4 canal, 8 lake / other.  Screening data, not a survey: confirm water frontage on the PA record / aerial."""
import os, sys, json, gzip, glob, time, re
import numpy as np
import pyarrow.parquet as pq, shapely, geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, box
from shapely.ops import unary_union, polygonize, linemerge
from pyproj import Transformer
sys.path.insert(0, os.path.dirname(__file__))
C = sys.argv[1]; REPO = os.path.join(os.path.dirname(__file__), '..'); RAW = os.environ.get('RAW', '/workspace/raw')
DD = {'miami-dade': 'data/', 'broward': 'data/broward/', 'monroe': 'data/monroe/'}[C]; DATA = os.path.join(REPO, DD)
R_OPEN, R_BAY = 400.0, 50.0
TOL, TOL_BAY, TOL_OCEAN, MIN_LAKE = 12.0, 20.0, 150.0, 4000.0
LINE_W = {'canal': 10.0, 'river': 15.0, 'stream': 4.0, 'drain': 4.0, 'ditch': 3.0}
TILE = 0.05; T0 = time.time()
log = lambda *a: print(f'[{time.time()-T0:6.0f}s]', *a, flush=True)
TR = Transformer.from_crs('EPSG:4326', 'EPSG:3086', always_xy=True)
def proj(g): return shapely.transform(g, lambda xy: np.column_stack(TR.transform(xy[:, 0], xy[:, 1])))

# ---------- packs (keys + land use + points) ----------
def read_pack(path):
    import struct
    b = gzip.decompress(open(path, 'rb').read()); hl = struct.unpack('<I', b[:4])[0]; h = json.loads(b[4:4 + hl]); base = 4 + hl; out = {'n': h['n']}
    for c in h['cols']:
        raw = b[base + c['offset']: base + c['offset'] + c['bytes']]
        out[c['name']] = np.frombuffer(raw, dtype=c['type']) if c['type'] != 'str' else raw.decode('utf-8').split('\n')
    return out
meta = json.load(open(os.path.join(DATA, 'meta.json'))); g0 = meta.get('geoOrigin') or [24.0, -81.5]
LUD = (meta.get('dicts') or {}).get('landuse') or []
recs = []   # (folio, lon, lat, improved)
for name in ('main', 'condo'):
    p = read_pack(os.path.join(DATA, name + '.bin.gz')); g = read_pack(os.path.join(DATA, name + '-geo.bin.gz'))
    lat = np.where(g['lat'] > 0, g['lat'] / 1e6 + g0[0], 0); lon = np.where(g['lon'] > 0, g['lon'] / 1e6 + g0[1], 0)
    imp = (p['bldg'] > 0) if 'bldg' in p else np.ones(p['n'], bool)
    for i in range(p['n']): recs.append((p['folio'][i], lon[i], lat[i], bool(imp[i])))
FOLIO_IMP = {f: im for f, _, _, im in recs}
log(C, 'pack records', len(recs))

# ---------- parcel polygons ----------
def rings_poly(rings):
    ps = [Polygon(r) for r in rings if len(r) >= 4]
    ps = [q if q.is_valid else q.buffer(0) for q in ps]
    if not ps: return None
    outer = [q for q in ps if q.area > 0]
    if not outer: return None
    u = outer[0] if len(outer) == 1 else unary_union(outer)
    return u
keys, geoms = [], []
if C == 'miami-dade':
    for fn in sorted(glob.glob(os.path.join(RAW, 'parcels', 'p_*.json'))):
        for fo, rings in json.load(open(fn)):
            g = rings_poly(rings)
            if g is not None: keys.append(str(fo)); geoms.append(g)
else:
    for fn in sorted(glob.glob(os.path.join(RAW, C, 'polys', '*.jsonl'))):
        for line in open(fn):
            k, use, rings = json.loads(line); g = rings_poly(rings)
            if g is None: continue
            keys.append(re.sub(r'\s+', '', k) if C == 'monroe' else k.strip().upper()); geoms.append(g)
log('parcel polygons', len(geoms))
if not geoms: sys.exit('no parcel polygons - run scripts/fetch_parcels.py / scripts/fetch_parcel_polys.py first')
PG = proj(np.array(geoms, dtype=object)); keys = np.array(keys, dtype=object)
# duplicates (stacked condo-unit polygons): keep them, they classify identically
IMPV = np.array([FOLIO_IMP.get(k, False) for k in keys])
cen = shapely.centroid(np.array(geoms, dtype=object)); CX, CY = shapely.get_x(cen), shapely.get_y(cen)
TREE = shapely.STRtree(PG)

# ---------- water ----------
W = os.path.join(RAW, 'water')
lo, la = CX[np.isfinite(CX)], CY[np.isfinite(CY)]
EXT = (lo.min() - 0.03, la.min() - 0.03, lo.max() + 0.03, la.max() + 0.03)
mar = gpd.read_file(os.path.join(W, 'marine_sfl.gpkg'), bbox=EXT)
MAR = proj(shapely.make_valid(shapely.intersection(np.array(mar.geometry.values, dtype=object), box(*EXT))))
MAR = shapely.union_all(MAR); log('marine water loaded')
lakes, canals = [], []
# Overture Maps base/water (OpenStreetMap-derived, ODbL), clipped to South Florida by scripts/fetch_water.py
SKIP_CLASS = {'swimming_pool', 'reflecting_pool', 'wastewater', 'fountain', 'fairway', 'ocean', 'bay', 'cape', 'strait', 'shoal', 'waterfall', 'spring'}
ov = pq.read_table(os.path.join(W, 'overture', 'water_sfl.parquet'), columns=['subtype', 'class', 'geometry', 'bbox']).to_pydict()
for st, cl, wkb, bb in zip(ov['subtype'], ov['class'], ov['geometry'], ov['bbox']):
    if cl in SKIP_CLASS or st in ('ocean', 'physical') or wkb is None: continue
    if bb['xmax'] < EXT[0] or bb['xmin'] > EXT[2] or bb['ymax'] < EXT[1] or bb['ymin'] > EXT[3]: continue
    kind = 'canal' if (st == 'canal' or cl in ('canal', 'ditch', 'drain', 'tidal_channel')) else 'lake'
    try:
        g = proj(shapely.from_wkb(wkb))
        if g.geom_type in ('LineString', 'MultiLineString'): g = g.buffer(LINE_W.get(cl, LINE_W.get(st, 6.0)))
        g = shapely.make_valid(g)
        if g.is_empty or g.geom_type in ('Point', 'MultiPoint'): continue
        if g.area < MIN_LAKE and kind == 'lake' and cl not in ('river', 'stream'): continue
        (canals if kind == 'canal' else lakes).append(g)
    except Exception:
        continue
log('inland water: lake/other', len(lakes), 'canal', len(canals))
LAKE_T = shapely.STRtree(np.array(lakes, dtype=object)) if lakes else None
CAN_T = shapely.STRtree(np.array(canals, dtype=object)) if canals else None
LAKES, CANS = np.array(lakes, dtype=object), np.array(canals, dtype=object)

# ---------- classify, tile by tile ----------
bits = np.zeros(len(PG), np.uint8); dist = {}
def first_row_ok(idx, wgeom, tol):
    """True unless the shortest gap to the water runs through another improved parcel that is itself at the water."""
    out = np.ones(len(idx), bool)
    d = shapely.distance(PG[idx], wgeom)
    for j, (i, dd) in enumerate(zip(idx, d)):
        if dd <= 3.0: continue
        a, b = shapely.ops.nearest_points(PG[i], wgeom)
        line = LineString([a, b]); pts = [line.interpolate(f, normalized=True) for f in (0.3, 0.55, 0.85)]
        for pt in pts:
            hit = TREE.query(pt, predicate='within')
            for h in hit:
                if h == i or not IMPV[h] or keys[h] == keys[i]: continue
                if shapely.distance(PG[h], wgeom) <= max(3.0, dd * 0.5): out[j] = False; break
            if not out[j]: break
    return out
X = np.arange(EXT[0], EXT[2], TILE); Y = np.arange(EXT[1], EXT[3], TILE); nt = 0
for x in X:
    for y in Y:
        sel = np.where((CX >= x) & (CX < x + TILE) & (CY >= y) & (CY < y + TILE))[0]
        if not len(sel): continue
        nt += 1
        tb = proj(box(x, y, x + TILE, y + TILE)); big = tb.buffer(R_OPEN * 2.5 + TOL_OCEAN)
        m = shapely.intersection(MAR, big)
        if not m.is_empty:
            opn = shapely.intersection(m.buffer(-R_OPEN).buffer(R_OPEN + 1.0), m)     # open water (>= 800 m across)
            bay = shapely.intersection(m.buffer(-R_BAY).buffer(R_BAY + 1.0), m)        # >= 100 m across
            mid = tb.buffer(TOL_OCEAN + 5)
            opn = shapely.intersection(opn, mid); bay = shapely.intersection(bay, mid); mm = shapely.intersection(m, mid)
            nar = shapely.difference(mm, bay.buffer(2.0)) if not bay.is_empty else mm
            for bit, wg, tol in ((1, opn, TOL_OCEAN), (2, bay, TOL_BAY), (4, nar, TOL)):
                if wg.is_empty: continue
                shapely.prepare(wg); c = sel[shapely.dwithin(PG[sel], wg, tol)]
                if not len(c): continue
                if bit == 2: c = c[~(bits[c] & 1).astype(bool)] if False else c
                ok = first_row_ok(c, wg, tol); bits[c[ok]] |= bit
        # inland
        for bit, tree, arr in ((4, CAN_T, CANS), (8, LAKE_T, LAKES)):
            if tree is None: continue
            cand = tree.query(tb.buffer(TOL + 5))
            if not len(cand): continue
            wg = shapely.union_all(arr[cand]); wg = shapely.difference(wg, MAR) if bit == 8 else wg
            if wg.is_empty: continue
            shapely.prepare(wg); c = sel[shapely.dwithin(PG[sel], wg, TOL)]
            if len(c): ok = first_row_ok(c, wg, TOL); bits[c[ok]] |= bit
        if nt % 50 == 0: log('tiles', nt, 'waterfront so far', int((bits > 0).sum()))
# bay-front lots that also reach open water are oceanfront (keep both bits; the tag shows the best one)
log('polygons classified', int((bits > 0).sum()), 'of', len(bits))

# ---------- map to pack records ----------
by_key = {}
for k, b in zip(keys, bits):
    if b: by_key[k] = by_key.get(k, 0) | int(b)
has_poly = set(keys.tolist())
need = [(f, lo_, la_) for f, lo_, la_, _ in recs if f not in has_poly and lo_ != 0]
wf_idx = np.where(bits > 0)[0]
if need and len(wf_idx):
    pts = proj(shapely.points(np.array([[a, b] for _, a, b in need])))
    t2 = shapely.STRtree(PG[wf_idx]); pi, gi = t2.query(pts, predicate='within')
    for a, b in zip(pi, gi): f = need[a][0]; by_key[f] = by_key.get(f, 0) | int(bits[wf_idx[b]])
recset = {f for f, *_ in recs}
out = {f: b for f, b in by_key.items() if f in recset}
groups = {}
for f, b in out.items(): groups.setdefault(str(b), []).append(f)
cnt = lambda m: sum(1 for b in out.values() if b & m)
best = lambda b: 1 if b & 1 else 2 if b & 2 else 4 if b & 4 else 8
counts = {'any': len(out), 'ocean': cnt(1), 'bay': cnt(2), 'canal': cnt(4), 'lake': cnt(8),
          'best': {k: sum(1 for b in out.values() if best(b) == v) for k, v in (('ocean', 1), ('bay', 2), ('canal', 4), ('lake', 8))},
          'records': len(recs), 'polygons': int(len(PG)), 'no_polygon_records': len(need)}
doc = {'v': 1, 'county': C, 'built': time.strftime('%Y-%m-%d'), 'packVer': meta.get('ver'), 'counts': counts,
       'method': {'r_open_m': R_OPEN, 'r_bay_m': R_BAY, 'tol_m': TOL, 'tol_bay_m': TOL_BAY, 'tol_ocean_m': TOL_OCEAN, 'min_lake_m2': MIN_LAKE},
       'sources': ['OpenStreetMap coastline water polygons (osmdata.openstreetmap.de, ODbL)', 'OpenStreetMap lakes / canals / rivers via Overture Maps base/water (ODbL)',
                   {'miami-dade': 'Miami-Dade County parcel polygons (MD_ComparableSales / PaGIS)', 'broward': 'BCPA parcel polygons (Broward_County_Parcel_Boundary)', 'monroe': 'Monroe County GIS parcel polygons (APO_GIS Current Parcels)'}[C]],
       'groups': {k: ','.join(sorted(v)) for k, v in groups.items()}}
p = os.path.join(DATA, 'water.json.gz')
open(p + '.tmp', 'wb').write(gzip.compress(json.dumps(doc, separators=(',', ':')).encode(), 9, mtime=0)); os.replace(p + '.tmp', p)
log('wrote', p, os.path.getsize(p), 'bytes', json.dumps(counts))
