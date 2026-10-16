#!/usr/bin/env python3
"""City / extra public ArcGIS layers for Monroe -> $RAW/monroe/layers/. All public, no login.
 Key West: Zoning_all_info (zoning + setbacks/ISR/coverage/transient flag), Wetlands | Marathon: official Zoning + FLUM | Islamorada: Zoning
 Monroe County AGOL (MonroeCountyGIS): Municipal_Boundaries, Substantial_Damage_Property, Repetitive_Loss_Areas, Historic_Standing_Structures
 Key Colony Beach + Layton: no digital zoning (PDF maps only) -> no layer; handled in build with FLUM / DOR fallback."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arcgis_lib import *
K = 'https://services3.arcgis.com/aIpcLPHSEqH4LbLl/arcgis/rest/services/'; M = 'https://services3.arcgis.com/Aw0N4WrtuqNFEOFX/arcgis/rest/services/'; C = 'https://services.arcgis.com/D7K7hj5GW1YIVRiA/arcgis/rest/services/'
L = {'kw_zoning': (K + 'Zoning_all_info/FeatureServer/0', 'ZONING,SECONDCODE,Transient,Front_Setb,Side_Setba,Street_Sid,Rear_Setba,Bldg_Cover,ISR,Open_Space'),
     'kw_harc': (K + 'Harc_District/FeatureServer/0', '*'),
     'mara_zoning': (M + 'Zoning_and_FLUM_(Public_View)/FeatureServer/0', 'ZONING,ORDINANCE_,PubStatus'),
     'mara_flum': (M + 'Zoning_and_FLUM_(Public_View)/FeatureServer/1', 'FLUM,VACANT,PubStatus'),
     'munis': (C + 'Municipal_Boundaries/FeatureServer/96', '*'),
     'subst_damage': (C + 'Substantial_Damage_Property/FeatureServer/20', '*'),
     'rep_loss': (C + 'Repetitive_Loss_Areas/FeatureServer/0', '*'),
     'historic_struct': (C + 'Historic_Standing_Structures/FeatureServer/0', 'SiteName,Address,YearBuilt,Destroyed,d_NRlisted')}
only = sys.argv[1:]
for k, (u, f) in L.items():
    if only and k not in only: continue
    try: fetch_layer(k, u, fields=f, offset_tol=0.000003 if k.startswith(('mara', 'isla')) else None)
    except Exception as e: print('FAIL', k, str(e)[:200])


def fetch_isla_basezoning():
    """Village of Islamorada parcel-level base zoning (AGOL services6/SaNl2PQPK6JCBCbN BaseZoning), attributes only, keyed by RECHAR (RE number)."""
    import requests, json
    u = 'https://services6.arcgis.com/SaNl2PQPK6JCBCbN/arcgis/rest/services/BaseZoning/FeatureServer/0/query'; rows = []; off = 0
    while True:
        f = requests.get(u, params=dict(where='1=1', outFields='RECHAR,ZONING,ZONE1,FLUC,PAST_ZONE,CHANGE,AK', returnGeometry='false', resultOffset=off, resultRecordCount=1000, f='json'), timeout=60).json()['features']
        if not f: break
        rows += [x['attributes'] for x in f]; off += len(f)
    json.dump(rows, open(os.path.join(RAW, 'monroe', 'layers', 'isla_basezoning.json'), 'w')); print('isla_basezoning', len(rows))
