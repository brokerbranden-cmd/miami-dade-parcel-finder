#!/usr/bin/env python3
"""Broward County, FL phase-1 packs -> data/broward/ (meta.json, main/condo packs, owners.json.gz, comps.json.gz, zoning-rules.json).
Inputs ($RAW/broward + $RAW/sdf): FDOR NAL 2026 preliminary roll (owners, mailing, values, use, 2 sales, exemptions), parcel centroids (BCPA parcel polygons),
FEMA flood (BCGIS FloodZones2024), county Land Use Plan, city / BMSD zoning layers, scheduled foreclosure + tax-deed auctions (broward.realforeclose / realtaxdeed).
Same pack format + column names as build_monroe.py / build_data.py so app.js reads it unchanged. Columns with no public Broward source are zeros (permits, code cases, Clerk, tax collector)."""
import json, os, re, sys, gzip, datetime as dt, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); SCR = os.path.abspath(os.path.join(HERE, '..', '..')); sys.path.insert(0, SCR); sys.path.insert(0, HERE)
import owner_kind, owners_lib, broward_zoning as BZ
RAWB = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'broward'); LAY = os.path.join(RAWB, 'layers')
NAL = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'sdf', 'Broward_Preliminary_NAL_2026', 'NAL16P202601.csv')
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SCR, '..', 'data', 'broward'); os.makedirs(OUT, exist_ok=True)
GEO0 = (25.0, -81.0)
COLS = ['PARCEL_ID', 'ASMNT_YR', 'DOR_UC', 'PA_UC', 'JV', 'AV_SD', 'TV_NSD', 'JV_HMSTD', 'LND_VAL', 'LND_SQFOOT', 'EFF_YR_BLT', 'ACT_YR_BLT', 'TOT_LVG_AREA', 'NO_BULDNG', 'NO_RES_UNTS',
        'SALE_PRC1', 'SALE_YR1', 'SALE_MO1', 'QUAL_CD1', 'OR_BOOK1', 'OR_PAGE1', 'SALE_PRC2', 'SALE_YR2', 'SALE_MO2', 'QUAL_CD2', 'OR_BOOK2', 'OR_PAGE2',
        'OWN_NAME', 'OWN_ADDR1', 'OWN_ADDR2', 'OWN_CITY', 'OWN_STATE', 'OWN_ZIPCD', 'OWN_STATE_DOM', 'FIDU_NAME', 'S_LEGAL', 'PHY_ADDR1', 'PHY_ADDR2', 'PHY_CITY', 'PHY_ZIPCD', 'PUBLIC_LND', 'EXMPT_01', 'EXMPT_02', 'EXMPT_03']
df = pd.read_csv(NAL, dtype=str, usecols=COLS, keep_default_na=False)
n_raw = len(df)
df['FOLIO'] = df.PARCEL_ID.str.replace(r'[^0-9A-Za-z]', '', regex=True).str.upper()   # Broward folios are 12 chars; condo units carry letters (e.g. 474131AA0010)
df = df[df.FOLIO != ''].drop_duplicates('FOLIO').reset_index(drop=True); n_roll = len(df)
cen = {}
for l in open(os.path.join(RAWB, 'centroids.jsonl')):
    a = json.loads(l)
    if a[1]: cen[re.sub(r'[^0-9A-Za-z]', '', str(a[0])).upper()] = (a[2], a[1])
df['LAT'] = [cen.get(f, (0, 0))[0] for f in df.FOLIO]; df['LON'] = [cen.get(f, (0, 0))[1] for f in df.FOLIO]
S = lambda c: df[c].fillna('').astype(str).str.strip()
N = lambda c: pd.to_numeric(df[c], errors='coerce').fillna(0)
uc = pd.to_numeric(S('DOR_UC'), errors='coerce').fillna(-1).astype(int)
is_farm = (uc >= 50) & (uc <= 69)
is_ref = (uc < 0) | ((N('JV') == 0) & (uc.isin([94, 95, 96, 98, 0, 99]) | (uc < 0)))   # right-of-way / submerged / centrally assessed / empty-value lots
keep = ~is_farm & ~is_ref
stats = {'raw_records': int(n_raw), 'roll_folios': int(n_roll), 'farmland_removed': int(is_farm.sum()), 'reference_removed': int((is_ref & ~is_farm).sum()), 'with_centroid': int(sum(1 for f in df.FOLIO if f in cen))}
df = df[keep].reset_index(drop=True); uc = uc[keep].reset_index(drop=True); n = len(df); print('kept', n, stats, flush=True)
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
lat = pd.to_numeric(df.LAT, errors='coerce').fillna(0).values; lon = pd.to_numeric(df.LON, errors='coerce').fillna(0).values
import geopandas as gpd
ok = (lat != 0)
pts = gpd.GeoDataFrame({'k': np.where(ok)[0]}, geometry=gpd.points_from_xy(lon[ok], lat[ok]), crs=4326)
# ---- FEMA flood zone at the parcel centroid (riskiest wins: V > A > X)
flood_s = [''] * n; fstats = {}
try:
    fz = gpd.read_file(os.path.join(LAY, 'flood.geojson'))
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
    j = gpd.sjoin(pts, fz[['lab', 'geometry']], how='left', predicate='within')
    j['r'] = j.lab.fillna('').map(lambda t: 3 if t.startswith('V') else 2 if t.startswith('A') else 1 if t else 0)
    j = j.sort_values('r', ascending=False).drop_duplicates('k')
    for k, t in zip(j.k, j.lab.fillna('')): flood_s[k] = t
    fstats = pd.Series([t.split(' ')[0] if t else 'none' for t in flood_s]).value_counts().to_dict(); print('flood', fstats, flush=True)
except Exception as e: print('WARN flood join skipped:', e)
city, city_i = dict_index(city_s); zips, zip_i = dict_index(list(zip5)); landuse, landuse_i = dict_index(lu_s); flood, flood_i = dict_index(flood_s)

# ---- zoning: parcel-keyed layers (BMSD, Lauderhill) by FOLIO, city polygons by centroid, county Land Use Plan as the fallback
zj = [''] * n; zc = [''] * n; zd = [''] * n; zsrc = np.zeros(n, np.uint8)   # zsrc: 1 city / BMSD zoning, 2 land-use-plan only
folio_ix = {f: i for i, f in enumerate(df.FOLIO)}
def load_jsonl(p): return [json.loads(l) for l in open(p)]
def put(i, jur, code, desc):
    if code and not zj[i]: zj[i] = jur; zc[i] = str(code).strip(); zd[i] = (desc or '').strip(); zsrc[i] = 1
cnt_z = {}
for name, jur, cf, df_ in (('z_bmsd', 'Unincorporated Broward (BMSD)', 'ZONING', 'TITLEDESCRIPTION'), ('z_lauderhill', 'Lauderhill', 'CLASS', 'DEFINITION')):
    p = os.path.join(LAY, name + '.jsonl')
    if not os.path.exists(p): continue
    c = 0
    for a in load_jsonl(p):
        i = folio_ix.get(re.sub(r'[^0-9A-Za-z]', '', str(a.get('FOLIO') or '')).upper())
        if i is not None and a.get(cf) and not zj[i]: put(i, jur, a[cf], a.get(df_) or a.get('DESCRIPTION')); c += 1
    cnt_z[jur] = c
CITY = [('z_fortlauderdale', 'Fort Lauderdale', 'ZONECLASS', 'ZONEDESC'), ('z_miramar', 'Miramar', 'ZONECODE', 'ZONEDESC'), ('z_deerfield', 'Deerfield Beach', 'ZONECLASS', 'ZONEDESC'),
        ('z_dania', 'Dania Beach', 'ZONE_1', 'DESCRIPTIO'), ('z_coopercity_res', 'Cooper City', 'Zoning01', 'Category'), ('z_coopercity_com', 'Cooper City', 'Zoning01', 'Category'),
        ('z_pembrokepark', 'Pembroke Park', 'Zone', 'Zone_Description'), ('z_pompano', 'Pompano Beach', 'ZONECLASS', 'ZONEDESC')]
for name, jur, cf, df_ in CITY:
    p = os.path.join(LAY, name + '.geojson')
    if not os.path.exists(p): print('missing', name); continue
    g = gpd.read_file(p)
    if cf not in g.columns: print('bad cols', name, list(g.columns)); continue
    g = g[g[cf].notna() & (g[cf].astype(str).str.strip() != '')][[cf, df_, 'geometry']].rename(columns={cf: 'c', df_: 'd'})
    g = g[g.geometry.notna()]
    j = gpd.sjoin(pts, g, how='inner', predicate='within').drop_duplicates('k'); c = 0
    for k, a, b in zip(j.k, j.c, j.d):
        if not zj[k]: put(k, jur, a, b if isinstance(b, str) else ''); c += 1
    cnt_z[jur] = cnt_z.get(jur, 0) + c; print('zoning', jur, c, flush=True)
# county land use plan (always stored in zinfo; used as zoning where no city / BMSD layer)
flu_code = np.zeros(n, np.int32) - 1
try:
    g = gpd.read_file(os.path.join(LAY, 'flu.geojson'))[['SLUC1', 'geometry']]; g = g[g.geometry.notna()]
    j = gpd.sjoin(pts, g, how='inner', predicate='within').drop_duplicates('k')
    for k, s in zip(j.k, j.SLUC1): flu_code[k] = int(s)
except Exception as e: print('WARN flu', e)
for i in range(n):
    if not zj[i] and flu_code[i] >= 0 and flu_code[i] in BZ.FLU:
        zj[i] = 'Broward Land Use Plan'; zc[i] = BZ.FLU[flu_code[i]][0].split(' (')[0].split(' - ')[0].upper()[:24]; zd[i] = BZ.FLU[flu_code[i]][0]; zsrc[i] = 2
# FLU entries need unique code per label (labels are unique per SLUC1): use the SLUC code in the key instead
for i in range(n):
    if zsrc[i] == 2: zc[i] = f'FLU-{flu_code[i]}'
zkey = {}; mzone = [None]; mz = np.zeros(n, np.uint16); rules = {}
for i in range(n):
    if not zj[i]: continue
    k = (zj[i], zc[i].upper())
    if k not in zkey:
        zkey[k] = len(mzone); mzone.append([zc[i], zj[i], zd[i] or zc[i], None, None, None])
        if zsrc[i] == 2:
            lbl, zt, dens = BZ.FLU[flu_code[i]]; rules[f'{k[0]}|{k[1]}'] = [dens or None, None, None, None, None, None, zt, 0, 'Broward County Land Use Plan (screening, not zoning)']
        else:
            rules[f'{k[0]}|{k[1]}'] = [None, None, None, None, None, None, BZ.zt_of(zc[i], zd[i]), 0, f'{zj[i]} zoning layer (screening)']
    mz[i] = zkey[k]
print('zoning types', pd.Series([rules[f'{a}|{b}'][6] for (a, b) in [(zj[i], zc[i].upper()) for i in range(n) if zj[i]]]).value_counts().to_dict(), flush=True)
zt_i = np.array([rules.get(f'{zj[i]}|{zc[i].upper()}', [0] * 7)[6] if zj[i] else 'none' for i in range(n)])
flu_lbl = [BZ.FLU[c][0] if c in BZ.FLU else '' for c in flu_code]

# ---- owners
o1 = S('OWN_NAME').str.replace(',', ' ', regex=False).str.replace(r'\s+', ' ', regex=True).str.strip(); fidu = S('FIDU_NAME')   # 'LAST,FIRST & SECOND' -> 'LAST FIRST & SECOND' (same order as Monroe: last-first)
_given = owner_kind.build_given(list(o1)); _kc = {}
def _cls(t):
    r = _kc.get(t)
    if r is None: r = _kc[t] = owner_kind.classify(t, _given)
    return r
res = [_cls((a, '', '')) for a in o1]; kinds = [r[0] for r in res]; subs = [r[1] for r in res]
GOVT_RE = re.compile(r"^(USA\b|U S A\b|UNITED STATES|US DEPT|BOARD OF TRUSTEES|TIITF|TRUSTEES OF THE INTERNAL|STATE OF FLORIDA|FLORIDA DEPT|FLORIDA DEPARTMENT|FLORIDA STATE|STATE OF FL|SOUTH FLORIDA WATER|SFWMD|BROWARD COUNTY|BROWARD CNTY|BROWARD CO\b|SCHOOL BOARD|CITY OF |TOWN OF |VILLAGE OF |HOUSING AUTHORITY|NORTH BROWARD HOSPITAL|BROWARD HEALTH|MEMORIAL HEALTHCARE|CENTRAL BROWARD WATER|NORTH SPRINGS IMPROVEMENT|WATER CONTROL DISTRICT|DRAINAGE DISTRICT|COMMUNITY REDEVELOPMENT|CRA\b|FLORIDA POWER|FPL\b|FDOT|FLA DEPT|BROWARD SHERIFF|POLICE|FIRE DISTRICT|SEMINOLE TRIBE|CHILDREN S SERVICES COUNCIL|UNITED STATES OF AMERICA)")
for _k, _o in enumerate(o1):
    if GOVT_RE.search(_o.upper().strip()) or 80 <= uc[_k] <= 89 or (str(df.PUBLIC_LND.iat[_k]).strip() not in ('', '0') and uc[_k] in (80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90)): kinds[_k] = 'govt'; subs[_k] = subs[_k] or 'agency'
EST = re.compile(r"\b(EST|ESTATE|EST OF|ESTATE OF|HEIRS?|DECEASED|DECD|DEC'D)\b")
est = np.array([k in ('person', 'trust') and bool(EST.search(re.sub(r'\b(LIFE|REAL|REALTY|RE|RL|R E) EST(ATE)?\b', ' ', (a + ' ' + f).upper()))) for a, f, k in zip(o1, fidu, kinds)])
ST = {'ALABAMA': 'AL', 'ALASKA': 'AK', 'ARIZONA': 'AZ', 'ARKANSAS': 'AR', 'CALIFORNIA': 'CA', 'COLORADO': 'CO', 'CONNECTICUT': 'CT', 'DELAWARE': 'DE', 'DISTRICT OF COLUMBIA': 'DC', 'FLORIDA': 'FL', 'GEORGIA': 'GA', 'HAWAII': 'HI',
      'IDAHO': 'ID', 'ILLINOIS': 'IL', 'INDIANA': 'IN', 'IOWA': 'IA', 'KANSAS': 'KS', 'KENTUCKY': 'KY', 'LOUISIANA': 'LA', 'MAINE': 'ME', 'MARYLAND': 'MD', 'MASSACHUSETTS': 'MA', 'MICHIGAN': 'MI', 'MINNESOTA': 'MN',
      'MISSISSIPPI': 'MS', 'MISSOURI': 'MO', 'MONTANA': 'MT', 'NEBRASKA': 'NE', 'NEVADA': 'NV', 'NEW HAMPSHIRE': 'NH', 'NEW JERSEY': 'NJ', 'NEW MEXICO': 'NM', 'NEW YORK': 'NY', 'NORTH CAROLINA': 'NC', 'NORTH DAKOTA': 'ND',
      'OHIO': 'OH', 'OKLAHOMA': 'OK', 'OREGON': 'OR', 'PENNSYLVANIA': 'PA', 'PENNSLYVANIA': 'PA', 'RHODE ISLAND': 'RI', 'SOUTH CAROLINA': 'SC', 'SOUTH DAKOTA': 'SD', 'TENNESSEE': 'TN', 'TEXAS': 'TX', 'UTAH': 'UT', 'VERMONT': 'VT',
      'VIRGINIA': 'VA', 'WASHINGTON': 'WA', 'WEST VIRGINIA': 'WV', 'WISCONSIN': 'WI', 'WYOMING': 'WY', 'PUERTO RICO': 'PR'}
mst_full = S('OWN_STATE').str.upper(); mst = mst_full.map(lambda s: ST.get(s, s)); dom = S('OWN_STATE_DOM').str.upper()
mstate = np.where(mst.str.len() <= 3, mst, np.where(dom.str.len() == 2, dom, mst))      # foreign countries keep their name (non-FL)
mzip5 = S('OWN_ZIPCD').str.replace(r'\.0$', '', regex=True).str[:5]
homestead = (N('JV_HMSTD') > 0).values; kinds_a = np.array(kinds)
vc = zip5[zip5 != ''].value_counts(); LOCAL_ZIPS = set(vc[vc >= 30].index)
def _st(a):
    t = re.sub(r'[^A-Z0-9 ]', ' ', a.upper()).split()
    if not t: return None
    num = re.match(r'\d+', t[0]); name = next((w for w in t[1:] if not re.match(r'^(N|S|E|W|NE|NW|SE|SW|NORTH|SOUTH|EAST|WEST|\d+|ST|AVE|RD|DR|LN|BLVD|CT|CIR|TER|PL|WAY|APT|UNIT|STE|BLDG)$', w)), t[1] if len(t) > 1 else '')
    return (num.group(0) if num else t[0], name[:6]) if t else None
same_addr = np.array([bool(a) and bool(m) and _st(a) is not None and _st(a) == _st(m) for a, m in zip(S('PHY_ADDR1'), S('OWN_ADDR1'))])
govt_k = kinds_a == 'govt'
in_cty = mzip5.isin(LOCAL_ZIPS).values
oos = (mstate != '') & (mstate != 'FL') & ~govt_k & ~homestead & ~same_addr
absz = (mzip5 != '').values & ~in_cty & ~govt_k & ~homestead & ~same_addr          # mails from outside Broward (other FL county or out of state / country)
local_other = in_cty & ~govt_k & ~homestead & ~same_addr & (mzip5 != zip5).values  # mails to a different address inside Broward: not flagged
absentee_stats = {'old_rule_zip_differs': int(((mzip5 != '') & (zip5 != '') & (mzip5 != zip5)).sum()), 'govt_owned': int(govt_k.sum()), 'homestead': int(homestead.sum()), 'same_address_mailing': int((same_addr & ~govt_k).sum()),
                  'absentee_new': int(absz.sum()), 'out_of_state': int(oos.sum()), 'florida_outside_broward': int((absz & ~oos).sum()), 'local_other_address_not_flagged': int(local_other.sum()), 'local_zips': len(LOCAL_ZIPS)}
print('absentee', absentee_stats, flush=True)
flags = (homestead * 1 | oos * 2 | absz * 4 | (kinds_a == 'corp') * 8 | (kinds_a == 'trust') * 16 | (kinds_a == 'govt') * 32 | est * 64).astype(np.uint8)
mail = []
for a1, a2, c, s0, z in zip(S('OWN_ADDR1'), S('OWN_ADDR2'), S('OWN_CITY'), mst, S('OWN_ZIPCD')):
    z = re.sub(r'\.0$', '', z); parts = [p for p in (a1, a2) if p] + [p for p in (c, (s0 + ' ' + z).strip()) if p]
    mail.append(re.sub(r'\s+', ' ', ', '.join(parts)).strip())
addr = [re.sub(r'\s+', ' ', a).strip() for a in S('PHY_ADDR1')]

# ---- numbers
DAY0 = dt.date(1900, 1, 1)
def sday(yc, mc):
    y = pd.to_numeric(df[yc], errors='coerce').fillna(0).astype(int).values; m = pd.to_numeric(df[mc], errors='coerce').fillna(0).astype(int).values
    out = np.zeros(n, np.int64)
    for k in np.where((y > 1800) & (y < 2100))[0]: out[k] = (dt.date(y[k], m[k] if 1 <= m[k] <= 12 else 1, 15) - DAY0).days
    return out
u32 = lambda a: np.clip(np.round(np.asarray(a, dtype=float)), 0, 4294967295).astype(np.uint32)
u16 = lambda a: np.clip(np.round(np.asarray(a, dtype=float)), 0, 65535).astype(np.uint16)
u8 = lambda a: np.clip(np.round(np.asarray(a, dtype=float)), 0, 255).astype(np.uint8)
mk = N('JV').values; landv = N('LND_VAL').values; bv = np.maximum(mk - landv, 0) * (landv > 0)
yb = N('ACT_YR_BLT').values; yb = np.where((yb > 1700) & (yb < 2100), yb, 0)
sd1 = sday('SALE_YR1', 'SALE_MO1'); sd2 = sday('SALE_YR2', 'SALE_MO2')
qf = lambda c: np.select([S(c).isin(['01', '02', '1', '2']), S(c) != ''], [1, 2], 0)
lot = N('LND_SQFOOT').values; sqft = N('TOT_LVG_AREA').values
today_d = (dt.date.today() - DAY0).days
yrs = np.where(sd1 > 0, (today_d - sd1) / 365.25, 0)
govt = kinds_a == 'govt'; corp_gov = np.isin(kinds_a, ['corp', 'govt'])
is_condo = np.array([('CONDOMINIUM' in s or 'COOPERATIVE' in s) for s in lu_s])
vacant = np.isin(uc.values, [0, 10, 40, 70])
tear = (bv > 0) & (mk > 0) & (bv / np.maximum(mk, 1) < 0.2) & ~is_condo

# ---- scheduled foreclosure / tax-deed auctions (public RealAuction calendars)
fc_txt = [''] * n; td_txt = [''] * n; fcb = np.zeros(n, bool); tdb = np.zeros(n, bool); auc_stats = {}
normA = lambda a: re.sub(r'[^A-Z0-9]', '', str(a).upper())
dig_ix, adr_ix = {}, {}
for k, (f, a1, a2, z) in enumerate(zip(df.FOLIO, S('PHY_ADDR1'), S('PHY_ADDR2'), S('PHY_ZIPCD'))):
    dig_ix.setdefault(re.sub(r'\D', '', f), []).append(k); adr_ix.setdefault((normA(a1 + a2), z[:5]), []).append(k)
ap = os.path.join(RAWB, 'auctions.json')
if os.path.exists(ap):
    A = json.load(open(ap)); auc_stats = {'pulled': A.get('pulled'), 'items': len(A['items'])}
    for it in A['items']:
        if it.get('status', '').lower() != 'scheduled': continue   # only future sales (closed / cancelled are history)
        fo = re.sub(r'[^0-9A-Za-z]', '', it.get('folio', '')).upper()
        i = folio_ix.get(fo)
        if i is None and fo.isdigit() and len(fo) >= 10:     # RealAuction drops the letters of condo folios (514215AA0010 -> 5142150010): digits-only key, then address + unit
            c = dig_ix.get(fo, []); i = c[0] if len(c) == 1 else None
        if i is None and it.get('address'):
            zz = re.findall(r'\d{5}', it.get('city', '')); c = adr_ix.get((normA(it['address']), zz[0] if zz else ''), []); i = c[0] if len(c) == 1 else None
        if i is None: auc_stats['unmatched'] = auc_stats.get('unmatched', 0) + 1; continue
        t = f"{it['date']} {('Tax deed' if it.get('src') == 'taxdeed' else 'Foreclosure')} sale" + (f", case {it['case']}" if it.get('case') else '') + (f", opening bid {it['opening_bid']}" if it.get('opening_bid') else '') + (f", judgment {it['judgment']}" if it.get('judgment') else '') + f" ({it.get('status', '')})"
        if it.get('src') == 'taxdeed': tdb[i] = True; td_txt[i] = (td_txt[i] + ' | ' if td_txt[i] else '') + t
        else: fcb[i] = True; fc_txt[i] = (fc_txt[i] + ' | ' if fc_txt[i] else '') + t
    auc_stats.update({'foreclosure_parcels': int(fcb.sum()), 'taxdeed_parcels': int(tdb.sum())})
print('auctions', auc_stats, flush=True)

# ---- buildability screen (bld 1 green / 2 yellow / 3 red) for vacant lots, teardown candidates and 1-9 unit homes; reasons "R~text¦Y~text¦G~text¦i~text"
lowrisk = np.array([not f.startswith('V') and not f.startswith('A') for f in flood_s]); hi_f = np.array([f.startswith('A') for f in flood_s]); ve_f = np.array([f.startswith('V') for f in flood_s])
small = lot < 5000; resz = np.isin(zt_i, ['sf', 'duplex', 'mf', 'mixed'])
cand = (vacant | tear | np.isin(uc.values, [1, 2, 8])) & ~govt & ~is_condo
bld = np.zeros(n, np.uint8); reasons = [''] * n; zinfo = [''] * n
for i in np.where(cand)[0]:
    R, Y, G, I = [], [], [], []
    zt = zt_i[i]
    if zt in ('civic', 'other') and zsrc[i]: R.append(f'Zoned {zd[i] or zc[i]} ({zj[i]}): public / conservation / non-residential district')
    elif zt in ('civic', 'other'): R.append(f'County land use plan: {flu_lbl[i]} (not residential)')
    elif zt == 'none': Y.append('No zoning or land-use layer matched this parcel')
    else: G.append(f'{"Zoned" if zsrc[i]==1 else "Land use plan"}: {zd[i] or zc[i]} ({zj[i]})')
    if zsrc[i] == 2: (Y if (vacant[i] or tear[i]) else I).append('City zoning layer not published: the county land use plan is shown, confirm the city zoning code')   # yellow only for the lots / teardowns being screened
    if ve_f[i]: R.append('FEMA zone VE (coastal high hazard)')
    elif hi_f[i]: I.append(f'FEMA {flood_s[i].split(" - ")[0]} (special flood hazard area: elevation / flood insurance apply; common across Broward, not a blocker)')
    elif flood_s[i]: G.append('FEMA ' + flood_s[i].split(' - ')[0] + ' (not high risk)')
    if small[i] and lot[i] > 0: Y.append(f'Small lot ({int(lot[i]):,} sf)')
    elif lot[i] >= 7500: G.append(f'Lot {int(lot[i]):,} sf')
    if zt in ('duplex', 'mf', 'mixed') and lot[i] >= 5000: G.append('Zoning / land use supports 2+ units: duplex / small multifamily screen')
    if vacant[i]: I.append('Vacant lot on the roll')
    if tear[i]: I.append('Building value under 20% of market value (teardown screen)')
    bld[i] = 3 if R else (2 if Y else 1)
    reasons[i] = '¦'.join([f'R~{x}' for x in R] + [f'Y~{x}' for x in Y] + [f'G~{x}' for x in G] + [f'i~{x}' for x in I])
for i in range(n):
    if zj[i]: zinfo[i] = f'{zj[i]}: {zc[i]} {zd[i]}'.strip() + (f' | County land use plan: {flu_lbl[i]}' if flu_lbl[i] and zsrc[i] == 1 else '')
dup = resz & np.isin(zt_i, ['duplex', 'mf', 'mixed']) & (lot >= 5000) & (vacant | tear | np.isin(uc.values, [1, 8]))
sigm = (fcb * 1 | tdb * 16 | (absz | oos) * 256 | vacant * 512 | dup * 2048 | tear * 16384).astype(np.uint16)
dsum = ['; '.join(x for x in (a, b) if x) for a, b in zip(fc_txt, td_txt)]

# ---- soft + hard distress scores (same shape as Monroe)
s_abs = np.where(oos, 6, np.where(absz, 4, 0)); s_long = np.where(yrs >= 20, 5, np.where(yrs >= 10, 2, 0))
s_tear = np.where(tear, 6, np.where((bv == 0) & (landv > 0) & (lot > 0) & ~corp_gov, 3, 0)); s_nohs = np.where(~homestead & ~corp_gov, 3, 0)
soft = np.minimum(20, s_abs + s_long + s_tear + s_nohs)
dsig = (est * (1 << 10)) | ((s_abs > 0) << 12) | ((s_long >= 5) << 13) | (tear << 14) | ((s_nohs > 0) << 15)
dhard = np.where(est, 15, 0) + np.where(fcb, 25, 0) + np.where(tdb, 30, 0)
dscore = np.where(govt, 0, np.minimum(100, dhard + soft)); dsig = np.where(govt, 0, dsig)
na = ~homestead & (absz | oos) & ~corp_gov & (bv > 0)
vsig = (na << 0) | ((yrs >= 20) << 6) | (tear << 7) | (est << 9)
vscore = np.minimum(100, na * 15 + (yrs >= 20) * 5 + tear * 8 + est * 8) * ~govt
z = lambda t: np.zeros(n, t)
og, owners = owners_lib.group_owners(list(o1), kinds, subs, list(S('OWN_ADDR1')), list(S('OWN_ADDR2')), list(S('OWN_ZIPCD').str.replace(r'\.0$', '', regex=True)), addr, list(zip5), np.zeros(n, bool), is_condo, mk)
owners['built'] = dt.datetime.now().strftime('%m/%d/%Y')
with gzip.open(os.path.join(OUT, 'owners.json.gz'), 'wt', compresslevel=9) as fh: json.dump(owners, fh, separators=(',', ':'))
G = np.array(owners['n']); owner_stats = {'groups': int(len(G) - 1), 'parcels_in_groups': int((og > 0).sum()), 'mail_links': owners['linkedMail'], 'groups_5plus': int((G[1:] >= 5).sum()), 'groups_2plus_distressed': 0, 'groups_2plus_distressed_non_institutional': 0}
# sale-qualification bits of the latest sale (FDOR codes): 30 affiliated parties (relative), 14 reservation of occupancy (life estate), 11 corrective / quit claim / tax deed, 19 fiduciary
q1 = S('QUAL_CD1'); sx = ((q1 == '30') * 1 | (q1 == '14') * 2 | (q1 == '11') * 4 | (q1 == '19') * 8).values.astype(np.uint8)
zoning_s = np.array([zj[i] + ': ' + zc[i] if zj[i] else 'No zoning / land-use layer' for i in range(n)]); zoning_d, zoning_i = dict_index(list(zoning_s))
cols_main = {'city': u8(city_i), 'zip': u16(zip_i), 'cra': u8(flood_i), 'landuse': u16(landuse_i), 'zoning': u16(zoning_i), 'mz': mz, 'tier': z(np.uint8), 'rogo': z(np.uint8), 'env': z(np.uint16), 'sigm': sigm, 'bld': bld,
    'lot': u32(lot), 'mkt': u32(mk), 'land': u32(landv), 'bldg': u32(bv), 'sqft': u32(sqft), 'yb': u16(yb), 'units': u16(N('NO_RES_UNTS')), 'beds': z(np.uint8), 'baths': z(np.uint8), 'stories': z(np.uint8),
    'sd1': u16(sd1), 'sale1': u32(N('SALE_PRC1')), 'sq1': u8(qf('QUAL_CD1')), 'flags': flags, 'prv': z(np.uint32), 'dscore': u8(dscore), 'dsig': u16(dsig), 'og': og.astype(np.uint32), 'vscore': u8(vscore), 'vsig': u16(vsig), 'pcs': z(np.uint16), 'sx': sx}
legal = [re.sub(r'\s+', ' ', s).strip() for s in S('S_LEGAL')]
book = [f'{b}-{p}' if b.strip('0 ') else '' for b, p in zip(S('OR_BOOK1'), S('OR_PAGE1'))]
str_main = {'folio': list(df.FOLIO), 'addr': addr, 'owner': list(o1)}
cols_det = {'assd': u32(N('AV_SD')), 'taxable': u32(N('TV_NSD')), 'sd2': u16(sd2), 'sale2': u32(N('SALE_PRC2')), 'sq2': u8(qf('QUAL_CD2')), 'sd3': z(np.uint16), 'sale3': z(np.uint32), 'bcount': u16(N('NO_BULDNG')),
            'lperm': z(np.uint16), 'pn5': z(np.uint16), 'cn_open': z(np.uint8), 'cn5': z(np.uint16), 'clast': z(np.uint16)}
str_det = {'mail': mail, 'legal': legal, 'psum': [''] * n, 'csum': [''] * n, 'grantor': [''] * n, 'book': book, 'reasons': reasons, 'rogo_txt': [''] * n, 'zinfo': zinfo, 'dsum': dsum}
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
    for name, lst in strs.items(): add(name, 'str', '\n'.join(lst[k].replace('\n', ' ') for k in rows).encode('utf-8'))
    hdr = json.dumps({'n': int(len(rows)), 'cols': hdr_cols}, separators=(',', ':')).encode(); hdr += b' ' * ((-(4 + len(hdr))) % 4)
    raw = len(hdr).to_bytes(4, 'little') + hdr + b''.join(blobs); gz = gzip.compress(raw, 9, mtime=0); open(path, 'wb').write(gz); return len(gz), len(raw)
ver = dt.datetime.now().strftime('%Y%m%d%H%M'); packs = []
for name, rows in (('main', np.where(~is_condo)[0]), ('condo', np.where(is_condo)[0])):
    f1, f2, f3 = f'{name}.bin.gz', f'{name}-detail.bin.gz', f'{name}-geo.bin.gz'
    b1, _ = write_pack(os.path.join(OUT, f1), rows, cols_main, str_main); b2, _ = write_pack(os.path.join(OUT, f2), rows, cols_det, str_det); b3, _ = write_pack(os.path.join(OUT, f3), rows, cols_geo, {})
    packs.append({'name': name, 'n': int(len(rows)), 'files': [f1], 'bytes': b1, 'detail': [f2], 'detailBytes': b2, 'geo': [f3], 'geoBytes': b3}); print(name, len(rows), f'main {b1/1e6:.2f}MB detail {b2/1e6:.2f}MB geo {b3/1e6:.2f}MB', flush=True)
# comps: qualified sales (FDOR 01/02) in the last 36 months (commercial 60); only 2025-26 sales are public
MONTHS, COMM = 36, 60
cut = int((dt.date.today() - dt.timedelta(days=int(MONTHS * 30.4))).strftime('%Y%m%d')); cutC = int((dt.date.today() - dt.timedelta(days=int(COMM * 30.4))).strftime('%Y%m%d'))
crow = []; bp = pd.Series(book); multi = set(np.where(bp.duplicated(keep=False) & (bp != ''))[0])
qq1 = qf('QUAL_CD1'); qq2 = qf('QUAL_CD2'); p1 = N('SALE_PRC1').values; p2 = N('SALE_PRC2').values
for k in np.where(lat != 0)[0]:
    lu4 = f'{uc[k]*100:04d}'; com = 10 <= uc[k] <= 49
    for slot, (sd, pr, q) in enumerate(((sd1[k], p1[k], qq1[k]), (sd2[k], p2[k], qq2[k]))):
        if q != 1 or pr < 1000 or sd <= 0: continue
        if slot == 0 and k in multi: continue
        d8 = int((DAY0 + dt.timedelta(days=int(sd))).strftime('%Y%m%d'))
        if d8 < (cutC if com else cut): continue
        crow.append([df.FOLIO[k], int(round(lat[k] * 1e5)), int(round(lon[k] * 1e5)), d8, int(pr), int(sqft[k]), int(lot[k]), lu4, -1, 'R', addr[k]])
crow.sort(key=lambda r: (-r[3], r[0]))
cmeta = {'built': dt.date.today().isoformat(), 'cutoff': cut, 'months': MONTHS, 'commMonths': COMM, 'commCutoff': cutC, 'n': len(crow), 'newest': crow[0][3] if crow else 0,
         'source': 'FDOR roll (Broward) qualified sales, sale month only (day set to the 15th); only the 2025-2026 sale file is public', 'cash_known': 0, 'cols': ['folio', 'lat5', 'lon5', 'date', 'price', 'sqft', 'lot', 'lu', 'cash', 'src', 'addr']}
with gzip.open(os.path.join(OUT, 'comps.json.gz'), 'wt') as fh: json.dump({'meta': cmeta, 'rows': crow}, fh, separators=(',', ':'))
print('comps', len(crow))
last_sale = int(max(sd1.max(), 0))
meta = {'ver': ver, 'county': 'broward', 'ownerKind': 'owner_kind.py (Python twin of app orgName)', 'total': int(n), 'built': dt.datetime.now().strftime('%m/%d/%Y'), 'rollYear': int(pd.to_numeric(df.ASMNT_YR, errors='coerce').max()), 'salesThrough': (DAY0 + dt.timedelta(days=last_sale)).strftime('%m/%Y'),
        'geoOrigin': list(GEO0), 'stats': stats, 'packs': packs, 'distress': None, 'owners': owner_stats, 'vacancy': {'ge40': int((vscore >= 40).sum()), 'ge60': int((vscore >= 60).sum())}, 'permitCov': None, 'ownersFile': 'owners.json.gz', 'distressFile': None,
        'flood': fstats, 'absentee': absentee_stats, 'auctions': auc_stats,
        'enrich': {'zoning_by_jur': cnt_z, 'zoning_city_or_bmsd': int((zsrc == 1).sum()), 'land_use_plan_only': int((zsrc == 2).sum()), 'no_layer': int((zsrc == 0).sum()), 'bld_green': int((bld == 1).sum()), 'bld_yellow': int((bld == 2).sum()), 'bld_red': int((bld == 3).sum()),
                   'vacant': int(vacant.sum()), 'teardown': int(tear.sum()), 'dup_zoning': int(dup.sum())},
        'screening': 'Buildability is a screening tool built from public map layers (city zoning where published, the county land use plan, FEMA flood) and the property roll. It is not a determination - confirm with the city / Broward County planning department.',
        'dicts': {'city': city, 'zip': zips, 'cra': flood, 'landuse': landuse, 'zoning': zoning_d, 'mzone': mzone},
        'sources': {'roll': 'FL Dept of Revenue NAL 2026 preliminary roll, county 16 (floridarevenue.com PTO data portal)', 'geometry': 'BCPA Broward_County_Parcel_Boundary (centroids)', 'flood': 'Broward County GIS FloodZones2024 (FEMA DFIRM 12011)', 'landuse': 'Broward County Land Use Plan (BCGIS FutureLandUse)', 'auctions': 'broward.realforeclose.com / broward.realtaxdeed.com'}}
json.dump(meta, open(os.path.join(OUT, 'meta.json'), 'w'), separators=(',', ':'))
json.dump({'built': dt.date.today().isoformat(), 'source': 'Broward city / BMSD zoning layers + county Land Use Plan (scripts/counties/broward/broward_zoning.py keyword screen)', 'fields': ['upa', 'stories', 'min_lot_sf', 'lot_cov', 'far', 'height_ft', 'zone_type', 'planned_dev', 'source'], 'counts': {'codes': len(rules)}, 'rules': rules}, open(os.path.join(OUT, 'zoning-rules.json'), 'w'), separators=(',', ':'))
print('DONE', n, owner_stats, meta['enrich'])

# a full rebuild drops the tax layer patched in by add_tax.py: re-apply it from the last pulls in $RAW/broward/tax/ (idempotent, non-fatal)
import subprocess as _sp, sys as _sys
_tax = _sp.run([_sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'add_tax.py'), OUT])
if _tax.returncode: print('WARN: Broward add_tax.py failed (exit %d) - tax layer missing from this build' % _tax.returncode)
