import json,requests,math,re,time
from concurrent.futures import ThreadPoolExecutor
from enrich import md,bw,UA
f=json.load(open('fdep_retail.json'))['features']
def dist(a,b):
    dx=(a['x']-b['x'])*math.cos(math.radians(a['y']))*111320; dy=(a['y']-b['y'])*110540
    return math.hypot(dx,dy)
opens=[x for x in f if x['attributes']['FACILITY_STATUS'] in('OPEN','OPEN-SH','OPEN-NSH') and x.get('geometry')]
closed=[x for x in f if x['attributes']['FACILITY_STATUS'] in('CLOSED','ABANDONED') and x.get('geometry')]
cand=[c for c in closed if min(dist(c['geometry'],o['geometry']) for o in opens)>80]
print(len(opens),len(closed),len(cand))
def parcels(c):
    g=c['geometry'];cty=c['attributes']['COUNTY']
    url="https://gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer/26/query" if cty=='MIAMI-DADE' else "https://gisweb-adapters.bcpa.net/arcgis/rest/services/BCPA_EXTERNAL_JAN26/MapServer/16/query"
    p=dict(geometry=json.dumps({'x':g['x'],'y':g['y']}),geometryType='esriGeometryPoint',inSR=4326,spatialRel='esriSpatialRelIntersects',distance=15,units='esriSRUnit_Meter',outFields='FOLIO',returnGeometry='false',f='json')
    for i in range(3):
        try: return [x['attributes']['FOLIO'] for x in requests.get(url,params=p,timeout=40,headers={'User-Agent':UA}).json().get('features',[])]
        except Exception: time.sleep(2)
    return []
def go(c):
    fol=list(dict.fromkeys(parcels(c)))[:6]
    best=None
    for fo in fol:
        pa=md(fo) if c['attributes']['COUNTY']=='MIAMI-DADE' else bw(fo)
        l=(pa.get('luc') or '')[:2]
        pa['folio']=fo
        if l.isdigit() and 10<=int(l)<=39:
            score={'26':0,'27':1,'10':2,'22':3,'21':4,'11':5,'12':6,'16':7}.get(l,8)
            if best is None or score<best[0]: best=(score,pa)
    c['parcel']=best[1] if best else None; c['nparcels']=len(fol)
    return c
with ThreadPoolExecutor(8) as ex: res=list(ex.map(go,cand))
json.dump(res,open('gas_matched.json','w'),indent=1)
import collections
print(collections.Counter((r['parcel'] or {}).get('luc','none')[:2] for r in res).most_common())
