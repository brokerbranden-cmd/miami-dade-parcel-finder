"""Adds the FDOR sale-qualification reason of the latest sale (QUAL_CD1) to the Monroe packs as a small column `sx` (uint8 bit mask), without a full rebuild:
  1 = code 30  (transaction between affiliated parties: family, corporate, business, landlord-tenant)  -> 'relative transfer'
  2 = code 14  (deed with a reservation of occupancy > 90 days = life estate interest)
  4 = code 11  (corrective / quit claim / tax deed, minimum doc stamps, no stamps, non-deed transfer)
  8 = code 19  (deeds to or from executors, guardians, receivers, trustees in bankruptcy)
Source: raw/monroe/parcels.jsonl (Florida statewide cadastral, QUAL_CD1) - the same roll the packs were built from. Re-run after build_monroe.py (build_monroe.py runs it at the end).
Usage: python3 scripts/counties/monroe/add_salex.py [data/monroe]"""
import gzip, json, os, re, sys, numpy as np
OUT = sys.argv[1] if len(sys.argv) > 1 else 'data/monroe'
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe', 'parcels.jsonl')
BIT = {'30': 1, '14': 2, '11': 4, '19': 8}
codes = {}
with open(RAW) as f:
    for l in f:
        a = json.loads(l); a = a.get('attributes', a); fo = re.sub(r'\D', '', str(a.get('PARCEL_ID') or ''))
        if fo and fo not in codes: codes[fo] = BIT.get(str(a.get('QUAL_CD1') or '').strip(), 0)
def patch(path):
    raw = gzip.decompress(open(path, 'rb').read()); hl = int.from_bytes(raw[:4], 'little'); h = json.loads(raw[4:4 + hl]); body = raw[4 + hl:]
    h['cols'] = [c for c in h['cols'] if c['name'] != 'sx']
    fc = next(c for c in h['cols'] if c['name'] == 'folio'); folios = body[fc['offset']:fc['offset'] + fc['bytes']].decode().split('\n')
    # strip an older sx blob by rebuilding the body from the remaining columns
    parts = []; off = 0; cols = []
    for c in h['cols']:
        b = body[c['offset']:c['offset'] + c['bytes']]; cols.append({**c, 'offset': off}); parts.append(b); off += len(b); pad = (-off) % 4
        if pad: parts.append(b'\0' * pad); off += pad
    sx = np.array([codes.get(f, 0) for f in folios], dtype=np.uint8); b = sx.tobytes()
    cols.append({'name': 'sx', 'type': 'uint8', 'offset': off, 'bytes': len(b)}); parts.append(b); off += len(b); pad = (-off) % 4
    if pad: parts.append(b'\0' * pad)
    hdr = json.dumps({'n': h['n'], 'cols': cols}, separators=(',', ':')).encode(); hdr += b' ' * ((-(4 + len(hdr))) % 4)
    out = gzip.compress(len(hdr).to_bytes(4, 'little') + hdr + b''.join(parts), 9, mtime=0); open(path, 'wb').write(out)
    return len(out), {k: int((sx & v > 0).sum()) for k, v in {'affiliated30': 1, 'lifeestate14': 2, 'quitclaim11': 4, 'fiduciary19': 8}.items()}
mp = os.path.join(OUT, 'meta.json'); meta = json.load(open(mp))
for p in meta['packs']:
    size, st = patch(os.path.join(OUT, p['files'][0])); p['bytes'] = size; print(p['name'], size, st)
meta['salex'] = True; meta['ver'] = __import__('datetime').datetime.now().strftime('%Y%m%d%H%M'); json.dump(meta, open(mp, 'w'), separators=(',', ':'))
print('ver', meta['ver'])
