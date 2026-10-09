"""Clerk probate exports -> Probate (PR) and Deceased-owner (DC) signals.

Input: Official Records CSV exports in raw/probate_downloads/ (probate_PAD_*.csv = PROBATE & ADMINISTRATION, probate_PRO_*.csv = PROBATE ORDER OF
DISTRIBUTION, probate_DCE_*.csv = DEATH CERTIFICATE (EST OF)); same columns as the lis-pendens exports, one row per party pairing
("PARTY / OTHER PARTY"), decedent names usually written "LAST FIRST M" and often end in "EST OF".

Rules (precision first - a record that cannot be tied to exactly one owner is left out and counted as unmatched / low confidence):
  * dedupe: rows pooled across files by Clerk's File Number (CFN), exact duplicate rows dropped; one CFN = one document.
  * decedent = the party whose name ends in EST OF / ESTATE OF (PAD, PRO); the only party on a DCE. PAD/PRO documents with no EST OF party have no
    known decedent (they only give PR when the property itself matches).
  * property match (PRO has legal / plat / block / address): (1) street address -> exactly one folio, or (2) plat book/page + lot (+ block) -> exactly one
    folio; then the folio's owner name must contain a party or decedent (-> high) - a legal-only match with no name agreement is 'medium',
    an address-only match with no name agreement is rejected.
  * name match (everything else): decedent name vs the owner names on the roll. "LAST FIRST M" is compared as a set of words with initials allowed to
    match full middle names; the roll's "&W SPOUSE" / "& SPOUSE" owners are split. Exactly one folio (or several folios with the identical owner
    name AND mailing address) -> match.  high = name has first+last+middle (initial or name) and agrees, or the roll already says EST OF / LE;
    medium = first+last only, unique county-wide.  Organizations / trusts / government owners are never name-matched.
  * signals: PR (probate / estate) from PAD/PRO matches, DC (owner deceased) from decedent matches (DCE, or PAD/PRO decedent). Each carries doc type,
    case number (Misc Ref when present), recorded date, CFN, match method + confidence, and the Clerk search link.
  * merge: a folio that already has a PR/DC record from the No-Heir-Probates / Obituary outputs gets this evidence folded into that record
    (same case number, same decedent, or - for DC - any existing DC record) instead of a second record; points are per signal code anyway.
"""
import csv, glob, collections, re, os

SUFFIX = {'JR', 'SR', 'II', 'III', 'IV', 'EST', 'ESTATE', 'OF', 'THE', 'LE', 'JTRS', 'ETAL', 'ETUX', 'DECEASED', 'DEC', 'DECD', 'TR', 'TRS', 'TRUSTEE', 'LIFE', 'ET', 'AL', 'UX', 'VIR', 'FKA', 'AKA', 'NKA', 'AND'}
ORG = re.compile(r'\b(LLC|INC|CORP|CORPORATION|COMPANY|CO|LTD|LP|LLP|BANK|ASSN|ASSOC|ASSOCIATION|FOUNDATION|CHURCH|TRUST|REVOCABLE|PARTNERS|HOLDINGS?|PROPERTIES|INVESTMENTS?|ENTERPRISES?|MORTGAGE|FUND|CITY OF|COUNTY|STATE OF|UNITED STATES|INTERNAL REVENUE|DEPT|DEPARTMENT|SECRETARY|HOUSING|SCHOOL|UNIVERSITY|COLLEGE)\b')
EST = re.compile(r'\b(EST|ESTATE) OF\b|\bEST OF$|\bESTATE$|\bEST$|\bDECEASED\b')
CASE = re.compile(r'\b(\d{4}-\d{5,6}-[A-Z]{2}-\d{2})\b')

def words(s): return re.findall(r"[A-Z]+", str(s).upper().replace("'", ''))
def person_key(name):
    """-> (frozenset of full words, frozenset of initials) from 'LAST FIRST M ...' or 'FIRST M LAST' (order does not matter); suffixes dropped"""
    w = [x for x in words(name) if x not in SUFFIX]
    full = frozenset(x for x in w if len(x) > 1); ini = frozenset(x for x in w if len(x) == 1)
    return full, ini
def owner_segments(owner):
    """'JOSE T VELASQUEZ &W MARIA' -> ['JOSE T VELASQUEZ', 'MARIA VELASQUEZ'];  'A B & C D SMITH' -> two segments sharing the surname when one has no surname"""
    o = str(owner or '').upper()
    if ORG.search(o) or not o.strip(): return []
    parts = [p.strip() for p in re.split(r'\s*&W?\s*|\s+&H\s+|\s+AND\s+', o) if p.strip()]
    segs = []
    for i, p in enumerate(parts):
        w = [x for x in words(p) if x not in SUFFIX]
        if i and len([x for x in w if len(x) > 1]) <= 1 and parts:   # spouse written with first name only: borrow the first segment's surname
            base = [x for x in words(parts[0]) if x not in SUFFIX and len(x) > 1]
            if base: p = p + ' ' + base[-1]
        segs.append(p)
    return segs

def clean_name(n): return re.sub(r'\s+', ' ', EST.sub(' ', n.upper())).strip()

def run(pa, RAWDIR, add, recs, norm_addr, addr_to_folio, LEG, CLERK_URL, pdate, STATS, CASEDIR=None):
    """pa: DataFrame(FOLIO, TRUE_OWNER1-3, TRUE_MAILING_ADDR1, TRUE_MAILING_ZIP_CODE); add(folio, code, date, title, amount, ref, url, extra); recs: folio -> records"""
    files = sorted(glob.glob(f'{RAWDIR}/probate_*.csv')) if RAWDIR else []
    by = collections.defaultdict(list); seen = set(); nrows = 0; ndup = 0
    for f in files:
        for r in csv.DictReader(open(f, encoding='utf-8-sig', errors='replace')):
            nrows += 1; k = tuple(r.values())
            if k in seen: ndup += 1; continue
            seen.add(k); by[r["Clerk's File Number"].strip()].append(r)
    docs = {}
    for cfn, rs in by.items():
        r0 = rs[0]; dt_ = re.search(r'- ([A-Z]{3})$', r0['Document Type'].strip()); typ = dt_.group(1) if dt_ else r0['Document Type'][:3]
        names = []
        for r in rs:
            a, _, b = r['Party Name'].partition(' / ')
            for x in (a.strip(), b.strip()):
                if x and x not in names: names.append(x)
        dec = [clean_name(x) for x in names if EST.search(x.upper())]
        if typ == 'DCE' and not dec and names: dec = [clean_name(names[0])]
        m = CASE.search(r0['Misc Ref'].upper())
        docs[cfn] = dict(cfn=cfn, typ=typ, dtype=r0['Document Type'].strip(), date=pdate(r0['Rec Date']), names=[clean_name(x) for x in names], dec=sorted(set(dec)), case=m.group(1) if m else '',
                         misc=r0['Misc Ref'].strip(), addr=r0['Address'].strip(), legal=r0['Legal'].strip(), blk=r0['Block Number'].strip().upper(),
                         plat=(r0['Plat Book/Page'] + '/').split('/')[:2], bp=r0['Rec Book/Page'].strip())
    # ----- owner name index: frozenset(full words) of each person segment -> [(folio, initials, owner field, mail key, has estate/LE marker)] -----
    idx = collections.defaultdict(list)
    O = {}
    for f, o1, o2, o3, ma, mz in zip(pa.FOLIO, pa.TRUE_OWNER1.fillna(''), pa.TRUE_OWNER2.fillna(''), pa.TRUE_OWNER3.fillna(''), pa.TRUE_MAILING_ADDR1.fillna(''), pa.TRUE_MAILING_ZIP_CODE.fillna('')):
        O[f] = ' | '.join(x for x in (o1, o2, o3) if x)
        mk = norm_addr(ma) + '|' + str(mz)[:5]
        for o in (o1, o2, o3):
            if not o: continue
            marker = bool(re.search(r'\b(EST OF|ESTATE OF|EST|HEIRS?|DECD|DECEASED|LE)\b', str(o).upper()))
            for seg in owner_segments(o):
                full, ini = person_key(seg)
                if len(full) >= 2: idx[full].append((f, ini, o, mk, marker))
    idx2 = collections.defaultdict(list)    # owner key minus one word -> (dropped word, entry): roll 'MARIA ELENA RAMIREZ' vs decedent 'RAMIREZ MARIA E'
    for key, lst in idx.items():
        if len(key) >= 3 and len(key) <= 4:
            for w in key:
                for c in lst: idx2[key - {w}].append((w, c))
    def match_by_name(dname):
        full, ini = person_key(dname)
        if len(full) < 2 or len(full) > 5: return None
        cands = []; confirmed = set()
        for c in idx.get(full, []):
            if ini and c[1] and not (ini & c[1]): continue      # initials contradict -> a different person
            cands.append(c)
            if (ini & c[1]) or len(full) >= 3: confirmed.add(c[0])

        for w, c in idx2.get(full, []):
            if ini and w[0] in ini: cands.append(c); confirmed.add(c[0])             # decedent shows only an initial where the roll has the full middle name
        if len(full) >= 3:                                      # decedent has a full middle name where the roll has only its initial
            for drop in full:
                for c in idx.get(full - {drop}, []):
                    if drop[0] in c[1]: cands.append(c); confirmed.add(c[0])
        if not cands: return None
        folios = sorted({c[0] for c in cands})
        if len(folios) > 1 and len({(re.sub(r'\W', '', c[2]), c[3]) for c in cands}) > 1: return ('ambiguous', len(folios))
        marker = any(c[4] for c in cands)
        conf = 'high' if (marker or confirmed) else 'medium'
        return ('ok', folios, conf, marker)
    def legal_match(d):
        try: pb, pg = int(d['plat'][0] or 0), int(d['plat'][1] or 0)
        except ValueError: return []
        lot = re.search(r'\bLOTS?\s+(\d+[A-Z]?)', d['legal'].upper())
        if not (pb and lot) or pb > 500: return []
        c = []
        for pgv in {pg, pg // 10 if pg % 10 == 0 else pg}:
            c += LEG.get((pb, pgv, lot.group(1), d['blk']), []) or (LEG.get((pb, pgv, lot.group(1), ''), []) if d['blk'] else [])
        return sorted(set(c))
    def owner_hits(folio, nm_list):
        o = O.get(folio, '').upper(); ow = set(words(o))
        for nm in nm_list:
            full, _ = person_key(nm)
            if len(full) >= 2 and full <= ow: return True
        return False

    C = collections.defaultdict(collections.Counter)   # per doc type counters
    dec_folios = collections.defaultdict(set)           # decedent word-set -> folios matched from recorded documents (corroboration for court cases)
    case_folios = collections.defaultdict(set)          # court case number -> folios (PRO Misc Ref 'CASE NO ...')
    detail = []
    def fold(folio, code, d, title, extra, url, case):
        """add a record, or fold this evidence into an existing PR/DC record from the No-Heir-Probates / Obituary outputs"""
        for r in recs.get(folio, []):
            if r[0] != code: continue
            if 'Clerk' in r[6] and 'CFN ' + d['cfn'] in r[6]: return 'dup'
            same_case = case and case.replace('-', '') in (r[4] or '').replace('-', '')
            same_dec = any(set(person_key(x)[0]) and person_key(x)[0] <= set(words(r[2] + ' ' + r[6])) for x in d['dec'])
            if same_case or same_dec or code == 'DC':
                r[6] = (r[6] + f"; also in Clerk {d['dtype']} {d.get('label', 'CFN')} {d['cfn']} ({d['date']}): {extra}")[:500]
                return 'merged'
        add(folio, code, d['date'], title, 0, case or d['cfn'], url, extra)
        return 'new'
    for cfn, d in sorted(docs.items(), key=lambda kv: kv[1]['date'] or 0):
        T = d['typ']; C[T]['documents'] += 1
        res = []   # (folio, method, confidence, decedent_matched)
        # ---- 1. property match (PRO) ----
        if T != 'DCE' and (d['addr'] or d['legal']):
            f = addr_to_folio(d['addr']) if d['addr'] else None
            if f:
                if owner_hits(f, d['names'] + d['dec']): res.append((f, 'address + party name', 'high', owner_hits(f, d['dec'])))
                else: C[T]['address matched but owner is neither party (rejected)'] += 1
            if not res:
                lf = legal_match(d)
                if len(lf) > 1: lf = [x for x in lf if owner_hits(x, d['names'])]
                if len(lf) == 1:
                    nm = owner_hits(lf[0], d['names'] + d['dec'])
                    res.append((lf[0], 'plat book/page + lot/block' + (' + party name' if nm else ''), 'high' if nm else 'medium', owner_hits(lf[0], d['dec'])))
        # ---- 2. decedent name vs owner name ----
        if not res and d['dec']:
            for dn in d['dec']:
                m = match_by_name(dn)
                if not m: continue
                if m[0] == 'ambiguous': C[T]['decedent name matches several different owners (skipped)'] += 1; continue
                _, folios, conf, marker = m
                for f in folios: res.append((f, 'decedent name vs owner name' + (' (roll already shows EST OF / LE)' if marker else ''), conf, True))
                break
        if not res:
            C[T]['unmatched'] += 1
            if T != 'DCE' and not d['dec'] and not d['addr'] and not d['legal']: C[T]['no decedent, no property (nothing to match)'] += 1
            continue
        title = {'DCE': 'Death certificate recorded', 'PAD': 'Probate & administration filed', 'PRO': 'Probate order of distribution'}.get(T, d['dtype'])
        for f, method, conf, decm in res:
            url = CLERK_URL
            base = f"CFN {d['cfn']}; {d['dtype']}; recorded {d['date']}" + (f"; OR {d['bp']}" if d['bp'] else '') + (f"; case {d['case']}" if d['case'] else '') + \
                   f"; decedent: {'; '.join(d['dec']) or 'not stated'}; match: {method} ({conf} confidence)"
            if conf == 'low': C[T]['low confidence (not flagged)'] += 1; continue
            C[T]['matched ' + conf] += 1; C[T]['matched'] += 1
            detail.append((cfn, f, T, method, conf))
            if decm:
                for dn in d['dec']: dec_folios[person_key(dn)[0]].add(f)
            if d['case']: case_folios[d['case']].add(f)
            if T == 'DCE':
                fold(f, 'DC', d, f"Owner deceased: death certificate recorded {d['date']} ({d['dec'][0] if d['dec'] else ''})", base, url, d['case'])
            else:
                fold(f, 'PR', d, f"Probate: {title}" + (f" - estate of {d['dec'][0]}" if d['dec'] else ''), base, url, d['case'])
                if decm and d['dec']: fold(f, 'DC', d, f"Owner deceased: estate of {d['dec'][0]} (probate filing)", base, url, d['case'])

    # ---------- court case lists (OCS File Date search): probate cases filed ----------
    OCS_URL = 'https://www2.miamidadeclerk.gov/ocs/'
    CT = {'ADMIN30': 'formal administration', 'SUMADMN31A': 'summary administration', 'ANCI34': 'ancillary administration', 'DWOADMIN33': 'disposition without administration',
          'ADMWDEATH': 'administration', 'CURCON37': 'curator / conservator'}
    cases = {}; ocs_files = sorted(glob.glob(f'{CASEDIR}/ocs_*.txt')) if CASEDIR else []
    ocs_rows = 0
    for f in ocs_files:
        txt = open(f, encoding='utf-8-sig', errors='replace').read()
        if not txt.strip(): continue
        for r in csv.DictReader(txt.splitlines()):
            ocs_rows += 1; lc = (r.get('local_case') or '').strip()
            if lc: cases.setdefault(lc, r)
    O_ = {'files': len(ocs_files), 'rows': ocs_rows, 'cases': len(cases)}
    if cases:
        pro = {c: [x for x in cs] for c, cs in case_folios.items()}
        oc = collections.Counter()
        for lc, r in sorted(cases.items(), key=lambda kv: pdate(kv[1].get('filing_date')) or 0):
            kind = (re.search(r'-([A-Z]{2})-', lc) or [0, ''])[1]
            if kind != 'CP': oc['skipped: ' + (kind or '?') + ' (not probate)'] += 1; continue
            oc['probate cases'] += 1
            nm = re.sub(r'^\s*IN\s+RE:?\s*', '', r.get('in_re_name') or '', flags=re.I).strip()
            nm = re.sub(r'\b(ESTATE OF|DECEASED|DEC\'?D)\b', ' ', nm, flags=re.I)
            dn = ' '.join(reversed([x.strip() for x in nm.split(',', 1)])) if ',' in nm else nm   # 'LAST, FIRST M' (order is irrelevant to the matcher)
            fd = pdate(r.get('filing_date')); res = []
            if lc in case_folios:
                for f in sorted(case_folios[lc]): res.append((f, 'case number = recorded probate document (PRO Misc Ref)', 'high'))
            else:
                m = match_by_name(dn)
                if m and m[0] == 'ambiguous': oc['name matches several different owners (skipped)'] += 1
                elif m:
                    _, folios, conf, marker = m
                    corro = person_key(dn)[0] in dec_folios and set(folios) & dec_folios[person_key(dn)[0]]
                    for f in folios:
                        if corro and f in dec_folios[person_key(dn)[0]]: res.append((f, 'decedent name vs owner name + same decedent in recorded probate/death-certificate document', 'high'))
                        else: res.append((f, 'decedent name vs owner name' + (' (roll already shows EST OF / LE)' if marker else ''), conf))
            res = [x for x in res if x[2] == 'high']     # precision: a filed case alone does not prove the decedent owned Miami-Dade property, so medium name-only matches are not flagged
            if not res: oc['unmatched or low confidence (not flagged)'] += 1; continue
            oc['matched'] += 1
            ct = r.get('case_type', '').strip(); st = (r.get('status') or '').strip()
            for f, method, conf in res:
                oc['flagged folios'] += 1
                extra = f"{r.get('in_re_name','').strip()}; case {lc} (state no. {r.get('state_case','').strip()}); filed {r.get('filing_date','').strip()}; type {ct}" + (f" ({CT[ct]})" if ct in CT else '') + \
                        f"; status {st}; section {r.get('section','').strip()}; match: {method} ({conf} confidence)"
                d_ = {'cfn': lc, 'label': 'case', 'dtype': 'OCS probate case', 'date': fd, 'dec': [clean_name(dn)]}
                fold(f, 'PR', d_, f"Probate case filed: {CT.get(ct, ct or 'case')} ({st.lower() or 'status n/a'})", extra, OCS_URL, lc)
                fold(f, 'DC', d_, f"Owner deceased: probate case filed for {clean_name(dn)}", extra, OCS_URL, lc)
        O_['by'] = dict(oc); O_['match_rate_pct_of_probate_cases'] = round(100 * oc['matched'] / oc['probate cases'], 1) if oc['probate cases'] else 0
        ds = sorted(pdate(r.get('filing_date')) for r in cases.values() if pdate(r.get('filing_date')))
        O_['filed_from'] = ds[0].isoformat() if ds else ''; O_['filed_to'] = ds[-1].isoformat() if ds else ''
        O_['source'] = OCS_URL + ' (File Date search; probate = local case -CP-, guardianship -GD- skipped)'
    S = {'files': [os.path.basename(x) for x in files], 'rows': nrows, 'duplicate_rows_dropped': ndup, 'documents': len(docs), 'by_type': {}}
    for T, c in C.items():
        dd = c['documents']; S['by_type'][T] = {**dict(c), 'match_rate_pct': round(100 * c['matched'] / dd, 1) if dd else 0}
    S['folios_flagged'] = len({x[1] for x in detail})
    dates = sorted(d['date'] for d in docs.values() if d['date'])
    S['recorded_from'] = dates[0].isoformat() if dates else ''; S['recorded_to'] = dates[-1].isoformat() if dates else ''
    S['source'] = 'https://onlineservices.miamidadeclerk.gov/officialrecords/ (PAD, PRO, DCE)'
    S['court_cases'] = O_
    STATS['clerk_probate'] = S
    return detail
