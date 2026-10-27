"""Puerto Rico waterfront, FEMA flood zone and assemblage layers (imported by build_pr.py).
Same outputs and bit meanings as the Florida builders (scripts/build_waterfront.py, scripts/build_assemblages.py), adapted to the
public PR inputs: CRIM parcel outlines (raw/polys), OSM coastline + inland water (raw/water), CRIM water parcels (TIPO A),
FEMA NFHL flood zones for PR (raw/flood). Projected metres: EPSG:32161 (NAD83 / Puerto Rico & Virgin Is.)."""
import glob, json, os, time
from collections import defaultdict, deque
import numpy as np, shapely
from shapely.strtree import STRtree
from pyproj import Transformer
T0 = time.time()
def log(*a): print(f'[pr_extras {time.time()-T0:6.0f}s]', *a, flush=True)
TR = Transformer.from_crs('EPSG:4326', 'EPSG:32161', always_xy=True)
def proj(g): return shapely.transform(g, lambda xy: np.column_stack(TR.transform(xy[:, 0], xy[:, 1])))
R_OPEN, R_BAY, TOL, TOL_BAY, TOL_OCEAN, MIN_LAKE = 400.0, 50.0, 12.0, 20.0, 60.0, 4000.0
LINE_W = {'canal': 10.0, 'river': 15.0, 'stream': 4.0, 'drain': 4.0, 'ditch': 3.0}

def load_polys(raw, want):
    """CRIM outlines -> (folio -> lon/lat polygon) for folios in `want`, plus projected CRIM water parcels (TIPO A)."""
    geo, water = {}, []
    for fn in sorted(glob.glob(f'{raw}/polys/*.jsonl')):
        for l in open(fn):
            d = json.loads(l); r = d.get('rings')
            if not r: continue
            ring = max(r, key=len)
            if len(ring) < 4: continue
            f = (d.get('NUM_CATASTRO') or '').strip(); t = d.get('TIPO') or 'P'
            if t == 'A': water.append(shapely.Polygon(ring))
            elif f in want and f not in geo: geo[f] = shapely.Polygon(ring)
    log('outlines', len(geo), 'CRIM water parcels', len(water))
    return geo, water

def flood_labels(raw, lon, lat):
    """FEMA zone label per centroid (same wording as the Monroe / Broward cra dictionary)."""
    G, A = [], []
    for fn in sorted(glob.glob(f'{raw}/flood/*.json')):
        for f in json.load(open(fn)):
            if not f['r']: continue
            try: g = shapely.make_valid(shapely.Polygon(f['r'][0], f['r'][1:]))
            except Exception: continue
            G.append(g); A.append(f['a'])
    log('flood polygons', len(G))
    def lab(a):
        z = (a.get('FLD_ZONE') or '').strip(); st = (a.get('ZONE_SUBTY') or '').upper(); b = a.get('STATIC_BFE'); bfe = f' (BFE {b:g} ft)' if isinstance(b, (int, float)) and b > -9000 else ''
        if z.startswith('V'): return 3, f'VE - coastal high hazard{bfe}'
        if z == 'AO': return 2, 'AO - high risk (shallow flooding)'
        if z.startswith('A'): return 2, f'{z} - high risk{bfe}'
        if z == 'X' and '0.2' in st: return 1, 'X - moderate risk (0.2%)'
        if z == 'X': return 0, 'X - minimal risk'
        if z in ('D',): return 0, 'D - undetermined risk'
        return -1, ''
    L = [lab(a) for a in A]
    tree = STRtree(G); n = len(lon); best = np.full(n, -1); out = [''] * n
    ok = np.where((lat != 0) & (lon != 0))[0]
    pi, gi = tree.query(shapely.points(lon[ok], lat[ok]), predicate='within')
    for p, g in zip(pi, gi):
        r, t = L[g]; k = ok[p]
        if r > best[k]: best[k] = r; out[k] = t
    log('flood labels', sum(1 for x in out if x))
    return out

def waterfront(raw, geo, crim_water, playa):
    """folio -> bits (1 ocean / open water, 2 bay / harbour, 4 canal / narrow marine, 8 lake / river / other)."""
    import geopandas as gpd
    m = gpd.read_file(os.path.join(raw, 'water', 'marine_pr.gpkg')).to_crs('EPSG:32161')
    marine = shapely.union_all(shapely.make_valid(m.geometry.values)); log('marine union')
    opn = marine.buffer(-R_OPEN).buffer(R_OPEN + 1); bay = marine.buffer(-R_BAY).buffer(R_BAY + 1).difference(opn); canal = marine.difference(opn).difference(bay)
    inl = []
    d = json.load(open(os.path.join(raw, 'water', 'inland_pr.json')))
    for e in d.get('elements', []):
        t = e.get('tags', {}); ww = t.get('waterway')
        if e['type'] == 'way' and e.get('geometry'):
            c = [(p['lon'], p['lat']) for p in e['geometry']]
            if ww in LINE_W and len(c) >= 2: inl.append(proj(shapely.LineString(c)).buffer(LINE_W[ww] / 2)); continue
            if len(c) >= 4 and c[0] == c[-1]:
                g = proj(shapely.make_valid(shapely.Polygon(c)))
                if g.area >= MIN_LAKE: inl.append(g)
        elif e['type'] == 'relation':
            for mb in e.get('members', []):
                if mb.get('role') == 'outer' and mb.get('geometry'):
                    c = [(p['lon'], p['lat']) for p in mb['geometry']]
                    if len(c) >= 4 and c[0] == c[-1]:
                        g = proj(shapely.make_valid(shapely.Polygon(c)))
                        if g.area >= MIN_LAKE: inl.append(g)
    for g in crim_water:   # CRIM water parcels (rivers, lagoons, reservoirs) not already marine
        g = proj(shapely.make_valid(g))
        if g.area >= MIN_LAKE: inl.append(g.difference(marine) if g.intersects(marine) else g)
    log('inland water pieces', len(inl))
    folios = list(geo); P = proj(np.array([geo[f] for f in folios], dtype=object)); P = shapely.make_valid(P)
    bits = np.zeros(len(folios), np.uint8)
    for b, w, tol in ((1, [opn], TOL_OCEAN), (2, [bay], TOL_BAY), (4, [canal], TOL), (8, inl, TOL)):
        parts = []
        for g in w:
            if g.is_empty: continue
            parts += list(shapely.get_parts(g)) if g.geom_type.startswith('Multi') or g.geom_type == 'GeometryCollection' else [g]
        parts = [shapely.segmentize(q, 2000) if q.area > 1e8 else q for q in parts if not q.is_empty and q.area > 0]
        if not parts: continue
        # very large water (open sea) is cut into 2 km tiles so the tree queries stay fast
        big = [q for q in parts if q.area > 4e6]; small = [q for q in parts if q.area <= 4e6]
        for q in big:
            x0, y0, x1, y1 = q.bounds; xs = np.arange(x0, x1, 2000); ys = np.arange(y0, y1, 2000)
            cells = [shapely.box(x, y, x + 2000, y + 2000) for x in xs for y in ys]
            cut = shapely.intersection(q, cells); small += [c for c in cut if not c.is_empty and c.area > 0]
        tree = STRtree(small); pi, _ = tree.query(P, predicate='dwithin', distance=tol)
        bits[np.unique(pi)] |= b; log('water bit', b, 'parcels', int((bits & b > 0).sum()))
    out = {f: int(v) for f, v in zip(folios, bits) if v}
    for f in playa:   # Junta beach (playa) overlay: oceanfront even when the mapped coastline sits a little offshore
        if f in geo: out[f] = out.get(f, 0) | 1
    return out

def assemblages(geo, cand, MAXG=8):
    """cand: folio -> (key, lot_sf, min_sf, upa). Adjoining candidates with the same key (municipio|zone), each under the zone
    minimum on its own. Returns a list of groups [[folio,...], ...]."""
    fs = [f for f in cand if f in geo]
    if not fs: return []
    P = shapely.make_valid(proj(np.array([geo[f] for f in fs], dtype=object))); tree = STRtree(P)
    a, b = tree.query(P, predicate='dwithin', distance=0.5)
    adj = defaultdict(set)
    for i, j in zip(a, b):
        if i < j and cand[fs[i]][0] == cand[fs[j]][0]: adj[i].add(j); adj[j].add(i)
    seen, groups = set(), []
    for s in sorted(adj):
        if s in seen: continue
        comp, q = [], deque([s]); seen.add(s)
        while q:
            u = q.popleft(); comp.append(u)
            for v in sorted(adj[u]):
                if v not in seen: seen.add(v); q.append(v)
        left = set(comp)
        while left:   # BFS pieces of up to MAXG parcels
            st = min(left); piece, q = [], deque([st]); used = {st}
            while q and len(piece) < MAXG:
                u = q.popleft(); piece.append(u)
                for v in sorted(adj[u]):
                    if v in left and v not in used: used.add(v); q.append(v)
            left -= set(piece)
            if len(piece) >= 2: groups.append([fs[k] for k in piece])
    log('assemblage groups', len(groups))
    return groups

def encode_ring(g):
    g = g.simplify(0.000003)
    if g.geom_type == 'MultiPolygon': g = max(g.geoms, key=lambda q: q.area)
    if g.geom_type != 'Polygon' or g.is_empty: return []
    enc, px, py = [], 0, 0
    for x, y in g.exterior.coords:
        x, y = round(x * 1e6), round(y * 1e6); enc += [x - px, y - py]; px, py = x, y
    return enc
