#!/usr/bin/env python3
"""Per-city parsers for utility shutoff / cut lists (Fla. ch. 119 public records) -> one common table per list.
  python3 scripts/utility_lists.py <county> <parser> <out_name> <source files...>
     writes $RAW/utility_shutoffs/<county>/<out_name>.csv + <out_name>.meta.json (picked up by scripts/build_utility.py),
     and $RAW/utility_shutoffs/<county>/unmatched/<out_name>_parse_skipped.csv (rows the parser could not use, e.g. no address).
  python3 scripts/utility_lists.py --list      -> registered parsers
Common table (CSV), the ONLY fields kept: address, city, disconnect_date, service_type, status, source, source_file.
Customer names, account / customer / location ids, meter numbers and balances are never written (they stay only in the
original file under $RAW/utility_shutoffs/_src/, which is outside the repo).
Counties are never mixed: one county per run, matching (build_utility.py) is restricted to the list's city / cities.
Add a city: write parse_<city>(files) -> (rows, skipped, meta) and register it in PARSERS. Lists that are already a clean
CSV / XLSX with a service-address column can skip this step and go straight into $RAW/utility_shutoffs/<county>/ with a
sidecar <file>.meta.json (that is how Coral Springs PRR-30368 and the Margate open-lien listing are loaded)."""
import os, sys, re, csv, json, glob, subprocess, datetime as dt
RAW = os.environ.get('RAW', '/workspace/raw'); HERE = os.path.dirname(os.path.abspath(__file__))
COLS = ['address', 'city', 'disconnect_date', 'service_type', 'status', 'source', 'source_file']
COUNTIES = ('miami-dade', 'broward', 'monroe')

def iso(v):
    if v is None or v == '': return ''
    if hasattr(v, 'date'): return v.date().isoformat()
    s = str(v).strip()
    for f in ('%m/%d/%y', '%m/%d/%Y', '%Y-%m-%d'):
        try: return dt.datetime.strptime(s, f).date().isoformat()
        except Exception: pass
    return ''
def clean_addr(a): return re.sub(r'\s+', ' ', str(a or '').replace('\u3001', ',').strip()).strip(' ,.')

# ---------- Pompano Beach (Broward): XLSX work-request export "Sep Cut List" ----------
# Columns: Work Request Header Assign Date | Meter Location Street Address | Work Request Header Completion Code | Work Request Header Close Date
# No names / account numbers in the export. Completion codes seen: PBF, FNLF (meaning not documented by the city; kept as 'status').
# disconnect_date = close date (cut work order completed); assign date used only when the close date is blank.
def parse_pompano_beach(files):
    import openpyxl
    rows, skipped = [], []
    for fn in files:
        ws = openpyxl.load_workbook(fn, read_only=True, data_only=True).worksheets[0]; it = ws.iter_rows(values_only=True)
        hd = [str(h or '').strip().lower() for h in next(it)]
        col = lambda *k: next(i for i, h in enumerate(hd) if all(x in h for x in k))
        ia, iad, ic, icd = col('street address'), col('assign date'), col('completion code'), col('close date')
        for k, r in enumerate(it, start=2):
            if not any(v is not None for v in r): continue
            if isinstance(r[iad], (int, float)) and r[ia] is None: continue          # trailing row count (e.g. 1530)
            a = clean_addr(r[ia]); d = iso(r[icd]) or iso(r[iad]); st = str(r[ic] or '').strip()
            if not a: skipped.append({'source_file': os.path.basename(fn), 'row': k, 'reason': 'no service address in the source row', 'date': d, 'status': st}); continue
            rows.append({'address': a, 'city': 'Pompano Beach', 'disconnect_date': d, 'service_type': 'water', 'status': ('completion code ' + st) if st else '',
                         'source': 'Pompano Beach water cut list', 'source_file': os.path.basename(fn)})
    return rows, skipped, {'source': 'Pompano Beach water cut list (Sep 2026)', 'short': 'Pompano Beach cut list', 'kind': 'water',
                           'cities': ['Pompano Beach', 'Lighthouse Point', 'Lauderdale By The Sea'],
                           'date_meaning': 'work order close date', 'status_codes': 'PBF / FNLF completion codes (undocumented)'}

# ---------- Deerfield Beach (Broward): scanned PDF "DELINQUENT NOTICE CUT LIST FOR CREWMEN" (report UT521L), one per run date ----------
# Two text lines per account: [cycle, customer id, NAME, serv, loc, balance, special code] / [route, location id, SERVICE ADDRESS, meter number].
# Only the service address (line 2), the report RUN DATE and the service column ('W' = water) are kept.
# OCR: RapidOCR (onnx) run by $OCR_PY (tesseract was not installable on the build box) (default /workspace/ocrenv/bin/python); OCR json cached next to the PDF.
OCR_PY = os.environ.get('OCR_PY', '/workspace/ocrenv/bin/python')
OCR_SNIPPET = r'''
import sys, json, os, subprocess, tempfile, glob
from rapidocr_onnxruntime import RapidOCR
eng = RapidOCR(); pdf, out = sys.argv[1], sys.argv[2]; res = []
with tempfile.TemporaryDirectory() as t:
    subprocess.run(['pdftoppm', '-r', '200', '-png', pdf, os.path.join(t, 'p')], check=True)
    for p in sorted(glob.glob(os.path.join(t, 'p-*.png')), key=lambda s: int(s.rsplit('-', 1)[1].split('.')[0])):
        r, _ = eng(p); res.append([[[list(map(float, pt)) for pt in b], tx, float(s)] for b, tx, s in (r or [])])
json.dump(res, open(out, 'w'))
'''
def ocr_pages(pdf):
    cache = pdf + '.ocr.json'
    if not os.path.exists(cache) or os.path.getmtime(cache) < os.path.getmtime(pdf):
        txt = subprocess.run(['pdftotext', '-layout', pdf, '-'], capture_output=True, text=True).stdout
        if len(txt.strip()) > 200: raise SystemExit(f'{pdf}: has a text layer; add a text parser branch instead of OCR')
        subprocess.run([OCR_PY, '-c', OCR_SNIPPET, pdf, cache], check=True)
    return json.load(open(cache))
CROP_SNIPPET = r'''
import sys, subprocess, tempfile, os, glob
from rapidocr_onnxruntime import RapidOCR
from PIL import Image
pdf, pg, x0, y0, x1, y1 = sys.argv[1], sys.argv[2], *map(float, sys.argv[3:7])
with tempfile.TemporaryDirectory() as t:
    subprocess.run(['pdftoppm', '-r', '400', '-png', '-f', pg, '-l', pg, pdf, os.path.join(t, 'p')], check=True)
    im = Image.open(glob.glob(os.path.join(t, 'p*.png'))[0]).crop((int(x0 * 2), int(y0 * 2), int(x1 * 2), int(y1 * 2)))
    q = os.path.join(t, 'c.png'); im.save(q); r, _ = RapidOCR()(q)
print(' '.join(b[1] for b in sorted(r or [], key=lambda b: b[0][0][0])))
'''
def ocr_crop(pdf, page, box):
    """second, 400 dpi look at one address cell the full-page OCR missed (cached in <pdf>.crops.json)"""
    cp = pdf + '.crops.json'; c = json.load(open(cp)) if os.path.exists(cp) else {}; k = f'{page}:' + ','.join(str(int(v)) for v in box)
    if k not in c:
        c[k] = subprocess.run([OCR_PY, '-c', CROP_SNIPPET, pdf, str(page), *map(str, box)], capture_output=True, text=True).stdout.strip(); json.dump(c, open(cp, 'w'))
    return c[k]
def lines_of(page):
    bx = sorted(page, key=lambda b: (b[0][0][1] + b[0][2][1]) / 2); rows = []
    for b in bx:
        yc = (b[0][0][1] + b[0][2][1]) / 2
        if rows and abs(rows[-1][0] - yc) < 11: rows[-1][1].append(b)
        else: rows.append([yc, [b]])
    return [(yc, sorted(bs, key=lambda b: b[0][0][0])) for yc, bs in rows]
DIRS = {'N', 'S', 'E', 'W', 'NE', 'NW', 'SE', 'SW'}
SUFX = ('BLVD', 'AVE', 'TER', 'WAY', 'CIR', 'HWY', 'TRL', 'PKWY', 'ST', 'AV', 'RD', 'DR', 'CT', 'PL', 'LN', 'TE')
def respace(a):
    """OCR drops some spaces in the fixed-pitch print ('1966NE4ST', '250NW42WAY'): put them back at digit/letter edges and
    around direction prefixes / street suffixes. Matching also uses a no-space key, so this only has to be readable."""
    a = re.sub(r"[`'\"]|(?<=\d)[-.,]+(?= ?[A-Z])", ' ', a); a = re.sub(r'(?<=\d)(?=[A-Z])|(?<=[A-Z])(?=\d)', ' ', a.upper()); w = a.split()
    if len(w) >= 2 and w[0].isdigit() and not w[1].isdigit():
        m = re.match(r'^(NE|NW|SE|SW|N|S|E|W)(\d.*)?$', w[1])
        if m and m.group(2): w[1:2] = [m.group(1), m.group(2)]
    out = []
    for t in w:
        m = re.match(r'^(\d+)(' + '|'.join(SUFX) + r')$', t)
        out += [m.group(1), m.group(2)] if m else [t]
    return ' '.join(out)
def parse_deerfield_beach(files):
    rows, skipped, totals = [], [], {}
    for fn in sorted(files):
        pages = ocr_pages(fn); run = ''; total = None; n0 = len(rows)
        for page in pages:
            L = lines_of(page)
            for yc, bs in L:
                t = ' '.join(b[1] for b in bs)
                if not run:
                    m = re.search(r'RUN DATE:?\s*(\d{1,2}/\d{1,2}/\d{2})', t)
                    if m: run = iso(m.group(1))
                m = re.search(r"Customer'?s?\.?\s+(\d+)\s*$", t)
                if m: total = int(m.group(1))
            allb = [((x[0][0][1] + x[0][2][1]) / 2, x[0][0][0], x[1].strip()) for x in page]
            for ym, xm, tm in allb:
                # anchor = the meter number (7-10 digits, meter column); the service address is the text left of it on the same
                # print line (+-16 px: scans are skewed), the account line with the name sits ~25 px above and is never read
                if not (re.fullmatch(r'\d{7,10}', re.sub(r'[.\s]', '', tm)) and 800 < xm < 1000): continue
                parts = [t for y, x, t in sorted(allb, key=lambda q: q[1]) if abs(y - ym) < 16 and 240 < x < 800]
                a = respace(clean_addr(' '.join(parts)))
                if not re.match(r'^\d', a):
                    a = respace(clean_addr(ocr_crop(fn, pages.index(page) + 1, (240, ym - 22, 800, ym + 18))))
                if not re.match(r'^\d+ ', a):
                    skipped.append({'source_file': os.path.basename(fn), 'row': f'page {pages.index(page) + 1} y{int(ym)}', 'reason': f'service address not readable by OCR ({a!r})', 'date': run}); continue
                rows.append({'address': a, 'city': 'Deerfield Beach', 'disconnect_date': run, 'service_type': 'water',
                             'status': 'on cut list (scheduled cut for nonpayment)', 'source': 'Deerfield Beach water cut list', 'source_file': os.path.basename(fn)})
        totals[os.path.basename(fn)] = {'run_date': run, 'read': len(rows) - n0, 'report_total': total}
        print(f'{os.path.basename(fn)}: run {run}, {len(rows) - n0} accounts read, report total {total}', file=sys.stderr)
    return rows, skipped, {'source': 'Deerfield Beach water cut list (Sep 2026)', 'short': 'Deerfield Beach cut list', 'kind': 'water', 'city': 'Deerfield Beach',
                           'ocr': True, 'date_meaning': 'cut list run date (crews cut after this date unless paid)', 'per_file': totals}

PARSERS = {'pompano_beach': ('broward', parse_pompano_beach), 'deerfield_beach': ('broward', parse_deerfield_beach)}

def main(a):
    if a[:1] == ['--list'] or len(a) < 4:
        print('\n'.join(f'{k} ({v[0]})' for k, v in PARSERS.items())); return
    county, name, out, files = a[0], a[1], a[2], a[3:]
    if county not in COUNTIES: raise SystemExit(f'unknown county {county}')
    pc, fn = PARSERS[name]
    if pc != county: raise SystemExit(f'parser {name} is for {pc}, not {county} (counties are never mixed)')
    rows, skipped, meta = fn(files)
    ud = os.path.join(RAW, 'utility_shutoffs', county); os.makedirs(os.path.join(ud, 'unmatched'), exist_ok=True)
    with open(os.path.join(ud, out + '.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, COLS); w.writeheader(); w.writerows(rows)
    meta = {**meta, 'address_col': 'address', 'date_col': 'disconnect_date', 'parser': name, 'parsed': dt.date.today().isoformat(),
            'source_files': [os.path.basename(f) for f in files], 'rows': len(rows), 'skipped': len(skipped)}
    json.dump(meta, open(os.path.join(ud, out + '.meta.json'), 'w'), indent=1)
    sp = os.path.join(ud, 'unmatched', out + '_parse_skipped.csv')
    with open(sp, 'w', newline='') as fh:
        w = csv.DictWriter(fh, sorted({k for r in skipped for k in r}) or ['reason']); w.writeheader(); w.writerows(skipped)
    print(f'{name}: {len(rows)} rows -> {ud}/{out}.csv ({len(skipped)} skipped -> {sp})')
if __name__ == '__main__': main(sys.argv[1:])
