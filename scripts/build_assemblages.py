#!/usr/bin/env python3
"""Assemblage groups -> data/asm.json.gz (groups + members, loaded on demand) and data/asm-polys.json.gz (member outlines,
loaded only when assemblages are shown on the map).

A group = 2+ adjoining parcels (sharing a lot line; parcels across a street never touch, so streets split groups) in the same
city zoning code, held by 2+ different owners, where every parcel has at least one reason to sell or redevelop:
  1 strong teardown, 2 teardown (default teardown rule, teardown.js), 4 estate / heirs owner, 8 held 10+ years,
  16 vacant land, 32 lot under the zone minimum, 64 out-of-state owner, 128 absentee owner (person, mails to another ZIP),
  256 recent buyer (sold in the last 2 years; informational, never a reason by itself).
Uses: single family, 2-9 units, townhouse, vacant land. Government and condo parcels are left out. Components larger than
MAXG are cut into BFS pieces of up to MAXG parcels. Combined-site math uses data/zoning-rules.json (units/acre, min lot, FAR).
Inputs: data/meta.json + data/main.bin.gz (any build: everything is keyed by folio), data/zoning-rules.json,
$RAW/parcels/p_*.json (scripts/fetch_parcels.py)."""
import glob, gzip, json, math, os, re, sys, time
from collections import defaultdict
import numpy as np
from shapely.geometry import Polygon, MultiPolygon
from shapely.strtree import STRtree
from shapely.validation import make_valid
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'data')
OUT = sys.argv[2] if len(sys.argv) > 2 else DATA
RAW = os.environ.get('RAW', '/workspace/raw')
MAXG, SQFT_AC = 8, 43560
T0 = time.time()
def log(*a): print(f'[{time.time()-T0:6.0f}s]', *a, flush=True)

def read_pack(path):
    u8 = gzip.open(path).read(); hl = int.from_bytes(u8[:4], 'little'); hdr = json.loads(u8[4:4+hl]); st = 4 + hl; c, s = {}, {}
    T = {'uint8': np.uint8, 'uint16': np.uint16, 'uint32': np.uint32}
    for col in hdr['cols']:
        b = u8[st+col['offset']: st+col['offset']+col['bytes']]
        if col['type'] == 'str': s[col['name']] = b.decode('utf-8').split('\n')
        else: c[col['name']] = np.frombuffer(b, dtype=T[col['type']])
    return hdr['n'], c, s

meta = json.load(open(os.path.join(DATA, 'meta.json'))); D = meta['dicts']
n, c, s = read_pack(os.path.join(DATA, 'main.bin.gz')); log('main pack', n)
zr = json.load(open(os.path.join(DATA, 'zoning-rules.json')))['rules']
mz = D['mzone']
Z = [None] + [zr.get(f"{e[1]}|{str(e[0]).upper()}") if e else None for e in mz[1:]]
lu = D['landuse']; LUC = [int(x[:4]) if x[:4].isdigit() else -1 for x in lu]
def lutype(x):
    u = x.upper(); code = int(x[:4]) if x[:4].isdigit() else 0
    if re.search('CONDOMINIUM|COOPERATIVE', u): return 'condo'
    if re.search('GOVERN', u) or 8000 <= code < 9000: return 'gov'
    if re.search('VACANT|ACREAGE NOT CLASSIFIED', u): return 'vacant'
    g = code // 100
    return {1: 'sf', 8: 'mf29'}.get(g, 'th' if g == 4 and 'TOWNHOUSE' in u else 'other')
LUT = [lutype(x) for x in lu]
today = (time.time() / 86400) + 25567  # days since 1900-01-01 (app.js DAY0)
fl, lot, mkt, land, yb, units, stories, sqft, sd1 = (c[k].astype(np.int64) for k in ('flags', 'lot', 'mkt', 'land', 'yb', 'units', 'stories', 'sqft', 'sd1'))
og = c['og'].astype(np.int64)

def zone(i):
    r = Z[c['mz'][i]]; return r
def tier(i):
    code = LUC[c['landuse'][i]]
    if not ((100 <= code < 200) or (800 <= code < 900)): return 0
    if not (mkt[i] > 0) or land[i] > mkt[i] or land[i] / mkt[i] < 0.8: return 0
    if not (0 < yb[i] <= 1969): return 0
    z = zone(i)
    if not z: return 1
    upa, st_, mn, cov, far = z[0], z[1], z[2], z[3], z[4]
    if mn and lot[i] > 0 and not z[7] and lot[i] < mn: return 1
    if upa and lot[i] > 0: return 2 if math.floor(lot[i] / SQFT_AC * upa + 1e-9) / max(units[i], 1) >= 3 else 1
    if lot[i] > 0 and sqft[i] > 0 and (far or (cov and st_)):
        x = lot[i] * far if far else lot[i] * min(cov, 100) / 100 * st_
        return 2 if math.floor(x) / sqft[i] >= 3 else 1
    if st_: return 2 if st_ / max(stories[i], 1) >= 3 else 1
    return 1

folios = s['folio']; addr = s['addr']; owner = s['owner']
bits = np.zeros(n, np.int32); cand = np.zeros(n, bool)
for i in range(n):
    t = LUT[c['landuse'][i]]
    if t not in ('sf', 'mf29', 'th', 'vacant') or fl[i] & 32: continue
    b = 0; tr = tier(i)
    if tr == 2: b |= 1 | 2
    elif tr == 1: b |= 2
    if fl[i] & 64: b |= 4
    held = today - sd1[i] if sd1[i] else 99999
    if held >= 3652.5: b |= 8
    if t == 'vacant': b |= 16
    z = zone(i)
    if z and z[2] and lot[i] > 0 and not z[7] and lot[i] < z[2]: b |= 32
    person = not (fl[i] & (8 | 16))
    if fl[i] & 2: b |= 64
    elif person and (fl[i] & 4) and not (fl[i] & 1): b |= 128
    if held < 730.5: b |= 256
    bits[i] = b
    if b & 255: cand[i] = True
log('candidates', int(cand.sum()))
fidx = {f: i for i, f in enumerate(folios) if cand[i]}

geoms, gi = [], []
for fn in sorted(glob.glob(os.path.join(RAW, 'parcels', 'p_*.json'))):
    for f, rings in json.load(open(fn)):
        i = fidx.get(f)
        if i is None or not rings: continue
        try:
            g = Polygon(rings[0], rings[1:]) if len(rings) == 1 else MultiPolygon([Polygon(r) for r in rings]) if all(len(r) > 3 for r in rings) else Polygon(rings[0])
            if not g.is_valid: g = make_valid(g)
            if g.is_empty: continue
        except Exception: continue
        geoms.append(g); gi.append(i)
log('candidate polygons', len(geoms))
tree = STRtree(geoms)
coslat = math.cos(math.radians(25.8)); M = 111320.0
adj = defaultdict(set)
pa, pb = tree.query(geoms, predicate='intersects')
for a, b in zip(pa, pb):
    if a >= b: continue
    ia, ib = gi[a], gi[b]
    if c['mz'][ia] != c['mz'][ib] or not c['mz'][ia]: continue
    inter = geoms[a].boundary.intersection(geoms[b].boundary) if True else None
    # length in metres (approx; degrees scaled)
    L = 0.0
    for part in getattr(inter, 'geoms', [inter]):
        if part.geom_type in ('LineString', 'LinearRing'):
            xy = np.asarray(part.coords)
            if len(xy) > 1: L += float(np.sum(np.hypot(np.diff(xy[:, 0]) * M * coslat, np.diff(xy[:, 1]) * M)))
    if L >= 3.0: adj[a].add(b); adj[b].add(a)
log('adjacent pairs', sum(len(v) for v in adj.values()) // 2)

seen, comps = set(), []
for a in sorted(adj, key=lambda k: -bin(bits[gi[k]]).count('1')):
    if a in seen: continue
    comp, q = [], [a]; seen.add(a)
    while q:
        x = q.pop(0); comp.append(x)
        for y in sorted(adj[x]):
            if y not in seen: seen.add(y); q.append(y)
    for k in range(0, len(comp), MAXG):
        piece = comp[k:k+MAXG]
        if len(piece) >= 2: comps.append(piece)
log('components', len(comps))

def street(a):
    m = re.match(r'^\s*\d+[A-Z]?\s+(.*)$', a or ''); return (m.group(1) if m else (a or '')).strip()
groups = []
for piece in comps:
    rows = [gi[k] for k in piece]
    okey = [int(og[i]) if og[i] else ('n:' + owner[i].split(' | ')[0]) for i in rows]
    owners = len(set(okey))
    if owners < 2: continue
    z = zone(rows[0]); upa, mn, far = (z[0], z[2], z[4]) if z else (None, None, None)
    L = int(sum(lot[i] for i in rows))
    u = math.floor(L / SQFT_AC * upa + 1e-9) if upa and L else None
    pb_ = sum(math.floor(lot[i] / SQFT_AC * upa + 1e-9) for i in rows if not mn or lot[i] >= mn) if u is not None else None
    gain = (u - pb_) if u is not None else 0
    sq = int(L * far) if far else None
    sqg = int(L * far - sum(lot[i] * far for i in rows if not mn or lot[i] >= mn)) if far else 0
    below = sum(1 for i in rows if mn and lot[i] < mn)
    meets = not mn or L >= mn
    unlock = below > 0 and meets
    upside = gain > 0 or unlock or (sqg >= 2500)
    sb = defaultdict(int)
    for i, k in zip(rows, okey): sb[k] |= int(bits[i])
    sellers = list(sb.values())
    strong = sum(1 for v in sellers if v & 1); est = sum(1 for v in sellers if v & 4); far_ = sum(1 for v in sellers if v & (64 | 128))
    score = 20 + 8 * min(owners, 5) + 10 * strong + 6 * est + 4 * far_ + min(gain, 10) * 3 + (15 if unlock else 0) + (5 if upside else 0) - (20 if not meets else 0)
    score = int(max(1, min(100, score)))
    sts = []
    for i in rows:
        st_ = street(addr[i])
        if st_ and st_ not in sts: sts.append(st_)
    groups.append(dict(rows=rows, owners=owners, okey=okey, z=str(mz[c['mz'][rows[0]]][0]), muni=str(mz[c['mz'][rows[0]]][1]), lot=L, units=u, partsB=pb_, gain=gain,
                       sqft=sq, sqftGain=sqg, unlock=unlock, below=below, minSize=int(mn or 0), meets=meets, upside=upside, score=score, streets=sts[:2], piece=piece))
groups.sort(key=lambda g: (-g['score'], -g['lot']))
log('groups', len(groups), 'upside', sum(g['upside'] for g in groups))

# ---- payload: groups table + members (folio, bits, seller index); polygons separately ----
zl, ml, sl = [], [], []
def ix(lst, v):
    try: return lst.index(v)
    except ValueError: lst.append(v); return len(lst) - 1
zi, mi, si = {}, {}, {}
def gx(d, lst, v):
    if v not in d: d[v] = len(lst); lst.append(v)
    return d[v]
G, Mm, polys = [], [], []
for k, g in enumerate(groups, 1):
    G.append([k, g['score'], 1 if g['upside'] else 0, g['owners'], gx(mi, ml, g['muni']), gx(zi, zl, g['z']), g['lot'], -1 if g['units'] is None else g['units'],
              -1 if g['partsB'] is None else g['partsB'], g['gain'], -1 if g['sqft'] is None else g['sqft'], g['sqftGain'], 1 if g['unlock'] else 0, g['below'], g['minSize'],
              1 if g['meets'] else 0] + [gx(si, sl, x) for x in g['streets']])
    sidx = {}; mem = []
    for i, ok in zip(g['rows'], g['okey']):
        mem.append(f"{folios[i]}.{int(bits[i]):x}.{sidx.setdefault(ok, len(sidx))}")
    Mm.append(','.join(mem))
    pp = []
    for p in g['piece']:
        geo = geoms[p].simplify(0.000003)
        ring = list((geo.geoms[0] if hasattr(geo, 'geoms') else geo).exterior.coords) if not geo.is_empty and geo.geom_type in ('Polygon', 'MultiPolygon') else []
        if hasattr(geo, 'geoms'): ring = list(max(geo.geoms, key=lambda q: q.area).exterior.coords) if geo.geom_type == 'MultiPolygon' else []
        q = [(round(x * 1e6), round(y * 1e6)) for x, y in ring]
        enc = []; px = py = 0
        for x, y in q: enc += [x - px, y - py]; px, py = x, y
        pp.append(enc)
    polys.append(pp)
mot = [[1, 'strong teardown'], [2, 'teardown'], [4, 'estate/heirs owner'], [8, 'held 10+ yrs'], [16, 'vacant land'], [32, 'under min lot'], [64, 'out-of-state owner'], [128, 'absentee owner']]
gm = {'built': time.strftime('%Y-%m-%d'), 'roll_built': meta['built'], 'groups': len(G), 'upside': sum(g['upside'] for g in groups), 'members': sum(len(g['rows']) for g in groups), 'maxGroup': MAXG,
      'cols': ['id', 'score', 'upside', 'owners', 'muni', 'zone', 'lot', 'units', 'partsB', 'gain', 'sqft', 'sqftGain', 'unlock', 'below', 'minSize', 'meets', 'streets...']}
# outlines split into 0.1-degree tiles (data/asm-polys/<x>_<y>.json.gz) so the map loads only the area in view
import shutil
TD = os.path.join(OUT, 'asm-polys')
shutil.rmtree(TD, ignore_errors=True); os.makedirs(TD)
tiles, gt, tdat = [], [], {}
for j, pp in enumerate(polys):
    r0 = next((r for r in pp if len(r) >= 2), [0, 0])
    key = f"{int(r0[0] // 100000)}_{int(r0[1] // 100000)}"
    if key not in tdat: tdat[key] = {'scale': 1e6, 'j': [], 'p': []}; tiles.append(key)
    gt.append(tiles.index(key))
    tdat[key]['j'].append(j); tdat[key]['p'].append(pp)
tot = 0
for key, d in tdat.items():
    fn = os.path.join(TD, key + '.json.gz')
    with gzip.open(fn, 'wt', compresslevel=9) as f: json.dump(d, f, separators=(',', ':'))
    tot += os.path.getsize(fn)
gm['tiles'] = tiles; gm['tileDeg'] = 0.1
with gzip.open(os.path.join(OUT, 'asm.json.gz'), 'wt', compresslevel=9) as f:
    json.dump({'meta': gm, 'mot': mot, 'munis': ml, 'zones': zl, 'streets': sl, 'g': G, 'm': Mm, 'gt': gt}, f, separators=(',', ':'))
old_single = os.path.join(OUT, 'asm-polys.json.gz')
if os.path.exists(old_single): os.remove(old_single)
log('wrote asm.json.gz', os.path.getsize(os.path.join(OUT, 'asm.json.gz')), 'outline tiles', len(tiles), tot, {k: v for k, v in gm.items() if k not in ('tiles', 'cols')})
