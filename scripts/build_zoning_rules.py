#!/usr/bin/env python3
"""Zoning rules + construction + adverse-possession extras -> data/zoning-rules.json and data/extras.json.gz.

Does NOT touch the main data packs (no rebuild needed). Sources are the public files served by the
"Miami-Dade Parcel Seeker" (https://oaken-pocket-t64p.here.now/), which are themselves built from public
county / city GIS layers, adopted code tables (Miami 21 Art. 4 Table 2, Miami-Dade Code ch. 33) and the
Property Appraiser roll / building details. They are cached in $RAW/seeker/ (downloaded if missing).

zoning-rules.json: one entry per meta.dicts.mzone code, keyed "<jurisdiction>|<CODE>" (survives pack rebuilds that renumber mzone):
  [upa, max_stories, min_lot_sf, max_lot_cov_pct, far, max_height_ft, zone_type, planned_dev(0/1), source]
  null = not confirmed (left blank on purpose). Matched by (jurisdiction, zone code); codes the Seeker
  zone list lacks fall back to its regex code table (Miami 21 rows only in Miami, County rows only in
  unincorporated), exactly like its gis/build_zoning.py.
extras.json.gz: {cn: {meta, groups}, ap: {meta, folios}} (construction category groups in the Seeker's
  compact base-36 delta format; folios with an adverse-possession claim noted in the PA legal description).
"""
import gzip, json, os, re, sys, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.environ.get('RAW', os.path.join(ROOT, 'raw'))
# The seeker sources live in the repo's raw/seeker (build_all.sh exports RAW=/workspace/raw, which has no seeker/ copy,
# and the here.now download now returns 403). SEEKER=<dir> overrides; $RAW/seeker is only used if it already holds the files.
SRC = os.environ.get('SEEKER') or next((d for d in (os.path.join(ROOT, 'raw', 'seeker'), os.path.join(RAW, 'seeker'))
                                        if os.path.exists(os.path.join(d, 'zoning_by_folio.js'))), os.path.join(ROOT, 'raw', 'seeker'))
BASE = 'https://oaken-pocket-t64p.here.now/'
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'data')

def src(name):
    p = os.path.join(SRC, name)
    if not os.path.exists(p):
        os.makedirs(SRC, exist_ok=True)
        print('downloading', BASE + name)
        urllib.request.urlretrieve(BASE + name, p)
    return open(p, encoding='utf-8').read()

def js_obj(text, key):
    i = text.index('"' + key + '":') + len(key) + 3
    return json.JSONDecoder().raw_decode(text, i)[0]

def fnum(v):
    try:
        v = float(v)
        return int(v) if v == int(v) else v
    except (TypeError, ValueError):
        return None

def juris(j):
    j = j.upper().strip()
    return {'MIAMI-DADE COUNTY': 'UNINCORPORATED', 'INDIAN CREEK': 'INDIAN CREEK VILLAGE'}.get(j, j)

def main():
    meta = json.load(open(os.path.join(OUT, 'meta.json')))
    mz = meta['dicts']['mzone']
    zf = src('zoning_by_folio.js')
    zones = js_obj(zf, 'zones')
    # (muni, code) -> best record (most numbers)
    best = {}
    for r in zones:
        k = (r[0].upper(), r[1].upper().replace(' ', ''))
        nums = [fnum(x) for x in (r[4], r[5], r[6], r[7], r[8], r[11])]
        rec = nums + [r[3] or None, 1 if r[14] in ('1', 'true', 'True') else 0, r[10] or '']
        if k not in best or sum(x is not None for x in nums) > sum(x is not None for x in best[k][:6]):
            best[k] = rec
    html = src('index.html')
    m = re.search(r'var ZONING_TABLE = (\{.*?\});\n', html, re.S)
    table = json.loads(m.group(1))['entries'] if m else []
    def lookup(code, muni):
        z = code.upper().replace(' ', '')
        for e in table:
            mm = re.search(e['re'].replace('(?![A-Z0-9])', '(?![A-Z0-9])'), z)
            if mm:
                if not ((e['group'] == 'Miami 21' and muni == 'MIAMI') or (e['group'] == 'County' and muni == 'UNINCORPORATED')):
                    return None
                st = int(mm.group(1)) if e['stories'] == '$1' else e['stories']
                return [e['upa'], st, e['min_lot_sf'], e['lot_cov'], e['far'], None, e['zt'] if e['zt'] != 'auto' else None, 1 if e['zt'] == 'pad' else 0, 'code table']
        return None
    rules, hit, tab, none = {}, 0, 0, 0
    for e in mz[1:]:
        code, mu = str(e[0]), juris(e[1])
        r = best.get((mu, code.upper().replace(' ', '')))
        if r and any(x is not None for x in r[:6]):
            hit += 1
        else:
            lk = lookup(code, mu)
            if lk and any(x is not None for x in lk[:5]):
                r = lk if not r else lk[:6] + [r[6] or lk[6], r[7] or lk[7], 'code table']; tab += 1
            elif not r:
                r = [None] * 6 + [None, 0, '']; none += 1
            else:
                none += 1
        # our own mzone numbers (2018 municipal file) fill blanks
        own = [fnum(e[3]), fnum(e[4]), fnum(e[5])]
        for j in range(3):
            if r[j] is None and own[j] is not None:
                r = list(r); r[j] = own[j]
        rules[str(e[1]) + '|' + str(e[0]).upper()] = r
    out = {'built': meta['built'], 'source': BASE + 'zoning_by_folio.js (gis/build_zoning.py: county/city GIS zoning maps, Miami 21 Art. 4 Table 2, Miami-Dade Code ch. 33, 2018 municipal zoning file)',
           'fields': ['upa', 'stories', 'min_lot_sf', 'lot_cov', 'far', 'height_ft', 'zone_type', 'planned_dev', 'source'],
           'counts': {'codes': len(mz) - 1, 'matched': hit, 'code_table': tab, 'no_numbers': none}, 'rules': rules}
    json.dump(out, open(os.path.join(OUT, 'zoning-rules.json'), 'w'), separators=(',', ':'))
    print('zoning-rules.json', out['counts'])
    cn = src('construction_by_folio.js')
    cn_meta, cn_groups = js_obj(cn, 'meta'), js_obj(cn, 'groups')
    ad = src('adverse_by_folio.js')
    ap_meta, ap_rows = js_obj(ad, 'meta'), js_obj(ad, 'rows')
    ex = {'cn': {'meta': cn_meta, 'groups': cn_groups}, 'ap': {'meta': ap_meta, 'folios': sorted({r[0] for r in ap_rows})}}
    with gzip.open(os.path.join(OUT, 'extras.json.gz'), 'wt', compresslevel=9) as f:
        json.dump(ex, f, separators=(',', ':'))
    print('extras.json.gz construction folios', cn_meta.get('folios'), 'adverse', len(ex['ap']['folios']))

if __name__ == '__main__':
    main()
