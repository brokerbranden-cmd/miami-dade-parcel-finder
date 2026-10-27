"""Unit tests for scripts/counties/broward/broward_lp.py (AcclaimWeb lis pendens / certificate of title matching). usage: python3 tests/unit_broward_lp.py"""
import os, sys, csv, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts', 'counties', 'broward'))
import broward_lp as B
fails = []
def check(ok, msg): print(('ok   ' if ok else 'FAIL ') + msg); ok or fails.append(msg)
H = ['DirectName', 'IndirectName', 'RecordDate', 'DocTypeDescription', 'InstrumentNumber', 'BookType', 'BookPage', 'DocLegalDescription', 'Consideration', 'CaseNumber']
OWN = ['MCMILLAN,PHILIP', 'LEITE,KARLUCIO G & ALINE', 'GONZALEZ,JOSE', 'GONZALEZ,JOSE', 'GONZALEZ,JOSE A', 'JUICE IN TOWN LLC', 'SMITH,JOHN', 'SMITH,JOHN R',
       'BUENO,ROSE MARIE', 'BUENO,ROSE', 'DOE,JANE', 'ROE,RICHARD']
LEG = ['ORIOLE ESTATES SEC 8 65-9 B', 'YORKVILLE 115-18 B', 'X 1-1 B', 'Y 1-2 B', 'Z 1-3 B', 'INVERWOOD CONDO', 'A 2-1 B', 'B 2-2 B',
       'HOMES IN BONAVENTURE 120-1 B', 'SUNRISE LAKES 99-1 B', 'CORAL GATE SEC 1 93-7 B LOT 5 BLK 3', 'CORAL GATE SEC 1 93-7 B LOT 6 BLK 3']
ROWS = [  # (plaintiff, defendant, legal, case) -> expected owner index or None
    ('WILMINGTON SAVINGS FUND SOCIETY', 'MCMILLAN,PHILIP', '', 'CACE-26-000001', 0, 'medium'),
    ('NEWREZ LLC', 'LEITE,KARLUCIO G', '', 'CACE-26-000002', 1, 'high'),             # middle initial agrees
    ('NEWREZ LLC', 'LEITE,ALINE', '', 'CACE-26-000003', 1, 'medium'),                # co-owner shares the surname
    ('NEWREZ LLC', 'GONZALEZ,JOSE', '', 'CACE-26-000004', None, None),               # common name -> never guessed
    ('U S BANK TRUST NATIONAL ASSN', 'JUICE IN TOWN LLC', '', 'CACE-26-000005', 5, 'high'),
    ('NEWREZ LLC', 'SMITH,JOHN Q', '', 'CACE-26-000006', None, None),                # middle initial conflicts with R; plain JOHN alone -> 1 candidate
    ('HOMES IN BONAVENTURE HOMEOWNERS ASSN INC', 'BUENO,ROSE', '', 'CONO-26-000007', 8, 'high'),   # 2 ROSE BUENOs, HOA names the community
    ('NEWREZ LLC', 'NOBODY,KNOWN', '', 'CACE-26-000008', None, None),
    ('NEWREZ LLC', 'DOE,JANE', 'CORAL GATE SEC 1 93-7 B LOT 5 BLK 3', 'CACE-26-000009', 10, 'high'),  # legal + name
    ('NEWREZ LLC', 'DOE,JANE', 'CORAL GATE SEC 1 93-7 B LOT 6 BLK 3', 'CACE-26-000010', None, None), # legal says a different owner's lot
]
d = tempfile.mkdtemp()
with open(os.path.join(d, 'LP_20261001-20261027.csv'), 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f); w.writerow(H)
    for k, (p, df_, lg, c, *_ ) in enumerate(ROWS): w.writerow([p, df_, '10/%d/2026 10:00:00 AM' % (k + 1), 'Lis Pendens', str(100 + k), 'O', '', lg, '0', c])
    w.writerow([ROWS[0][0], ROWS[0][1], '10/1/2026 10:00:00 AM', 'Lis Pendens', '100', 'O', '', '', '0', ROWS[0][3]])   # duplicate instrument (overlapping exports)
with open(os.path.join(d, 'CET_20261001-20261027.csv'), 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f); w.writerow(H)
    w.writerow(['BROWARD COUNTY CIRCUIT COURT', 'BUYER,AT SALE', '10/27/2026 11:00:00 AM', 'Certificate of Title', '900', 'O', '', 'CORAL GATE SEC 1 93-7 B LOT 5 BLK 3', '1', 'CACE-26-000009'])
    w.writerow(['BROWARD COUNTY CIRCUIT COURT', 'FNMA', '10/27/2026 11:00:00 AM', 'Certificate of Title', '901', 'O', '', 'WISTERIA COURT CONDO UNIT 17', '0', 'CACE-24-1'])
lp, cet, st, un = B.run(d, OWN, LEG)
roll = B.Roll(OWN, LEG)
for p, df_, lg, c, exp, conf in ROWS:
    i, cf, how = B.match({'DirectName': p, 'IndirectName': df_, 'DocLegalDescription': lg, 'CaseNumber': c}, roll)
    check(i == exp and cf == conf, f'{df_} [{lg or "no legal"}] -> {i} {cf} ({how}); expected {exp} {conf}')
check(st['lp_docs'] == len(ROWS), f"duplicate instrument dropped: {st['lp_docs']} docs")
check(st['matched'] + st['unmatched'] == st['lp_docs'] and st['matched'] == 6, f"counts add up: {st['matched']} matched + {st['unmatched']} unmatched")
check(st['cet_matched'] == 1 and 10 in cet, 'certificate of title matched by unique legal (lot + block); condo unit with no unit in roll legal stays unmatched')
check(10 not in lp and st['closed_by_cet'] == 1, 'certificate of title on the same case closes that lis pendens')
check(all(u['reason'] for u in un) and len(un) == st['unmatched'], 'every unmatched row carries a reason')
check(B.kind('HOLLY LAKE ASSN INC', '')[0] == 'H' and B.kind('PENNYMAC LOAN SERVICES LLC', '')[0] == 'M' and B.kind('DAVIE TOWN', '')[0] == 'G', 'plaintiff kinds')
check(B.persons('LEITE,KARLUCIO G & ALINE') == [('LEITE', 'KARLUCIO', 'G'), ('LEITE', 'ALINE', '')] and B.persons('JUICE IN TOWN LLC') == [], 'owner name parsing')
check('match medium' in B.text(lp[0][0]) and 'CACE-26-000001' in B.text(lp[0][0]), 'drawer text has case + confidence')
r2 = B.Roll(['BROWN,JULIAN EDDIE'], ['A 1-1 B'])
check(B.match({'IndirectName': 'BROWN,JULIAN ANTHONY', 'DirectName': 'X BANK'}, r2)[0] is None, 'conflicting middle initial never matches')
print(f'\n{"FAILED " + str(len(fails)) if fails else "ALL PASSED"}'); sys.exit(1 if fails else 0)
