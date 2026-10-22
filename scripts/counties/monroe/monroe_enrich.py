"""Monroe enrichment: zoning dictionary, ROGO / dedication / tier, environment bits, Clerk foreclosure + probate matching, Marathon code cases, MCeSearch permits/code (if fetched),
tax-deed notices, and the per-parcel Buildability rating (screening tool - NOT a determination). Used by build_monroe.py; inputs are numpy arrays aligned to the built parcel rows."""
import os, re, json, collections, datetime as dt, numpy as np, pandas as pd
import monroe_zoning as MZ
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe')
TIER = {'': 0, 'I': 1, 'II': 2, 'III': 3, 'III-A': 4, 'Military': 5}
TIER_LABEL = ['', 'Tier I (Natural Area)', 'Tier II (Big Pine Key / No Name Key)', 'Tier III (infill)', 'Tier III-A (Special Protection Area)', 'Military']
ROGO_ST = ['', 'ROGO/NROGO allocation awarded', 'Applied for ROGO allocation (not awarded)', 'ROGO dedicated / development rights retired', 'ROGO dedication - affordable housing / land trust record']
# env bits
E = dict(fnai=1, ff=2, nwi_fw=4, nwi_est=8, mangrove=16, upland=32, cbrs=64, species=128, deer=256, historic=512, subdmg=1024, repl=2048, kwsewer=4096, beach=8192, water=16384)
ENV_LABEL = {'fnai': 'State / federal conservation land (FNAI)', 'ff': 'Florida Forever project boundary', 'nwi_fw': 'Freshwater wetland (NWI)', 'nwi_est': 'Estuarine / marine wetland (NWI)', 'mangrove': 'Mangrove / salt marsh habitat',
             'upland': 'Hammock / pineland habitat (clearing limits)', 'cbrs': 'Coastal Barrier Resources System unit', 'species': 'Protected-species focus area', 'deer': 'Key deer focus area', 'historic': 'Historic district',
             'subdmg': 'Substantial-damage record', 'repl': 'FEMA repetitive-loss area', 'kwsewer': 'Key West sewer main nearby', 'beach': 'Beach berm / buttonwood', 'water': 'Open water / submerged'}
# signal bits (sigm column; filters)
SG = dict(fc_open=1, fc_any=2, pr_open=4, pr_any=8, taxdeed=16, code=32, permit_recent=64, permit_open=128, absentee=256, vacant=512, estate=1024, dup=2048, rogo_award=4096, rogo_applied=8192, teardown=16384, rogo_ded=32768)
RES_GROUPS = {'sf', 'low', 'mf', 'mh', 'mx', 'rs'}
VACANT_UC = {0, 10, 40, 70, 80, 99}
def tcase_sentence(s): return s[:1].upper() + s[1:]
YEAR_NOW = dt.date.today().year

def load_geo(folios):
    g = pd.read_pickle(f'{RAW}/geo_attrs.pkl').drop_duplicates('FOLIO').set_index('FOLIO'); g = g.reindex(folios)
    for c in g.columns:
        if g[c].dtype == object: g[c] = g[c].fillna('')
    return g

def zoning_tables(g, jur_name):
    """-> mz index array, mzone dict list (meta.dicts.mzone), rules dict {jur|CODE: [upa, stories, min_lot, cov, far, height, zone_type, pd, source]}, group per parcel, plain label per parcel"""
    n = len(g); mzone = [None]; idx = {}; mzi = np.zeros(n, np.uint16); grp = np.array(['na'] * n, dtype=object); label = [''] * n; rules = {}
    ZT = {'sf': 'sf', 'low': 'sf', 'mf': 'mf', 'mh': 'sf', 'cm': 'com', 'mx': 'mixed', 'in': 'ind', 'cs': 'other', 'pu': 'civic', 'mi': 'civic', 'rs': 'com', 'na': 'other'}
    MINLOT = {('Islamorada', 'NR'): 43560, ('Islamorada', 'RE'): 21780, ('Islamorada', 'R1'): 4500, ('Islamorada', 'R1M'): 4500, ('Islamorada', 'R2'): 5000, ('Islamorada', 'R3'): 12000, ('Islamorada', 'R4'): 16000, ('Islamorada', 'TA'): 4500}
    UPA = {('Islamorada', 'NR'): 0.25, ('Islamorada', 'RE'): 0.5, ('Islamorada', 'MF'): 6, ('Islamorada', 'MH'): 6, ('Islamorada', 'VC'): 6, ('Islamorada', 'TC'): 6, ('Islamorada', 'NC'): 6, ('Islamorada', 'MR'): 6, ('Islamorada', 'CF'): 2, ('Islamorada', 'HC'): 1}
    for k in range(n):
        j = g.jur.iat[k]; code = g.zcode.iat[k]
        if not code: continue
        name, gr = MZ.lookup(j, code); key = (j, code)
        if key not in idx:
            idx[key] = len(mzone); jn = j
            mzone.append([code, jn, name, UPA.get(key), None, MINLOT.get(key)])
            ml = MINLOT.get(key)
            rules[f'{jn}|{code}'] = [UPA.get(key), None, ml, None, None, 35 if j == 'Islamorada' else None, ('duplex' if key == ('Islamorada', 'R2') else ZT[gr]), 0, 'Monroe County LDC / municipal code (screening)']
        mzi[k] = idx[key]; grp[k] = gr; label[k] = name
    return mzi, mzone, rules, grp, label

def rogo_tables(re_list):
    """-> status (0..4), text, last_award_year per parcel"""
    rg = pd.DataFrame(json.load(open(f'{RAW}/rogo.json'))); n = len(re_list)
    rg = rg[rg.re.fillna('') != '']
    aw = rg[rg.award].sort_values(['year', 'q']).groupby('re').last(); ap = rg[~rg.award].sort_values(['year', 'q']).groupby('re').last(); cnt = rg.groupby('re').size()
    st = np.zeros(n, np.uint8); txt = [''] * n; yr = np.zeros(n, np.uint8)
    for k, r in enumerate(re_list):
        if r in aw.index:
            a = aw.loc[r]; st[k] = 1; yr[k] = int(a.year); txt[k] = f"{a['kind']} allocation awarded - year {int(a.year)} Q{int(a['q'])} ({a['cat'] or 'n/a'}){(' permit ' + a.permit) if a.permit else ''}"
        elif r in ap.index:
            a = ap.loc[r]; st[k] = 2; yr[k] = int(a.year); txt[k] = f"Applied for {a['kind']} allocation {cnt[r]}x, last in year {int(a.year)} Q{int(a['q'])} (rank {int(a['rank']) if pd.notna(a['rank']) else '?'}) - not awarded"
    return st, txt, yr

# ---------------- Clerk matching ----------------
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import probate_lib as PL
ENT = re.compile(r'\b(LLC|L L C|INC|CORP|CORPORATION|LTD|LP|LLP|TRUST|BANK|ASSOCIATION|COMPANY|CO|HOLDINGS|PROPERTIES|INVESTMENTS?|PARTNERS|PARTNERSHIP)\b')
NOISE = re.compile(r'\b(UNKNOWN|HEIRS?|DEVISEES|GRANTEES|ASSIGNEES|LIENORS|CREDITORS|TRUSTEES|TENANTS?|OCCUPANTS?|DOES?|JOHN|JANE|SPOUSE|ET AL|ETAL|ANY AND ALL|PARTIES|CLAIMANTS|ALL OTHER|PERSONAL REPRESENTATIVES?|ADMINISTRATORS?|THE|OR|AND|AS|OF|IN POSSESSION)\b')
def norm_ent(s): return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9 ]', ' ', s.upper().replace('&', ' AND '))).strip()
def build_owner_index(owners, kinds, folios):
    pk = collections.defaultdict(set); ent = collections.defaultdict(set)
    for k, (o, kd) in enumerate(zip(owners, kinds)):
        if kd == 'govt': continue
        if kd in ('corp', 'trust') or PL.ORG.search(o.upper()): ent[norm_ent(o)].add(k)
        for seg in PL.owner_segments(o):
            full, ini = PL.person_key(seg)
            if len(full) >= 2: pk[full].add(k)
    return pk, ent
def match_person(name_words_full, pk):
    """exact full-word set, or owner words subset of candidate words (middle names) with >= 2 shared"""
    hit = pk.get(name_words_full)
    if hit: return hit
    return set()
def run_clerk(owners, kinds, folios):
    d = json.load(open(f'{RAW}/clerk_cases.json')); pk, ent = build_owner_index(owners, kinds, folios); n = len(owners)
    fc = [[] for _ in range(n)]; pr = [[] for _ in range(n)]; st = collections.Counter()
    for c in d['cases']:
        style = c['style'].upper(); cands = set(); how = ''
        if c['kind'] == 'foreclosure':
            parts = re.split(r'\s+VS\.?\s+', style, maxsplit=1)
            if len(parts) < 2: st['fc_no_vs'] += 1; continue
            dfn = [t.strip() for t in parts[1].split(',')]
            segs = []
            for i in range(len(dfn)):
                t = dfn[i]
                if ENT.search(t) and not NOISE.fullmatch(t): segs.append(('E', norm_ent(t)))
                if i + 1 < len(dfn): segs.append(('P', dfn[i] + ' ' + dfn[i + 1]))
                segs.append(('P', t))
            for kind, s in segs:
                if kind == 'E':
                    h = ent.get(s)
                    if h: cands |= h
                else:
                    full, ini = PL.person_key(NOISE.sub(' ', s))
                    if len(full) >= 2:
                        h = pk.get(full)
                        if not h:  # candidate has a middle name the roll does not (or vice versa): allow subset with >= 2 words, unique only
                            h = set()
                            for ofull, ks in pk.items():
                                if len(ofull) >= 2 and (ofull <= full or full <= ofull) and len(ofull & full) >= 2 and abs(len(ofull) - len(full)) <= 1: h |= ks
                        cands |= h
        else:  # probate: decedent
            m = re.search(r'ESTATE OF\s+(.+?)(?:,?\s+DECEASED)?$', style) or re.search(r'IN RE:?\s*(.+)$', style)
            if not m: st['pr_no_name'] += 1; continue
            nm = re.sub(r'\b(DECEASED|THE|ESTATE|OF|IN RE|AKA|A K A|FKA)\b.*$', '', m.group(1)).strip() if False else m.group(1)
            nm = re.split(r'\b(?:A/?K/?A|F/?K/?A)\b', nm)[0]
            full, ini = PL.person_key(nm)
            if len(full) < 2: st['pr_short'] += 1; continue
            cands = set(pk.get(full, ()))
            if not cands:
                for ofull, ks in pk.items():
                    if (ofull <= full or full <= ofull) and len(ofull & full) >= 2 and abs(len(ofull) - len(full)) <= 1: cands |= ks
        if not cands: st[c['kind'] + '_unmatched'] += 1; continue
        # precision-first: one owner entity (all matched parcels share the same normalized owner name)
        names = {norm_ent(owners[k]) for k in cands}
        if len(names) > 1 or len(cands) > 6: st[c['kind'] + '_ambiguous'] += 1; continue
        st[c['kind'] + '_matched'] += 1
        for k in cands: (fc if c['kind'] == 'foreclosure' else pr)[k].append(c)
    return fc, pr, dict(st)

def clerk_summary(lst, label):
    if not lst: return '', 0, 0
    lst = sorted(lst, key=lambda x: x['filed'], reverse=True); openn = sum(1 for x in lst if x['status'].startswith(('Pending', 'Reopened')))
    s = '; '.join(f"{x['case']} {x['type']} filed {x['filed']} - {x['status']}" for x in lst[:3])
    return f'{label}: {s}', len(lst), openn

# ---------------- permits / code ----------------
def load_mce(re_list):
    """MCeSearch (legacy county permits <10/2022, code cases <1/2024) - partial if the fetch was blocked; keyed by 14-digit parcel id -> 8-6 RE"""
    out = {'permits': collections.defaultdict(list), 'code': collections.defaultdict(list)}
    for fn, key in (('mce_permits.jsonl', 'permits'), ('mce_code.jsonl', 'code')):
        p = os.path.join(RAW, fn)
        if not os.path.exists(p): continue
        for line in open(p):
            try: r = json.loads(line)
            except Exception: continue
            pid = re.sub(r'\D', '', str(r.get('parcel_id') or ''))
            if len(pid) >= 14: out[key][pid[-14:-6] + '-' + pid[-6:]].append(r)
    return out

# ---------------- Buildability rating ----------------
RATE = {'': 0, 'G': 1, 'Y': 2, 'R': 3}
def score_parcel(P):
    """P = dict of per-parcel facts -> (rating 'G'/'Y'/'R'/'', [(sev, text)]).  sev: R blocker, Y caution, i info, G positive.
    Vacant lots and improved lots are judged differently: an existing lawful structure already shows the lot was buildable (rebuild / expand / replace), so most
    natural-resource flags only warn there; on a vacant lot they are blockers. This is a SCREEN built from public map layers - confirm with county / city planning."""
    R = []; add = lambda s, t: R.append((s, t))
    if P['govt']: return 'R', [('R', 'Owned by a government / conservation agency (federal, state, county or city) - not a private building opportunity')]
    if P['uc'] in (94, 95, 96, 98) and P['mkt'] == 0: return '', []
    vac = P['vacant']; imp = P['improved']; g = P['zgrp']; z = P['zcode']; jur = P['jur']
    # zoning
    if z:
        if g == 'cs': add('R' if vac else 'Y', f'Zoning {z} ({P["zlabel"]}): development essentially prohibited' if vac else f'Zoning {z} is a conservation / native district - existing structure may be nonconforming; expansion limited')
        elif g in ('pu', 'mi'): add('R' if vac else 'Y', f'Zoning {z} ({P["zlabel"]}) is public / institutional - not residential')
        elif g in ('cm', 'in'): add('Y', f'Zoning {z} ({P["zlabel"]}) is non-residential - housing only if allowed as a conditional / mixed use')
        elif g in RES_GROUPS: add('G', f'Zoning {z}: {P["zlabel"]}')
        else: add('i', f'Zoning {z}: {P["zlabel"]}')
        if P['dup']: add('G', 'Zoning appears to allow 2+ units (duplex / multifamily) - confirm density and allocation')
    else:
        add('i', f'No digital zoning map for {jur} - use / FLUM only ({P["flum"] or "n/a"}); confirm zoning with {jur if jur != "Unincorporated" else "county"} planning')
    # tier (unincorporated)
    t = P['tier']
    if t == 1: add('R' if vac else 'Y', 'Tier I (Natural Area): new residential allocations essentially unavailable' if vac else 'Tier I (Natural Area): rebuild OK, expansion / new units very limited')
    elif t == 5: add('R', 'Military land use designation')
    elif t == 2: add('Y', 'Tier II (Big Pine Key / No Name Key): restricted - habitat conservation plan, Key deer limits')
    elif t == 4: add('Y', 'Tier III-A (Special Protection Area): extra clearing and habitat limits')
    elif t == 3: add('i', 'Tier III (infill area): ROGO allocation process applies')
    # ROGO / allocation
    rs = P['rogo']
    if rs == 3: add('R' if vac else 'Y', 'ROGO dedicated lot - development rights retired / restricted by recorded dedication' + (f' ({P["ded_note"]})' if P['ded_note'] else ''))
    elif rs == 4: add('Y', 'ROGO dedication record (' + (P['ded_note'] or P['ded_type']) + ') - check recorded restriction')
    if rs == 1: add('G', P['rogo_txt'])
    elif rs == 2 and vac: add('Y', P['rogo_txt'])
    if vac and rs not in (1, 3) and g in RES_GROUPS:
        who = {'Unincorporated': 'Monroe County ROGO', 'Key West': 'Key West BPAS', 'Marathon': 'Marathon BPAS', 'Islamorada': 'Islamorada BPAS'}.get(jur, 'a building-permit allocation')
        add('Y', f'Vacant lot needs a residential building allocation ({who}); none on record' + ('. County ROGO final allocation period closed 7/13/2026; next pool awaits an ordinance' if jur == 'Unincorporated' else '. City allocation awards are not published as data'))
    # environment
    e = P['env']
    if e & E['fnai']: add('R' if vac else 'Y', f'Inside conservation land: {P["fnai"]}')
    if e & E['ff']: add('Y', f'Inside Florida Forever project boundary ({P["ff"]}) - state acquisition target; limits and buyers vary')
    wet = e & (E['nwi_fw'] | E['nwi_est'] | E['mangrove'] | E['water'])
    if wet:
        w = [ENV_LABEL[k] for k in ('nwi_fw', 'nwi_est', 'mangrove', 'water') if e & E[k]]
        add('R' if vac else 'Y', ' / '.join(w) + ' at the parcel centre' + (' - a vacant lot here is typically not permittable (verify delineation)' if vac else ' - existing structure predates / is permitted; expansion limited'))
    if e & E['upland']: add('Y', f'{P["habitat"] or "Upland"} habitat (tropical hardwood hammock / pineland): clearing and open-space limits apply')
    if e & E['beach']: add('Y', f'{P["habitat"] or "Beach berm / buttonwood"} habitat: coastal setbacks / limits')
    if e & E['cbrs']: add('Y', f'CBRS unit {P["cbrs"]}: no federal flood insurance; ROGO / BPAS point penalty')
    if e & E['deer']: add('Y', 'Key deer focus area (Big Pine / No Name Key): USFWS consultation, ROGO penalty')
    elif e & E['species']: add('Y', 'Protected species focus area: ' + P['species'].replace(';', ', ') + ' - habitat review / USFWS consultation')
    if e & E['historic']: add('Y', f'{P["hist"]}: design review for new construction / demolition')
    if e & E['subdmg']: add('Y', 'County substantial-damage property record (rebuild limited to flood rules)')
    if e & E['repl']: add('i', 'FEMA repetitive-loss area')
    # flood
    f = P['flood']
    if f.startswith('V'): add('R' if vac else 'Y', f'FEMA {f.split(" ")[0]} coastal high-hazard zone: elevated pile construction, ROGO / BPAS penalty, limited insurance')
    elif f.startswith('A'): add('i', f'FEMA {f.split(" ")[0]} high-risk zone: must elevate to base flood elevation; flood insurance required')
    elif f: add('G', f'FEMA {f.split(" ")[0]}: lower flood risk')
    # utilities
    if jur == 'Key West': add('G' if e & E['kwsewer'] else 'i', 'Key West sewer main within ~100 ft' if e & E['kwsewer'] else 'Key West: no sewer main found near the parcel - verify connection')
    else: add('i', 'Sewer / central water not published as parcel data - verify with FKAA and the sewer district (most Keys areas are now on central sewer)')
    # lot size
    lot = P['lot']; mn = P['minlot']
    if lot > 0:
        if mn and lot < mn: add('Y', f'Lot {lot:,.0f} sf is under the {z} minimum of {mn:,.0f} sf (may be a grandfathered platted lot - verify)')
        if lot < 1500 and vac: add('R', f'Lot only {lot:,.0f} sf - too small for a conforming building envelope')
        elif lot < 3000 and vac: add('Y', f'Small lot ({lot:,.0f} sf): setbacks may leave a very small building envelope')
        elif lot >= 5000 and vac: add('G', f'Lot {lot:,.0f} sf')
        elif lot >= 5000: add('i', f'Lot {lot:,.0f} sf')
    # existing structure
    if imp:
        add('G' if P['yb'] else 'i', f'Existing structure ({"built " + str(P["yb"]) if P["yb"] else "year unknown"}, building value ${P["bldg"]:,.0f}) - rebuild / replace of a lawful unit generally does not need a new allocation' if P['bldg'] else 'Existing structure on the roll')
        if P['teardown']: add('G', 'Low building-to-land value: teardown / redevelopment candidate')
    elif vac: add('i', 'No structure on the roll (vacant)')
    if P['subdmg'] is False and False: pass
    if P['taxdeed']: add('i', 'Tax-deed application advertised Feb-Mar 2026')
    sev = {s for s, _ in R}
    rating = 'R' if 'R' in sev else 'Y' if 'Y' in sev else 'G'
    return rating, R

def enrich(df, g, uc, bv, lot, yb, sqft, mk, kinds, est, flood_s, absent, owners_s, addr):
    n = len(df); folios = list(df.FOLIO); st = {}
    mzi, mzone, rules, zgrp, zlabel = zoning_tables(g, None); st['zoning_assigned'] = int((mzi > 0).sum()); st['zoning_by_jur'] = {j: int(((mzi > 0) & (g.jur.values == j)).sum()) for j in g.jur.unique()}
    tier = g.tier.map(TIER).fillna(0).astype(np.uint8).values
    res = [f[-14:-6] + '-' + f[-6:] for f in folios]
    rst, rtxt, ryr = rogo_tables(res)
    ded = g.ded_type.values; rst = np.where(np.isin(ded, ['DED-C', 'DR-C', 'DR-P', 'VHBP']), 3, np.where(np.isin(ded, ['LTF', 'DED-AFH', 'STATUS CHANGE']) & (rst != 1), 4, rst)).astype(np.uint8)
    # env bits
    env = np.zeros(n, np.uint16); h = g.habitat.values; nt = g.nwi_type.values
    def setb(mask, name): 
        nonlocal env; env = env | (mask.astype(np.uint16) * np.uint16(E[name]))
    setb(g.fnai.values != '', 'fnai'); setb(g.ff.values != '', 'ff')
    setb(np.array([('Freshwater' in t) for t in nt]), 'nwi_fw'); setb(np.array([('Estuarine and Marine Wetland' in t) for t in nt]), 'nwi_est'); setb(np.array([('Deepwater' in t) for t in nt]), 'water')
    setb(np.isin(h, ['Mangrove', 'Scrub Mangrove', 'Salt Marsh', 'Freshwater Wetland']), 'mangrove'); setb(h == 'Water', 'water')
    setb(np.isin(h, ['Hammock', 'Pineland']), 'upland'); setb(np.isin(h, ['Beach Berm', 'Buttonwood']), 'beach')
    setb(g.cbrs.values != '', 'cbrs'); sp = g.species.values; setb(sp != '', 'species'); setb(np.array(['Key deer' in s for s in sp]), 'deer')
    setb(g.historic.values != '', 'historic'); setb(g.subdmg.values.astype(bool), 'subdmg'); setb(g.repl.values.astype(bool), 'repl'); setb(g.kw_sewer.values.astype(bool), 'kwsewer')
    # clerk
    fc, pr, cst = run_clerk(list(owners_s), kinds, folios); st['clerk_match'] = cst
    fcs = [clerk_summary(x, 'Foreclosure') for x in fc]; prs = [clerk_summary(x, 'Probate') for x in pr]
    # marathon code cases
    mc = collections.defaultdict(list)
    p = os.path.join(RAW, 'marathon_code.json')
    if os.path.exists(p):
        for r in json.load(open(p)): mc[r['re']].append(r)
    # MCE
    mce = load_mce(res); st['mce_permit_parcels'] = len(mce['permits']); st['mce_code_parcels'] = len(mce['code'])
    td = {x['re'] for x in json.load(open(f'{RAW}/tax_deed_apps.json'))} if os.path.exists(f'{RAW}/tax_deed_apps.json') else set()
    today = dt.date.today(); y5 = today.year - 5
    lperm = np.zeros(n, np.uint16); pn5 = np.zeros(n, np.uint16); cn_open = np.zeros(n, np.uint8); cn5 = np.zeros(n, np.uint16); clast = np.zeros(n, np.uint16)
    psum = [''] * n; csum = [''] * n; sigm = np.zeros(n, np.uint16); bld = np.zeros(n, np.uint8); reasons = [''] * n; rtxt_out = [''] * n; zinfo = [''] * n
    DAY0 = dt.date(1900, 1, 1); dd = lambda d: (d - DAY0).days
    gc_ = lambda c: g[c].values if c in g.columns else None
    KW = dict(F=gc_('kw_Front_Setb'), S=gc_('kw_Side_Setba'), R=gc_('kw_Rear_Setba'), C=gc_('kw_Bldg_Cover'), I=gc_('kw_ISR'))
    def parse_date(s):
        s = str(s or '')[:10]
        try: return dt.datetime.strptime(s, '%Y-%m-%d').date()
        except Exception: return None
    for k in range(n):
        r = res[k]; sg = 0
        pl = mce['permits'].get(r, []); cl = mce['code'].get(r, [])
        if pl:
            ds = sorted([(parse_date(x.get('apply_date')), x) for x in pl if parse_date(x.get('apply_date'))], key=lambda t: t[0], reverse=True)
            if ds: lperm[k] = min(65535, dd(ds[0][0])); pn5[k] = sum(1 for d, _ in ds if d.year >= y5)
            psum[k] = f'{len(pl)} county permits (legacy system, through 9/2022); latest ' + '; '.join(f"{x.get('permit_no')} {x.get('permit_desc') or x.get('permit_type')} {str(x.get('apply_date'))[:10]} {x.get('status')}" for _, x in ds[:3])
        mrows = mc.get(r, [])
        if cl or mrows:
            cn5[k] = sum(1 for x in cl if (parse_date(x.get('open_date') or x.get('date')) or dt.date(1900, 1, 1)).year >= y5) + len(mrows)
            cn_open[k] = sum(1 for x in cl if str(x.get('status', '')).upper().startswith(('OPEN', 'ACTIVE'))) 
            bits = []
            if cl: bits.append(f'{len(cl)} county code cases (through 2023)')
            if mrows: bits.append('Marathon magistrate: ' + '; '.join(f"{x['case']} {x['date']} {x['violation'][:90]}" for x in mrows[:2]))
            csum[k] = ' | '.join(bits)
            sg |= SG['code']
        fcl, fcn, fco = fcs[k]; prl, prn, pro = prs[k]
        if fcn: sg |= SG['fc_any'] | (SG['fc_open'] if fco else 0)
        if prn: sg |= SG['pr_any'] | (SG['pr_open'] if pro else 0)
        if r in td: sg |= SG['taxdeed']
        if absent[k]: sg |= SG['absentee']
        if est[k]: sg |= SG['estate']
        if rst[k] == 1: sg |= SG['rogo_award']
        if rst[k] == 2: sg |= SG['rogo_applied']
        if rst[k] in (3, 4): sg |= SG['rogo_ded']
        vac = (uc[k] in VACANT_UC) or (bv[k] <= 10000 and sqft[k] == 0 and uc[k] <= 9 and uc[k] != 4)
        imp = (not vac) and (sqft[k] > 0 or bv[k] > 10000 or uc[k] in (1, 2, 4, 8, 3))
        tear = bool(imp and mk[k] > 0 and bv[k] > 0 and bv[k] / max(mk[k], 1) < 0.2)
        g_ = zgrp[k]; zc = g.zcode.iat[k]; mn = mzone[mzi[k]][5] if mzi[k] else None
        dup = (g_ in ('mf', 'mx', 'rs')) or (g.jur.iat[k] == 'Islamorada' and zc in ('R2', 'R3', 'R4', 'MF')) or (g.jur.iat[k] == 'Key West' and zc in ('MDR', 'MDR-C', 'HMDR', 'HDR', 'HHDR', 'HSMDR', 'MDR-1'))
        if vac: sg |= SG['vacant']
        if tear: sg |= SG['teardown']
        if dup and g_ in RES_GROUPS: sg |= SG['dup']
        env_k = int(env[k]); P = dict(govt=kinds[k] == 'govt', uc=int(uc[k]), mkt=float(mk[k]), vacant=bool(vac), improved=bool(imp), zgrp=g_, zcode=zc, zlabel=zlabel[k], jur=g.jur.iat[k], flum=g.flum.iat[k], tier=int(tier[k]),
                      rogo=int(rst[k]), rogo_txt=rtxt[k], ded_note=g.ded_note.iat[k], ded_type=g.ded_type.iat[k], env=env_k, fnai=g.fnai.iat[k], ff=g.ff.iat[k], habitat=g.habitat.iat[k], cbrs=g.cbrs.iat[k],
                      species=g.species.iat[k], hist=g.historic.iat[k], flood=flood_s[k] or '', lot=float(lot[k]), minlot=mn, yb=int(yb[k]), bldg=float(bv[k]), teardown=tear, subdmg=False, taxdeed=r in td, dup=bool(dup))
        rating, R = score_parcel(P); bld[k] = RATE[rating]
        order = {'R': 0, 'Y': 1, 'G': 2, 'i': 3}; R.sort(key=lambda t: order[t[0]])
        reasons[k] = '¦'.join(f'{s}~{t}' for s, t in R); sigm[k] = sg
        rtxt_out[k] = '; '.join(x for x in (rtxt[k], (g.ded_note.iat[k] if rst[k] in (3, 4) else '')) if x)
        extra = ' | '.join(x for x in (fcl, prl) if x)
        kwtxt = ''
        if g.jur.iat[k] == 'Key West' and KW['F'] is not None and str(KW['F'][k]).strip() not in ('', '0', 'nan'):
            kwtxt = f"Key West setbacks front {KW['F'][k]} / side {KW['S'][k]} / rear {KW['R'][k]} ft, building coverage {KW['C'][k]}%, impervious {KW['I'][k]}%"
        zinfo[k] = ' '.join(x for x in ((f"Zoning source: {g.zsrc.iat[k]}." if g.zsrc.iat[k] else ''), (f"FLUM {g.flum.iat[k]}." if g.flum.iat[k] else ''), kwtxt) if x)
        if extra: csum[k] = (csum[k] + ' | ' if csum[k] else '') + extra
    st['buildability'] = {k: int((bld == v).sum()) for k, v in RATE.items() if k}
    st['signals'] = {k: int(((sigm & v) > 0).sum()) for k, v in SG.items()}
    st['rogo'] = {ROGO_ST[i]: int((rst == i).sum()) for i in range(1, 5)}
    cols = dict(mz=mzi, tier=tier, rogo=rst, env=env, sigm=sigm, bld=bld, lperm=lperm, pn5=pn5, cn_open=cn_open, cn5=cn5, clast=clast)
    strs = dict(reasons=reasons, rogo_txt=rtxt_out, zinfo=zinfo, psum=psum, csum=csum)
    return cols, strs, mzone, rules, st
