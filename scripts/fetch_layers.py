#!/usr/bin/env python3
"""Download supporting public layers from Miami-Dade County GIS:
 - County (unincorporated) zoning polygons  MD_LandInformation/MapServer/18
 - Municipal zoning polygons (all 34 cities) MD_LandInformation/MapServer/19
 - Community Redevelopment Area polygons    MD_LandInformation/MapServer/20
 - PaGis TINC_CODE (tax-increment district code) per OBJECTID  MD_ComparableSales/MapServer/5
Writes GeoJSON / JSON into raw/."""
import json, os, sys, requests
RAW = sys.argv[1] if len(sys.argv) > 1 else '/workspace/raw'
LI = 'https://gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer'
PG = 'https://gisweb.miamidade.gov/arcgis/rest/services/MD_ComparableSales/MapServer/5/query'
def oids(url):
    return sorted(requests.get(url + '/query', params={'where': '1=1', 'returnIdsOnly': 'true', 'f': 'json'}, timeout=120).json()['objectIds'])
def poly_layer(lid, name):
    url = f'{LI}/{lid}'; ids = oids(url); feats = []
    for i in range(0, len(ids), 200):
        part = ids[i:i+200]
        r = requests.post(url + '/query', data={'objectIds': ','.join(map(str, part)), 'outFields': '*', 'returnGeometry': 'true',
                                               'outSR': '4326', 'f': 'geojson'}, timeout=300)
        feats += r.json()['features']
    json.dump({'type': 'FeatureCollection', 'features': feats}, open(os.path.join(RAW, name), 'w'))
    print(name, len(feats), 'of', len(ids), flush=True)
def tinc():
    out = {}
    for s in range(0, 960000, 20000):
        r = requests.post(PG, data={'where': f'OBJECTID>{s} AND OBJECTID<={s+20000}', 'outFields': 'OBJECTID,TINC_CODE',
                                    'returnGeometry': 'false', 'f': 'json'}, timeout=300).json()
        for f in r['features']:
            t = (f['attributes']['TINC_CODE'] or '').strip()
            if t: out[f['attributes']['OBJECTID']] = t
    json.dump(out, open(os.path.join(RAW, 'tinc.json'), 'w')); print('tinc', len(out))
if __name__ == '__main__':
    os.makedirs(RAW, exist_ok=True)
    poly_layer(18, 'county_zoning.geojson'); poly_layer(19, 'municipal_zoning.geojson'); poly_layer(20, 'cra.geojson'); tinc()
