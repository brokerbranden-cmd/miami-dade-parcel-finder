"""Per-parcel permit / code-case columns from RAW/permit_index.json (made by merge_permits.py). Used by vacancy_lib.py and build_data.py.

Coverage rules (the vacancy score only penalises 'no permit' where permits are actually covered):
  permit window = from the first year the city's permit source is complete (>=40% of its recent annual volume) until today.
  window >= 8 years: full 'no permit' points   5-8 years: half points   < 5 years or no data: never penalised
"""
import json, os, datetime as dt
import numpy as np

DAY0 = dt.date(1900, 1, 1)
PCS = [  # (code, label) - bit order of the `pcs` pack column, mirrored in app.js PCS
    ('PO', 'Open permit'), ('PX', 'Expired / revoked permit'), ('P5', 'Permit in last 5 yrs'), ('PN', 'No permit in coverage window'),
    ('CO', 'Open code case'), ('C5', 'Code case in last 5 yrs'), ('CL', 'Code lien / fines'), ('PC', 'City has permit data'),
]
PBIT = {c: i for i, (c, _) in enumerate(PCS)}

def days(s):
    try: return (dt.date.fromisoformat(s[:10]) - DAY0).days if s else 0
    except Exception: return 0

def coverage(RAW, today=None):
    """{muni: {city, permit_from, permit_years, permit_level(full|half|recent|none), code_from, code_level, ...}} + catalog info"""
    today = today or dt.date.today()
    import permit_catalog
    idx = json.load(open(f'{RAW}/permit_index.json')) if os.path.exists(f'{RAW}/permit_index.json') else {'coverage': {}, 'sources': []}
    cov = {}
    for m, c in permit_catalog.CATALOG.items():
        v = idx['coverage'].get(m, {})
        pf = v.get('permit_from', ''); cf = v.get('code_from', '')
        py = (today - dt.date.fromisoformat(pf)).days / 365.25 if pf else 0
        cy = (today - dt.date.fromisoformat(cf)).days / 365.25 if cf else 0
        lvl = lambda y: 'full' if y >= 8 else 'half' if y >= 5 else 'recent' if y > 0 else 'none'
        cov[m] = {'city': c['city'], 'status': c['status'], 'portal': c.get('portal', ''), 'tech': c.get('tech', ''), 'reason': c.get('reason', ''),
                  'permit_from': pf, 'permit_years': round(py, 1), 'permit_level': lvl(py), 'code_from': cf, 'code_years': round(cy, 1), 'code_level': lvl(cy),
                  'permit_src': (v.get('permit') or {}).get('label', ''), 'code_src': (v.get('code') or {}).get('label', ''),
                  'permit_note': c.get('permit', ''), 'code_note': c.get('code', '')}
    return cov, idx

def load(RAW, folios, yb, bv, today=None):
    """arrays aligned with `folios`; yb = year built, bv = building value (only built parcels can be 'no permit')"""
    today = today or dt.date.today()
    cov, idx = coverage(RAW, today)
    n = len(folios); P = idx.get('permits', {}); C = idx.get('cases', {})
    T24 = (today - dt.timedelta(days=730)).isoformat()
    z = lambda t: np.zeros(n, t)
    out = dict(last=z(np.int32), n5=z(np.uint16), nopen=z(np.uint8), nexp=z(np.uint8), nrev=z(np.uint8), recent=z(bool), exp_last=z(np.int32),
               cn_open=z(np.uint8), cn5=z(np.uint16), clast=z(np.int32), clien=z(bool), cflags=z(np.uint8), np_flag=z(bool), pcov=z(bool), plevel=z(np.uint8),
               cfrom_year=z(np.uint16), pfrom_year=z(np.uint16), has_p=z(bool), has_c=z(bool))
    psum = [''] * n; csum = [''] * n
    pfrom = np.zeros(n, np.int32); plev = np.zeros(n, np.uint8)       # permit window start (days) and level 0 none 1 recent 2 half 3 full
    LV = {'none': 0, 'recent': 1, 'half': 2, 'full': 3}
    for k, f in enumerate(folios):
        c = cov.get(f[:2])
        if c and c['permit_from']:
            plev[k] = LV[c['permit_level']]; pfrom[k] = days(c['permit_from']); out['pfrom_year'][k] = int(c['permit_from'][:4])
        if c and c['code_from']: out['cfrom_year'][k] = int(c['code_from'][:4])
        v = P.get(f)
        if v:
            out['has_p'][k] = True; out['last'][k] = days(v[0]); out['n5'][k] = v[1]; out['nopen'][k] = min(255, v[2]); out['nexp'][k] = min(255, v[3]); out['nrev'][k] = min(255, v[4])
            out['exp_last'][k] = days(v[5]); out['recent'][k] = v[0] >= T24
            psum[k] = f"{v[6]} · last {v[0]}" + (f" · {v[1]} in 5 yrs" if v[1] else '') + (f" · {v[2]} open" if v[2] else '') + (f" · {v[3] + v[4]} expired/revoked" if v[3] + v[4] else '')
        w = C.get(f)
        if w:
            out['has_c'][k] = True; out['cn_open'][k] = min(255, w[0]); out['cn5'][k] = min(65535, w[1]); out['clast'][k] = days(w[2]); out['clien'][k] = bool(w[5]); out['cflags'][k] = w[6]
            csum[k] = f"{w[4] or 'Case'} · {w[3]} · opened {w[2]}" + (f" · {w[0]} open" if w[0] else '') + (' · lien' if w[5] else '') + (f" · {w[1]} in 5 yrs" if w[1] else '')
    out['plevel'] = plev
    built = (np.asarray(bv) > 0)
    yb = np.asarray(yb)
    # 'no permit in window': permit coverage >= 5 yrs, building older than the window, no permit since the window start
    elig = built & (plev >= 2) & (yb > 0) & (yb < out['pfrom_year'].astype(np.int64))
    out['np_flag'] = elig & (out['last'] < pfrom)
    out['np_full'] = plev >= 3
    out['pcov'] = plev >= 2
    # pcs bits
    pcs = np.zeros(n, np.uint16)
    pcs |= ((out['nopen'] > 0).astype(np.uint16) << PBIT['PO']); pcs |= (((out['nexp'] + out['nrev']) > 0).astype(np.uint16) << PBIT['PX'])
    pcs |= ((out['n5'] > 0).astype(np.uint16) << PBIT['P5']); pcs |= (out['np_flag'].astype(np.uint16) << PBIT['PN'])
    pcs |= ((out['cn_open'] > 0).astype(np.uint16) << PBIT['CO']); pcs |= ((out['cn5'] > 0).astype(np.uint16) << PBIT['C5'])
    pcs |= (out['clien'].astype(np.uint16) << PBIT['CL']); pcs |= ((plev >= 1).astype(np.uint16) << PBIT['PC'])
    out['pcs'] = pcs; out['psum'] = psum; out['csum'] = csum; out['cov'] = cov; out['idx_stats'] = idx.get('stats', {}); out['sources'] = idx.get('sources', []); out['index_built'] = idx.get('built', '')
    return out
