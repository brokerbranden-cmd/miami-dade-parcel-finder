import json,requests,re,time
from concurrent.futures import ThreadPoolExecutor
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
def md(folio):
    f=re.sub(r'\D','',folio)
    for i in range(3):
        try:
            j=requests.get(f"https://apps.miamidadepa.gov/PApublicServiceProxy/PaServicesProxy.ashx?Operation=GetPropertySearchByFolio&clientAppName=PropertySearch&folioNumber={f}",headers={'User-Agent':UA},timeout=40).json()
            p=j.get('PropertyInfo') or {}
            a=(j.get('Assessment') or {}).get('AssessmentInfos') or [{}]
            sa=(j.get('SiteAddress') or [{}])
            return {'luc':p.get('DORCode'),'lucdesc':p.get('DORDescription'),'owner':'; '.join(o.get('Name','') for o in j.get('OwnerInfos') or []),
              'market':a[0].get('TotalValue'),'assessed':a[0].get('AssessedValue'),'lot':p.get('LotSize'),'bldg':p.get('BuildingActualArea'),'yr':p.get('YearBuilt'),'muni':p.get('Municipality'),'zone':p.get('PrimaryZoneDescription'),
              'site':(sa[0].get('Address') if sa else None)}
        except Exception as e: err=str(e); time.sleep(2)
    return {'err':err}
def bw(folio):
    f=re.sub(r'[^0-9A-Za-z]','',folio)
    for i in range(3):
        try:
            j=requests.post("https://web.bcpa.net/BcpaClient/search.aspx/getParcelInformation",json={"folioNumber":f,"taxyear":"2026","action":"CURRENT","use":""},headers={'User-Agent':UA},timeout=40).json()
            b=j['d']['parcelInfok__BackingField'][0]
            uc=b.get('useCode') or ''
            return {'luc':uc.split(' - ')[0].strip(),'lucdesc':uc,'owner':'; '.join(x for x in [b.get('ownerName1'),b.get('ownerName2')] if x),
              'market':b.get('justValue'),'assessed':b.get('sohValue') or b.get('assessedValue'),'lot':b.get('landCalcFact1'),'bldg':b.get('bldgTotSqFootage') or b.get('bldgSqFT'),'yr':b.get('actualAge'),'muni':b.get('situsCity'),'zone':b.get('landCalcZoning'),'legal':(b.get('legal') or '').strip(),'site':b.get('situsAddress1')}
        except Exception as e: err=str(e); time.sleep(2)
    return {'err':err}
if __name__=='__main__':
    items=[]
    for s in ['broward.realforeclose.com','broward.realtaxdeed.com','miamidade.realforeclose.com']: items+=json.load(open(f'auc_{s}.json'))
    def go(x):
        pid=x.get('Parcel ID','')
        if not re.search(r'\d',pid): x['pa']={'err':'no parcel'}; return x
        x['pa']=md(pid) if x['site'].startswith('miamidade') else bw(pid)
        return x
    with ThreadPoolExecutor(6) as ex: res=list(ex.map(go,items))
    json.dump(res,open('auctions_enriched.json','w'),indent=1)
    import collections
    print(len(res), sum('err' in r['pa'] for r in res))
    print(collections.Counter((r['pa'].get('luc') or 'NA')[:2] for r in res).most_common())
    