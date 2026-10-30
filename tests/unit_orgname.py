"""Owner-kind regression, per county (Oct 30, 2026: 'AMERICAN EXPRESS TRAVEL RELATE', 'SOUTHERN SHORES ACQUISITIONS L' and 'FLORIDA EASTERN
ECCLESIASTICAL' were listed under 'Individuals (not a company)'). For EVERY county in counties.js (data-driven, nothing per county here):
  1. known company / organization names are not individuals (app orgName and the Python twin scripts/org_name.py),
  2. person names that carry a business-looking word ('JOHN BANK', 'ELLEN MAY SERVICE', 'MEIR BEN NISSAN', 'RAMSARAN ARLENE S L') stay individuals,
  3. in the county's own data, after the app's load-time reclassification (reclassOwners), no parcel whose owner name contains a known
     company name is left an individual (flags & (8|16|32) == 0 is what the Individuals filter shows),
  4. the app (tests/unit_orgname.js) and the Python twin reclassify exactly the same rows of every pack.
    python3 tests/unit_orgname.py      -> exit 0 only if every check passed"""
import gzip, json, os, re, struct, subprocess, sys, tempfile
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
from org_name import org_name, org_given

COMPANIES = ['AMERICAN EXPRESS TRAVEL RELATE', 'AMERICAN EXPRESS TRAVEL RELATED SERVICES', 'SOUTHERN SHORES ACQUISITIONS L', 'SOUTHERN SHORES ACQUISITIONS',
             'FLORIDA EASTERN ECCLESIASTICAL', 'NRNS ACQUISITION 3696', 'BLACK PEARL HOME ACQUISITIONS', 'GLOBAL SIGNAL ACQUISITIONS IV',
             'SUNSET ACQUISITIONS CORPORATIO', 'HOMESWEETHOME1LLC', 'THE NATURE CONSERVANCY', 'KEY LARGO VOLUNTEER AMBULANCE', 'INVERSIONES TIERRA LIMITADA',
             'MCDONALDS RESTAURANTS OF FL', 'PRETORIA ESTATE AG', 'IT GLOBAL SRO', '113 NE 7TH STREET', 'SOUTH FLORIDA COMMERCIAL',
             'HOUSE OF BROOKINS ECCLESIASTIC', 'COTTONWOOD COMMERCIAL PROPERTI', 'WESTON ACQUISITIONS & DEVELOPM', 'SPECTOR & SONS', 'CHRISTIAN LIFE CENTER',
             'THE MOST REVEREND THOMAS G WENSKI', 'REPUBLIC OF FRANCE', 'NSP BRICKELL DST', 'ROSENBERG & ROSENBERG PROPERTI', 'MIAMI HOME LOANS']
PEOPLE = ['JOHN BANK', 'MARIA POWER', 'MARINA ROSSI', 'ELLEN MAY SERVICE', 'NICHOLAS OLIVER BANK', 'ROBERT CHURCH', 'SMITH JOHN TRAVEL', 'GARCIA MARIA EXPRESS',
          'MEIR BEN NISSAN', 'RAMSARAN ARLENE S L', 'COUNCIL JAIME', 'JOSE PLAZA', 'WILLIAMS TRAVIS AG', 'JOHN & MARY CAPITAL', 'DEV PATEL', 'MARIA FLORIDA',
          'CHRISTIAN DANIELLE FORSYTHE', 'GARY GRIBBLE & JENNIFER REAL', 'ANA QUINTERO | 5941 SW 185 WAY', 'JOHN SOUTHERN', 'EDWARD SUNSHINE & W ANNE',
          'ROXANNA A GOLTZER LE | REM MEMORIAL SLOAN KETTERING | CANCER CENTER', 'VELIZ ANGEL AND BEATRIZ COMMUN', 'KASPERSETZ FLORIDA LIVING TRUS',
          'TOYOTA JAMES R & SANDRA', 'CHAPTER JENNY LYNN', 'WILMA COUNCIL', 'MICHEL VAZQUEZ | HAYDEELIZ PLAZA', 'HOOL LANCE W REV SEPARATE PROP']
# whole-word (substring) owner names Branden reported: no parcel of any county whose owner contains one of these may be an individual
REPORTED = ['AMERICAN EXPRESS TRAVEL', 'SOUTHERN SHORES ACQUISITIONS', 'FLORIDA EASTERN ECCLESIASTICAL']

def parse(fn):
    b = gzip.open(fn).read(); hl = struct.unpack('<I', b[:4])[0]; h = json.loads(b[4:4 + hl]); st = 4 + hl; out = {'n': h['n'], 'owner': None, 'flags': None}
    for c in h['cols']:
        x = b[st + c['offset']: st + c['offset'] + c['bytes']]
        if c['name'] == 'owner': out['owner'] = x.decode('utf8').split('\n')
        if c['name'] == 'flags':
            sz = {'uint8': 1, 'uint16': 2, 'uint32': 4}[c['type']]; out['flags'] = list(struct.unpack('<%d%s' % (len(x) // sz, {1: 'B', 2: 'H', 4: 'I'}[sz]), x))
    return out

def py_fixed(d, given):
    """rows the Python twin reclassifies (same loop as the app's reclassOwners), memoised per distinct name"""
    memo = {}; out = []
    for i, (o, f) in enumerate(zip(d['owner'], d['flags'])):
        if f & (8 | 16 | 32): continue
        r = memo.get(o)
        if r is None: r = memo[o] = org_name(o, given)
        if r: out.append(i)
    return out

def main():
    errs = []
    def ok(c, m):
        print(('PASS ' if c else 'FAIL ') + m)
        if not c: errs.append(m)
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as t: json.dump(COMPANIES + PEOPLE, t); tn = t.name
    js = json.loads(subprocess.run(['node', os.path.join(R, 'tests', 'unit_orgname.js'), tn], check=True, capture_output=True, text=True).stdout); os.unlink(tn)
    ok(len(js) >= 1, f'counties in counties.js: {list(js)}')
    for cid, c in js.items():
        withnames = [p for p in c['packs'] if p['hasOwner']]
        if not withnames:
            print(f'NOTE {cid}: no owner names in its packs ({c["dir"]}); name checks not applicable'); continue
        g0 = None
        for p in withnames:
            d = parse(os.path.join(R, c['dir'], json.load(open(os.path.join(R, c['dir'], 'meta.json')))['packs'][[q['name'] for q in c['packs']].index(p['name'])]['files'][0]))
            g = org_given(d['owner'], d['flags'])
            if g0 is not None: g = g | g0   # as reclassOwners: the condo pack adds the main pack's given names
            elif p is c['packs'][0]: g0 = g
            ok(sorted(g) == p['given'], f'{cid}/{p["name"]}: given-name sets agree (py {len(g)}, js {len(p["given"])}; diff {sorted(set(p["given"]) ^ g)[:10]})')
            pf = py_fixed(d, g); jf = p['fixed']; dj = sorted(set(jf) - set(pf)); dp = sorted(set(pf) - set(jf))
            ok(not dj and not dp, f'{cid}/{p["name"]}: app and Python twin reclassify the same rows ({len(jf)}; app-only {[d["owner"][i] for i in dj[:5]]}, py-only {[d["owner"][i] for i in dp[:5]]})')
            for x in COMPANIES:
                ok(p['names'][x] and org_name(x, g), f'{cid}/{p["name"]}: {x!r} is a company (app {p["names"][x]}, py {org_name(x, g)})')
            for x in PEOPLE:
                ok(not p['names'][x] and not org_name(x, g), f'{cid}/{p["name"]}: {x!r} stays an individual (app {p["names"][x]}, py {org_name(x, g)})')
            fixed = set(jf); left = []; seen = 0
            for i, (o, f) in enumerate(zip(d['owner'], d['flags'])):
                u = re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9& ]+', ' ', (o or '').upper()))
                for x in REPORTED:
                    if x in u:
                        seen += 1
                        if not (f & (8 | 16 | 32)) and i not in fixed: left.append(o)
            ok(not left, f'{cid}/{p["name"]}: {seen} parcels owned by {REPORTED}: none left under Individuals {left[:5]}')
    print('ERRORS:', errs[:20] if errs else 'none', f'({len(errs)})'); sys.exit(1 if errs else 0)

if __name__ == '__main__': main()
