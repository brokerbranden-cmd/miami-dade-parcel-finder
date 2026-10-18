"""Monroe tax-delinquent layer: Tax Collector unpaid-tax report (county-taxes.net/fl-monroe) -> parcel packs, no full rebuild.
Adds to each Monroe main pack: txy (uint8, delinquent tax years), txo (uint16, oldest unpaid year), txb (uint32, delinquent balance in whole $), txf (uint8 flags),
and to each detail pack the string column taxs (per-year detail for the drawer). Also writes meta.json -> tax {...} and data/monroe/tax-audit.json (counts, dedupe + match audit).
  txf bits: 1 = certificate / bidder on a delinquent year   2 = county-held certificate (bidder 99999 / held-certificate list)
            4 = current-year bill also unpaid (not yet delinquent)   8 = tax-bill owner name differs from the current roll owner   16 = 3+ certificates

MATCHING  Tax collector 'Account Number' (= 'Property ID', 7 digits) is the Property Appraiser AltKey: parcels.jsonl ALT_KEY. It is NOT the RE number, so the last-14-digits-of-folio rule
          cannot be applied to this export (checked: 0 of 3,297 accounts equal any RE). Each account -> ALT_KEY -> 20-digit folio. Verified by site-address agreement (99%) and owner name.
DEDUPE    Pulls are given oldest -> newest. A row is keyed (Account Number, Tax Yr). The NEWEST pull wins for every key it contains (balances accrue interest, so the older balance is stale).
          A key present only in an OLDER pull is treated as resolved (paid / redeemed) since the newer pull and is dropped, unless --keep-older-only is given (sensitivity run).
          v2 is the newest pull: it is a subset of v1 (no v2-only keys), its balances are >= v1 for 791 of 792 changed rows (interest), and its 4 county-held balances equal the held-certificate
          list 'Price to Purchase' exactly (v1 does not).
DELINQUENT  Tax year <= as-of year - 1 (2025). The current-year bill (2026) is not delinquent until April 1, 2027; it is kept apart (txf 4, drawer line) and never counts as a delinquent year.
Usage: python3 scripts/counties/monroe/add_tax.py [data/monroe] [--asof 2026-10-16] [--pulls old.csv new.csv] [--held held.csv] [--keep-older-only] [--dry]
Inputs default to $RAW/monroe/tax/ (re-download notes: scripts/counties/monroe/TAX_REFRESH.md)."""
import argparse, csv, datetime as dt, gzip, json, os, re, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument('out', nargs='?', default=os.path.join(HERE, '..', '..', '..', 'data', 'monroe'))
ap.add_argument('--asof', default='2026-10-16'); ap.add_argument('--pulls', nargs='+'); ap.add_argument('--held'); ap.add_argument('--keep-older-only', action='store_true'); ap.add_argument('--dry', action='store_true')
A = ap.parse_args()
RAWM = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe'); TD = os.path.join(RAWM, 'tax')
pulls = A.pulls or [os.path.join(TD, 'monroe_unpaid_taxes.csv'), os.path.join(TD, 'monroe_unpaid_taxes_v2.csv')]
held_f = A.held or os.path.join(TD, 'monroe_county_held_certificates.csv')
ASOF = dt.date.fromisoformat(A.asof); CUR = ASOF.year; LASTDEL = CUR - 1
COUNTY_BIDDER = '99999'

def rd(path): return list(csv.DictReader(open(path, newline='', encoding='utf-8-sig')))
def num(s):
    try: return round(float(str(s).replace(',', '').replace('$', '')), 2)
    except Exception: return 0.0
# ---- merge pulls (newest wins per (account, year))
rows = {}; srcpull = {}; pull_stats = []
for pi, path in enumerate(pulls):
    rs = [r for r in rd(path) if (r.get('Account Status') or 'Unpaid').strip().lower() == 'unpaid']
    keys = set()
    for r in rs:
        k = (r['Account Number'].strip(), int(r['Tax Yr'])); keys.add(k); rows[k] = r; srcpull[k] = pi
    pull_stats.append({'file': os.path.basename(path), 'rows': len(rs), 'keys': len(keys), 'accounts': len({k[0] for k in keys})})
newest = {k for k, p in srcpull.items() if p == len(pulls) - 1}
older_only = {k for k in rows if k not in newest}
dedupe = {'pulls': pull_stats, 'authoritative': os.path.basename(pulls[-1]), 'keys_in_newest': len(newest), 'keys_only_in_older': len(older_only),
          'older_only_by_year': {str(y): sum(1 for k in older_only if k[1] == y) for y in sorted({k[1] for k in older_only})}, 'older_only_balance': round(sum(num(rows[k]['Balance Amount']) for k in older_only), 2),
          'rule': 'newest pull wins per (account, tax year); keys only in an older pull treated as resolved (dropped)' if not A.keep_older_only else 'SENSITIVITY: keys only in older pulls KEPT'}
if len(pulls) > 1:
    old = {k for k, p in srcpull.items() if p == 0} | {k for k in newest if False}
    first = {(r['Account Number'].strip(), int(r['Tax Yr'])): num(r['Balance Amount']) for r in rd(pulls[0])}
    ch = [(k, num(rows[k]['Balance Amount']) - first[k]) for k in newest if k in first]
    dedupe['balance_changed_rows'] = sum(1 for _, d in ch if abs(d) > 0.005); dedupe['balance_up'] = sum(1 for _, d in ch if d > 0.005); dedupe['balance_down'] = sum(1 for _, d in ch if d < -0.005)
    dedupe['newest_only_keys'] = len(newest - set(first))
use = dict(rows) if A.keep_older_only else {k: rows[k] for k in newest}
# ---- county-held certificates list
held = {}
if os.path.exists(held_f):
    for r in rd(held_f): held[(r['Account Number'].strip(), int(r['Tax Yr']))] = r
# ---- account -> folio via ALT_KEY
ak2folio = {}
with open(os.path.join(RAWM, 'parcels.jsonl')) as f:
    for l in f:
        a = json.loads(l); a = a.get('attributes', a); fo = re.sub(r'\D', '', str(a.get('PARCEL_ID') or '')); ak = str(a.get('ALT_KEY') or '').strip()
        if fo and ak and ak not in ak2folio: ak2folio[ak] = (fo, a.get('OWN_NAME') or '', a.get('PHY_ADDR1') or '')
accts = sorted({k[0] for k in use} | {k[0] for k in held})
matched = {a for a in accts if a in ak2folio}
# ---- pack folios (parcels that are in the app: farmland / reference parcels were dropped by build_monroe.py)
def read_pack(path):
    raw = gzip.decompress(open(path, 'rb').read()); hl = int.from_bytes(raw[:4], 'little'); h = json.loads(raw[4:4 + hl]); return h, raw[4 + hl:]
meta_p = os.path.join(A.out, 'meta.json'); meta = json.load(open(meta_p))
pack_folios = {}
for p in meta['packs']:
    h, body = read_pack(os.path.join(A.out, p['files'][0])); fc = next(c for c in h['cols'] if c['name'] == 'folio')
    pack_folios[p['name']] = body[fc['offset']:fc['offset'] + fc['bytes']].decode().split('\n')
in_pack = {f for v in pack_folios.values() for f in v}
NM_STOP = {'AND', 'OF', 'THE', 'LLC', 'INC', 'TRUST', 'CORP', 'CO', 'LP', 'LTD', 'REVOCABLE', 'LIVING', 'FAMILY', 'JR', 'SR'}
def toks(s): return set(re.sub(r'[^A-Z ]', ' ', str(s).upper()).split()) - NM_STOP
def same_owner(a, b):
    x, y = toks(a), toks(b)
    if not x or not y: return True
    return len(x & y) / min(len(x), len(y)) >= 0.5
def a1(s): return re.sub(r'[^A-Z0-9 ]', '', str(s).upper()).split()[:2]
# ---- aggregate per folio
P = {}; ver = {'matched_rows': 0, 'addr_agree': 0, 'addr_checked': 0, 'owner_agree': 0, 'owner_checked': 0}; unmatched_rows = []; first_row = {}
for (ac, yr), r in sorted(use.items()):
    if ac not in ak2folio: unmatched_rows.append((ac, yr, num(r['Balance Amount']), r['Owner Name'], r['Physical Location'])); continue
    fo, rown, raddr = ak2folio[ac]; g = P.setdefault(fo, {'acc': set(), 'yrs': {}, 'cur': 0.0, 'owner': r['Owner Name'].strip(), 'oaddr': r['Owner Address'].strip(), 'held': {}, 'diff': False})
    g['acc'].add(ac); bal = num(r['Balance Amount']); cert = (r.get('Cert #') or '').strip(); bid = (r.get('Bidder #') or '').strip()
    if yr <= LASTDEL: g['yrs'][(ac, yr)] = (bal, cert, bid)
    else: g['cur'] += bal
    if ac not in first_row:
        first_row[ac] = 1; ver['matched_rows'] += 1
        pl = (r.get('Physical Location') or '').strip()
        if pl and not pl.upper().startswith('VACANT') and raddr: ver['addr_checked'] += 1; ver['addr_agree'] += int(a1(pl) == a1(raddr))
        ver['owner_checked'] += 1; same = same_owner(r['Owner Name'], rown); ver['owner_agree'] += int(same)
        if not same: g['diff'] = True
for (ac, yr), r in held.items():
    if ac in ak2folio:
        fo = ak2folio[ac][0]; g = P.setdefault(fo, {'acc': {ac}, 'yrs': {}, 'cur': 0.0, 'owner': r.get('Owner Name', ''), 'oaddr': '', 'held': {}, 'diff': False})
        g['held'][(ac, yr)] = (r.get('Cert #', ''), num(r.get('Price to Purchase')))
        if yr <= LASTDEL and (ac, yr) not in g['yrs']: g['yrs'][(ac, yr)] = (num(r.get('Price to Purchase')), (r.get('Cert #') or '').strip(), COUNTY_BIDDER)
# delinquent parcels only (>=1 delinquent year); current-year-only parcels keep txf 4 so the drawer can say 'current bill unpaid'
agg = {}
for fo, g in P.items():
    ys = sorted({y for (_, y) in g['yrs']}); bal = round(sum(v[0] for v in g['yrs'].values()), 2)
    certs = [(y, v[1], v[2]) for (a, y), v in sorted(g['yrs'].items(), key=lambda t: t[0][1]) if v[1] or v[2]]
    fl = (1 if certs else 0) | (2 if (g['held'] or any(v[2] == COUNTY_BIDDER for v in g['yrs'].values())) else 0) | (4 if g['cur'] > 0 else 0) | (8 if g['diff'] else 0) | (16 if len(certs) >= 3 else 0)
    agg[fo] = {'n': len(ys), 'old': ys[0] if ys else 0, 'bal': bal, 'fl': fl, 'cur': round(g['cur'], 2), 'g': g, 'ys': ys}
# ---- numbers
cur_only = [fo for fo, v in agg.items() if v['n'] == 0]
D = {fo: v for fo, v in agg.items() if v['n'] > 0}
Din = {fo: v for fo, v in D.items() if fo in in_pack}
st = {'asof': A.asof, 'delinquent_cutoff_year': LASTDEL, 'current_year': CUR, 'accounts_in_report': len(accts), 'accounts_matched': len(matched), 'accounts_unmatched': sorted(set(accts) - matched),
      'account_match_rate': round(len(matched) / max(1, len(accts)), 4), 'parcels_matched': len(P), 'parcels_in_app': sum(1 for fo in P if fo in in_pack),
      'rows_used': len(use), 'rows_unmatched': len(unmatched_rows), 'verify': ver,
      'delinquent_parcels': len(Din), 'delinquent_1plus': len(Din), 'delinquent_2plus': sum(1 for v in Din.values() if v['n'] >= 2), 'delinquent_3plus': sum(1 for v in Din.values() if v['n'] >= 3),
      'delinquent_5plus': sum(1 for v in Din.values() if v['n'] >= 5), 'current_year_only_parcels': sum(1 for fo in cur_only if fo in in_pack),
      'with_certificate': sum(1 for v in Din.values() if v['fl'] & 1), 'county_held': sum(1 for v in Din.values() if v['fl'] & 2), 'owner_differs_from_roll': sum(1 for v in Din.values() if v['fl'] & 8),
      'total_balance_delinquent': round(sum(v['bal'] for v in Din.values()), 2), 'total_balance_current_year_unpaid': round(sum(v['cur'] for v in agg.values()), 2),
      'total_balance_2plus': round(sum(v['bal'] for v in Din.values() if v['n'] >= 2), 2), 'balance_ge_5k': sum(1 for v in Din.values() if v['bal'] >= 5000), 'balance_ge_25k': sum(1 for v in Din.values() if v['bal'] >= 25000),
      'oldest_year_min': min((v['old'] for v in Din.values()), default=0),
      'if_current_year_counted': {'parcels_2plus': sum(1 for v in agg.values() if v['n'] + (1 if v['cur'] > 0 else 0) >= 2 and v['n'] + (1 if v['cur'] > 0 else 0) > 0)}}
st['total_balance_all_unpaid_incl_current'] = round(sum(v['bal'] + v['cur'] for v in agg.values()), 2)
audit = {'dedupe': dedupe, 'stats': st, 'unmatched_rows': unmatched_rows, 'method': __doc__.split('\n')[0]}
print(json.dumps(audit, indent=1, default=str)[:6000])
if A.dry: sys.exit(0)

# ---- patch packs
def fmt_s(s): return str(s).replace('\n', ' ').replace('¦', '/').replace('~', '-')
def tax_str(fo):
    v = agg.get(fo)
    if not v: return ''
    g = v['g']; it = [f"o~{fmt_s(g['owner'])}~{fmt_s(g['oaddr'])}"]
    for (ac, yr), (bal, cert, bid) in sorted(g['yrs'].items(), key=lambda t: t[0][1]): it.append(f'y~{yr}~{bal:.2f}~{cert}~{bid}')
    if g['cur'] > 0: it.append(f"c~{CUR}~{g['cur']:.2f}")
    for (ac, yr), (cn, pr) in sorted(g['held'].items(), key=lambda t: t[0][1]): it.append(f'h~{yr}~{cn}~{pr:.2f}')
    it.append('a~' + ','.join(sorted(g['acc']))); return '¦'.join(it)
def patch(path, folios, newcols):
    h, body = read_pack(path); names = {n for n, _, _ in newcols}
    parts = []; off = 0; cols = []
    for c in h['cols']:
        if c['name'] in names: continue
        b = body[c['offset']:c['offset'] + c['bytes']]; cols.append({**c, 'offset': off}); parts.append(b); off += len(b); pad = (-off) % 4
        if pad: parts.append(b'\0' * pad); off += pad
    for name, typ, b in newcols:
        cols.append({'name': name, 'type': typ, 'offset': off, 'bytes': len(b)}); parts.append(b); off += len(b); pad = (-off) % 4
        if pad: parts.append(b'\0' * pad); off += pad
    hdr = json.dumps({'n': h['n'], 'cols': cols}, separators=(',', ':')).encode(); hdr += b' ' * ((-(4 + len(hdr))) % 4)
    out = gzip.compress(len(hdr).to_bytes(4, 'little') + hdr + b''.join(parts), 9, mtime=0); open(path, 'wb').write(out); return len(out)
for p in meta['packs']:
    fol = pack_folios[p['name']]; z = lambda t: np.zeros(len(fol), t)
    txy, txo, txb, txf = z(np.uint8), z(np.uint16), z(np.uint32), z(np.uint8)
    for k, fo in enumerate(fol):
        v = agg.get(fo)
        if not v: continue
        txy[k] = min(v['n'], 255); txo[k] = v['old']; txb[k] = int(min(round(v['bal']), 4294967295)); txf[k] = v['fl']
    p['bytes'] = patch(os.path.join(A.out, p['files'][0]), fol, [('txy', 'uint8', txy.tobytes()), ('txo', 'uint16', txo.tobytes()), ('txb', 'uint32', txb.tobytes()), ('txf', 'uint8', txf.tobytes())])
    p['detailBytes'] = patch(os.path.join(A.out, p['detail'][0]), fol, [('taxs', 'str', '\n'.join(tax_str(fo) if fo in agg else '' for fo in fol).encode('utf-8'))])
    print(p['name'], len(fol), 'tax rows', int((txy > 0).sum()))
meta['tax'] = {'asof': A.asof, 'asofLabel': ASOF.strftime('%b %-d, %Y'), 'source': 'Monroe County Tax Collector, delinquent / unpaid tax report (county-taxes.net/fl-monroe), downloaded ' + ASOF.strftime('%b %-d, %Y'),
               'sourceUrl': 'https://county-taxes.net/fl-monroe', 'cutoffYear': LASTDEL, 'currentYear': CUR, 'delinquent': st['delinquent_parcels'], 'delinquent2plus': st['delinquent_2plus'], 'delinquent3plus': st['delinquent_3plus'],
               'withCertificate': st['with_certificate'], 'countyHeld': st['county_held'], 'totalBalance': st['total_balance_delinquent'], 'matchRate': st['account_match_rate'],
               'nextCertSale': 'May 2027', 'cols': ['txy', 'txo', 'txb', 'txf'], 'detail': 'taxs', 'pulls': dedupe['authoritative'], 'rule': dedupe['rule']}
meta['ver'] = dt.datetime.now().strftime('%Y%m%d%H%M'); json.dump(meta, open(meta_p, 'w'), separators=(',', ':'))
json.dump(audit, open(os.path.join(A.out, 'tax-audit.json'), 'w'), indent=1, default=str)
print('ver', meta['ver'])
