#!/usr/bin/env python3
"""Fetch Puerto Rico public layers (CRIM parcels feb_2025 centroids, JP zoning attrs).
Resumable: writes one JSONL chunk per OBJECTID page. Usage: fetch_pr_layers.py parcels|zoning OUTDIR"""
import json, os, sys, time, urllib.request, urllib.parse
B = "https://sigejp.pr.gov/server/rest/services"
L = {
 "parcels": (B + "/crim/crim_feb_2025/MapServer/0", "OBJECTID,NUM_CATASTRO,INSIDE_X,INSIDE_Y,TIPO,Shape.STArea()", 2000),
 "zoning": (B + "/calificacion/cali_vige/MapServer/0", "OBJECTID,num_catast,cali,descrip,clasi,municipio,barrio,cuerdas,cali_2021,id_playa,id_riesgo,id_hist,id_agric,id_res_nat", 500),
}
def get(u, p):
    for a in range(8):
        try:
            with urllib.request.urlopen(u + "?" + urllib.parse.urlencode(p), timeout=90) as r:
                d = json.load(r)
            if "error" in d: raise RuntimeError(d["error"])
            return d
        except Exception as e:
            print("retry", a, e, flush=True); time.sleep(5 * (a + 1))
    raise SystemExit("failed " + str(p))
def main():
    kind, out = sys.argv[1], sys.argv[2]
    url, fields, n = L[kind]; os.makedirs(out, exist_ok=True)
    # OBJECTID range via ordered 1-row queries (outStatistics returns HTTP 500 on the zoning layer)
    oid = lambda o: get(url + "/query", {"where": "1=1", "outFields": "OBJECTID", "orderByFields": "OBJECTID " + o, "resultRecordCount": 1, "returnGeometry": "false", "f": "json"})["features"][0]["attributes"]["OBJECTID"]
    mn, mx = oid("ASC"), oid("DESC")
    print(kind, "oid range", mn, mx, flush=True)
    # optional OBJECTID sub-range (argv 3/4) so several workers can split one layer; pages are aligned to mn
    if len(sys.argv) > 4: a0, a1 = int(sys.argv[3]), int(sys.argv[4]); mx = min(mx, a1); mn = mn + max(0, (a0 - mn) // n) * n
    lo = mn
    while lo <= mx:
        hi = lo + n - 1; fn = f"{out}/{kind}_{lo:09d}.jsonl"
        if not os.path.exists(fn):
            d = get(url + "/query", {"where": f"OBJECTID>={lo} AND OBJECTID<={hi}", "outFields": fields, "returnGeometry": "false", "f": "json"})
            if d.get("exceededTransferLimit"): raise SystemExit("page truncated at %d - lower the page size" % lo)
            with open(fn + ".tmp", "w") as f:
                for ft in d.get("features", []): f.write(json.dumps(ft["attributes"]) + "\n")
            os.rename(fn + ".tmp", fn)
            print(kind, lo, len(d.get("features", [])), flush=True)
        lo = hi + 1
    print("DONE", kind, flush=True)
if __name__ == "__main__": main()
