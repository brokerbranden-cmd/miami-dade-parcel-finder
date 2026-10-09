"""'Likely vacant / neglected' hint (vscore 0-100 + vsig bits). Keep in sync with app.js VSIG and README "Vacancy & condition hints".

Only public records are used - nothing is inferred from imagery, and there is no utility data (Miami-Dade publishes none):
  roll (PA)      homestead exemption, mailing address, last sale date, land / building value, year built
  distress layer tax delinquency (TC/TX/TD), probate / deceased (PR/DC), open unsafe-structure case
  violations     county code-compliance cases (open or in lien) - neglect types and foreclosure-registry cases;
                 county building cases of type 'Expired Permit'
  permits        City of Miami permits 2014-present (City of Miami parcels only); County Building Dept permits (last ~2 years)
Only parcels with a building (building value > 0) and a non-government owner are scored.
"""
import json, os, re, datetime as dt, collections
import numpy as np

# (code, label, points)  - bit = index
VSIG = [
    ('NA', 'No homestead + absentee owner', 15),     # 18 when the mailing address is out of state; 5 = no homestead but mail at the property
    ('US', 'Open unsafe structure case', 25),
    ('NG', 'Neglect code case (overgrowth, junk, abandoned, upkeep, min. housing, unsecured pool)', 15),
    ('FR', 'Foreclosure registry case', 12),
    ('XP', 'Expired / revoked permit', 8),
    ('NP', 'No permit on record since 2014 (City of Miami)', 6),   # 10 when built 1970 or earlier ("old, no improvements")
    ('LO', 'Owned 20+ years', 5),
    ('LB', 'Building < 20% of value', 8),
    ('TX', 'Tax delinquent', 10),
    ('ES', 'Estate / owner deceased', 8),
    ('OV', 'Other open code / building case', 4),
    ('RP', 'Recent permit (activity)', -15),          # permit issued in the last 24 months -> someone is working on it
]
VBIT = {c: i for i, (c, _, _) in enumerate(VSIG)}
NEGLECT = re.compile(r'Junk/Trash/Overgrowth|Abandoned Property|Structure Maintenance|Minimum Housing|Unsecured Pool|Pool Maintenance|Bee Infestation', re.I)
FREG = re.compile(r'Foreclosure Registry|Foreclosed Property', re.I)

def _fol(s): return re.sub(r'\D', '', str(s or ''))

def compute(RAW, folios, kinds, homestead, oos, absz, yrs_owned, bv, mk, yb, dsig_hard, today=None):
    today = today or dt.date.today()
    n = len(folios); idx = {f: k for k, f in enumerate(folios)}
    neg = np.zeros(n, bool); freg = np.zeros(n, bool); xp = np.zeros(n, bool); ov = np.zeros(n, bool)
    stats = collections.Counter()
    def V(nm):
        p = f'{RAW}/viol/{nm}.json'
        return json.load(open(p))['rows'] if os.path.exists(p) else []
    for nm in ('cc_open', 'cc_lien'):
        for r in V(nm):
            k = idx.get(_fol(r['FOLIO']))
            if k is None: continue
            d = r.get('PROBLEM_DESC') or ''
            if NEGLECT.search(d): neg[k] = True
            elif FREG.search(d): freg[k] = True
            elif nm == 'cc_open': ov[k] = True
    for r in V('bldg_open'):
        k = idx.get(_fol(r['FOLIO']))
        if k is None: continue
        if r['CASE_TYPE'] == 'Expired Permit': xp[k] = True
        elif r['CASE_TYPE'] != 'Unsafe Structure': ov[k] = True
    # permits
    city_cov = np.array([f[:2] == '01' for f in folios])
    has_city = np.zeros(n, bool); recent = np.zeros(n, bool); last_permit = [''] * n
    cutoff = (today - dt.timedelta(days=730)).isoformat()
    pf = f'{RAW}/permits.json'
    pmeta = None
    if os.path.exists(pf):
        P = json.load(open(pf)); pmeta = {'pulled': P['pulled'], 'coverage': P['coverage'], 'sources': P['sources']}
        for f, v in P['city'].items():
            k = idx.get(f)
            if k is None: continue
            has_city[k] = True; last_permit[k] = max(last_permit[k], v[0] or '')
            # expired/revoked permit with no later permit issued and nothing active
            if v[3] and v[2] and v[2] >= (v[0] or '') and not v[4]: xp[k] = True
        for f, v in P['county'].items():
            k = idx.get(f)
            if k is not None: last_permit[k] = max(last_permit[k], v[0] or '')
        recent = np.array([lp >= cutoff for lp in last_permit])
    else:
        city_cov[:] = False
    lp_days = np.array([(dt.date.fromisoformat(x) - dt.date(1900, 1, 1)).days if x else 0 for x in last_permit])
    corp_gov = np.array([k in ('corp', 'govt') for k in kinds]); govt = np.array([k == 'govt' for k in kinds])
    built = (bv > 0) & ~govt
    pts = np.zeros(n, np.int32); bits = np.zeros(n, np.int64)
    def put(mask, code, p):
        nonlocal pts, bits
        mask = mask & built
        pts += np.where(mask, p, 0).astype(np.int32); bits |= mask.astype(np.int64) << VBIT[code]
    nohs = ~homestead & ~corp_gov
    put(nohs & oos, 'NA', 18); put(nohs & ~oos & absz, 'NA', 15)
    put(nohs & ~oos & ~absz, 'NA', 0)  # bit only below
    bits &= ~((nohs & ~oos & ~absz).astype(np.int64) << VBIT['NA'])
    pts += np.where(built & nohs & ~oos & ~absz, 5, 0).astype(np.int32)
    put((dsig_hard >> 5 & 1).astype(bool), 'US', 25)
    put(neg, 'NG', 15); put(freg, 'FR', 12); put(xp, 'XP', 8)
    nop = city_cov & ~has_city & (yb > 0) & (yb < 2014)
    put(nop & (yb <= 1970), 'NP', 10); put(nop & (yb > 1970), 'NP', 6)
    put(yrs_owned >= 20, 'LO', 5)
    put((mk > 0) & (bv / np.maximum(mk, 1) < 0.2), 'LB', 8)
    put(((dsig_hard >> 2) & 1 | (dsig_hard >> 3) & 1 | (dsig_hard >> 4) & 1).astype(bool), 'TX', 10)
    put(((dsig_hard >> 10) & 1 | (dsig_hard >> 11) & 1).astype(bool), 'ES', 8)
    put(ov & ~neg, 'OV', 4)
    put(recent, 'RP', -15)
    vscore = np.clip(pts, 0, 100)
    stats = {'scored_parcels': int(built.sum()), 'ge40': int((vscore >= 40).sum()), 'ge60': int((vscore >= 60).sum()),
             'by_signal': {c: int(((bits >> b) & 1).sum()) for b, (c, _, _) in enumerate(VSIG)},
             'city_of_miami_with_permit': int(has_city.sum()), 'recent_permit': int((recent & built).sum()), 'permits': pmeta}
    return vscore.astype(np.uint8), bits.astype(np.uint16), lp_days, stats
