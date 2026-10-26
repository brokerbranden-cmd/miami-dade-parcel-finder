"""Utility shutoff-list import slot: a CSV in $RAW/utility_shutoffs/<county>/ becomes the top signal 'Utility shutoff list' (bit 1, best code 1),
matched to parcels by service address (+ zip), for every county. Runs scripts/build_utility.py into a temp file (data/ is not touched)."""
import os, sys, json, gzip, subprocess, tempfile, struct, csv, datetime as dt
REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'); errs = []
def ok(c, m):
    print(('PASS ' if c else 'FAIL ') + m, flush=True)
    if not c: errs.append(m)
def pack(path):
    b = gzip.decompress(open(path, 'rb').read()); hl = struct.unpack('<I', b[:4])[0]; h = json.loads(b[4:4 + hl]); base = 4 + hl; o = {}
    for c in h['cols']:
        if c['type'] == 'str' and c['name'] in ('folio', 'addr'): o[c['name']] = b[base + c['offset']: base + c['offset'] + c['bytes']].decode().split('\n')
    return o, h['n']
for cid, d in (('miami-dade', 'data/'), ('broward', 'data/broward/'), ('monroe', 'data/monroe/')):
    p, n = pack(os.path.join(REPO, d, 'main.bin.gz')); from collections import Counter
    cnt = Counter(p['addr'][:n]); pick = [(p['folio'][i], p['addr'][i]) for i in range(0, n, max(1, n // 400)) if p['addr'][i] and cnt[p['addr'][i]] == 1][:3]
    with tempfile.TemporaryDirectory() as raw:
        ud = os.path.join(raw, 'utility_shutoffs', cid); os.makedirs(ud)
        with open(os.path.join(ud, 'test_water_utility.csv'), 'w', newline='') as fh:
            w = csv.writer(fh); w.writerow(['Account', 'Service Address', 'Shutoff Date', 'Service Type'])
            day = (dt.date.today() - dt.timedelta(days=20)).strftime('%m/%d/%Y')
            for f, a in pick: w.writerow(['x', a.lower(), day, 'Water'])
            w.writerow(['x', '1 NOWHERE IMAGINARY ST', day, 'Water'])
        out = os.path.join(raw, 'u.json.gz'); r = subprocess.run([sys.executable, os.path.join(REPO, 'scripts', 'build_utility.py'), cid], env={**os.environ, 'RAW': raw, 'UT_OUT': out}, capture_output=True, text=True)
        ok(r.returncode == 0, f'{cid}: build ran ({r.stderr[-300:]})')
        if r.returncode: continue
        U = json.load(gzip.open(out)); R = U['rows']
        ok(all(f in R and R[f][0] & 1 and R[f][1] == 1 and R[f][3] == 'Water shut off' and R[f][4].startswith('Utility shutoff list') for f, _ in pick), f'{cid}: {len(pick)} listed addresses -> top signal Utility shutoff list')
        ok(U['counts']['list'] >= len(pick) and U['lists'][0]['rows'] == len(pick) + 1 and U['lists'][0]['matched'] == len(pick), f"{cid}: list stats {U['lists']}")
print('FAILED: ' + '; '.join(errs) if errs else 'ALL PASS'); sys.exit(1 if errs else 0)
