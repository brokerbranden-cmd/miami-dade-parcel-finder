#!/usr/bin/env python3
"""Utility / public-land layers (public ArcGIS) -> $RAW/monroe/layers/: Key West sewer gravity/force mains.
There is NO countywide public parcel-level sewer/central-water layer (FKAA, KLWTD, Cudjoe Regional etc. do not publish one) -> utilities rating stays 'unknown' outside Key West sewer mains. (The Hub 'Hydrants' / 'Public Lands' items are Ohio data - discarded.)"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arcgis_lib import *
H = 'https://services8.arcgis.com/ToWOUVqNUhbTXzVc/arcgis/rest/services/'; K = 'https://services3.arcgis.com/aIpcLPHSEqH4LbLl/arcgis/rest/services/'
L = {'kw_sewer_gravity': (K + 'GRAVITY_MAIN_TO317/FeatureServer/0', '*'), 'kw_sewer_force': (K + 'FORCE_MAIN_TO317/FeatureServer/0', '*')}
for k, (u, f) in L.items():
    try: fetch_layer(k, u, fields=f, offset_tol=0.000005 if k == 'public_lands' else None)
    except Exception as e: print('FAIL', k, str(e)[:200])
