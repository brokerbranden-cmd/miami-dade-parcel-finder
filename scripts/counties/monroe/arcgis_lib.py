"""Small ArcGIS REST paging helper for the Monroe fetchers (resume-friendly: every layer is cached as geojson/jsonl under $RAW/monroe/layers).
mcgis4.monroecounty-fl.gov serves an incomplete TLS chain (python requests -> SSLError), so VERIFY is off for that host ONLY, read-only public GIS queries."""
import json, os, time, requests, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe'); LAY = os.path.join(RAW, 'layers'); os.makedirs(LAY, exist_ok=True)
H = {'User-Agent': 'parcel-finder/1.0 (public data research)'}
INSECURE_HOSTS = ('mcgis4.monroecounty-fl.gov',)
def _verify(url): return not any(h in url for h in INSECURE_HOSTS)
def q(url, p, tries=4, post=True):
    for i in range(tries):
        try:
            r = (requests.post if post else requests.get)(url, **({'data': p} if post else {'params': p}), headers=H, timeout=180, verify=_verify(url)); r.raise_for_status(); j = r.json()
            if 'error' in j: raise RuntimeError(str(j['error'])[:200])
            return j
        except Exception as e:
            if i == tries - 1: raise
            print('retry', str(e)[:140], flush=True); time.sleep(4 * (i + 1))
def fetch_layer(name, base, fields='*', where='1=1', geom=True, page=None, prec=6, force=False, offset_tol=None, extra=None):
    """Page a layer by OBJECTID chunks -> $RAW/monroe/layers/<name>.geojson (or .jsonl when geom=False). Returns the path. Cached."""
    path = os.path.join(LAY, name + ('.geojson' if geom else '.jsonl'))
    if os.path.exists(path) and not force: print('cached', name); return path
    meta = q(base, {'f': 'json'}, post=False); page = page or min(int(meta.get('maxRecordCount') or 1000), 1000)
    oidf = next((f['name'] for f in meta.get('fields', []) if f['type'] == 'esriFieldTypeOID'), 'OBJECTID')
    ids = sorted(q(base + '/query', {'where': where, 'returnIdsOnly': 'true', 'f': 'json'})['objectIds'] or []); print(name, len(ids), 'features', flush=True)
    feats = []
    for k in range(0, len(ids), page):
        c = ids[k:k + page]; p = {'where': f'{oidf}>={c[0]} AND {oidf}<={c[-1]}' + (f' AND ({where})' if where != '1=1' else ''), 'outFields': fields, 'returnGeometry': 'true' if geom else 'false',
             'outSR': 4326, 'f': 'geojson' if geom else 'json', 'geometryPrecision': prec}
        if offset_tol: p['maxAllowableOffset'] = offset_tol
        if extra: p.update(extra)
        j = q(base + '/query', {k2: v for k2, v in p.items()}); feats += j['features'] if geom else [f['attributes'] for f in j['features']]
        print(' ', name, len(feats), '/', len(ids), flush=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as fh:
        if geom: json.dump({'type': 'FeatureCollection', 'features': feats}, fh)
        else:
            for a in feats: fh.write(json.dumps(a) + '\n')
    os.replace(tmp, path); return path
