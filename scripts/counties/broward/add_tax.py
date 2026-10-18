"""Broward tax-delinquent layer: Broward County Tax Collector public reports (county-taxes.net/broward) -> parcel packs, no full rebuild (data/broward only).
Adds to each Broward main/condo pack: txy (uint8 delinquent tax years), txo (uint16 oldest unpaid year), txb (uint32 balance, whole $), txf (uint8 flags), txd (uint16 next tax-deed sale, days since 1900-01-01),
and to each detail pack the string column taxs (drawer detail). Folds tax delinquency into dscore / dsig / vscore / vsig (idempotent) and writes meta.json -> tax + data/broward/tax-audit.json.
  txf bits: 1 = outstanding investor certificate (Issued / Purchased / Transferred)   2 = county-held certificate (buyer BROWARD COUNTY)   16 = 3+ delinquent years with certificate
            32 = tax-deed auction scheduled (on/after the as-of date)   64 = tax-deed application on file (Applied / Certified), auction or not

INPUTS ($RAW/broward/tax/, see scripts/counties/broward/TAX_REFRESH.md)
  broward_unpaid_real_estate_2023_2025.csv   unpaid accounts, Tax Yr 2023-2025, Balance Amount, Cert Status, Deed Status. Rows with a blank Account Number are report subtotals ('Grand Total' + 16 status subtotals): dropped.
  broward_unpaid_tax_certificates.csv        certificates on unpaid accounts, Tax Yr back to 1998 (Cert Buyer, Cert Status, Redemption Amt / Unpaid Tax when present)
  broward_tax_deed_auction_<date>.csv        scheduled tax-deed sales (Account Number = folio, Deed Sale Date, Applicant)
  broward_prior_3yr_unpaid.csv               small Boca-only sample (account-level balance); unioned: used for the parcel balance only when the account has no balance rows in the 2023-2025 report
  broward_unpaid_real_estate.csv             NOT used (old 2014-2017 report, mostly 'Paid In Full')
MATCH   Account Number = the 12-character Broward folio with dashes (474119-01-0014 -> 474119010014; condo 494330-BE-0390 -> 494330BE0390), upper-cased; same key as the packs.
DELINQUENT YEAR (account, tax year), tax year <= as-of year - 1 (2025; the 2026 bills are mailed Nov 1 and are not delinquent until Apr 1, 2027):
  * listed in the 2023-2025 unpaid report (its Balance Amount), OR
  * a certificate row that is still live: Cert Status Issued / Purchased / Transferred (outstanding), Surrendered (holder surrendered it to apply for a tax deed: the year is still unpaid), or Redeemed with
    a tax deed Applied / Certified (the certificate was redeemed into the deed process; year still unpaid). Redeemed with no deed, Canceled and Deleted certificates are paid / void: ignored. Deed 'Paid Off': ignored.
  Balance of a year = report Balance Amount; else the certificate row's Redemption Amt / Unpaid Tax; else unknown (0, counted in the audit: older certificate-only years carry no amount in the export).
Usage: python3 scripts/counties/broward/add_tax.py [data/broward] [--asof 2026-10-18] [--dry]"""
import argparse, csv, datetime as dt, glob, gzip, json, os, re, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument('out', nargs='?', default=os.path.join(HERE, '..', '..', '..', 'data', 'broward')); ap.add_argument('--asof', default='2026-10-18'); ap.add_argument('--dry', action='store_true')
A = ap.parse_args()
TD = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'broward', 'tax')
ASOF = dt.date.fromisoformat(A.asof); CUR = ASOF.year; LAST = CUR - 1; DAY0 = dt.date(1900, 1, 1)
def rd(p): return list(csv.DictReader(open(p, newline='', encoding='utf-8-sig')))
def num(s):
    try: return round(float(str(s).replace(',', '').replace('$', '')), 2)
    except Exception: return 0.0
nf = lambda s: re.sub(r'[^0-9A-Za-z]', '', str(s or '')).upper()
def pdate(s):
    for f in ('%m/%d/%Y', '%Y-%m-%d'):
        try: return dt.datetime.strptime(s.strip(), f).date()
        except Exception: pass
    return None
def read_pack(path):
    raw = gzip.decompress(open(path, 'rb').read()); hl = int.from_bytes(raw[:4], 'little'); h = json.loads(raw[4:4 + hl]); return h, raw[4 + hl:]
meta_p = os.path.join(A.out, 'meta.json'); meta = json.load(open(meta_p))
pack_folios = {}
for p in meta['packs']:
    h, body = read_pack(os.path.join(A.out, p['files'][0])); fc = next(c for c in h['cols'] if c['name'] == 'folio'); pack_folios[p['name']] = body[fc['offset']:fc['offset'] + fc['bytes']].decode().split('\n')
in_pack = {f for v in pack_folios.values() for f in v}
Y = {}      # (folio, yr) -> dict(bal, cert, buyer, status, deed, src)
audit = {'files': {}}
# ---- 2023-2025 unpaid report
re_rows = rd(os.path.join(TD, 'broward_unpaid_real_estate_2023_2025.csv')); keep = [r for r in re_rows if r['Account Number'].strip()]
audit['files']['unpaid_real_estate_2023_2025'] = {'rows': len(re_rows), 'subtotal_rows_dropped': len(re_rows) - len(keep), 'rows_used': len(keep), 'accounts': len({r['Account Number'] for r in keep})}
owner = {}
for r in keep:
    if r['Account Status'].strip().lower() != 'unpaid' or not r['Tax Yr'].isdigit(): continue
    fo, yr = nf(r['Account Number']), int(r['Tax Yr'])
    if yr > LAST: continue
    d = Y.setdefault((fo, yr), {'bal': 0.0, 'cert': '', 'buyer': '', 'status': '', 'deed': '', 'src': 're'}); d['bal'] += num(r['Balance Amount']); d['deed'] = r['Deed Status'].strip(); d['rstatus'] = r['Cert Status'].strip()
    owner.setdefault(fo, (r['Owner Name'].strip(), r['Billing Address'].strip()))
# ---- certificates
OUT = {'Issued', 'Purchased', 'Transferred'}
crt = rd(os.path.join(TD, 'broward_unpaid_tax_certificates.csv')); cstat = {}; added = 0; ignored = {}
for r in crt:
    fo = nf(r['Account Number']); yr = int(r['Tax Yr']) if r['Tax Yr'].isdigit() else 0; st = r['Cert Status'].strip(); dd = r['Deed Status'].strip()
    if not fo or not yr or yr > LAST: continue
    owner.setdefault(fo, (r['Billing Address Name'].strip(), r['Billing Address'].strip()))
    live = (st in OUT or st == 'Surrendered' or (st == 'Redeemed' and ('Applied' in dd or 'Certified' in dd))) and dd != 'Paid Off'
    amt = num(r['Redemption Amt']) or num(r['Unpaid Tax'])
    if (fo, yr) in Y:
        d = Y[(fo, yr)]; d['cert'] = r['Cert #'].strip(); d['buyer'] = r['Cert Buyer'].strip(); d['status'] = st
        if not d['deed'] or d['deed'] == '-- None --': d['deed'] = dd
        if not d['bal']: d['bal'] = amt
    elif live:
        Y[(fo, yr)] = {'bal': amt, 'cert': r['Cert #'].strip(), 'buyer': r['Cert Buyer'].strip(), 'status': st, 'deed': dd, 'src': 'cert'}; added += 1
    else: ignored[st] = ignored.get(st, 0) + 1
audit['files']['unpaid_tax_certificates'] = {'rows': len(crt), 'accounts': len({nf(r['Account Number']) for r in crt}), 'years_added_cert_only': added, 'rows_ignored_paid_or_void_by_status': ignored}
# ---- prior 3-yr sample
prior = {}
pf = os.path.join(TD, 'broward_prior_3yr_unpaid.csv')
if os.path.exists(pf):
    for r in rd(pf):
        if r['Account Number'].strip(): prior[nf(r['Account Number'])] = prior.get(nf(r['Account Number']), 0) + num(r['Balance Amount'])
    audit['files']['prior_3yr_unpaid'] = {'accounts': len(prior)}
# ---- tax-deed auctions
auc = {}; arows = 0
for f in sorted(glob.glob(os.path.join(TD, 'broward_tax_deed_auction_*.csv'))):
    for r in rd(f):
        arows += 1; d = pdate(r['Deed Sale Date']); fo = nf(r['Account Number'])
        if not fo or not d or d < ASOF: continue
        if fo not in auc or d < auc[fo]['date']: auc[fo] = {'date': d, 'applicant': r['Applicant'].strip(), 'app': r['Deed Application #'].strip(), 'yr': r['Tax Yr'].strip(), 'status': r['Deed Status'].strip()}
audit['files']['tax_deed_auctions'] = {'rows': arows, 'upcoming_accounts': len(auc), 'dates': sorted({str(v['date']) for v in auc.values()})}
# ---- aggregate per folio
agg = {}
for (fo, yr), d in Y.items():
    g = agg.setdefault(fo, {'yrs': {}}); g['yrs'][yr] = d
for fo in auc: agg.setdefault(fo, {'yrs': {}})
for fo, g in agg.items():
    ys = sorted(g['yrs']); bal = round(sum(d['bal'] for d in g['yrs'].values()), 2); unk = sum(1 for d in g['yrs'].values() if not d['bal'])
    if fo in prior and (fo not in {k[0] for k, d in Y.items() if d['src'] == 're'}): bal = max(bal, round(prior[fo], 2))
    out = [y for y in ys if g['yrs'][y]['status'] in OUT]; county = [y for y in out if 'BROWARD COUNTY' in g['yrs'][y]['buyer'].upper()]
    deed = any(('Applied' in d['deed'] or 'Certified' in d['deed']) for d in g['yrs'].values())
    fl = (1 if out else 0) | (2 if county else 0) | (16 if len(out) >= 3 else 0) | (32 if fo in auc else 0) | (64 if (deed or fo in auc) else 0)
    g.update(n=len(ys), old=ys[0] if ys else 0, bal=bal, fl=fl, unk=unk, ys=ys)
Din = {fo: g for fo, g in agg.items() if g['n'] > 0 and fo in in_pack}
matched_cert = len({nf(r['Account Number']) for r in crt} & in_pack); tot_cert = len({nf(r['Account Number']) for r in crt})
matched_re = len({nf(r['Account Number']) for r in keep} & in_pack); tot_re = len({nf(r['Account Number']) for r in keep})
st = {'asof': A.asof, 'delinquent_cutoff_year': LAST,
      'match': {'certificate_accounts': [matched_cert, tot_cert, round(matched_cert / tot_cert, 4)], 'real_estate_accounts': [matched_re, tot_re, round(matched_re / tot_re, 4)],
                'auction_accounts': [len(set(auc) & in_pack), len(auc)], 'prior_accounts': [len(set(prior) & in_pack), len(prior)],
                'unmatched_sample': sorted(({nf(r['Account Number']) for r in crt} | {nf(r['Account Number']) for r in keep}) - in_pack)[:12]},
      'delinquent_parcels': len(Din), 'delinquent_2plus': sum(1 for g in Din.values() if g['n'] >= 2), 'delinquent_3plus': sum(1 for g in Din.values() if g['n'] >= 3), 'delinquent_5plus': sum(1 for g in Din.values() if g['n'] >= 5),
      'with_certificate': sum(1 for g in Din.values() if g['fl'] & 1), 'county_held': sum(1 for g in Din.values() if g['fl'] & 2), 'deed_applied': sum(1 for g in Din.values() if g['fl'] & 64),
      'deed_auction_upcoming': sum(1 for fo in auc if fo in in_pack), 'parcels_with_unknown_year_balance': sum(1 for g in Din.values() if g['unk']),
      'total_balance': round(sum(g['bal'] for g in Din.values()), 2), 'total_balance_2plus': round(sum(g['bal'] for g in Din.values() if g['n'] >= 2), 2), 'balance_ge_10k': sum(1 for g in Din.values() if g['bal'] >= 10000),
      'oldest_year_min': min((g['old'] for g in Din.values()), default=0), 'auction_parcels_without_delinquent_year_rows': sum(1 for fo in auc if fo in in_pack and agg[fo]['n'] == 0)}
audit['stats'] = st
print(json.dumps(audit, indent=1, default=str)[:5000])
if A.dry: sys.exit(0)
# ---- patch
def fs(s): return str(s).replace('\n', ' ').replace('¦', '/').replace('~', '-')
def tax_str(fo):
    g = agg.get(fo)
    if not g: return ''
    o = owner.get(fo, ('', '')); it = [f'o~{fs(o[0])}~{fs(o[1])}']
    for y in g['ys']: d = g['yrs'][y]; it.append(f"y~{y}~{d['bal']:.2f}~{d['cert']}~{fs(d['buyer'])}~{fs(d['status'])}")
    if fo in auc: a = auc[fo]; it.append(f"d~{a['date'].isoformat()}~{fs(a['applicant'])}~{a['app']}~{a['yr']}")
    it.append('a~' + fo); return '¦'.join(it)
DT = {'uint8': np.uint8, 'uint16': np.uint16, 'uint32': np.uint32}
def getcol(path, name):
    h, body = read_pack(path); c = next((c for c in h['cols'] if c['name'] == name), None)
    return None if c is None else np.frombuffer(body[c['offset']:c['offset'] + c['bytes']], dtype=DT[c['type']]).copy()
def patch(path, newcols):
    h, body = read_pack(path); names = {n for n, _, _ in newcols}; parts = []; off = 0; cols = []
    for c in h['cols']:
        if c['name'] in names: continue
        b = body[c['offset']:c['offset'] + c['bytes']]; cols.append({**c, 'offset': off}); parts.append(b); off += len(b); pad = (-off) % 4
        if pad: parts.append(b'\0' * pad); off += pad
    for name, typ, b in newcols:
        cols.append({'name': name, 'type': typ, 'offset': off, 'bytes': len(b)}); parts.append(b); off += len(b); pad = (-off) % 4
        if pad: parts.append(b'\0' * pad); off += pad
    hdr = json.dumps({'n': h['n'], 'cols': cols}, separators=(',', ':')).encode(); hdr += b' ' * ((-(4 + len(hdr))) % 4)
    out = gzip.compress(len(hdr).to_bytes(4, 'little') + hdr + b''.join(parts), 9, mtime=0); open(path, 'wb').write(out); return len(out)
def pts(n, fl):
    """distress points (same scale as scripts/build_distress.py): certificate(s) 10 + 4 per extra year (max 18); delinquent without a certificate 6; tax deed application / sale 30"""
    n = np.asarray(n).astype(int); fl = np.asarray(fl)
    t = np.where(n == 0, 0, np.where(fl & 1, np.minimum(18, 10 + 4 * (n - 1)), 6)); return t + np.where((fl & (32 | 64)) > 0, 30, 0)
prev = bool((meta.get('tax') or {}).get('scored'))
for p in meta['packs']:
    fol = pack_folios[p['name']]; N = len(fol); z = lambda t: np.zeros(N, t); mp_ = os.path.join(A.out, p['files'][0])
    txy, txo, txb, txf, txd = z(np.uint8), z(np.uint16), z(np.uint32), z(np.uint8), z(np.uint16)
    for k, fo in enumerate(fol):
        g = agg.get(fo)
        if not g: continue
        txy[k] = min(g['n'], 255); txo[k] = g['old']; txb[k] = int(min(round(g['bal']), 4294967295)); txf[k] = g['fl']
        if fo in auc: txd[k] = (auc[fo]['date'] - DAY0).days
    ds, dg, vs, vg, fl0 = (getcol(mp_, c) for c in ('dscore', 'dsig', 'vscore', 'vsig', 'flags')); oy, of_ = getcol(mp_, 'txy'), getcol(mp_, 'txf')
    ds = ds.astype(int); vs = vs.astype(int)
    if oy is not None and prev: ds = ds - pts(oy, of_); vs = vs - np.where(oy > 0, 10, 0)
    dg = (dg & ~np.uint16(4 | 8 | 16)).astype(np.uint16); vg = (vg & ~np.uint16(256)).astype(np.uint16)
    dl = ((txy > 0) | ((txf & 32) > 0)) & ((fl0 & 32) == 0)
    ds = np.where(dl, np.minimum(100, ds + pts(txy, txf)), ds); vs = np.where(dl, np.minimum(100, vs + 10), vs)
    dg = dg | np.where(dl & ((txf & (32 | 64)) > 0), 4, 0).astype(np.uint16) | np.where(dl & (txy > 0) & ((txf & 1) > 0), 8, 0).astype(np.uint16) | np.where(dl & (txy > 0) & ((txf & 1) == 0), 16, 0).astype(np.uint16)
    vg = vg | np.where(dl, 256, 0).astype(np.uint16)
    p['bytes'] = patch(mp_, [('txy', 'uint8', txy.tobytes()), ('txo', 'uint16', txo.tobytes()), ('txb', 'uint32', txb.tobytes()), ('txf', 'uint8', txf.tobytes()), ('txd', 'uint16', txd.tobytes()),
                              ('dscore', 'uint8', np.clip(ds, 0, 255).astype(np.uint8).tobytes()), ('dsig', 'uint16', dg.tobytes()), ('vscore', 'uint8', np.clip(vs, 0, 255).astype(np.uint8).tobytes()), ('vsig', 'uint16', vg.tobytes())])
    p['detailBytes'] = patch(os.path.join(A.out, p['detail'][0]), [('taxs', 'str', '\n'.join(tax_str(fo) if fo in agg else '' for fo in fol).encode('utf-8'))])
    print(p['name'], N, 'tax rows', int((txy > 0).sum()), 'auction', int((txf & 32 > 0).sum()), 'scored', int(dl.sum()))
meta['tax'] = {'asof': A.asof, 'asofLabel': ASOF.strftime('%b %-d, %Y'), 'source': 'Broward County Tax Collector public reports (county-taxes.net/broward), downloaded ' + ASOF.strftime('%b %-d, %Y'), 'sourceUrl': 'https://county-taxes.net/broward',
               'cutoffYear': LAST, 'currentYear': CUR, 'delinquent': st['delinquent_parcels'], 'delinquent2plus': st['delinquent_2plus'], 'delinquent3plus': st['delinquent_3plus'], 'withCertificate': st['with_certificate'],
               'countyHeld': st['county_held'], 'deedAuctions': st['deed_auction_upcoming'], 'totalBalance': st['total_balance'], 'auctionDates': audit['files']['tax_deed_auctions']['dates'],
               'nextCertSale': 'late May 2027 (expected; recent sales were May 29, 2025 and May 28, 2026)', 'scored': True, 'cols': ['txy', 'txo', 'txb', 'txf', 'txd'], 'detail': 'taxs'}
meta['ver'] = dt.datetime.now().strftime('%Y%m%d%H%M'); json.dump(meta, open(meta_p, 'w'), separators=(',', ':'))
json.dump(audit, open(os.path.join(A.out, 'tax-audit.json'), 'w'), indent=1, default=str); print('ver', meta['ver'])
