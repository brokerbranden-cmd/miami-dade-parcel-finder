#!/usr/bin/env python3
"""Monroe County, FL phase-1 packs -> data/monroe/ (meta.json, main/condo packs, owners.json.gz, comps.json.gz).
Input: $RAW/monroe/parcels.jsonl + flood.geojson from fetch_monroe.py (FL statewide cadastral = FDOR roll, FEMA NFHL).
Same pack format + column names as scripts/build_data.py so app.js reads it unchanged. Columns with no Monroe source are zeros:
zoning / city zoning code (mcgis4 unreachable), CRA (re-used for the FEMA flood zone), permits/code cases, Clerk/tax distress.
Soft signals only: absentee / out of state, long hold, low building value (teardown basics), no homestead, estate/heirs owner names."""
import json, os, re, sys, gzip, datetime as dt, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); SCR = os.path.abspath(os.path.join(HERE, '..', '..')); sys.path.insert(0, SCR)
import owner_kind, owners_lib
sys.path.insert(0, HERE)
import monroe_enrich as ME
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe')
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SCR, '..', 'data', 'monroe'); os.makedirs(OUT, exist_ok=True)
GEO0 = (24.0, -83.2)   # pack lat/lon origin (Monroe reaches -82.9 at the Dry Tortugas; Miami-Dade's origin -81.5 would clip Key West)

df = pd.read_json(f'{RAW}/parcels.jsonl', lines=True, dtype=False)
n_raw = len(df)
df['FOLIO'] = df.PARCEL_ID.fillna('').astype(str).str.replace(r'\D', '', regex=True)
df = df[df.FOLIO != ''].drop_duplicates('FOLIO').reset_index(drop=True); n_roll = len(df)
S = lambda c: df[c].fillna('').astype(str).str.strip()
N = lambda c: pd.to_numeric(df[c], errors='coerce').fillna(0)
uc = pd.to_numeric(S('DOR_UC'), errors='coerce').fillna(-1).astype(int)
is_farm = (uc >= 50) & (uc <= 69)
is_ref = (uc < 0) | ((N('JV') == 0) & (uc.isin([94, 95, 96, 98]) | (uc < 0)))   # right-of-way / submerged / centrally assessed with no value
keep = ~is_farm & ~is_ref
stats = {'raw_records': int(n_raw), 'roll_folios': int(n_roll), 'farmland_removed': int(is_farm.sum()), 'reference_removed': int((is_ref & ~is_farm).sum())}
df = df[keep].reset_index(drop=True); uc = uc[keep].reset_index(drop=True); n = len(df); print('kept', n, stats)

DOR = {0:'VACANT RESIDENTIAL',1:'SINGLE FAMILY',2:'MOBILE HOME',3:'MULTIFAMILY 10+ UNITS',4:'CONDOMINIUM',5:'COOPERATIVE',6:'RETIREMENT HOME',7:'MISC RESIDENTIAL',
 8:'MULTIFAMILY 2-9 UNITS',9:'RESIDENTIAL COMMON ELEMENTS',10:'VACANT COMMERCIAL',11:'STORES',12:'MIXED USE STORE / OFFICE',13:'DEPARTMENT STORE',14:'SUPERMARKET',
 15:'REGIONAL SHOPPING CENTER',16:'COMMUNITY SHOPPING CENTER',17:'OFFICE 1 STORY',18:'OFFICE MULTI-STORY',19:'PROFESSIONAL SERVICE',20:'AIRPORT / MARINA',
 21:'RESTAURANT',22:'DRIVE-IN RESTAURANT',23:'FINANCIAL',24:'INSURANCE',25:'REPAIR SERVICE',26:'SERVICE STATION',27:'AUTO SALES / REPAIR',28:'PARKING / MOBILE HOME PARK',
 29:'WHOLESALE',30:'FLORIST / GREENHOUSE',31:'DRIVE-IN THEATER',32:'THEATER / AUDITORIUM',33:'NIGHTCLUB / BAR',34:'BOWLING / ARENA',35:'TOURIST ATTRACTION',36:'CAMP',
 37:'RACE TRACK',38:'GOLF COURSE',39:'HOTEL / MOTEL',40:'VACANT INDUSTRIAL',41:'LIGHT MANUFACTURING',42:'HEAVY INDUSTRIAL',43:'LUMBER YARD',44:'PACKING PLANT',
 45:'CANNERY / BOTTLER',46:'FOOD PROCESSING',47:'MINERAL PROCESSING',48:'WAREHOUSE / DISTRIBUTION',49:'OPEN STORAGE',70:'VACANT INSTITUTIONAL',71:'CHURCH',
 72:'PRIVATE SCHOOL',73:'PRIVATE HOSPITAL',74:'HOME FOR THE AGED',75:'NON-PROFIT SERVICE',76:'MORTUARY / CEMETERY',77:'CLUB / LODGE',78:'SANITARIUM',79:'CULTURAL',
 80:'VACANT GOVERNMENTAL',81:'MILITARY',82:'GOVERNMENTAL PARK / FOREST',83:'PUBLIC SCHOOL',84:'COLLEGE',85:'PUBLIC HOSPITAL',86:'COUNTY GOVERNMENTAL',87:'STATE GOVERNMENTAL',
 88:'FEDERAL GOVERNMENTAL',89:'MUNICIPAL GOVERNMENTAL',90:'LEASEHOLD GOVERNMENTAL',91:'UTILITY',92:'MINING',93:'SUBSURFACE RIGHTS',94:'RIGHT-OF-WAY',
 95:'SUBMERGED / RIVERS / LAKES',96:'SEWAGE / WASTE LAND',97:'OUTDOOR RECREATION',98:'CENTRALLY ASSESSED',99:'ACREAGE NOT AGRICULTURAL'}
lu_s = [f'{c*100:04d} - {DOR.get(c, "USE " + str(c))}' for c in uc]
def dict_index(vals):
    d = ['']; ix = {'': 0}; out = np.zeros(len(vals), np.int64)
    for k, v in enumerate(vals):
        if v not in ix: ix[v] = len(d); d.append(v)
        out[k] = ix[v]
    return d, out
def tcase(s): return ' '.join(w.capitalize() for w in s.split())
city_s = [tcase(c) if c else 'Unincorporated' for c in S('PHY_CITY')]
zip5 = S('PHY_ZIPCD').str.replace(r'\.0$', '', regex=True).str[:5]
# FEMA flood zone at the parcel centroid
lat = pd.to_numeric(df.LAT, errors='coerce').fillna(0).values; lon = pd.to_numeric(df.LON, errors='coerce').fillna(0).values
flood_s = [''] * n; fstats = {}
try:
    import geopandas as gpd
    fz = gpd.read_file(f'{RAW}/flood.geojson')
    def lab(z, sub, bfe):
        z = z.strip() if isinstance(z, str) else ''; sub = sub.upper() if isinstance(sub, str) else ''; b = pd.to_numeric(bfe, errors='coerce')
        if not z: return ''
        if z.startswith('V'): t = f'{z} - coastal high hazard'
        elif z.startswith('A'): t = f'{z} - high risk'
        elif z == 'X': t = 'X - moderate risk (0.2%)' if '0.2' in sub else 'X - minimal risk'
        else: t = z
        if b and b > -9000 and b > 0: t += f' (BFE {b:g} ft)'
        return t
    fz['lab'] = [lab(a, b, c) for a, b, c in zip(fz.FLD_ZONE, fz.ZONE_SUBTY, fz.STATIC_BFE)]
    ok = (lat != 0)
    pts = gpd.GeoDataFrame({'k': np.where(ok)[0]}, geometry=gpd.points_from_xy(lon[ok], lat[ok]), crs=4326)
    j = gpd.sjoin(pts, fz[['lab', 'geometry']], how='left', predicate='within')
    # several overlapping polygons: keep the riskiest (V > A > X)
    j['r'] = j.lab.fillna('').map(lambda t: 3 if t.startswith('V') else 2 if t.startswith('A') else 1 if t else 0)
    j = j.sort_values('r', ascending=False).drop_duplicates('k')
    for k, t in zip(j.k, j.lab.fillna('')): flood_s[k] = t
    fstats = pd.Series([t.split(' ')[0] if t else 'none' for t in flood_s]).value_counts().to_dict()
    print('flood', fstats)
except Exception as e:
    print('WARN flood join skipped:', e)
city, city_i = dict_index(city_s); zips, zip_i = dict_index(list(zip5)); landuse, landuse_i = dict_index(lu_s); flood, flood_i = dict_index(flood_s)

# owners
o1 = S('OWN_NAME'); fidu = S('FIDU_NAME')
_given = owner_kind.build_given(list(o1)); _kc = {}
def _cls(t):
    r = _kc.get(t)
    if r is None: r = _kc[t] = owner_kind.classify(t, _given)
    return r
res = [_cls((a, '', '')) for a in o1]; kinds = [r[0] for r in res]; subs = [r[1] for r in res]
# agencies the generic classifier misses (Monroe has ~26k federal / state conservation parcels: NPS, USFWS, TIIF trustees, FDOT, water management)
GOVT_RE = re.compile(r"^(USA\b|U S A\b|UNITED STATES|US FISH|US DEPT|BOT TIIF|BOARD OF TRUSTEES|TIITF|TRUSTEES OF THE INTERNAL|DOT/ST|DOT ST|FLORIDA DEPT|FLORIDA DEPARTMENT|STATE OF FLORIDA|ST OF FL|FISH AND WILDLIFE|FL FISH|SOUTH FLORIDA WATER|SFWMD|MONROE COUNTY\b|CITY OF |CITY OF$|FLORIDA KEYS AQUEDUCT|KEYS ENERGY|FKAA|FLORIDA KEYS MOSQUITO|MONROE CO |SCHOOL BOARD)")
for _k, _o in enumerate(o1):
    if GOVT_RE.search(_o.upper().strip()): kinds[_k] = 'govt'; subs[_k] = subs[_k] or 'agency'

EST = re.compile(r"\b(EST|ESTATE|EST OF|ESTATE OF|HEIRS?|DECEASED|DECD|DEC'D)\b")
est = np.array([k in ('person', 'trust') and bool(EST.search(re.sub(r'\b(LIFE|REAL|REALTY|RE|RL|R E) EST(ATE)?\b', ' ', (a + ' ' + f).upper())))
                for a, f, k in zip(o1, fidu, kinds)])
mst = S('OWN_STATE').str.upper(); mst2 = S('OWN_STATE_').str.upper()
mstate = np.where(mst2 != '', mst2, mst)
mzip5 = S('OWN_ZIPCD').str.replace(r'\.0$', '', regex=True).str[:5]
homestead = (N('JV_HMSTD') > 0).values
kinds_a = np.array(kinds)
# ---- absentee / out-of-area owner (fixed): the old rule 'mailing ZIP differs from site ZIP' flagged 60,676 of 88,552 (68%) - it counted the ~26k federal / state conservation
# parcels (NPS mails to DC 20240, Tallahassee 32399 TIIF, USFWS Atlanta 30345), Keys-local owners (PO box in another Keys ZIP) and vacant lots.
# New rule: private owner, no homestead exemption, mailing address is NOT the site address, and the mailing ZIP is outside the Keys (330xx Monroe ZIPs).
KEYS_ZIPS = {'33001', '33036', '33037', '33040', '33041', '33042', '33043', '33044', '33045', '33050', '33051', '33052', '33070', '33034'}
def _st(a): return re.sub(r'\b(STREET|ST|AVENUE|AVE|ROAD|RD|DRIVE|DR|LANE|LN|BOULEVARD|BLVD|COURT|CT|CIRCLE|CIR|TERRACE|TER|PLACE|PL|WAY|HIGHWAY|HWY|KEY)\b', '', re.sub(r'[^A-Z0-9 ]', ' ', a.upper())).split()[:2]
same_addr = np.array([bool(a) and bool(m) and _st(a) == _st(m) and _st(a) != [] for a, m in zip(S('PHY_ADDR1'), S('OWN_ADDR1'))])
govt_k = kinds_a == 'govt'
in_keys = mzip5.isin(KEYS_ZIPS).values
oos = (mstate != '') & (mstate != 'FL') & ~govt_k & ~homestead & ~same_addr
absz = (mzip5 != '').values & ~in_keys & ~govt_k & ~homestead & ~same_addr
keys_local_other = in_keys & ~govt_k & ~homestead & ~same_addr & (mzip5 != zip5).values
absentee_stats = {'old_rule_zip_differs': int(((mzip5 != '') & (zip5 != '') & (mzip5 != zip5)).sum()), 'govt_owned': int(govt_k.sum()), 'homestead': int(homestead.sum()), 'same_address_mailing': int((same_addr & ~govt_k).sum()),
                  'absentee_new': int(absz.sum()), 'out_of_state': int(oos.sum()), 'florida_outside_keys': int((absz & ~oos).sum()), 'keys_local_other_address_not_flagged': int(keys_local_other.sum())}
print('absentee', absentee_stats)
flags = (homestead * 1 | oos * 2 | absz * 4 | (kinds_a == 'corp') * 8 | (kinds_a == 'trust') * 16 | (kinds_a == 'govt') * 32 | est * 64).astype(np.uint8)
mail = []
for a1, a2, c, st, z, s2 in zip(S('OWN_ADDR1'), S('OWN_ADDR2'), S('OWN_CITY'), S('OWN_STATE'), S('OWN_ZIPCD'), S('OWN_STATE_')):
    z = re.sub(r'\.0$', '', z)
    st = st if len(st) <= 3 else st
    parts = [p for p in (a1, a2) if p] + [p for p in (c, (st + ' ' + z).strip()) if p]
    if s2 and len(s2) > 2 and s2.upper() not in ('USA', 'US', 'UNITED STATES', st.upper()): parts.append(s2)
    mail.append(re.sub(r'\s+', ' ', ', '.join(parts)).strip())
addr = [re.sub(r'\s+', ' ', a).strip() for a in S('PHY_ADDR1')]

# numbers
DAY0 = dt.date(1900, 1, 1)
def sday(yc, mc):
    y = pd.to_numeric(df[yc], errors='coerce').fillna(0).astype(int).values; m = pd.to_numeric(df[mc], errors='coerce').fillna(0).astype(int).values
    out = np.zeros(n, np.int64)
    for k in range(n):
        if 1800 < y[k] < 2100: out[k] = (dt.date(y[k], m[k] if 1 <= m[k] <= 12 else 1, 15) - DAY0).days
    return out
u32 = lambda a: np.clip(np.round(np.asarray(a, dtype=float)), 0, 4294967295).astype(np.uint32)
u16 = lambda a: np.clip(np.round(np.asarray(a, dtype=float)), 0, 65535).astype(np.uint16)
u8 = lambda a: np.clip(np.round(np.asarray(a, dtype=float)), 0, 255).astype(np.uint8)
mk = N('JV').values; landv = N('LND_VAL').values; bv = np.maximum(mk - landv, 0) * (landv > 0)   # FDOR has no building value: JV - land (0 when land value is blank)
yb = N('ACT_YR_BLT').values; yb = np.where((yb > 1700) & (yb < 2100), yb, 0)
sd1 = sday('SALE_YR1', 'SALE_MO1'); sd2 = sday('SALE_YR2', 'SALE_MO2')
# FDOR qualification codes: 01 / 02 = qualified (arm's length); 11+ = disqualified (DOR Rule 12D-8.011 sale qualification codes)
qf = lambda c: np.select([S(c).isin(['01', '02', '1', '2']), S(c) != ''], [1, 2], 0)
lot = N('LND_SQFOOT').values
today_d = (dt.date.today() - DAY0).days
yrs = np.where(sd1 > 0, (today_d - sd1) / 365.25, 0)
govt = kinds_a == 'govt'; corp_gov = np.isin(kinds_a, ['corp', 'govt'])
s_abs = np.where(oos, 6, np.where(absz, 4, 0)); s_long = np.where(yrs >= 20, 5, np.where(yrs >= 10, 2, 0))
tear = (bv > 0) & (mk > 0) & (bv / np.maximum(mk, 1) < 0.2)
s_tear = np.where(tear, 6, np.where((bv == 0) & (landv > 0) & (lot > 0) & ~corp_gov, 3, 0))
s_nohs = np.where(~homestead & ~corp_gov, 3, 0)
soft = np.minimum(20, s_abs + s_long + s_tear + s_nohs)
dsig = (est * (1 << 10)) | ((s_abs > 0) << 12) | ((s_long >= 5) << 13) | (tear << 14) | ((s_nohs > 0) << 15)
dhard = np.where(est, 15, 0)
dscore = np.where(govt, 0, np.minimum(100, dhard + soft)); dsig = np.where(govt, 0, dsig)
# vacancy hint (vacancy_lib bit order): NA=0 (15), LO=6 (5), LB=7 (8), ES=9 (8); public records only, no code/utility data in Monroe yet
na = ~homestead & (absz | oos) & ~corp_gov & (bv > 0)
vsig = (na << 0) | ((yrs >= 20) << 6) | (tear << 7) | (est << 9)
vscore = np.minimum(100, na * 15 + (yrs >= 20) * 5 + tear * 8 + est * 8) * ~govt
z = lambda t: np.zeros(n, t)
# owner portfolios
is_condo = np.array([('CONDOMINIUM' in s or 'COOPERATIVE' in s) for s in lu_s])
og, owners = owners_lib.group_owners(list(o1), kinds, subs, list(S('OWN_ADDR1')), list(S('OWN_ADDR2')), list(S('OWN_ZIPCD').str.replace(r'\.0$', '', regex=True)),
                                     addr, list(zip5), np.zeros(n, bool), is_condo, mk)
owners['built'] = dt.datetime.now().strftime('%m/%d/%Y')
with gzip.open(os.path.join(OUT, 'owners.json.gz'), 'wt', compresslevel=9) as fh: json.dump(owners, fh, separators=(',', ':'))
G = np.array(owners['n']); GF = np.array(owners['fl']); GD = np.array(owners['nd'])
owner_stats = {'groups': int(len(G) - 1), 'parcels_in_groups': int((og > 0).sum()), 'mail_links': owners['linkedMail'], 'groups_5plus': int((G[1:] >= 5).sum()),
               'groups_2plus_distressed': 0, 'groups_2plus_distressed_non_institutional': 0}

# ---- Monroe enrichment (zoning, ROGO/tier, environment, Clerk, permits/code, buildability rating)
_geo = ME.load_geo(list(df.FOLIO)); _kinds = list(kinds)
ecols, estrs, mzone, zrules, estats = ME.enrich(df, _geo, uc.values, bv, lot, yb, N('TOT_LVG_AR').values, mk, _kinds, est, flood_s, absz, list(o1), addr)
print('enrich', json.dumps(estats)[:1500])
zoning_s = np.where(ecols['mz'] > 0, '', [('No digital zoning map - ' + j) for j in _geo.jur.values])
zoning_d, zoning_i = dict_index(list(zoning_s))
cols_main = {'city': u8(city_i), 'zip': u16(zip_i), 'cra': u8(flood_i), 'landuse': u16(landuse_i), 'zoning': u16(zoning_i), 'mz': ecols['mz'], 'tier': ecols['tier'], 'rogo': ecols['rogo'], 'env': ecols['env'], 'sigm': ecols['sigm'], 'bld': ecols['bld'],
    'lot': u32(lot), 'mkt': u32(mk), 'land': u32(landv), 'bldg': u32(bv), 'sqft': u32(N('TOT_LVG_AR')), 'yb': u16(yb), 'units': u16(N('NO_RES_UNT')),
    'beds': z(np.uint8), 'baths': z(np.uint8), 'stories': z(np.uint8), 'sd1': u16(sd1), 'sale1': u32(N('SALE_PRC1')), 'sq1': u8(qf('QUAL_CD1')), 'flags': flags,
    'prv': z(np.uint32), 'dscore': u8(dscore), 'dsig': u16(dsig), 'og': og.astype(np.uint32), 'vscore': u8(vscore), 'vsig': u16(vsig), 'pcs': z(np.uint16)}
legal = [re.sub(r'\s+', ' ', s).strip() for s in S('S_LEGAL')]
book = [f'{b}-{p}' if b.strip('0 ') else '' for b, p in zip(S('OR_BOOK1'), S('OR_PAGE1'))]
str_main = {'folio': list(df.FOLIO), 'addr': addr, 'owner': [re.sub(r'\s+', ' ', o).strip() for o in o1]}
cols_det = {'assd': u32(N('AV_SD')), 'taxable': u32(N('TV_NSD')), 'sd2': u16(sd2), 'sale2': u32(N('SALE_PRC2')), 'sq2': u8(qf('QUAL_CD2')), 'sd3': z(np.uint16),
            'sale3': z(np.uint32), 'bcount': u16(N('NO_BULDNG')), 'lperm': ecols['lperm'], 'pn5': ecols['pn5'], 'cn_open': ecols['cn_open'], 'cn5': ecols['cn5'], 'clast': ecols['clast']}
str_det = {'mail': mail, 'legal': legal, 'psum': estrs['psum'], 'csum': estrs['csum'], 'grantor': [''] * n, 'book': book, 'reasons': estrs['reasons'], 'rogo_txt': estrs['rogo_txt'], 'zinfo': estrs['zinfo']}
cols_geo = {'lat': np.where(lat != 0, (lat - GEO0[0]) * 1e6, 0).clip(0, 4e9).astype(np.uint32), 'lon': np.where(lon != 0, (lon - GEO0[1]) * 1e6, 0).clip(0, 4e9).astype(np.uint32)}

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
    raw = len(hdr).to_bytes(4, 'little') + hdr + b''.join(blobs); gz = gzip.compress(raw, 9, mtime=0); open(path, 'wb').write(gz); return len(gz), len(raw)

ver = dt.datetime.now().strftime('%Y%m%d%H%M'); packs = []
for name, rows in (('main', np.where(~is_condo)[0]), ('condo', np.where(is_condo)[0])):
    f1, f2, f3 = f'{name}.bin.gz', f'{name}-detail.bin.gz', f'{name}-geo.bin.gz'
    b1, _ = write_pack(os.path.join(OUT, f1), rows, cols_main, str_main); b2, _ = write_pack(os.path.join(OUT, f2), rows, cols_det, str_det); b3, _ = write_pack(os.path.join(OUT, f3), rows, cols_geo, {})
    packs.append({'name': name, 'n': int(len(rows)), 'files': [f1], 'bytes': b1, 'detail': [f2], 'detailBytes': b2, 'geo': [f3], 'geoBytes': b3})
    print(name, len(rows), f'main {b1/1e6:.2f}MB detail {b2/1e6:.2f}MB geo {b3/1e6:.2f}MB')

# simple comps: qualified sales (FDOR codes 01/02) in the last 12 months (commercial 24), same rows layout as scripts/build_comps.py
MONTHS, COMM = 36, 60
cut = int((dt.date.today() - dt.timedelta(days=int(MONTHS * 30.4))).strftime('%Y%m%d')); cutC = int((dt.date.today() - dt.timedelta(days=int(COMM * 30.4))).strftime('%Y%m%d'))
crow = []; bp = pd.Series(book); multi = set(np.where(bp.duplicated(keep=False) & (bp != ''))[0])
q1 = qf('QUAL_CD1'); q2 = qf('QUAL_CD2'); p1 = N('SALE_PRC1').values; p2 = N('SALE_PRC2').values; sqft = N('TOT_LVG_AR').values
for k in range(n):
    if not lat[k]: continue
    lu4 = f'{uc[k]*100:04d}'; com = 10 <= uc[k] <= 49
    for slot, (sd, pr, q) in enumerate(((sd1[k], p1[k], q1[k]), (sd2[k], p2[k], q2[k]))):
        if q != 1 or pr < 1000 or sd <= 0: continue
        if slot == 0 and k in multi: continue
        d8 = int((DAY0 + dt.timedelta(days=int(sd))).strftime('%Y%m%d'))
        if d8 < (cutC if com else cut): continue
        crow.append([df.FOLIO[k], int(round(lat[k] * 1e5)), int(round(lon[k] * 1e5)), d8, int(pr), int(sqft[k]), int(lot[k]), lu4, -1, 'R', addr[k]])
crow.sort(key=lambda r: (-r[3], r[0]))
cmeta = {'built': dt.date.today().isoformat(), 'cutoff': cut, 'months': MONTHS, 'commMonths': COMM, 'commCutoff': cutC, 'n': len(crow), 'newest': crow[0][3] if crow else 0,
         'source': 'Florida DOR roll (Monroe) qualified sales, sale month only (day set to the 15th)', 'cash_known': 0,
         'cols': ['folio', 'lat5', 'lon5', 'date', 'price', 'sqft', 'lot', 'lu', 'cash', 'src', 'addr']}
with gzip.open(os.path.join(OUT, 'comps.json.gz'), 'wt') as fh: json.dump({'meta': cmeta, 'rows': crow}, fh, separators=(',', ':'))
print('comps', len(crow))

fst = json.load(open(f'{RAW}/fetch_stats.json')) if os.path.exists(f'{RAW}/fetch_stats.json') else {}
last_sale = int(max(sd1.max(), 0))
meta = {'ver': ver, 'county': 'monroe', 'total': int(n), 'built': dt.datetime.now().strftime('%m/%d/%Y'),
        'rollYear': int(pd.to_numeric(df.ASMNT_YR, errors='coerce').max()), 'salesThrough': (DAY0 + dt.timedelta(days=last_sale)).strftime('%m/%Y'),
        'geoOrigin': list(GEO0), 'stats': stats, 'packs': packs, 'distress': None, 'owners': owner_stats,
        'vacancy': {'ge40': int((vscore >= 40).sum()), 'ge60': int((vscore >= 60).sum())}, 'permitCov': None, 'ownersFile': 'owners.json.gz', 'distressFile': None,
        'flood': fstats, 'fetch': fst, 'absentee': absentee_stats, 'enrich': estats, 'ownerKind': 'owner_kind.py (Python twin of app orgName)', 'screening': 'Buildability is a screening tool built from public map layers (zoning, ROGO/Tier, FNAI, NWI, habitat, CBRS, FEMA flood). It is not a determination - confirm with Monroe County / city planning.',
        'dicts': {'city': city, 'zip': zips, 'cra': flood, 'landuse': landuse, 'zoning': zoning_d, 'mzone': mzone},
        'sources': {'roll': 'https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0 (CO_NO=54)',
                    'flood': 'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28 (DFIRM_ID 12087)'}}
json.dump(meta, open(os.path.join(OUT, 'meta.json'), 'w'), separators=(',', ':'))
json.dump({'built': dt.date.today().isoformat(), 'source': 'Monroe County LDC / Key West / Marathon / Islamorada district tables (scripts/counties/monroe/monroe_zoning.py)',
           'fields': ['upa', 'stories', 'min_lot_sf', 'lot_cov', 'far', 'height_ft', 'zone_type', 'planned_dev', 'source'], 'counts': {'codes': len(zrules)}, 'rules': zrules}, open(os.path.join(OUT, 'zoning-rules.json'), 'w'), separators=(',', ':'))
print('meta', n, 'est', int(est.sum()), 'oos', int(oos.sum()), 'absentee', int(absz.sum()), 'homestead', int(homestead.sum()), 'teardown-ish', int(tear.sum()),
      'held20', int((yrs >= 20).sum()), 'vacant lots', int(sum(1 for s in lu_s if 'VACANT' in s)), 'owners', owner_stats)
# sale-qualification bits (relative transfer / life estate) are added as a small column to the packs just built
import subprocess, sys as _sys
subprocess.run([_sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'add_salex.py'), OUT], check=True)
# a full rebuild drops the tax-delinquent layer (meta.tax + tax pack columns): re-apply it from the last tax pulls in $RAW/monroe/tax/
# (add_tax.py is idempotent; non-fatal so a missing pull only leaves the layer out and is reported)
_tax = subprocess.run([_sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'add_tax.py'), OUT])
if _tax.returncode: print('WARN: Monroe add_tax.py failed (exit %d) - tax layer missing from this build' % _tax.returncode)
