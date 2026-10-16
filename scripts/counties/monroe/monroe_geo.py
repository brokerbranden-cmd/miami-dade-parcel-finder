#!/usr/bin/env python3
"""Spatial joins for Monroe: parcel centroid -> jurisdiction, zoning (county / Key West / Marathon / Islamorada), FLUM, Tier, CBRS, habitat, species focus areas,
FNAI conservation lands, Florida Forever, NWI wetlands, historic districts, repetitive-loss areas, public lands; plus attribute joins (ROGO dedication, substantial damage).
Writes $RAW/monroe/geo_attrs.pkl (DataFrame indexed by FOLIO). Run standalone: python3 monroe_geo.py  (needs the layers from fetch_monroe_*_layers.py)."""
import os, sys, re, json, gc, numpy as np, pandas as pd, geopandas as gpd
RAW = os.path.join(os.environ.get('RAW', '/workspace/raw'), 'monroe'); LAY = os.path.join(RAW, 'layers')
UTM = 26917
def load_pts():
    df = pd.read_json(f'{RAW}/parcels.jsonl', lines=True, dtype=False)
    df['FOLIO'] = df.PARCEL_ID.fillna('').astype(str).str.replace(r'\D', '', regex=True); df = df[df.FOLIO != ''].drop_duplicates('FOLIO').reset_index(drop=True)
    lat = pd.to_numeric(df.LAT, errors='coerce'); lon = pd.to_numeric(df.LON, errors='coerce'); ok = lat.notna() & lon.notna() & (lat != 0)
    pts = gpd.GeoDataFrame({'FOLIO': df.FOLIO[ok].values}, geometry=gpd.points_from_xy(lon[ok], lat[ok]), crs=4326, index=np.where(ok)[0])
    return df, pts
def layer(name, cols=None):
    g = gpd.read_file(os.path.join(LAY, name + '.geojson'))
    if cols: g = g[[c for c in cols if c in g.columns] + ['geometry']]
    g['geometry'] = g.geometry.make_valid() if not g.geometry.is_valid.all() else g.geometry
    return g
def join(pts, g, cols, how='first'):
    j = gpd.sjoin(pts[['geometry']], g, how='left', predicate='within').drop(columns='index_right')
    j = j[~j.index.duplicated(keep='first')]
    return j[cols]
def near(pts, g, cols, maxd=40):
    """nearest polygon within maxd metres for points that matched nothing"""
    a = pts[['geometry']].to_crs(UTM); b = g[cols + ['geometry']].to_crs(UTM)
    j = gpd.sjoin_nearest(a, b, how='left', max_distance=maxd).drop(columns='index_right'); j = j[~j.index.duplicated(keep='first')]
    return j[cols]
def main():
    df, pts = load_pts(); n = len(df); out = pd.DataFrame(index=range(n)); out['FOLIO'] = df.FOLIO
    st = {}
    # jurisdiction
    mu = layer('munis', ['MUNICIPALITY']); j = join(pts, mu, ['MUNICIPALITY']); out['jur'] = j.MUNICIPALITY.reindex(out.index).fillna('Unincorporated').replace({'Key Colony Beach': 'Key Colony Beach'})
    # zoning by jurisdiction
    out['zcode'] = ''; out['zsrc'] = ''
    def put(mask_jur, g, col, src, fix=None):
        sub = pts[pts.index.isin(out.index[out.jur == mask_jur])]
        if not len(sub): return
        j1 = join(sub, g, [col]).reindex(sub.index); miss = j1[col].isna()
        if miss.any():
            j2 = near(sub[miss], g, [col], 60); j1.loc[j2.index, col] = j2[col].reindex(j2.index)
        v = j1[col].fillna('').astype(str).str.strip()
        if fix: v = v.map(fix)
        out.loc[sub.index, 'zcode'] = v.values; out.loc[sub.index, 'zsrc'] = src
    cz = layer('zoning', ['ZONE_', 'Zone_Desc']); cz['ZONE_'] = cz.ZONE_.str.strip().str.upper()
    cz_un = cz[cz.ZONE_ != 'INC']          # unincorporated districts only ('INC' polygons are the cities)
    put('Unincorporated', cz_un, 'ZONE_', 'Monroe County land-use district map'); del cz; gc.collect()
    kz = layer('kw_zoning', ['ZONING', 'Front_Setb', 'Side_Setba', 'Rear_Setba', 'Bldg_Cover', 'ISR', 'Open_Space', 'Transient']); kz = kz[kz.ZONING.fillna('').str.strip() != '']
    kz['ZONING'] = kz.ZONING.str.strip().str.upper(); put('Key West', kz, 'ZONING', 'City of Key West zoning map')
    sub = pts[pts.index.isin(out.index[out.jur == 'Key West'])]
    if len(sub):
        kj = join(sub, kz, ['Front_Setb', 'Side_Setba', 'Rear_Setba', 'Bldg_Cover', 'ISR', 'Open_Space', 'Transient']).reindex(sub.index)
        for c in kj.columns: out.loc[sub.index, 'kw_' + c] = kj[c].fillna('').astype(str).str.strip().values
    mz = layer('mara_zoning', ['ZONING', 'PubStatus']); mz['ZONING'] = mz.ZONING.str.strip().str.upper(); put('Marathon', mz, 'ZONING', 'City of Marathon official zoning map')
    # Islamorada: parcel-level base zoning keyed by RE number (BaseZoning, Village of Islamorada AGOL)
    ib = pd.DataFrame(json.load(open(f'{LAY}/isla_basezoning.json'))); ib['re'] = ib.RECHAR.fillna('').str.strip(); ib = ib[ib.ZONING.fillna('').str.strip() != ''].drop_duplicates('re').set_index('re')
    ismask = out.jur == 'Islamorada'; out['re'] = out.FOLIO.str[-14:].str[:8] + '-' + out.FOLIO.str[-6:]
    out.loc[ismask, 'zcode'] = out.loc[ismask, 're'].map(ib.ZONING.str.strip().str.upper()).fillna(''); out.loc[ismask & (out.zcode != ''), 'zsrc'] = 'Village of Islamorada base zoning (parcel layer)'
    # FLUM
    fl = layer('flum', ['FLUM', 'FLUMDESC']); fl = fl[fl.FLUM.fillna('') != 'INC']; out['flum'] = join(pts, fl, ['FLUM']).FLUM.reindex(out.index).fillna('').values
    mfl = layer('mara_flum', ['FLUM']); sub = pts[pts.index.isin(out.index[out.jur == 'Marathon'])]; out.loc[sub.index, 'flum'] = join(sub, mfl, ['FLUM']).FLUM.reindex(sub.index).fillna('').str.title().values
    del fl, mfl; gc.collect()
    # Tier (unincorporated)
    ti = layer('tier', ['Tier']); out['tier'] = join(pts, ti, ['Tier']).Tier.reindex(out.index).fillna('').values; out.loc[out.jur != 'Unincorporated', 'tier'] = ''
    # CBRS, habitat
    cb = layer('cbrs', ['CBRS_ID', 'CBRS_TYP']); jj = join(pts, cb, ['CBRS_ID']); out['cbrs'] = jj.CBRS_ID.reindex(out.index).fillna('').values
    hb = layer('habitat', ['DESCRIPTION']); out['habitat'] = join(pts, hb, ['DESCRIPTION']).DESCRIPTION.reindex(out.index).fillna('').values; del hb; gc.collect()
    # species focus areas
    sp = {'sp_keydeer': 'Key deer', 'sp_marsh_rabbit': 'Lower Keys marsh rabbit', 'sp_woodrat': 'Key Largo woodrat', 'sp_schaus': 'Schaus swallowtail', 'sp_indigo': 'Eastern indigo snake',
          'sp_tree_cactus': 'Florida Keys tree cactus', 'sp_rice_rat': 'Silver rice rat', 'sp_cotton_mouse': 'Key Largo cotton mouse', 'sp_tree_snail': 'Stock Island tree snail'}
    out['species'] = ''
    for k, lab in sp.items():
        p = os.path.join(LAY, k + '.geojson')
        if not os.path.exists(p): continue
        g = gpd.read_file(p)[['geometry']]; hit = gpd.sjoin(pts[['geometry']], g, how='inner', predicate='within'); idx = hit.index.unique()
        out.loc[idx, 'species'] = out.loc[idx, 'species'].map(lambda s: (s + ';' if s else '') + lab); st['species_' + k] = int(len(idx)); del g, hit; gc.collect()
    # conservation lands, Florida Forever
    fn = layer('fnai_conslands', ['MANAME', 'MATYPE', 'OWNER']); j = join(pts, fn, ['MANAME', 'MATYPE']); out['fnai'] = j.MANAME.reindex(out.index).fillna('').values; out['fnai_type'] = j.MATYPE.reindex(out.index).fillna('').values
    ff = layer('florida_forever', ['SITENAME', 'FF_CAT']); out['ff'] = join(pts, ff, ['SITENAME']).SITENAME.reindex(out.index).fillna('').values
    # NWI wetlands
    nw = layer('nwi', ['ATTRIBUTE', 'WETLAND_TYPE']); j = join(pts, nw, ['ATTRIBUTE', 'WETLAND_TYPE']); out['nwi'] = j.ATTRIBUTE.reindex(out.index).fillna('').values; out['nwi_type'] = j.WETLAND_TYPE.reindex(out.index).fillna('').values; del nw; gc.collect()
    # historic districts / repetitive loss / KW wetlands
    hs = pd.concat([layer('tavernier', ['PARCELNO']).assign(h='Tavernier historic district'), layer('kw_harc', ['USE_ID']).assign(h='Key West HARC historic district')]); hs = gpd.GeoDataFrame(hs[['h', 'geometry']], crs=4326)
    out['historic'] = join(pts, hs, ['h']).h.reindex(out.index).fillna('').values
    rl = layer('rep_loss', ['RL_Area']); out['repl'] = join(pts, rl, ['RL_Area']).RL_Area.reindex(out.index).notna().values
    # Key West sewer: parcel within 30 m of a gravity/force main (only public utility layer)
    sw = pd.concat([gpd.read_file(f'{LAY}/kw_sewer_gravity.geojson')[['geometry']], gpd.read_file(f'{LAY}/kw_sewer_force.geojson')[['geometry']]]); sw = gpd.GeoDataFrame(sw, crs=4326).to_crs(UTM)
    kwp = pts[pts.index.isin(out.index[out.jur == 'Key West'])].to_crs(UTM); out['kw_sewer'] = False
    jn = gpd.sjoin_nearest(kwp, sw[['geometry']], how='left', max_distance=30); out.loc[jn.index[jn.index_right.notna()].unique(), 'kw_sewer'] = True
    # attribute joins
    rd = pd.DataFrame([f['properties'] for f in json.load(open(f'{LAY}/rogo_ded.geojson'))['features']]); rd['re'] = rd.RE_NUM.fillna('').str.strip().str.replace(r'\s', '', regex=True)
    rd['d'] = rd.TYPE.fillna('').str.strip(); rdd = rd[rd.re != ''].drop_duplicates('re').set_index('re')
    out['ded_type'] = out.re.map(rdd.d).fillna(''); out['ded_note'] = out.re.map((rdd.ROGO_Dedication_Type.fillna('') + ' ' + rdd.ROGO_Notes.fillna('')).str.strip()).fillna('')
    sd = pd.DataFrame([f['properties'] for f in json.load(open(f'{LAY}/subst_damage.geojson'))['features']]); sd_re = set(sd.RECHAR.fillna('').str.strip()); out['subdmg'] = out.re.isin(sd_re)
    out.to_pickle(f'{RAW}/geo_attrs.pkl')
    st.update({'n': n, 'with_geom': int(len(pts)), 'jur': out.jur.value_counts().to_dict(), 'zoning_found': int((out.zcode != '').sum()), 'tier': out.tier.replace('', 'none').value_counts().to_dict(), 'cbrs': int((out.cbrs != '').sum()),
               'fnai': int((out.fnai != '').sum()), 'ff': int((out.ff != '').sum()), 'nwi': int((out.nwi != '').sum()), 'species_any': int((out.species != '').sum()), 'ded': int((out.ded_type != '').sum()), 'subdmg': int(out.subdmg.sum()),
               'historic': int((out.historic != '').sum()), 'repl': int(out.repl.sum()), 'habitat': out.habitat.replace('', 'none').value_counts().to_dict()})
    print(json.dumps(st, indent=1))
if __name__ == '__main__': main()
