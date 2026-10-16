#!/usr/bin/env python3
"""Monroe County GIS (mcgis4 APO_GIS MapServer, public) layers -> $RAW/monroe/layers/: zoning (unincorporated land-use districts), Tier overlay, FLUM,
ROGO density-reduction / dedicated parcels, CBRS, land-cover habitat, species focus areas, Tavernier historic district, county parcel attributes (AK, area name, MCPA url)."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arcgis_lib import *
B = 'https://mcgis4.monroecounty-fl.gov/public/rest/services/APO_GIS/MapServer/'
L = {'zoning': (19, 'ZONE_,Zone_Desc,Muinicode_URL'), 'tier': (18, 'Tier'), 'flum': (20, 'FLUM,FLUM_Label,FLUMDESC'), 'rogo_ded': (1, 'RE_NUM,LEGAL,TYPE,DATE_ADDED,COMMENTS,OWNER,ROGO_Dedication_Type,Book,Page,ROGO_Notes'),
     'cbrs': (12, 'CBRS_ID,CBRS_TYP,CBRS_TF'), 'habitat': (15, 'CODE,DESCRIPTION'), 'tavernier': (14, 'PARCELNO'),
     'sp_keydeer': (30, '*'), 'sp_marsh_rabbit': (24, '*'), 'sp_woodrat': (33, '*'), 'sp_schaus': (32, '*'), 'sp_indigo': (26, '*'), 'sp_tree_cactus': (29, '*'), 'sp_rice_rat': (34, '*'), 'sp_cotton_mouse': (31, '*'), 'sp_tree_snail': (36, '*')}
only = sys.argv[1:]
for k, (i, f) in L.items():
    if only and k not in only: continue
    try: fetch_layer(k, B + str(i), fields=f, offset_tol=0.000005 if k in ('habitat', 'flum', 'zoning') else None)
    except Exception as e: print('FAIL', k, str(e)[:200])
fetch_layer('county_parcels', B + '6', fields='PARCELNO,RECHAR,AK,KEYNAME,LOCATION,MCPA_URL,TYPE1,AREA1,SUBDIVISION,SPECUSE,PC,NBRBLDG,YRBLT,FLA,CONDO_COMPLEX,PHYS_ADDR_LBL,LEGAL1', geom=False)
