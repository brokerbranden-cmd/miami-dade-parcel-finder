#!/usr/bin/env python3
"""Point-in-polygon: give every parcel point its actual city/county zoning district and CRA polygon.
- Parcels in a city -> Municipal Zoning layer polygon of that same city (falls back to any city polygon).
- Unincorporated parcels -> County Zoning (Zone_Poly_U) polygon.
Output raw/spatial.parquet: FOLIO, MZ_CODE, MZ_JURIS, MZ_DESC, CRA_POLY"""
import sys, pandas as pd, geopandas as gpd
RAW = sys.argv[1] if len(sys.argv) > 1 else '/workspace/raw'
df = pd.read_parquet(f'{RAW}/pagis.parquet', columns=['FOLIO', 'TRUE_SITE_CITY', 'LAT', 'LON'])
df = df[df.FOLIO.notna()].drop_duplicates('FOLIO').reset_index(drop=True)
pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.LON, df.LAT), crs=4326)
muni = gpd.read_file(f'{RAW}/municipal_zoning.geojson')[['ZONE', 'ZONEDESC', 'MUNICNAME', 'geometry']]
muni = muni[(muni.MUNICNAME != 'UNINCORPORATED') & muni.ZONE.notna() & ~muni.ZONE.str.upper().isin(['NONE', ''])]
muni['geometry'] = muni.geometry.make_valid()
cnty = gpd.read_file(f'{RAW}/county_zoning.geojson')[['ZONE', 'ZONE_DESC', 'geometry']]
cnty = cnty[cnty.ZONE.notna()]; cnty['geometry'] = cnty.geometry.make_valid()
cra = gpd.read_file(f'{RAW}/cra.geojson')[['LOCATION', 'geometry']]; cra['geometry'] = cra.geometry.make_valid()

def norm_city(s): return (s or '').upper().replace('INDIAN CREEK VILLAGE', 'INDIAN CREEK').strip()
pts['CITYU'] = pts.TRUE_SITE_CITY.fillna('').str.upper()
# municipal
j = gpd.sjoin(pts[['CITYU', 'geometry']], muni, how='inner', predicate='within')
j['same'] = j.CITYU == j.MUNICNAME.map(norm_city)
j = j.sort_values(['same'], ascending=False)
j = j[~j.index.duplicated(keep='first')]
city_mask = pts.CITYU.ne('UNINCORPORATED COUNTY') & pts.CITYU.ne('')
res = pd.DataFrame(index=pts.index, columns=['MZ_CODE', 'MZ_JURIS', 'MZ_DESC'], dtype=object)
mj = j[city_mask.reindex(j.index).values]
res.loc[mj.index, 'MZ_CODE'] = mj.ZONE.str.strip().values
res.loc[mj.index, 'MZ_JURIS'] = mj.MUNICNAME.values
res.loc[mj.index, 'MZ_DESC'] = mj.ZONEDESC.values
# county (unincorporated, plus city parcels that matched no city polygon but sit on county zoning)
need = pts[res.MZ_CODE.isna()]
k = gpd.sjoin(need[['geometry']], cnty, how='inner', predicate='within')
k = k[~k.index.duplicated(keep='first')]
res.loc[k.index, 'MZ_CODE'] = k.ZONE.str.strip().values
res.loc[k.index, 'MZ_JURIS'] = 'MIAMI-DADE COUNTY'
res.loc[k.index, 'MZ_DESC'] = k.ZONE_DESC.values
c = gpd.sjoin(pts[['geometry']], cra, how='inner', predicate='within')
c = c[~c.index.duplicated(keep='first')]
res['CRA_POLY'] = None; res.loc[c.index, 'CRA_POLY'] = c.LOCATION.str.strip().values
res['FOLIO'] = pts.FOLIO
print('zoning matched', res.MZ_CODE.notna().sum(), 'of', len(res)); print(res.MZ_JURIS.value_counts().head(40)); print('cra', res.CRA_POLY.notna().sum())
res.to_parquet(f'{RAW}/spatial.parquet', index=False)
