#!/usr/bin/env python3
"""Broward phase-1 fetch #2: county + city layers (public ArcGIS REST) -> $RAW/broward/layers/*.geojson|jsonl (cached; delete a file to re-pull).
County: Future Land Use (county plan, all parcels), FEMA flood zones 2024 (BCGIS hosted copy of the effective DFIRM), BMSD zoning (unincorporated, parcel/FOLIO keyed).
Cities that publish a zoning polygon layer: Fort Lauderdale, Miramar, Deerfield Beach, Dania Beach, Cooper City, Pembroke Park, Pompano Beach; Lauderhill publishes parcel(FOLIO)-keyed zoning."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arcgis_lib import fetch_layer
BC = 'https://services.arcgis.com/JMAJrTsHNLrSsWf5/arcgis/rest/services/'
L = [  # name, url, fields, geom, extra kwargs
 ('flu', BC + 'FutureLandUse/FeatureServer/0', 'BPC_BCFUTU,SLUC1,ACRES,DENSITY', True, {}),
 ('flood', BC + 'FloodZones2024/FeatureServer/0', 'FLD_ZONE,ZONE_SUBTY,STATIC_BFE,SFHA_TF,DFIRM_ID', True, {'prec': 5, 'offset_tol': 0.00003}),
 ('z_bmsd', BC + 'Broward_Municipal_Service_District_Zoning/FeatureServer/2', 'FOLIO,ZONING,DESCRIPTION,TITLEDESCRIPTION', False, {}),
 ('z_lauderhill', 'https://services1.arcgis.com/pSjP2dIrOd0DE2qH/arcgis/rest/services/Zoning_2025/FeatureServer/0', 'FOLIO,CLASS,DEFINITION,SLUC1', False, {}),
 ('z_fortlauderdale', 'https://gis.fortlauderdale.gov/server/rest/services/ZoningDistrict/FeatureServer/0', 'ZONECLASS,ZONEDESC,SUBDISTRICT,HEIGHT', True, {}),
 ('z_miramar', 'https://services6.arcgis.com/dAtAhTJ12QXYHJYN/arcgis/rest/services/MiramarZoning/FeatureServer/7', 'ZONECODE,ZONEDESC', True, {}),
 ('z_deerfield', 'https://services1.arcgis.com/yJ4j7ns7W6juha0m/arcgis/rest/services/DFB_Zoning/FeatureServer/44', 'ZONECLASS,ZONEDESC', True, {}),
 ('z_dania', 'https://services6.arcgis.com/GlEnqdgm3eQv6Ys5/arcgis/rest/services/Interactive_Zoning_Map_2022Q1/FeatureServer/0', 'ZONE_1,CATEGORY,DESCRIPTIO', True, {}),
 ('z_coopercity_res', 'https://services5.arcgis.com/amVUb5DLd9MURz8U/arcgis/rest/services/CC_Zoning_View/FeatureServer/1', 'Zoning01,Zoning02,Category,LUDecrip,LULabel', True, {}),
 ('z_coopercity_com', 'https://services5.arcgis.com/amVUb5DLd9MURz8U/arcgis/rest/services/CC_Zoning_View/FeatureServer/2', 'Zoning01,Zoning02,Category,LUDecrip,LULabel', True, {}),
 ('z_pembrokepark', 'https://services3.arcgis.com/vtilYbC3YeF6EBJ1/arcgis/rest/services/Zoning_View/FeatureServer/0', 'Zone,Zone_Description', True, {}),
 ('z_pompano', 'https://services.arcgis.com/HnPbdNoPBNAJ6Oel/arcgis/rest/services/ZoningWebMapService2022/FeatureServer/13', 'ZONECLASS,ZONEDESC,OVERLAY_DISTRICT', True, {}),
]
only = sys.argv[1:]
for name, url, fields, geom, kw in L:
    if only and name not in only: continue
    try: fetch_layer(name, url, fields=fields, geom=geom, **kw)
    except Exception as e: print('FAILED', name, str(e)[:200], flush=True)
