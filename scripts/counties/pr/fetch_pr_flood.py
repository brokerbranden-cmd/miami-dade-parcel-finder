#!/usr/bin/env python3
"""FEMA NFHL flood hazard zones for Puerto Rico (DFIRM_ID 72*), public FEMA layer 28 -> OUTDIR/flood_<offset>.json. Resumable."""
import json, os, sys, time, urllib.request, urllib.parse
U = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
def get(p):
    for a in range(8):
        try:
            with urllib.request.urlopen(U + "?" + urllib.parse.urlencode(p), timeout=180) as r: d = json.load(r)
            if "error" in d: raise RuntimeError(d["error"])
            return d
        except Exception as e: print("retry", a, e, flush=True); time.sleep(5 * (a + 1))
    raise SystemExit("failed")
W = "DFIRM_ID LIKE '72%'"
ids = sorted(get({"where": W, "returnIdsOnly": "true", "f": "json"})["objectIds"]); print("ids", len(ids), flush=True)
for k in range(0, len(ids), 100):
    fn = f"{out}/flood_{k:06d}.json"
    if os.path.exists(fn): continue
    d = get({"objectIds": ",".join(map(str, ids[k:k+100])), "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE", "returnGeometry": "true", "outSR": "4326", "geometryPrecision": "6", "maxAllowableOffset": "0.00001", "f": "json"})
    json.dump([{"a": f["attributes"], "r": (f.get("geometry") or {}).get("rings")} for f in d["features"]], open(fn + ".tmp", "w")); os.rename(fn + ".tmp", fn)
    print("flood", k, len(d["features"]), flush=True)
print("DONE flood", flush=True)
