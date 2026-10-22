#!/usr/bin/env python3
"""Estimated owner equity (Miami-Dade) from RAW/clerk_owner/<folio>.json (fetch_mortgages.py) + the PA roll.

Per parcel (current owner only):
  * owner rows = Clerk rows whose first party is the owner's name ("LAST FIRST..." / company name, whole words).
  * anchor = the owner's acquisition deed: a deed row with this folio, or the PA's last-sale book/page (OR_BK_1/OR_PG_1).
  * mortgage (MORTGAGE - MOR, DEED WITH MORTGAGE, MORTGAGE WITH RELEASE, ...) belongs to the parcel when it carries this folio,
    or was recorded within 5 days of the anchor deed in the same book (purchase money), or references (orig book/page) a
    mortgage already linked (modifications, partial claims). Folio-less refinances are linked only when the owner owns
    just this one parcel in the roll and the search was not capped ("medium" confidence).
  * mortgages recorded before the acquisition (minus 60 days) are ignored.
  * open = no SATISFACTION OF MORTGAGE / RELEASE / PARTIAL RELEASE OF MORTGAGE (full) whose orig book/page or orig CFN
    points to it. Assignments (AMO) update the lender shown.
  * amount = intangible tax / 0.002 when present (FL intangible tax is 2 mills on the note), else the consideration.
    Amounts > 3x max(just value, deed price) are treated as unknown (bad index data).
  * balance: first-lien institutional loans amortized as 30-yr fixed at the Freddie Mac PMMS annual average for the
    origination year; private-party notes, subordinate/partial-claim mortgages (reference another mortgage) and
    HELOC-type lenders = full amount.
  * equity = PA just (market) value - sum(open balances). Estimate only.
writes data/equity.json.gz
"""
import json, os, re, sys, glob, gzip, time
from datetime import date, datetime
import pyarrow.parquet as pq

RAW = os.environ.get('RAW', '/workspace/raw')
OUT = sys.argv[1] if len(sys.argv) > 1 else 'data'
PMMS = {1990: 10.13, 1991: 9.25, 1992: 8.39, 1993: 7.31, 1994: 8.38, 1995: 7.93, 1996: 7.81, 1997: 7.60, 1998: 6.94, 1999: 7.44,
        2000: 8.05, 2001: 6.97, 2002: 6.54, 2003: 5.83, 2004: 5.84, 2005: 5.87, 2006: 6.41, 2007: 6.34, 2008: 6.03, 2009: 5.04,
        2010: 4.69, 2011: 4.45, 2012: 3.66, 2013: 3.98, 2014: 4.17, 2015: 3.85, 2016: 3.65, 2017: 3.99, 2018: 4.54, 2019: 3.94,
        2020: 3.11, 2021: 2.96, 2022: 5.34, 2023: 6.81, 2024: 6.72, 2025: 6.62, 2026: 6.30}
MTG = re.compile(r'^(MORTGAGE - MOR|DEED WITH MORTGAGE|MORTGAGE WITH RELEASE|ANY PROPERTY TRANSFER AND MORTGAGE|MODIFICATION OF MORTGAGE|MORTGAGE MODIFICATION)')
MODIF = re.compile(r'MODIF')
SAT = re.compile(r'^(SATISFACTION OF MORTGAGE|RELEASE - REL|RELEASE OF MORTGAGE)')
ASG = re.compile(r'^ASSIGNMENT OF MORTGAGE')
DEED = re.compile(r'DEED')
ORGW = re.compile(r'\b(LLC|INC|CORP|BANK|N A|NA|ASSN|ASSOCIATION|MORTGAGE|LENDING|LOAN|FINANCIAL|FUNDING|CREDIT|CAPITAL|SERVICING|TRUST|FSB|HOME|HOMES|FEDERAL|SAVINGS|UNION|COMPANY|CO|LP|LTD|FUND|SECRETARY|URBAN|HOUSING|COUNTY|STATE|SYSTEMS)\b')
HELOC = re.compile(r'CREDIT UNION|EQUITY|HELOC|CREDIT LINE')
SUBORD = re.compile(r'HOUSING AND URBAN|SECRETARY OF HOUSING|MIAMI DADE COUNTY|CITY OF|FLORIDA HOUSING|HFA|COUNTY')

def d8(s):
    try: return datetime.strptime(str(s).split(' ')[0], '%m/%d/%Y').date()
    except Exception: return None

def norm(s): return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9 ]', ' ', str(s or '').upper())).strip()

def balance(amt, start, rate, today):
    r = rate / 100 / 12; n = 360
    k = (today.year - start.year) * 12 + today.month - start.month
    if k >= n: return 0
    if k <= 0: return amt
    pay = amt * r / (1 - (1 + r) ** -n)
    return max(0, amt * (1 + r) ** k - pay * ((1 + r) ** k - 1) / r)

def lender_name(s):
    s = norm(s)
    if 'MORTGAGE ELECTRONIC REGISTRATION' in s: return 'MERS (lender nominee)'
    return s.title()[:60]

def main():
    today = date.today()
    pa = pq.read_table(os.path.join(RAW, 'pagis.parquet'), columns=['FOLIO', 'TRUE_OWNER1', 'DOS_1', 'PRICE_1', 'OR_BK_1', 'OR_PG_1', 'TOTAL_VAL_CUR']).to_pandas().drop_duplicates('FOLIO')
    owners_n = pa['TRUE_OWNER1'].value_counts().to_dict()
    pa = pa.set_index('FOLIO')
    rows, stats = [], {'checked': 0, 'capped': 0, 'free_clear': 0, 'with_open': 0, 'open_loans': 0, 'medium': 0, 'unknown_amount': 0}
    for fp in glob.glob(os.path.join(RAW, 'clerk_owner', '*.json')):
        f = os.path.basename(fp)[:-5]
        if not re.fullmatch(r'\d{13}', f) or f not in pa.index: continue
        try: J = json.load(open(fp))
        except Exception: continue
        p = pa.loc[f]; fol = int(f); term = J['term']
        want = norm(term[1] + ' ' + term[2]) if term[0] == 'person' else norm(term[1])
        mine = [m for m in J['models'] if (norm(m.get('firsT_PARTY')) + ' ').startswith(want + ' ')]
        dos = d8(datetime.strptime(str(int(p.DOS_1)), '%Y%m%d').strftime('%m/%d/%Y')) if p.DOS_1 == p.DOS_1 and p.DOS_1 else None
        value = float(p.TOTAL_VAL_CUR or 0); price = float(p.PRICE_1 or 0) if p.PRICE_1 == p.PRICE_1 else 0
        bk1 = int(p.OR_BK_1) if p.OR_BK_1 == p.OR_BK_1 and p.OR_BK_1 else 0; pg1 = int(p.OR_PG_1) if p.OR_PG_1 == p.OR_PG_1 and p.OR_PG_1 else 0
        anchors = [m for m in mine if DEED.search(m['doC_TYPE'] or '') and not MTG.search(m['doC_TYPE']) and (m['foliO_NUMBER'] == fol or (bk1 and m['reC_BOOK'] == bk1 and m['reC_PAGE'] == pg1))]
        single = owners_n.get(p.TRUE_OWNER1, 0) == 1 and not J.get('capped')
        stats['checked'] += 1; stats['capped'] += bool(J.get('capped'))
        floor = None
        if dos: floor = date.fromordinal(dos.toordinal() - 60)
        linked, conf = {}, 'high'
        def key(m): return (m['reC_BOOK'], m['reC_PAGE'])
        mtgs = [m for m in mine if MTG.search(m['doC_TYPE'] or '') and (floor is None or (d8(m['reC_DATE']) or today) >= floor)]
        for m in mtgs:
            rd = d8(m['reC_DATE']); ok = m['foliO_NUMBER'] == fol
            for a in anchors:
                ad = d8(a['reC_DATE'])
                if rd and ad and abs((rd - ad).days) <= 5 and m['reC_BOOK'] == a['reC_BOOK'] and abs(m['reC_PAGE'] - a['reC_PAGE']) <= 60: ok = True
            if ok: linked[key(m)] = m
        for _ in range(3):
            for m in mtgs:
                if key(m) not in linked and (m['oriG_REC_BOOK'], m['oriG_REC_PAGE']) in linked: linked[key(m)] = m
        if single:
            for m in mtgs:
                if key(m) not in linked and not m['foliO_NUMBER']: linked[key(m)] = m; conf = 'medium'
        sats = set((m['oriG_REC_BOOK'], m['oriG_REC_PAGE']) for m in mine if SAT.search(m['doC_TYPE'] or '') and m['oriG_REC_BOOK'])
        asg = {}
        for m in sorted([m for m in mine if ASG.search(m['doC_TYPE'] or '')], key=lambda m: d8(m['reC_DATE']) or today):
            asg[(m['oriG_REC_BOOK'], m['oriG_REC_PAGE'])] = m['seconD_PARTY']
        loans = []
        for k, m in linked.items():
            if MODIF.search(m['doC_TYPE']) or k in sats: continue
            if (m['oriG_REC_BOOK'], m['oriG_REC_PAGE']) in sats: continue
            rd = d8(m['reC_DATE']) or today
            amt = (m['intangible'] or 0) / 0.002 if (m['intangible'] or 0) > 0 else float(m['consideratioN_1'] or 0)
            lender = m['seconD_PARTY'] or ''
            cur = asg.get(k, '')
            unknown = amt <= 100 or amt > 3 * max(value, price, 1)
            sub = bool(m['oriG_REC_BOOK']) or bool(SUBORD.search(norm(lender)))
            private = not ORGW.search(norm(lender))
            heloc = bool(HELOC.search(norm(lender)))
            kind = 'private' if private else 'subordinate' if sub else 'heloc' if heloc else 'first'
            if unknown: bal = None; stats['unknown_amount'] += 1
            elif kind == 'first': bal = balance(amt, rd, PMMS.get(rd.year, PMMS[2026] if rd.year > 2026 else PMMS[1990]), today)
            else: bal = amt
            loans.append([rd.strftime('%Y%m%d'), round(amt) if not unknown else 0, lender_name(cur or lender), kind, None if bal is None else round(bal), m['clerk_File']])
        loans.sort(reverse=True)
        # dedupe re-recorded copies (same lender + amount within 30 days)
        ded = []
        for l in loans:
            if any(l[1] and l[1] == x[1] and l[2] == x[2] and abs((datetime.strptime(l[0], '%Y%m%d') - datetime.strptime(x[0], '%Y%m%d')).days) <= 30 for x in ded): continue
            ded.append(l)
        # refinance rule: an older first-lien loan is assumed paid off when a later first-lien loan of >= 70% of its amount
        # was recorded (satisfactions of refinanced loans are often indexed under another name variant or not yet recorded)
        loans, refi = [], 0
        for l in ded:
            if l[3] == 'first' and l[1] and any(x[3] == 'first' and x[1] >= 0.7 * l[1] and x[0] > l[0] for x in loans): refi += 1; continue
            loans.append(l)
        known = [l[4] for l in loans if l[4] is not None]
        bal = round(sum(known)); n = len(loans)
        if n: stats['with_open'] += 1; stats['open_loans'] += n
        elif not J.get('capped'): stats['free_clear'] += 1
        if conf == 'medium' and n: stats['medium'] += 1
        eq = round(value - bal) if value else None
        pct = round(100 * eq / value) if value else None
        flags = ('c' if J.get('capped') else '') + ('m' if conf == 'medium' and n else '') + ('u' if any(l[4] is None for l in loans) else '') + ('r' if refi else '')
        lender = loans[0][2] if loans else ''
        rows.append([f, bal, n, lender, round(value), eq, pct, flags, J['pulled'][:10], loans[:6]])
    meta = {'built': datetime.now().strftime('%Y-%m-%d %H:%M ET'), 'county': 'Miami-Dade', 'stats': stats,
            'cols': ['folio', 'estBal', 'nOpen', 'lender', 'value', 'estEq', 'eqPct', 'flags', 'checked', 'loans'],
            'loanCols': ['recDate', 'amount', 'lender', 'kind', 'estBal', 'cfn'],
            'rates': 'Freddie Mac PMMS 30-yr fixed annual average by origination year (2025-26 approximate)',
            'source': 'https://onlineservices.miamidadeclerk.gov/officialrecords/ (public Name/Document search, current owner from acquisition date)',
            'rule': 'Estimate only: PA just value minus estimated balances of recorded mortgages with no recorded satisfaction/release. flags: c=owner search capped at 500 rows (coverage incomplete), m=folio-less refinance linked by owner name, u=a loan amount could not be read (not in the balance), r=older loan(s) assumed refinanced (no satisfaction found but a later first loan of >=70% of the amount exists)'}
    os.makedirs(OUT, exist_ok=True)
    json.dump({'meta': meta, 'rows': rows}, gzip.open(os.path.join(OUT, 'equity.json.gz'), 'wt'), separators=(',', ':'))
    print('equity', json.dumps(stats), 'rows', len(rows))

if __name__ == '__main__':
    main()
