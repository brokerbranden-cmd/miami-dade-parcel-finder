#!/usr/bin/env python3
"""Puerto Rico phase-1 packs -> data/pr/<municipio>/ (one data folder per municipio so the page loads ~20k-100k parcels, not 1.44M).
Inputs ($PRRAW, default /workspace/pr/raw): parcels/*.jsonl (CRIM parcelario feb_2025, public, no owner / value / address) and
zoning/*.jsonl (Junta de Planificacion calificacion vigente, keyed by num_catast). Same pack format and column names as the
Florida builds (scripts/counties/broward/build_broward.py) so app.js reads it unchanged; columns with no public PR source are zeros.
Writes data/pr/index.json (municipio list, counts, bytes) for the municipio picker."""
import json, os, re, sys, gzip, glob, unicodedata, datetime as dt, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); SCR = os.path.abspath(os.path.join(HERE, '..', '..'))
RAW = os.environ.get('PRRAW', '/workspace/pr/raw')
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SCR, '..', 'data', 'pr')
GEO0 = (17.8, -67.95)   # pack lat/lon origin (south-west of Mona / Cabo Rojo; Culebra/Vieques reach -65.2)

def jl(kind):
    rows = []
    for f in sorted(glob.glob(f'{RAW}/{kind}/*.jsonl')):
        with open(f) as fh: rows += [json.loads(l) for l in fh]
    return pd.DataFrame(rows)
P = jl('parcels'); Z = jl('zoning')
n_raw = len(P)
P['NUM_CATASTRO'] = P.NUM_CATASTRO.fillna('').astype(str).str.strip()
P = P[(P.TIPO.fillna('P') == 'P') & (P.NUM_CATASTRO != '')]       # drop road (V) / water (A) polygons
P = P.drop_duplicates('NUM_CATASTRO').reset_index(drop=True)
stats = {'raw_features': int(n_raw), 'parcels_kept': int(len(P)), 'dropped_road_water_or_blank': int(n_raw - len(P))}
Z['num_catast'] = Z.num_catast.fillna('').astype(str).str.strip()
Z = Z[Z.num_catast != ''].drop_duplicates('num_catast')
m = P.merge(Z, left_on='NUM_CATASTRO', right_on='num_catast', how='left', suffixes=('', '_z'))
lat = pd.to_numeric(m.INSIDE_Y, errors='coerce').fillna(0).values; lon = pd.to_numeric(m.INSIDE_X, errors='coerce').fillna(0).values
muni = m.municipio.fillna('').astype(str).str.strip().values.copy()
# parcels the zoning layer does not list: municipio of the most common zoned neighbour in the same ~1 km cell (then 3x3 cells)
cell = lambda la, lo, s=0.01: (np.floor(la / s).astype(np.int64) * 100000 + np.floor(lo / s).astype(np.int64))
ok = (muni != '') & (lat != 0)
ck = cell(lat, lon); vote = pd.DataFrame({'c': ck[ok], 'm': muni[ok]}).groupby('c').m.agg(lambda s: s.value_counts().index[0]).to_dict()
miss = (muni == '') & (lat != 0); filled = 0
for k in np.where(miss)[0]:
    c0 = ck[k]; best = vote.get(c0)
    if best is None:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                best = best or vote.get(c0 + dy * 100000 + dx)
    if best: muni[k] = best; filled += 1
stats.update({'zoning_matched': int(m.cali.notna().sum()), 'muni_from_neighbours': int(filled), 'no_muni': int((muni == '').sum())})
print(stats, flush=True)

def slug(s): return re.sub(r'[^a-z0-9]+', '-', unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()).strip('-') or 'sin-municipio'
# ---- zoning: plain-language English next to the official Spanish district name (Reglamento Conjunto 2020 districts)
EN = {'residencial': 'residential', 'comercial': 'commercial', 'industrial': 'industrial', 'agricola': 'agricultural', 'agrícola': 'agricultural', 'turistico': 'tourist',
      'turístico': 'tourist', 'conservacion': 'conservation', 'conservación': 'conservation', 'preservacion': 'preservation', 'preservación': 'preservation', 'recursos': 'resources',
      'bosque': 'forest', 'baja': 'low', 'alta': 'high', 'intermedio': 'intermediate', 'intermedia': 'intermediate', 'densidad': 'density', 'general': 'general', 'liviano': 'light',
      'pesado': 'heavy', 'mixto': 'mixed', 'urbano': 'urban', 'rural': 'rural', 'dotacional': 'public facilities', 'desarrollo': 'development', 'selectivo': 'selective',
      'productivo': 'productive', 'local': 'local', 'central': 'central', 'suelo': 'land', 'cuerpos': 'bodies', 'de': 'of', 'agua': 'water', 'zona': 'zone', 'historica': 'historic',
      'histórica': 'historic', 'costanera': 'coastal', 'playa': 'beach', 'vial': 'roadway', 'sitio': 'site', 'especial': 'special', 'uso': 'use', 'publico': 'public', 'público': 'public',
      'y': 'and', 'en': 'in', 'area': 'area', 'área': 'area', 'no': 'not', 'calificado': 'zoned', 'construccion': 'construction', 'mediana': 'medium', 'ruta': 'route', 'escenica': 'scenic', 'escénica': 'scenic'}
def en(s): return ' '.join(EN.get(w.lower(), w.lower()) for w in str(s).split()) if s else ''
def ztype(code, desc):
    c = (code or '').upper(); d = unicodedata.normalize('NFKD', (desc or '').lower()).encode('ascii', 'ignore').decode()
    if 'residencial' in d or c.startswith('R'):
        return 'mf' if re.search(r'\balta\b|R-A|R-U|R-CT|R-T|RT|R-5|R-4', c + ' ' + d) else 'sf'
    if 'mixto' in d or c.startswith(('M-', 'MX')): return 'mixed'
    if 'comercial' in d or 'turist' in d or c.startswith(('C-', 'CT', 'DTS')): return 'com'
    if 'industrial' in d or c.startswith('I-'): return 'ind'
    if 'dotacional' in d or 'public' in d or c.startswith('DT'): return 'civic'
    return 'other'
zc = m.cali.fillna('').astype(str).str.strip().values; zd = m.descrip.fillna('').astype(str).str.strip().values
barrio = m.barrio.fillna('').astype(str).str.strip().values
cuerdas = pd.to_numeric(m.cuerdas, errors='coerce').fillna(0).values
area_m2 = pd.to_numeric(m['Shape.STArea()'], errors='coerce').fillna(0).values
lot = np.where(area_m2 > 0, area_m2 * 10.7639, cuerdas * 3930.395 * 10.7639)   # 1 cuerda = 3,930.395 m2
OVL = [('id_playa', 'beach / coast overlay'), ('id_riesgo', 'hazard overlay'), ('id_hist', 'historic zone'), ('id_agric', 'agricultural reserve'), ('id_res_nat', 'natural reserve')]
ovl = [', '.join(lbl for col, lbl in OVL if col in m and pd.notna(v[col]) and str(v[col]).strip() not in ('', '0')) for v in m[[c for c, _ in OVL if c in m]].to_dict('records')]

u32 = lambda a: np.clip(np.round(np.asarray(a, dtype=float)), 0, 4294967295).astype(np.uint32)
def write_pack(path, rows, cols, strs):
    blobs, hdr_cols, off = [], [], 0
    def add(name, typ, b):
        nonlocal off
        hdr_cols.append({'name': name, 'type': typ, 'offset': off, 'bytes': len(b)}); blobs.append(b); off += len(b)
        pad = (-off) % 4
        if pad: blobs.append(b'\0' * pad); off += pad
    for name, arr in cols.items():
        a = arr[rows]; add(name, {np.dtype('uint8'): 'uint8', np.dtype('uint16'): 'uint16', np.dtype('uint32'): 'uint32'}[a.dtype], a.tobytes())
    for name, lst in strs.items():
        add(name, 'str', '\n'.join(lst[k].replace('\n', ' ') for k in rows).encode('utf-8'))
    hdr = json.dumps({'n': int(len(rows)), 'cols': hdr_cols}, separators=(',', ':')).encode(); hdr += b' ' * ((-(4 + len(hdr))) % 4)
    raw = len(hdr).to_bytes(4, 'little') + hdr + b''.join(blobs); gz = gzip.compress(raw, 9, mtime=0); open(path, 'wb').write(gz); return len(gz)

ver0 = dt.datetime.now().strftime('%Y%m%d%H%M'); os.makedirs(OUT, exist_ok=True); index = []
folio_all = m.NUM_CATASTRO.values
for mu in sorted(set(muni), key=lambda s: slug(s)):
    rows_all = np.where(muni == mu)[0]; n = len(rows_all); sl = slug(mu); od = os.path.join(OUT, sl); os.makedirs(od, exist_ok=True)
    idx = np.arange(n); z = lambda t: np.zeros(n, t)
    # dictionaries (per municipio): city = barrio, zip unknown, landuse = not public
    bs = [barrio[k] or mu or 'Sin barrio' for k in rows_all]; city = ['']; ci = {'': 0}; city_i = np.zeros(n, np.uint8)
    for j, b in enumerate(bs):
        if b not in ci:
            if len(city) >= 255: b = 'Otros barrios'
            if b not in ci: ci[b] = len(city); city.append(b)
        city_i[j] = ci[b]
    mzone = [None]; mzi = {}; mz = np.zeros(n, np.uint16); rules = {}
    for j, k in enumerate(rows_all):
        c = zc[k]
        if not c: continue
        if c not in mzi:
            mzi[c] = len(mzone); d = zd[k] or c
            mzone.append([c, mu or 'Puerto Rico', f'{d} ({en(d)})' if en(d) and en(d) != d.lower() else d, None, None, None])
            rules[f'{mu or "Puerto Rico"}|{c}'] = [None, None, None, None, None, None, ztype(c, d), 0, 'Junta de Planificacion, calificacion vigente (screening only)']
        mz[j] = mzi[c]
    zinfo = [ovl[k] for k in rows_all]
    la = lat[rows_all]; lo = lon[rows_all]
    cols_main = {'city': city_i, 'zip': z(np.uint16), 'cra': z(np.uint8), 'landuse': np.ones(n, np.uint16), 'zoning': z(np.uint16), 'mz': mz, 'tier': z(np.uint8), 'rogo': z(np.uint8),
        'env': z(np.uint16), 'sigm': z(np.uint16), 'bld': z(np.uint8), 'lot': u32(lot[rows_all]), 'mkt': z(np.uint32), 'land': z(np.uint32), 'bldg': z(np.uint32), 'sqft': z(np.uint32),
        'yb': z(np.uint16), 'units': z(np.uint16), 'beds': z(np.uint8), 'baths': z(np.uint8), 'stories': z(np.uint8), 'sd1': z(np.uint16), 'sale1': z(np.uint32), 'sq1': z(np.uint8),
        'flags': z(np.uint8), 'prv': z(np.uint32), 'og': z(np.uint32), 'pcs': z(np.uint16), 'sx': z(np.uint8), 'dscore': z(np.uint8), 'dsig': z(np.uint16), 'vscore': z(np.uint8), 'vsig': z(np.uint16)}
    str_main = {'folio': [folio_all[k] for k in rows_all], 'addr': [''] * n, 'owner': [''] * n}
    cols_det = {'assd': z(np.uint32), 'taxable': z(np.uint32), 'sd2': z(np.uint16), 'sale2': z(np.uint32), 'sq2': z(np.uint8), 'sd3': z(np.uint16), 'sale3': z(np.uint32), 'bcount': z(np.uint16),
        'lperm': z(np.uint16), 'pn5': z(np.uint16), 'cn_open': z(np.uint8), 'cn5': z(np.uint16), 'clast': z(np.uint16)}
    e = [''] * n
    str_det = {'mail': e, 'legal': e, 'psum': e, 'csum': e, 'nsum': e, 'grantor': e, 'book': e, 'reasons': e, 'rogo_txt': e, 'zinfo': zinfo, 'dsum': e}
    cols_geo = {'lat': np.where(la != 0, (la - GEO0[0]) * 1e6, 0).clip(0, 4e9).astype(np.uint32), 'lon': np.where(lo != 0, (lo - GEO0[1]) * 1e6, 0).clip(0, 4e9).astype(np.uint32)}
    packs = []; e0 = np.zeros(0, np.int64)
    for name, rr in (('main', idx), ('condo', e0)):
        f1, f2, f3 = f'{name}.bin.gz', f'{name}-detail.bin.gz', f'{name}-geo.bin.gz'
        b1 = write_pack(os.path.join(od, f1), rr, cols_main, str_main); b2 = write_pack(os.path.join(od, f2), rr, cols_det, str_det); b3 = write_pack(os.path.join(od, f3), rr, cols_geo, {})
        packs.append({'name': name, 'n': int(len(rr)), 'files': [f1], 'bytes': b1, 'detail': [f2], 'detailBytes': b2, 'geo': [f3], 'geoBytes': b3})
    zt = pd.Series([rules[f'{mu or "Puerto Rico"}|{zc[k]}'][6] if zc[k] else 'none' for k in rows_all]).value_counts().to_dict()
    meta = {'ver': f'{ver0}-{sl}', 'county': 'pr', 'municipio': mu, 'muniSlug': sl, 'total': int(n), 'built': dt.datetime.now().strftime('%m/%d/%Y'), 'rollYear': 2025, 'salesThrough': '',
            'geoOrigin': list(GEO0), 'stats': {'parcels': int(n), 'zoned': int((mz > 0).sum())}, 'packs': packs, 'distress': None, 'owners': None, 'vacancy': {'ge40': 0, 'ge60': 0},
            'permitCov': None, 'ownersFile': None, 'distressFile': None, 'flood': None, 'zoneTypes': zt,
            'screening': 'Zoning is the Junta de Planificacion calificacion map (screening only). Confirm with the Junta de Planificacion / OGPe before relying on it.',
            'dicts': {'city': city, 'zip': [''], 'cra': [''], 'landuse': ['', '9900 - USE CODE NOT PUBLIC (CRIM)'], 'zoning': [''], 'mzone': mzone},
            'sources': {'parcels': 'https://sigejp.pr.gov/server/rest/services/crim/crim_feb_2025/MapServer/0', 'zoning': 'https://sigejp.pr.gov/server/rest/services/calificacion/cali_vige/MapServer/0'}}
    json.dump(meta, open(os.path.join(od, 'meta.json'), 'w'), separators=(',', ':'))
    json.dump({'built': dt.date.today().isoformat(), 'source': 'Junta de Planificacion calificacion vigente (district names only; no dimensional rules published as data)',
               'fields': ['upa', 'stories', 'min_lot_sf', 'lot_cov', 'far', 'height_ft', 'zone_type', 'planned_dev', 'source'], 'counts': {'codes': len(rules)}, 'rules': rules},
              open(os.path.join(od, 'zoning-rules.json'), 'w'), separators=(',', ':'))
    # waterfront is not built for PR yet: write a valid empty file so the page does not 404 (listed as not in this release)
    with gzip.open(os.path.join(od, 'water.json.gz'), 'wt') as fh:
        json.dump({'v': '1', 'county': 'pr', 'built': dt.date.today().isoformat(), 'packVer': meta['ver'], 'counts': {'any': 0, 'records': int(n)}, 'sources': ['Not built for Puerto Rico yet (planned: CRIM water polygons + coastline)'], 'groups': {}}, fh)
    tb = sum(p['bytes'] + p['detailBytes'] + p['geoBytes'] for p in packs)
    index.append({'name': mu or 'Sin municipio', 'slug': sl, 'n': int(n), 'bytes': int(tb), 'lat': float(np.median(la[la != 0])) if (la != 0).any() else 18.2, 'lon': float(np.median(lo[lo != 0])) if (lo != 0).any() else -66.5})
    print(sl, n, f'{tb/1e6:.2f}MB', flush=True)
index.sort(key=lambda r: unicodedata.normalize('NFKD', r['name']).encode('ascii', 'ignore').decode().lower())
json.dump({'built': dt.date.today().isoformat(), 'total': int(sum(r['n'] for r in index)), 'stats': stats, 'municipios': index}, open(os.path.join(OUT, 'index.json'), 'w'), separators=(',', ':'), ensure_ascii=False)
print('total', sum(r['n'] for r in index), 'municipios', len(index), 'bytes', sum(r['bytes'] for r in index))
