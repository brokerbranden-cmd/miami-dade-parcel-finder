#!/usr/bin/env python3
"""Clerk / auction signals the cards and filters use (written to data/signals.json.gz, loaded at start):
  pf  open pre-foreclosure: lis pendens matched to a folio (scripts/build_distress.py -> data/distress.json.gz) that show NO later
      closing event in the data we hold:
        - a cancellation / dismissal / certificate of title in the Clerk exports (raw/lp_downloads/{clp,dis,cot}_*.csv, RAW/clerk/CLP|COT/*.json)
          linked to the lis pendens by case number or by the original book/page
        - a foreclosure sale already held (RAW/auctions.json status sold / canceled-final) for the same case
        - a recorded transfer of the parcel (PA roll DOS_1..3) after the lis pendens date
  pb  probate filed: Clerk probate filings (PAD / PRO / DCE / probate case) matched to the parcel, high or medium confidence only
  au  scheduled auctions with the plaintiff's max bid (RAW/auctions.json from scripts/fetch_auctions.py)
usage: RAW=/workspace/raw build_signals.py data
"""
import csv, glob, gzip, json, os, re, sys, collections, datetime as dt
import pandas as pd

RAW = os.environ.get('RAW', '/workspace/raw'); OUT = sys.argv[1] if len(sys.argv) > 1 else 'data'
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = json.load(gzip.open(os.path.join(OUT, 'distress.json.gz')))
day = lambda s: int(str(s).replace('-', '')[:8]) if s else 0
case_key = lambda c: re.sub(r'[^0-9A-Z]', '', re.sub(r'-\d\d$', '', (c or '').upper().strip()))

# ---- closing events from the Clerk (whatever exports / cached searches exist) ----
closed_case, closed_bp, n_close = {}, {}, collections.Counter()
for kind in ('clp', 'dis', 'cot'):
    for f in glob.glob(f'{HERE}/raw/lp_downloads/{kind}_*.csv'):
        for r in csv.DictReader(open(f, encoding='utf-8-sig', errors='replace')):
            d = day(pd.to_datetime(r.get('Rec Date', ''), errors='coerce').strftime('%Y%m%d') if r.get('Rec Date') else '')
            ck = case_key((r.get('Misc Ref') or '').split(' ')[0])
            if ck: closed_case[ck] = max(closed_case.get(ck, 0), d); n_close[kind] += 1
for code in ('CLP', 'COT'):
    for f in glob.glob(f'{RAW}/clerk/{code}/*.json'):
        for m in json.load(open(f)).get('models', []):
            d = day(pd.to_datetime(m.get('reC_DATE'), errors='coerce').strftime('%Y%m%d')) if m.get('reC_DATE') else 0
            if m.get('oriG_REC_BOOK'): closed_bp[(int(m['oriG_REC_BOOK']), int(m['oriG_REC_PAGE']))] = d
            ck = case_key(m.get('casE_NUM') or (m.get('misC_REF') or '').split(' ')[0])
            if ck: closed_case[ck] = max(closed_case.get(ck, 0), d)
            n_close[code.lower()] += 1
# certificates of title matched to parcels by build_distress.py (CTI exports carry no case number): folio -> [date, cfn, how]
COT = {f: [day(v[0]), v[1], v[2]] for f, v in (json.load(open(f'{RAW}/cot_matches.json')).items() if os.path.exists(f'{RAW}/cot_matches.json') else [])}
# ---- auctions ----
AU = json.load(open(f'{RAW}/auctions.json'))
sold_case = {}
for it in AU['items']:
    stt = (it.get('status') or '').lower()
    if it.get('type', '').upper().startswith('FORECLOS') and re.search(r'sold|canceled per|cancelled per|bankruptcy', stt) is None and stt != 'scheduled':
        pass
    if re.search(r'sold', stt): sold_case[case_key(it['case'])] = day(dt.datetime.strptime(it['date'], '%m/%d/%Y').strftime('%Y%m%d'))
# ---- roll transfers ----
roll = pd.read_parquet(f'{RAW}/pagis.parquet', columns=['FOLIO', 'DOS_1', 'DOS_2', 'DOS_3'])
roll['FOLIO'] = roll.FOLIO.astype(str).str.zfill(13)
lastsale = dict(zip(roll.FOLIO, roll[['DOS_1', 'DOS_2', 'DOS_3']].apply(pd.to_numeric, errors='coerce').max(axis=1).fillna(0).astype(int)))
in_roll = set(roll.FOLIO)
# ---- pre-foreclosure ----
pf, why_out = [], collections.Counter(); lp_days = []
for folio, recs in DIST['recs'].items():
    best = None
    for r in recs:
        if r[0] != 'LP': continue
        code, date, title, amt, ref, url, extra = r[:7]
        d = day(date); lp_days.append(d)
        cfn = (re.search(r'CFN ([\d ]+R \d+)', extra) or [0, ''])[1].replace(' ', '')
        conf = 'H' if '(high confidence)' in extra else 'M'
        ck = case_key(ref if '-' in (ref or '') else '')
        bp = re.search(r'OR (\d+)/(\d+)', extra)
        if ck and closed_case.get(ck, 0) >= d: why_out['cancelled / dismissed / certificate of title'] += 1; continue
        if bp and (int(bp[1]), int(bp[2])) in closed_bp: why_out['cancelled (book/page)'] += 1; continue
        if COT.get(folio, [0])[0] >= d: why_out['certificate of title (parcel)'] += 1; continue
        if ck and sold_case.get(ck, 0) >= d: why_out['foreclosure sale held'] += 1; continue
        if lastsale.get(folio, 0) > d: why_out['parcel transferred after the lis pendens'] += 1; continue
        kind = 'H' if 'HOA' in title else 'M' if 'Mortgage' in title else 'O'
        row = [folio, d, cfn, ref if '-' in (ref or '') else '', conf, kind]
        if not best or d > best[1]: best = row
    if best: pf.append(best)
# ---- probate ----
PBT = [('PRO', r'order of distribution'), ('PAD', r'Probate & administration'), ('DCE', r'death certificate recorded'), ('CP', r'probate case filed|Probate case filed')]
pb = []
for folio, recs in DIST['recs'].items():
    best = None
    for r in recs:
        if r[0] not in ('PR', 'DC'): continue
        m = re.search(r'\((high|medium) confidence\)', r[6] or '')
        if not m: continue                       # obituary / unknown-heir notices carry no Clerk match confidence
        t = next((k for k, rx in PBT if re.search(rx, r[2], re.I)), None)
        if not t: continue
        cfn = (re.search(r'CFN ([\d ]+R \d+)', r[6]) or [0, ''])[1].replace(' ', '') or (r[4] or '')
        row = [folio, day(r[1]), t, cfn, 'H' if m[1] == 'high' else 'M', (r[2].split('(')[1].rstrip(')') if t == 'CP' and '(' in r[2] else '')]
        if not best or (row[4], row[1]) > (best[4] if best[4] != 'H' else 'Z', best[1]) or (row[4] == 'H' and best[4] == 'M'): best = row
    if best: pb.append(best)
# ---- auctions with max bid ----
money = lambda s: round(float(re.sub(r'[^\d.]', '', s)), 2) if s and re.search(r'\d', s) else 0
au, au_out = [], []
for it in AU['items']:
    if it.get('status') != 'scheduled' or not it.get('folio'): continue
    adate = day(dt.datetime.strptime(it['date'], '%m/%d/%Y').strftime('%Y%m%d')); ct = COT.get(it['folio'].zfill(13))
    # sale already ended in a certificate of title: CTI recorded on/after the sale date, or within 180 days before it (stale listing)
    if ct and it['type'].upper().startswith('FORE') and ct[0] >= int((dt.datetime.strptime(str(adate), '%Y%m%d') - dt.timedelta(days=180)).strftime('%Y%m%d')):
        au_out.append([it['folio'].zfill(13), adate, it['case'], ct[0], ct[1]]); continue
    mb = it.get('max_bid', None)
    au.append([it['folio'].zfill(13), day(dt.datetime.strptime(it['date'], '%m/%d/%Y').strftime('%Y%m%d')), 'F' if it['type'].upper().startswith('FORE') else 'T',
               it['case'], money(it.get('judgment')), money(it.get('opening_bid')), money(mb) if mb else 0, 1 if (mb or '').strip().lower() == 'hidden' else (-1 if mb is None else 0)])
lp_days = sorted(x for x in lp_days if x)
meta = {'built': dt.datetime.now().strftime('%Y-%m-%d %H:%M ET'), 'distressBuilt': DIST.get('built'), 'auctionsPulled': AU.get('pulled'),
        'pf': {'n': len(pf), 'from': lp_days[0] if lp_days else 0, 'to': lp_days[-1] if lp_days else 0, 'excluded': dict(why_out), 'closing_docs': dict(n_close),
               'rule': 'Lis pendens matched to the parcel with no later cancellation, dismissal or certificate of title in the Clerk files we hold, no foreclosure sale held for the case, and no recorded transfer of the parcel since'},
        'pb': {'n': len(pb), 'high': sum(r[4] == 'H' for r in pb), 'medium': sum(r[4] == 'M' for r in pb)},
        'ct': {'n': len(COT), 'auctions_removed': len(au_out), 'rule': 'Clerk CERTIFICATE OF TITLE - CTI matched to the parcel (plat/lot/block, condo book/page + unit or address): closes lis pendens recorded on or before it and scheduled foreclosure sales within 180 days after it'},
        'au': {'n': len(au), 'maxBidShown': sum(r[6] > 0 for r in au), 'hidden': sum(r[7] == 1 for r in au)}}
json.dump({'meta': meta, 'pf': pf, 'pb': pb, 'au': au, 'ct': sorted([f, v[0], v[1]] for f, v in COT.items()), 'auOut': au_out}, gzip.open(os.path.join(OUT, 'signals.json.gz'), 'wt'), separators=(',', ':'))
print(json.dumps(meta, indent=1))
