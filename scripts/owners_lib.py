"""Owner portfolio grouping (used by build_data.py).

Group key per parcel:
  * companies / trusts / government: normalized first-owner name (entity names are specific enough on their own)
  * individuals: normalized first-owner name + normalized mailing address (common names like JOSE RODRIGUEZ would
    otherwise lump unrelated people together)
Second link (catches LLC clusters): name keys that share one normalized mailing address (street + unit + ZIP) are merged
when that address is used by 2-12 distinct names, is not the parcel's own site address, and no government / bank /
association owner uses it (registered-agent and management-company addresses stay unlinked).
A merged cluster never exceeds 12 distinct names (so registered-agent / law-firm addresses can't chain unrelated LLCs).
Groups with 2+ parcels get an id >= 1; single-parcel owners get 0.
Group flags: 1 government, 2 bank / lender / GSE, 4 association / HOA / non-profit / church, 8 large holder (200+ parcels).
"""
import re, collections
import numpy as np

SUFFIX = re.compile(r"\b(LLC|L L C|LC|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|LP|L P|LLLP|LLP|PLLC|PA|P A|NA|N A|THE|"
                    r"TR|TRS|TRSTEE|TRUSTEE|TRUSTEES|AS TRUSTEE|JTRS|JTWROS|TEN COM|TENANTS IN COMMON|LE|L/E|REM|REMAINDERMAN|H/E|&W|&H|ETAL|ET AL|ET UX|ETUX|JR|SR|II|III|IV)\b")
BANK = re.compile(r"\b(BANK|BANCORP|MORTGAGE|MTG|LENDING|LOAN|SERVICING|SAVINGS|CREDIT UNION|FEDERAL NATIONAL|FANNIE MAE|FREDDIE MAC|FEDERAL HOME LOAN|"
                  r"SECRETARY OF HOUSING|HOUSING AND URBAN|HUD\b|SEC OF HUD|US SEC HUD|NATIONAL ASSOCIATION|TRUST COMPANY|DEUTSCHE|WILMINGTON|WELLS FARGO|JPMORGAN|CITIBANK)")
ASSOC = re.compile(r"\b(ASSN|ASSOCIATION|ASSOC|CONDOMINIUM|CONDO|HOMEOWNERS|HOA|POA|CHURCH|MINISTR|CONGREGATION|TEMPLE|DIOCESE|ARCHDIOCESE|SYNAGOGUE|MOSQUE|"
                   r"FOUNDATION|SOCIETY|UNIVERSITY|COLLEGE|SCHOOL|ACADEMY|HOSPITAL|CLUB|CEMETERY|FLORIDA POWER|FPL|RAILWAY|RAILROAD|UTILIT|TELEPHONE|BELLSOUTH|AT&T)")
STREET = {'STREET': 'ST', 'AVENUE': 'AVE', 'AV': 'AVE', 'ROAD': 'RD', 'DRIVE': 'DR', 'COURT': 'CT', 'PLACE': 'PL', 'TERRACE': 'TER', 'TERR': 'TER',
          'BOULEVARD': 'BLVD', 'LANE': 'LN', 'HIGHWAY': 'HWY', 'PARKWAY': 'PKWY', 'CIRCLE': 'CIR', 'NORTH': 'N', 'SOUTH': 'S', 'EAST': 'E', 'WEST': 'W',
          'NORTHWEST': 'NW', 'NORTHEAST': 'NE', 'SOUTHWEST': 'SW', 'SOUTHEAST': 'SE', 'SUITE': 'STE', 'APARTMENT': 'APT', 'UNIT': 'APT', '#': 'APT',
          'P O BOX': 'PO BOX', 'POST OFFICE BOX': 'PO BOX', 'POBOX': 'PO BOX'}

def norm_name(s):
    s = s.upper().replace('&', ' & ').replace("'", '')
    s = re.sub(r'[.,/\\\-"()]', ' ', s); s = s.replace(' & W ', ' &W ').replace(' & H ', ' &H ')
    s = re.sub(r'\bL\s?L\s?C\b', 'LLC', s)
    s = SUFFIX.sub(' ', s)
    s = re.sub(r'\b(LIVING|REVOCABLE|REV|IRREVOCABLE|IRREV|FAMILY|LAND|DECLARATION OF|AGREEMENT|DTD|DATED|U/A|UA)\b', ' ', s) if 'TRUST' in s or ' TR ' in f' {s} ' else s
    s = re.sub(r'\bTRUST\b', ' ', s)
    s = re.sub(r'\b\d{1,2} \d{1,2} \d{2,4}\b', ' ', s)          # trust dates
    s = re.sub(r'[^A-Z0-9& ]', ' ', s); s = re.sub(r'\s+', ' ', s).strip(' &')
    return s

def norm_mail(a1, a2, z):
    s = (a1 + ' ' + a2).upper().replace('.', ' ').replace(',', ' ')
    s = re.sub(r'\bP\s*O\s*BOX\b|\bPOST OFFICE BOX\b|\bPOBOX\b', 'PO BOX', s)
    s = re.sub(r'#', ' ', s)
    s = re.sub(r'\b(\d+)\s*(FL|FLR|FLOOR|ST FL|ND FL|RD FL|TH FL)\b', r'\1', s)
    w = [STREET.get(x, x) for x in s.split()]
    w = [re.sub(r'^(\d+)(ST|ND|RD|TH)$', r'\1', x) for x in w]
    w = [x for x in w if x not in UNITW]          # 'STE 403', '#403', '403' and 'FL 2' / '2 FLOOR' all collapse
    s = ' '.join(w).strip()
    z = (z or '')[:5]
    return f'{s}|{z}' if s and z else ''

MAX_NAMES = 12
UNITW = {'APT', 'STE', 'SUITE', 'UNIT', 'FL', 'FLR', 'FLOOR', 'RM', 'ROOM', 'NO', 'BLDG', 'OFFICE', 'OFC'}

class UF:
    def __init__(self, n): self.p = list(range(n)); self.sz = [1] * n
    def find(self, x):
        while self.p[x] != x: self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a, b, cap):
        a, b = self.find(a), self.find(b)
        if a == b or self.sz[a] + self.sz[b] > cap: return False
        a, b = min(a, b), max(a, b); self.p[b] = a; self.sz[a] += self.sz[b]; return True

def group_owners(owner1, kinds, subs, mail1, mail2, mzip, site_addr, site_zip, distressed, is_condo, mkt):
    n = len(owner1)
    nn = [norm_name(s) for s in owner1]
    mk = [norm_mail(a, b, z) for a, b, z in zip(mail1, mail2, mzip)]
    site = [norm_mail(a, '', z) for a, z in zip(site_addr, site_zip)]
    key = [(f'P:{a}|{m}' if k == 'person' else f'E:{a}') if a else '' for a, m, k in zip(nn, mk, kinds)]
    kid = {}; kof = np.zeros(n, dtype=np.int64) - 1
    for i, k in enumerate(key):
        if k: kof[i] = kid.setdefault(k, len(kid))
    uf = UF(len(kid))
    # mailing-address link between different names
    by_mail = collections.defaultdict(set); bad_mail = set()
    for i in range(n):
        if kof[i] < 0 or not mk[i]: continue
        if mk[i].split('|')[0] == site[i].split('|')[0] and kinds[i] == 'person': continue   # owner lives there: not a portfolio link
        by_mail[mk[i]].add(kof[i])
        if kinds[i] == 'govt' or subs[i] in ('bank', 'assoc', 'utility', 'inst'): bad_mail.add(mk[i])
    linked = 0
    for m, ks in sorted(by_mail.items(), key=lambda x: len(x[1])):   # small (most specific) address groups first
        if 2 <= len(ks) <= MAX_NAMES and m not in bad_mail:
            ks = sorted(ks)
            linked += sum(uf.union(ks[0], k, MAX_NAMES) for k in ks[1:]) > 0   # a cluster never grows past MAX_NAMES names
    root = np.array([uf.find(int(k)) if k >= 0 else -1 for k in kof])
    cnt = collections.Counter(root[root >= 0].tolist())
    gid = {}; og = np.zeros(n, dtype=np.uint32)
    for i in range(n):
        r = root[i]
        if r >= 0 and cnt[r] >= 2: og[i] = gid.setdefault(r, len(gid) + 1)
    G = len(gid) + 1
    gn = np.bincount(og, minlength=G); gc = np.bincount(og, weights=is_condo.astype(float), minlength=G)
    gd = np.bincount(og, weights=np.asarray(distressed).astype(float), minlength=G)
    gmv = np.bincount(og, weights=mkt.astype(float), minlength=G)
    names = collections.defaultdict(collections.Counter); flags = np.zeros(G, dtype=np.int64)
    for i in np.nonzero(og)[0]:
        g = og[i]; names[g][owner1[i]] += 1
        if kinds[i] == 'govt': flags[g] |= 1
        if subs[i] == 'bank': flags[g] |= 2
        if subs[i] in ('assoc', 'inst', 'utility'): flags[g] |= 4
    flags |= (gn >= 200) * 8
    disp = [''] * G; nvar = [0] * G
    for g, c in names.items(): disp[g] = c.most_common(1)[0][0]; nvar[g] = len(c)
    return og, {'n': gn.astype(int).tolist(), 'nc': gc.astype(int).tolist(), 'nd': gd.astype(int).tolist(), 'mv': (gmv / 1000).round().astype(int).tolist(),
                'fl': flags.astype(int).tolist(), 'name': disp, 'nv': nvar, 'linkedMail': linked}
