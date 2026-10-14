import json,re,datetime,collections,os
import pandas as pd
from classify import ptype,cats
TODAY=datetime.date(2026,10,8)
P=json.load(open('parcels_v2.json'));cache=json.load(open('pa_cache_md.json'))
oc=json.load(open('oc_status.json')) if os.path.exists('oc_status.json') else {}
bk=json.load(open('cl_bk.json')) if os.path.exists('cl_bk.json') else {}
from oc_lookup_owners import owners as PRI_OWNERS
PRI_OWNERS=set(PRI_OWNERS)
def money(v):
    if v in (None,''): return None
    if isinstance(v,(int,float)): return float(v)
    s=re.sub(r'[^\d.]','',str(v)); return float(s) if s else None
def ff(p):
    d=p['folio']
    return f"{d[:2]}-{d[2:6]}-{d[6:9]}-{d[9:]}" if p['county']=='Miami-Dade' and len(d)==13 else d
def paurl(p):
    return f"https://www.miamidade.gov/Apps/PA/propertysearch/#/?folio={p['folio']}" if p['county']=='Miami-Dade' else f"https://web.bcpa.net/BcpaClient/#/Record-Search (folio {p['folio']})"
def taxurl(p):
    return ('https://miamidade.county-taxes.com/public/real_estate/parcels/' if p['county']=='Miami-Dade' else 'https://broward.county-taxes.com/public/real_estate/parcels/')+p['folio']
def sunbiz(o): return 'https://search.sunbiz.org/Inquiry/CorporationSearch/ByName (search: '+o+')'
LIVE=json.load(open('live_tax.json')) if os.path.exists('live_tax.json') else {}
rows=[];detail=[];queue=[]
for k,p in P.items():
    o1=(p.get('owner') or '').split(';')[0].strip()
    # owner entity
    ent='';ent_src=''
    if o1 in oc:
        e=oc[o1]; ent=e['status']+' (OpenCorporates FL registry mirror)'
        ent_src=(e['matches'][0]['url'] if e['matches'] else e['search'])
        if e['status']=='Inactive':
            foreign='/us_fl/M' in ent_src or '/us_fl/F' in ent_src
            if foreign:
                ent='Inactive - FL foreign-entity registration (doc '+ent_src.rsplit('/',1)[1]+') inactive/revoked; home-state entity may still exist (OpenCorporates FL mirror of Sunbiz)'
                p['signals'].append(dict(type='Owner entity: FL foreign registration INACTIVE (authority revoked/withdrawn; confirm on Sunbiz)',date=None,case=e['matches'][0]['name'],amount=None,amount_label='',url=ent_src,pts=8))
            else:
                ent='Inactive - domestic FL entity (doc '+ent_src.rsplit('/',1)[1]+'), likely dissolved/admin-dissolved (OpenCorporates FL mirror of Sunbiz)'
                p['signals'].append(dict(type='Owner entity: domestic FL entity INACTIVE (dissolved/admin-dissolved; confirm on Sunbiz)',date=None,case=e['matches'][0]['name'],amount=None,amount_label='',url=ent_src,pts=15))
    elif o1 in PRI_OWNERS: ent='Not yet checked'
    for h in bk.get(o1,[]) or []:
        p['signals'].append(dict(type=f"Owner bankruptcy filing ({h['court'].upper()}, ch. {h['chapter'] or '?'})",date=h['filed'],case=h['caseName'],amount=None,amount_label='',url=h['url'],pts=25))
    u=[];seen=set()
    for x in p['signals']:
        kk=(x['type'],x.get('case'),x.get('date'))
        if kk not in seen: seen.add(kk);u.append(x)
    p['signals']=u
    t,cr,ind,condo=ptype(p); cs=cats(p)
    if p['county']=='Miami-Dade':
        c=cache.get(p['folio'],{})
        for a,b in (('market',money(c.get('market'))),('assessed',money(c.get('assessed'))),('lot',money(c.get('lot'))),('bldg',money(c.get('bldg'))),('lucdesc',c.get('lucdesc'))):
            if not p.get(a) and b: p[a]=b
        if not p.get('owner') and c.get('owner'): p['owner']=c['owner']
        if not p.get('address') and c.get('site'): p['address']=c['site'].split(',')[0]
    # tax
    tx=p.get('tax'); base={'Miami-Dade':('2026 ad (May 2026)','2025 ad (May 2025)'),'Broward':('2026 ad (Apr 2026)','2025 ad (Apr 2025)')}[p['county']]
    tdapp=p.get('tax_deed_app','')
    if tx:
        yrs=tx['years']; on26,on25=tx['on26'],tx['on25']
        if on26:
            st=f"UNPAID as of {base[0]}: ${tx['amt26']:,.2f} advertised"+(f"; also delinquent on {base[1]} (${tx['amt25']:,.2f})" if on25 else '')
            amt=(tx['amt26'] or 0)+((tx['amt25'] or 0) if on25 else 0)
            certs=('Likely 2+ (TY'+', TY'.join(yrs)+') unless paid before sale/redeemed' if len(yrs)>=2 else 'Likely 1 (TY'+yrs[0]+', 2026 certificate sale) unless paid before sale')
        else:
            st=f"Was delinquent on {base[1]} (${tx['amt25']:,.2f}); NOT on 2026 ad -> later year(s) appear paid"
            amt=None; certs='Possibly 1 (TY'+', TY'.join(yrs)+' certificate) if not redeemed'
        st+='. Live payoff UNVERIFIED (county-taxes.com requires human captcha).'
        ny=len(yrs) if on26 else 0
    else:
        st='No delinquency: not on 2025 or 2026 delinquent-tax ads' ; amt=None; certs='None indicated by ads'; ny=0
    tdbid=[x['amount'] for x in p['signals'] if x['type']=='Tax deed auction scheduled' and x.get('amount')]
    if tdapp:
        certs='YES - certificate holder applied for tax deed; '+certs
        if tdbid: amt=max(tdbid); st+=f' Tax deed opening bid ${amt:,.2f} (covers certificates, taxes, fees).'
    basis='estimated from delinquent-tax ads (Apr/May 2025-2026)' if tx else 'ads only (not listed)'
    checked='';lpy='';npo=None
    L=LIVE.get(k)
    if L and L.get('total_due') is None: L=None
    if L:
        basis='LIVE (county-taxes.com)'; checked=L['checked_at']; lpy=L.get('last_paid_year') or ''; npo=L.get('not_payable_online')
        yl=sorted(L['years']); amt=L['total_due']; ny=len(yl) if yl else (0 if not amt else None)
        parts=[f"TY{y} ${v:,.2f}" if v else f"TY{y}" for y,v in sorted(L['years'].items())]
        st=(f"UNPAID - total due ${amt:,.2f} live" + (": "+', '.join(parts) if parts else '') + (f"; ${L['not_payable_online']:,.2f} not payable online" if L.get('not_payable_online') else '')) if amt else 'PAID - $0 due (live)'
        cl=L.get('certificates') or []
        certs=(f"{len(cl)} outstanding: "+'; '.join('#'+c['number']+(f" TY{c['year']}" if c.get('year') else '')+(f" issued {c['issued']}" if c.get('issued') else '')+(f" face ${c['face']:,.2f}" if c.get('face') else '')+(f" rate {c['rate']}%" if c.get('rate') is not None else '') for c in cl)) if cl else ('None outstanding' if 'reader' in L['source'] or amt==0 else 'not captured')
        td=L.get('tax_deed_app')
        tdapp=(f"YES - application #{td['number']} {td.get('status','')} {td.get('date','')}".strip()) if td else 'None shown on live bill'
        st+=f" [{L['source']}]"
    # score
    best=collections.defaultdict(int)
    for s in p['signals']:
        c=cats(dict(signals=[s])).pop()
        best[c]=max(best[c],s.get('pts',0))
    if tx:
        best['tax']=(15 if tx['on26'] else 5)+(10 if tx['on26'] and tx['on25'] else 0)+(5 if any(int(y)<int(2025 if tx['on26'] else 2024) for y in tx['years']) else 0)
        a=amt or 0; best['tax']+=(5 if a>=25000 else 0)+(5 if a>=100000 else 0)
    if L:
        best.pop('tax',None)
        if amt:
            best['tax']=15+(10 if (ny or 0)>=2 or len(L.get('certificates') or [])>=2 else 0)+((10 if 'auction' in best else 25) if L.get('tax_deed_app') else 0)+(5 if amt>=25000 else 0)+(5 if amt>=100000 else 0)+(5 if any(int(y)<=2023 for y in L['years']) else 0)
    ncode=sum(1 for s in p['signals'] if s['type'].startswith('Code enforcement'))
    if ncode>1: best['code']+=5
    score=sum(best.values())+5*max(0,len(best)-1)
    sigs=sorted(set(s['type'] for s in p['signals']))
    fut=sorted([s['date'] for s in p['signals'] if s.get('date') and s['date']>=TODAY.isoformat() and ('auction' in s['type'] or 'Unsafe' in s['type'])])
    lat=sorted([s['date'] for s in p['signals'] if s.get('date')],reverse=True)
    auc=[s for s in p['signals'] if 'auction' in s['type']]
    urls=[]
    for s in p['signals']:
        if s['url'] not in urls: urls.append(s['url'])
    cases=[s['case'] for s in p['signals'] if s.get('case') and not s['type'].startswith('Delinquent')]
    notes=[s['note'] for s in p['signals'] if s.get('note')]
    r=dict(distress_score=score,county=p['county'],address=p.get('address'),city=p.get('city'),folio_parcel_id=ff(p),property_type=t,
        corner_retail_flag='Y' if cr else '',warehouse_industrial_flag='Y' if ind else '',commercial_condo_flag='Y' if condo else '',
        land_use_code=p.get('luc'),land_use_desc=p.get('lucdesc'),owner=p.get('owner'),owner_entity_status=ent,owner_entity_source=ent_src or (sunbiz(o1) if ent else ''),
        current_tax_status=st,years_delinquent=ny,amount_due_now=round(amt,2) if amt else None,certificates_outstanding=certs,tax_deed_application=tdapp or ('None found (upcoming auction calendars Oct-Dec 2026)'),tax_data_basis=basis,tax_status_checked_at=checked,last_paid_year=lpy,not_payable_online_amount=npo,
        signal_count=len(best),signal_categories=', '.join(sorted(best)),all_signals=' | '.join(sigs),
        next_key_date=fut[0] if fut else '',latest_signal_date=lat[0] if lat else '',case_numbers='; '.join(cases[:6]),
        auction_amount=(auc[0]['amount'] if auc else None),auction_amount_label=(auc[0]['amount_label'] if auc else ''),
        assessed_value=p.get('assessed'),market_value=p.get('market'),lot_sqft=p.get('lot'),bldg_sqft=p.get('bldg'),
        source_urls=' ; '.join(urls),property_appraiser_url=paurl(p),tax_status_check_url=taxurl(p),notes=' / '.join(notes)[:600])
    rows.append(r)
    queue.append(dict(key=k,county=p['county'],folio=p['folio'],address=p.get('address'),property_type=t,corner=cr,industrial=ind,condo=condo,ncat=len(best),auction=('auction' in best),tax=bool(tx),url=taxurl(p)))
    for s in p['signals']:
        detail.append(dict(county=p['county'],folio_parcel_id=ff(p),address=p.get('address'),property_type=t,signal=s['type'],date=s.get('date'),case_or_ref=s.get('case'),amount=s.get('amount'),amount_label=s.get('amount_label'),source_url=s['url'],note=s.get('note','')))
df=pd.DataFrame(rows)
TP={'gas station':0,'fast food':1,'convenience store':2,'vacant commercial (former gas station)':3,'restaurant (freestanding/sit-down)':4,'retail store':5,'strip / shopping center':6}
df['_tp']=df.property_type.map(lambda v:TP.get(v,9))
df=df.sort_values(['distress_score','signal_count','amount_due_now','_tp'],ascending=[False,False,False,True]).drop(columns='_tp')
df.insert(0,'rank',range(1,len(df)+1))
dd=pd.DataFrame(detail)
df.to_csv('../distressed_commercial.csv',index=False)
q=pd.DataFrame(queue)
def tier(r):
    if r.ncat>=2 or r.auction: return 1
    if r.condo: return 9
    if (r.corner or r.industrial) and r.tax: return 2
    if r.tax: return 3
    return 4
q['tier']=q.apply(tier,axis=1); q=q[q.tier<9].sort_values(['tier']); q.to_csv('live_tax_queue.csv',index=False)
print('queue tiers',q.tier.value_counts().sort_index().to_dict())
src=pd.DataFrame([
 ('MDC 2026 delinquent RE tax ad (PDF, May 2026)','https://www.miamidade.gov/resources/legal-ads/county/tax-collector/2026/2026-05-20-public-notice-delinquent-property-taxes.pdf.pdf','Worked - 39,358 records parsed','Annual (May)'),
 ('MDC 2025 delinquent RE tax ad (PDF, May 2025)','https://www.miamidade.gov/resources/legal-ads/2025/2025-05-28-delinquent-real-estate-property-taxes.pdf','Worked - 39,448 records; used for multi-year delinquency','Annual'),
 ('Broward 2026 RE delinquent ad list (PDF via browardcountylegalnotices.com)','https://auth-api.transform.civicplus.com/storage/forms/40563/attachments/893ed383-58f9-444e-89ba-8526e8fc9a60','Worked - 32,010 records (notice page https://browardcountylegalnotices.com/real-estate-and-tangible-taxes-advertisement-lists-for-tax-certificate-auction)','Annual (Apr)'),
 ('Broward 2025 RE delinquent ad list (PDF)','https://auth-api.transform.civicplus.com/storage/forms/40563/attachments/fb09cc3f-24a5-4dac-a6cf-c9af27b717bd','Worked - 31,878 records','Annual'),
 ('FDOR statewide cadastral (Broward land use/value)','https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0','Worked (PARCEL_ID IN batches; slow ~25 s/150)','Annual roll'),
 ('MDC parcel GIS (DOR 10-49)','https://gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer/26','Worked - 32,440 commercial+industrial parcels','Daily-ish'),
 ('RealAuction calendars (MDC FC+TD, Broward FC, Broward TD)','https://miamidade.realforeclose.com ; https://broward.realforeclose.com ; https://broward.realtaxdeed.com','Worked (browser UA). Oct-Dec 2026 calendars','Daily'),
 ('MDC Code Compliance violations/liens','https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/CCVIOL_gdb/FeatureServer/0','Worked (unincorporated MDC)','Daily'),
 ('City of Miami 40-yr recertification','https://services1.arcgis.com/CvuPhqcTQpZPT9qY/arcgis/rest/services/40_Year_Recertification/FeatureServer/0','Worked - 1,907 pending/NOT approved; 764 comm/ind folios','Daily (edited Oct 2026)'),
 ('MDC Unsafe Structures Board notices/agendas','https://www.miamidade.gov/global/government/boards/unsafe-structures.page','Worked (PDF; Oct 14 2026 notice + Jun/Jul/Sep agendas; address-matched)','Monthly'),
 ('FDEP storage tanks (closed retail stations)','https://ca.dep.state.fl.us/arcgis/rest/services/OpenData/DWM_STCM/MapServer/1','Worked','Weekly'),
 ('OpenCorporates FL company search (Sunbiz mirror)','https://opencorporates.com/companies/us_fl?q=','Worked (web search page, active/inactive only; ~3-6 s/query; dissolution reason/date needs login or Sunbiz)','On demand'),
 ('CourtListener RECAP search (FL bankruptcy courts)','https://www.courtlistener.com/api/rest/v4/search/?type=r','Worked anonymously (exact owner-name match, filed 2021+)','On demand'),
 ('Tax collector live status (Grant Street county-taxes.com)','https://miamidade.county-taxes.com/public/real_estate/parcels/<folio> ; https://broward.county-taxes.com/public/real_estate/parcels/<folio>','BLOCKED - Cloudflare Turnstile "Verify you are human" checkbox in headless & headful Chrome; Apify rag-web-browser returned 0 pages. Needs a human browser session.',''),
 ('Miami-Dade Clerk Official Records (lis pendens)','https://onlineservices.miamidadeclerk.gov/officialrecords/','Needs login (anonymous users get Turnstile; site says "Login to avoid verification challenges")',''),
 ('Broward Official Records (lis pendens)','https://officialrecords.broward.org/AcclaimWeb/','BLOCKED - Cloudflare challenge',''),
 ('Broward Clerk case search (foreclosure filings)','https://www.browardclerk.org/Web2','Needs captcha in browser',''),
 ('Sunbiz','https://search.sunbiz.org','BLOCKED - Cloudflare (used OpenCorporates mirror instead); bulk SFTP sftp.floridados.gov port 22 closed from box',''),
 ('LienHub (certificate/tax deed app status)','https://lienhub.com','BLOCKED - Cloudflare',''),
],columns=['source','url','status','refresh'])
legend=pd.DataFrame([
 ('Auction scheduled (foreclosure or tax deed)',35),('Foreclosure lawsuit filed (news/court)',30),('Unsafe structure board hearing',25),('Owner bankruptcy (CourtListener)',25),
 ('Delinquent tax on 2026 ad (estimate) / unpaid on LIVE bill',15),('LIVE: 2+ unpaid years or 2+ certificates','+10'),('LIVE: tax deed application filed (+10 if a tax deed auction is already counted)','+25'),('LIVE: unpaid year 2023 or older','+5'),('LIVE: paid ($0 due)','0 for tax'),('...also on 2025 ad (2+ years)','+10'),('...back-year taxes listed','+5'),('...amount >= $25k / >= $100k','+5 / +5'),('Only on 2025 ad (later paid)',5),
 ('MDC code lien / county lis pendens',20),('...multiple code cases','+5'),('City of Miami recert overdue (recert yr <=2022 / later)','15 / 10'),('Owner entity inactive (FL registry)',15),('Closed gas station (FDEP)',10),('Fast-food closure (franchisee Ch.11)',10),
 ('Each additional signal category beyond the first','+5')],columns=['component','points'])
with pd.ExcelWriter('../distressed_commercial.xlsx',engine='openpyxl') as w:
    df.to_excel(w,sheet_name='All leads by score',index=False)
    df[df.tax_data_basis.str.startswith('LIVE')].to_excel(w,sheet_name='Live tax checked',index=False)
    df[df.corner_retail_flag=='Y'].to_excel(w,sheet_name='Corner retail',index=False)
    df[df.warehouse_industrial_flag=='Y'].to_excel(w,sheet_name='Warehouse-industrial',index=False)
    dd.to_excel(w,sheet_name='Signals detail',index=False)
    legend.to_excel(w,sheet_name='Score legend',index=False)
    src.to_excel(w,sheet_name='Sources & blocks',index=False)
    for ws in w.book.worksheets:
        ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width=min(45,max(8,max(len(str(c.value or '')) for c in col[:200])+2))
json.dump(dict(n=len(df)),open('build2_stats.json','w'))
print(len(df), 'corner',(df.corner_retail_flag=='Y').sum(),'ind',(df.warehouse_industrial_flag=='Y').sum(),'condo',(df.commercial_condo_flag=='Y').sum())
print(dd.groupby('signal').folio_parcel_id.nunique().to_string())
print(df.property_type.value_counts().to_string())
print(df.signal_count.value_counts().to_string())
pd.set_option('display.width',250);pd.set_option('display.max_colwidth',60)
print(df.head(20)[['rank','distress_score','county','address','city','folio_parcel_id','property_type','signal_categories','amount_due_now','years_delinquent','tax_data_basis','certificates_outstanding','tax_deed_application','owner','owner_entity_status','next_key_date','case_numbers','auction_amount']].to_csv(sep='|'))
