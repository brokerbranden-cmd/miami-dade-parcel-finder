#!/usr/bin/env python3
"""Build the compact data packs the web app reads (data/meta.json + data/*.bin.gz).

Inputs (made by the fetch_* scripts and spatial_join.py, all from public Miami-Dade County sources):
  raw/pagis.parquet         Property Appraiser roll (PaGis layer), one row per folio, with WGS84 point
  raw/spatial.parquet       city/county zoning district + CRA polygon per folio (point-in-polygon)
  raw/zone_desc.json        PA zoning code -> description
  raw/tinc.json             PA tax-increment district code per OBJECTID
Pack format (same as the original app): uint32 LE header length, JSON header {n, cols:[{name,type,offset,bytes}]},
then column blobs (typed arrays, 4-byte aligned; strings joined with '\n'). Whole pack gzipped.
"""
import json, os, re, sys, gzip, datetime as dt, numpy as np, pandas as pd

RAW = os.environ.get('RAW', '/workspace/raw')
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(OUT, exist_ok=True)

df = pd.read_parquet(f'{RAW}/pagis.parquet')
n_raw = len(df)
df = df[df.FOLIO.notna()].drop_duplicates('FOLIO').reset_index(drop=True)
n_roll = len(df)
sp = pd.read_parquet(f'{RAW}/spatial.parquet')
df = df.merge(sp, on='FOLIO', how='left')
tinc = json.load(open(f'{RAW}/tinc.json'))
df['TINC'] = df.OBJECTID.astype(int).astype(str).map(tinc)
zdesc = json.load(open(f'{RAW}/zone_desc.json'))

S = lambda c: df[c].fillna('').astype(str).str.strip()
N = lambda c: pd.to_numeric(df[c], errors='coerce').fillna(0)

dor = S('DOR_CODE_CUR')
dcode = pd.to_numeric(dor, errors='coerce').fillna(0).astype(int)
# drop farmland (agricultural DOR codes 5000-6999) and reference-only folios (DOR 0000, no values)
is_farm = (dcode >= 5000) & (dcode < 7000)
is_ref = (dor == '0000') | (S('REFERENCE_ONLY_FLAG') == 'Y') & (N('TOTAL_VAL_CUR') == 0)
keep = ~is_farm & ~is_ref
stats = {'raw_records': int(n_raw), 'roll_folios': int(n_roll), 'farmland_removed': int(is_farm.sum()), 'reference_removed': int((is_ref & ~is_farm).sum())}
df = df[keep].reset_index(drop=True)
S = lambda c: df[c].fillna('').astype(str).str.strip()
N = lambda c: pd.to_numeric(df[c], errors='coerce').fillna(0)
n = len(df); print('kept', n, stats)

# ---------- dictionaries ----------
def dict_index(values, first=''):
    uniq = sorted(set(values) - {first})
    lst = [first] + uniq; idx = {v: i for i, v in enumerate(lst)}
    return lst, np.array([idx[v] for v in values], dtype=np.int64)

landuse_s = (S('DOR_CODE_CUR') + ' - ' + S('DOR_DESC').str.replace(r'\s+', ' ', regex=True)).where(S('DOR_CODE_CUR') != '', '')
landuse, landuse_i = dict_index(list(landuse_s))
pz = S('PRIMARY_ZONE').where(lambda x: x.str.match(r'^[0-9A-Z]{2,4}$'), '')
zoning_s = [f"{z} - {zdesc.get(z, '') or ''}".strip() if z else '' for z in pz]
zoning_s = [re.sub(r'\s+', ' ', z) for z in zoning_s]
zoning, zoning_i = dict_index(zoning_s)
city, city_i = dict_index(list(S('TRUE_SITE_CITY')))
zip5 = S('TRUE_SITE_ZIP_CODE').str[:5].where(lambda s: s.str.match(r'^\d{5}$'), '')
zips, zip_i = dict_index(list(zip5))

# CRA: official county CRA polygons; else PA tax-increment district code (named by code + city)
cra_poly = S('CRA_POLY').str.replace(r'\s+', ' ', regex=True)
def cra_name(p, t, c):
    if p: return p.replace('Opa-Locka', 'Opa-locka') + ' CRA'
    if t and re.match(r'^90\d\d$', t): return f'Tax increment district {t} ({c or "County"})'
    return ''
tinc_s = S('TINC'); tinc_city = pd.DataFrame({'t': tinc_s, 'c': S('TRUE_SITE_CITY')}).groupby('t').c.agg(lambda x: x.value_counts().index[0]).to_dict()
cra_s = [cra_name(p, t, tinc_city.get(t, '')) for p, t in zip(cra_poly, tinc_s)]
cra, cra_i = dict_index(cra_s)

# Municipal / county zoning districts (mzone): [code, jurisdiction, description, units/acre, stories, min lot sqft]
JUR = {'MIAMI-DADE COUNTY': 'Miami-Dade County', 'OPA-LOCKA': 'Opa-locka', 'INDIAN CREEK VILLAGE': 'Indian Creek'}
def jname(j): return JUR.get(j, ' '.join(w.capitalize() for w in j.split()))
SMALL = {'of', 'and', 'or', 'the', 'to', 'in', 'a'}
def tcase(s):
    s = re.sub(r'\s+', ' ', s or '').strip()
    if not s: return ''
    if s.upper() != s: return s[0].upper() + s[1:]
    out = []
    for i, w in enumerate(s.lower().split(' ')):
        if re.search(r'\d', w) or re.fullmatch(r'\(?[a-z]{1,3}-?\d*\)?', w) and w.strip('()') in ('ru', 'bu', 'iu', 'eu', 'gu', 'pad', 'pud', 'cra', 'hd', 'ci', 'cs', 'mu', 'tod', 'sf'):
            out.append(w.upper())
        elif i and w in SMALL: out.append(w)
        else: out.append(re.sub(r'[a-z]', lambda m: m.group(0).upper(), w, count=1))
    return ' '.join(out)
def m21(code):
    """Miami 21 transect parameters (Miami 21 Code, Article 4 Table 4 / Article 5): units per acre, max stories, min lot."""
    m = re.match(r'^T(\d)(?:-(\d+)[AB]?)?-([LOR])$', code)
    if m:
        t, h, sub = int(m.group(1)), m.group(2), m.group(3)
        if t == 3: return ('18' if sub == 'O' else '9'), '2', '5000'
        if t == 4: return '36', '3', '5000'
        if t == 5: return '65', '5', '5000'
        if t == 6: return '150', (h or ''), '5000'
    if code == 'D1': return '36', '', ''
    if code == 'CI-HD': return '150', '', ''
    return '', '', ''
mz_list = [None]; mz_idx = {}
mz_i = np.zeros(n, dtype=np.int64)
for k, (c, j, d) in enumerate(zip(S('MZ_CODE'), S('MZ_JURIS'), S('MZ_DESC'))):
    if not c: continue
    key = (c, j, d)
    if key not in mz_idx:
        upa, st, ml = m21(c) if j == 'MIAMI' else ('', '', '')
        mz_idx[key] = len(mz_list); mz_list.append([c, jname(j), tcase(d) or c, upa, st, ml])
    mz_i[k] = mz_idx[key]

# ---------- owner flags ----------
o1, o2, o3 = S('TRUE_OWNER1'), S('TRUE_OWNER2'), S('TRUE_OWNER3')
owner_all = (o1 + ' ' + o2 + ' ' + o3).str.upper().str.replace(r'\s+', ' ', regex=True)
owner_str = [' | '.join([x for x in t if x]) for t in zip(o1, o2, o3)]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import owner_kind
EST = re.compile(r"\b(EST|ESTATE|EST OF|ESTATE OF|HEIRS?|DECEASED|DECD|DEC'D)\b")
# owner type = owner_kind.classify (see that module): 'govt' | 'corp' (every non-government organization, incl. utilities, banks, associations,
# institutions) | 'trust' | 'person'. Care-of / attn lines are ignored; owner-name lines are read together.
_given = owner_kind.build_given(list(o1))
_kc = {}
def _cls(t):
    r = _kc.get(t)
    if r is None: r = _kc[t] = owner_kind.classify(t, _given)
    return r
_res = [_cls(t) for t in zip(o1, o2, o3)]
kinds = [r[0] for r in _res]
subs = [r[1] for r in _res]
est = [k in ('person', 'trust') and bool(EST.search(re.sub(r'\b(LIFE|REAL|REALTY|RE|RL|R E) EST(ATE)?\b', ' ', s))) for s, k in zip(owner_all, kinds)]

mstate = S('TRUE_MAILING_STATE').str.upper(); mcountry = S('TRUE_MAILING_COUNTRY').str.upper()
oos = ((mstate != '') & (mstate != 'FL')) | (~mcountry.isin(['', 'USA', 'US', 'U S A', 'UNITED STATES']))
mzip5 = S('TRUE_MAILING_ZIP_CODE').str[:5]
absz = (mzip5 != '') & (zip5 != '') & (mzip5 != zip5)
homestead = N('HSTEAD_EX_VAL_CUR') > 0
senior = (N('CNTY_SR_EX_VAL_CUR') > 0) | (N('CNTY_LNG_TERM_SR_EX_VAL_CUR') > 0)
FLAG = {'homestead': 1, 'oos': 2, 'absz': 4, 'corp': 8, 'trust': 16, 'govt': 32, 'estate': 64, 'senior': 128}
flags = (homestead.values * 1 | oos.values * 2 | absz.values * 4 | np.array([k == 'corp' for k in kinds]) * 8 |
         np.array([k == 'trust' for k in kinds]) * 16 | np.array([k == 'govt' for k in kinds]) * 32 | np.array(est) * 64 | senior.values * 128).astype(np.uint8)

# ---------- strings ----------
def clean(s): return re.sub(r'\s+', ' ', s.replace('\n', ' ')).strip()
mail = []
for a1, a2, a3, c, st, z, co in zip(S('TRUE_MAILING_ADDR1'), S('TRUE_MAILING_ADDR2'), S('TRUE_MAILING_ADDR3'), S('TRUE_MAILING_CITY'),
                                   S('TRUE_MAILING_STATE'), S('TRUE_MAILING_ZIP_CODE'), S('TRUE_MAILING_COUNTRY')):
    z = re.sub(r'-0000$', '', z)
    parts = [p for p in (a1, a2, a3) if p] + [p for p in (c, (st + ' ' + z).strip()) if p]
    if co and co.upper() not in ('USA', 'US', 'UNITED STATES'): parts.append(co)
    mail.append(clean(', '.join(parts)))
LEGAL_CUT = re.compile(r'\s(LOT SIZE\b|OR \d{3,5}-\d|COC \d|F/A/U\b|FAU\b)')
def legal_short(s):
    s = clean(s); m = LEGAL_CUT.search(s)
    return s[:m.start()].strip() if m and m.start() > 8 else s
legal = [legal_short(s) for s in S('LEGAL')]
addr = [clean(a) for a in S('TRUE_SITE_ADDR')]

# ---------- numbers ----------
DAY0 = dt.date(1900, 1, 1)
def days(col):
    out = np.zeros(n, dtype=np.int64)
    for k, v in enumerate(S(col)):
        if len(v) >= 8 and v[:8].isdigit():
            try: out[k] = (dt.date(int(v[:4]), int(v[4:6]), int(v[6:8])) - DAY0).days
            except ValueError: pass
    return out
u32 = lambda a: np.clip(np.round(np.asarray(a, dtype=float)), 0, 4294967295).astype(np.uint32)
u16 = lambda a: np.clip(np.round(np.asarray(a, dtype=float)), 0, 65535).astype(np.uint16)
u8 = lambda a: np.clip(np.round(np.asarray(a, dtype=float)), 0, 255).astype(np.uint8)
heated = N('BUILDING_HEATED_AREA'); actual = N('BUILDING_ACTUAL_AREA')
sqft = np.where(heated > 0, heated, actual)
qflag = lambda c: np.select([S(c) == 'Q', S(c) == 'U'], [1, 2], 0)
yb = N('YEAR_BUILT'); yb = np.where((yb > 1700) & (yb < 2100), yb, 0)
lat = pd.to_numeric(df.LAT, errors='coerce').fillna(0).values; lon = pd.to_numeric(df.LON, errors='coerce').fillna(0).values

# ---------- distress score (see README "Distress Score") ----------
# hard signals come from build_distress.py (RAW/distress.parquet); soft owner/property signals are added here.
dfile = f'{RAW}/distress.parquet'
if os.path.exists(dfile):
    dd = pd.read_parquet(dfile)
    dmap = df[['FOLIO']].merge(dd, on='FOLIO', how='left')
    dsig = dmap.dsig.fillna(0).astype(np.int64).values; dhard = dmap.dhard.fillna(0).values
else:
    dsig = np.zeros(n, dtype=np.int64); dhard = np.zeros(n)
est_a = np.array(est); corp_gov = np.array([k in ('corp', 'govt') for k in kinds])
dsig = dsig | (est_a * (1 << 10))                     # PR bit also set by estate/heirs owner names
dpts = dmap.dpts.fillna('').values if os.path.exists(dfile) else np.array([''] * n)
has_pr = np.array(['"PR"' in x for x in dpts]); has_dc = np.array(['"DC"' in x for x in dpts])
dhard = dhard + np.where(est_a & ~has_pr, np.where(has_dc, 7, 15), 0)   # estate/heirs owner name = PR (PR+DC capped at 22)
bv, mk, landv = N('BUILDING_VAL_CUR').values, N('TOTAL_VAL_CUR').values, N('LAND_VAL_CUR').values
sd1d = days('DOS_1'); today_d = (dt.date.today() - DAY0).days
yrs_owned = np.where(sd1d > 0, (today_d - sd1d) / 365.25, 0)
s_abs = np.where(oos.values, 6, np.where(absz.values, 4, 0))
s_long = np.where(yrs_owned >= 20, 5, np.where(yrs_owned >= 10, 2, 0))
tear = (bv > 0) & (mk > 0) & (bv / np.maximum(mk, 1) < 0.2)
s_tear = np.where(tear, 6, np.where((bv == 0) & (N('LOT_SIZE').values > 0) & ~corp_gov, 3, 0))
s_nohs = np.where(~homestead.values & ~corp_gov, 3, 0)
soft = np.minimum(20, s_abs + s_long + s_tear + s_nohs)
dsig = dsig | ((s_abs > 0) << 12) | ((s_long >= 5) << 13) | (tear << 14) | ((s_nohs > 0) << 15)
govt_a = np.array([k == 'govt' for k in kinds])
dscore = np.where(govt_a, 0, np.minimum(100, dhard + soft))  # government-owned land never scores
dsig = np.where(govt_a, 0, dsig)
# ---------- vacancy / neglect hint (see scripts/vacancy_lib.py / README "Vacancy & condition hints") ----------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vacancy_lib
vscore, vsig, lastpermit, vac_stats = vacancy_lib.compute(RAW, list(S('FOLIO')), kinds, homestead.values, oos.values, absz.values,
                                                          yrs_owned, bv, mk, yb, dsig.astype(np.int64))
vbonus = np.where(vscore >= 60, 8, np.where(vscore >= 40, 5, 0))       # capped soft signal on top of the distress score
dscore = np.where(govt_a, 0, np.minimum(100, dscore + vbonus))
print('vacancy:', {k: v for k, v in vac_stats.items() if k != 'permits'})
import permit_lib
pl = getattr(vacancy_lib.compute, 'pl', None)       # per-parcel permit / code-case columns (None when merge_permits.py has not run: packs then carry zeros)
z = lambda t: np.zeros(len(df), t)
PC = {'pcs': z(np.uint16), 'pn5': z(np.uint16), 'cn_open': z(np.uint8), 'cn5': z(np.uint16), 'clast': z(np.uint16), 'psum': [''] * len(df), 'csum': [''] * len(df)}
if pl is not None:
    PC = {'pcs': pl['pcs'], 'pn5': pl['n5'], 'cn_open': pl['cn_open'], 'cn5': pl['cn5'], 'clast': pl['clast'].astype(np.uint16), 'psum': pl['psum'], 'csum': pl['csum']}
    print('permit columns: parcels with permit data', int(pl['has_p'].sum()), 'with case data', int(pl['has_c'].sum()), 'no-permit flagged', int(pl['np_flag'].sum()))
pd.DataFrame({'FOLIO': df.FOLIO.values, 'dscore': dscore.astype(int), 'dsig': dsig.astype(int), 'hard': np.minimum(100, dhard).astype(int), 'soft': soft.astype(int)}).to_parquet(f'{RAW}/scores.parquet', index=False)
print('distress: parcels with any hard signal', int((dhard > 0).sum()), 'score>=50', int((dscore >= 50).sum()), 'score>=70', int((dscore >= 70).sum()))

# ---------- owner portfolios (see scripts/owners_lib.py / README "Owner portfolios") ----------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import owners_lib
landuse_up = [x.upper() for x in landuse_s]
is_condo_all = np.array(['CONDOMINIUM' in x or 'COOPERATIVE' in x for x in landuse_up])
og, owners = owners_lib.group_owners(list(o1), kinds, subs, list(S('TRUE_MAILING_ADDR1')), list(S('TRUE_MAILING_ADDR2')), list(S('TRUE_MAILING_ZIP_CODE')),
                                     list(S('TRUE_SITE_ADDR')), list(zip5), (dhard > 0) & ~govt_a, is_condo_all, N('TOTAL_VAL_CUR').values)
owners['built'] = dt.datetime.now().strftime('%m/%d/%Y')
with gzip.open(os.path.join(OUT, 'owners.json.gz'), 'wt', compresslevel=9) as fh: json.dump(owners, fh, separators=(',', ':'))
G = np.array(owners['n']); GF = np.array(owners['fl']); GD = np.array(owners['nd'])
owner_stats = {'groups': int(len(G) - 1), 'parcels_in_groups': int((og > 0).sum()), 'mail_links': owners['linkedMail'],
               'groups_5plus': int((G[1:] >= 5).sum()), 'groups_2plus_distressed': int((GD[1:] >= 2).sum()),
               'groups_2plus_distressed_non_institutional': int(((GD[1:] >= 2) & (GF[1:] == 0)).sum())}
print('owners:', owner_stats)

cols_main = {
    'city': u8(city_i), 'zip': u16(zip_i), 'cra': u8(cra_i), 'landuse': u16(landuse_i), 'zoning': u16(zoning_i), 'mz': u16(mz_i),
    'lot': u32(N('LOT_SIZE')), 'mkt': u32(N('TOTAL_VAL_CUR')), 'land': u32(N('LAND_VAL_CUR')), 'bldg': u32(N('BUILDING_VAL_CUR')),
    'sqft': u32(sqft), 'yb': u16(yb), 'units': u16(N('UNIT_COUNT')), 'beds': u8(N('BEDROOM_COUNT')),
    'baths': u8((N('BATHROOM_COUNT') + 0.5 * N('HALF_BATHROOM_COUNT')) * 10), 'stories': u8(N('FLOOR_COUNT')),
    'sd1': u16(days('DOS_1')), 'sale1': u32(N('PRICE_1')), 'sq1': u8(qflag('QU_FLG_1')), 'flags': flags,
    'prv': u32(N('TOTAL_VAL_PRI')), 'dscore': u8(dscore), 'dsig': u16(dsig), 'og': og.astype(np.uint32), 'vscore': vscore, 'vsig': vsig, 'pcs': PC['pcs'],
}
str_main = {'folio': list(S('FOLIO')), 'addr': addr, 'owner': [clean(o) for o in owner_str]}
cols_det = {'assd': u32(N('ASSESSED_VAL_CUR')), 'taxable': u32(N('CNTY_TAXABLE_VAL_CUR')), 'sd2': u16(days('DOS_2')), 'sale2': u32(N('PRICE_2')),
            'sq2': u8(qflag('QU_FLG_2')), 'sd3': u16(days('DOS_3')), 'sale3': u32(N('PRICE_3')), 'bcount': u16(N('BUILDING_COUNT')), 'lperm': u16(lastpermit),
            'pn5': PC['pn5'], 'cn_open': PC['cn_open'], 'cn5': PC['cn5'], 'clast': PC['clast']}
str_det = {'mail': mail, 'legal': legal, 'psum': PC['psum'], 'csum': PC['csum'], 'grantor': [clean(x) for x in S('GRANTOR_1')],
           'book': [f'{b}-{p}' if b.strip('0') else '' for b, p in zip(S('OR_BK_1'), S('OR_PG_1'))]}
cols_geo = {'lat': ((lat - 24.0) * 1e6).clip(0, 4e9).astype(np.uint32), 'lon': ((lon + 81.5) * 1e6).clip(0, 4e9).astype(np.uint32)}

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
    hdr = json.dumps({'n': int(len(rows)), 'cols': hdr_cols}, separators=(',', ':')).encode()
    hdr += b' ' * ((-(4 + len(hdr))) % 4)
    raw = len(hdr).to_bytes(4, 'little') + hdr + b''.join(blobs)
    gz = gzip.compress(raw, 9, mtime=0)
    open(path, 'wb').write(gz)
    return len(gz), len(raw)

# condo pack = land-use descriptions with CONDOMINIUM / COOPERATIVE (same rule as the app's luType)
is_condo = np.array(['CONDOMINIUM' in s.upper() or 'COOPERATIVE' in s.upper() for s in landuse_s])
order_main = np.where(~is_condo)[0]; order_condo = np.where(is_condo)[0]
ver = dt.datetime.now().strftime('%Y%m%d%H%M')
packs = []
for name, rows in (('main', order_main), ('condo', order_condo)):
    f1 = f'{name}.bin.gz'; f2 = f'{name}-detail.bin.gz'; f3 = f'{name}-geo.bin.gz'
    b1, r1 = write_pack(os.path.join(OUT, f1), rows, cols_main, str_main)
    b2, r2 = write_pack(os.path.join(OUT, f2), rows, cols_det, str_det)
    b3, r3 = write_pack(os.path.join(OUT, f3), rows, cols_geo, {})
    packs.append({'name': name, 'n': int(len(rows)), 'files': [f1], 'bytes': b1, 'detail': [f2], 'detailBytes': b2, 'geo': [f3], 'geoBytes': b3})
    print(name, len(rows), f'main {b1/1e6:.1f}MB (raw {r1/1e6:.1f}) detail {b2/1e6:.1f}MB geo {b3/1e6:.1f}MB')

permit_cov = None
if pl is not None:
    permit_cov = {'built': pl['index_built'], 'cities': {m: {k: v for k, v in c.items() if k not in ('permit_note', 'code_note')} | {'permit_note': c['permit_note'], 'code_note': c['code_note']} for m, c in pl['cov'].items()},
                  'stats': pl['idx_stats'], 'sources': [{k: r.get(k) for k in ('city', 'kind', 'records', 'matched_folio', 'matched_address', 'match_rate', 'url')} for r in pl['sources']]}
last_sale = int(max(cols_main['sd1'].max(), 0))
meta = {
    'ver': ver, 'total': int(n), 'built': dt.datetime.now().strftime('%m/%d/%Y'),
    'rollYear': int(pd.to_numeric(df.ASSESSMENT_YEAR_CUR, errors='coerce').max()),
    'salesThrough': (DAY0 + dt.timedelta(days=last_sale)).strftime('%m/%d/%Y'),
    'stats': stats, 'packs': packs,
    'distress': json.load(open(f'{RAW}/distress_stats.json')) if os.path.exists(f'{RAW}/distress_stats.json') else None,
    'owners': owner_stats, 'vacancy': vac_stats, 'permitCov': permit_cov, 'ownersFile': 'owners.json.gz',
    'distressFile': 'distress.json.gz' if os.path.exists(os.path.join(OUT, 'distress.json.gz')) else None,
    'dicts': {'city': city, 'zip': zips, 'cra': cra, 'landuse': landuse, 'zoning': zoning, 'mzone': mz_list},
    'sources': {
        'roll': 'https://gisweb.miamidade.gov/arcgis/rest/services/MD_ComparableSales/MapServer/5',
        'municipalZoning': 'https://gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer/19',
        'countyZoning': 'https://gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer/18',
        'cra': 'https://gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer/20',
        'zoneDescriptions': 'https://apps.miamidadepa.gov/PApublicServiceProxy/PaServicesProxy.ashx (GetPropertySearchByFolio)'},
}
json.dump(meta, open(os.path.join(OUT, 'meta.json'), 'w'), separators=(',', ':'))
print('meta written', meta['total'], meta['salesThrough'], 'mz', len(mz_list), 'cra', len(cra), 'landuse', len(landuse), 'zoning', len(zoning))
pd.Series(kinds).value_counts().pipe(print); print('estate', sum(est), 'oos', int(oos.sum()), 'homestead', int(homestead.sum()), 'senior', int(senior.sum()))
