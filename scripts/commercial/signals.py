import json,re,datetime,collections
P={}  # key -> parcel
MDPDF26="https://www.miamidade.gov/resources/legal-ads/county/tax-collector/2026/2026-05-20-public-notice-delinquent-property-taxes.pdf.pdf"
MDPDF25="https://www.miamidade.gov/resources/legal-ads/2025/2025-05-28-delinquent-real-estate-property-taxes.pdf"
BW26="https://auth-api.transform.civicplus.com/storage/forms/40563/attachments/893ed383-58f9-444e-89ba-8526e8fc9a60"
BW25="https://auth-api.transform.civicplus.com/storage/forms/40563/attachments/fb09cc3f-24a5-4dac-a6cf-c9af27b717bd"
CCV="https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/CCVIOL_gdb/FeatureServer/0/query?where=CASE_NUM%3D%27{}%27&outFields=*&f=html"
REC="https://services1.arcgis.com/CvuPhqcTQpZPT9qY/arcgis/rest/services/40_Year_Recertification/FeatureServer/0/query?where=FolioNumber%3D%27{}%27&outFields=*&f=html"
USB="https://www.miamidade.gov/resources/legal-ads/county/regulatory-economic-resources/2026/2026-10-14-unsafe-structures-board-public-notice-legal-ads.pdf"
C=json.load(open('mdc_comind_parcels.json'))
cad=json.load(open('bw_cadastral.json'))
def getp(county,folio,**info):
    k=('MD:' if county=='Miami-Dade' else 'BW:')+folio
    p=P.setdefault(k,dict(county=county,folio=folio,signals=[]))
    for a,b in info.items():
        if b not in (None,'') and not p.get(a): p[a]=b
    return p
def mdinfo(f):
    p=C.get(f)
    if not p: return {}
    return dict(address=(p.get('TRUE_SITE_ADDR') or '').strip(),city=(p.get('TRUE_SITE_CITY') or '').strip(),luc=p['DOR_CODE_CUR'],lucdesc=p['DOR_DESC'],owner='; '.join(filter(None,[p.get('TRUE_OWNER1'),p.get('TRUE_OWNER2')])))
def bwinfo(f):
    v=cad.get(f)
    if not v: return {}
    return dict(address=v['PHY_ADDR1'],city=v['PHY_CITY'],luc=v['DOR_UC'],owner=v['OWN_NAME'],market=v['JV'],lot=v['LND_SQFOOT'],bldg=v['TOT_LVG_AR'],yrblt=v['ACT_YR_BLT'],bw_condo=(not v['LND_SQFOOT']))
def money(v):
    if v in (None,''): return None
    if isinstance(v,(int,float)): return float(v)
    s=re.sub(r'[^\d.]','',str(v)); return float(s) if s else None
def sig(p,**s): p['signals'].append(s)
# 1 auctions
for x in json.load(open('auctions_enriched.json')):
    pa=x['pa']
    if 'err' in pa: continue
    c=(pa.get('luc') or '')[:2]
    if not (c.isdigit() and 10<=int(c)<=49): continue
    county='Miami-Dade' if x['site'].startswith('miamidade') else 'Broward'
    f=re.sub(r'[^0-9A-Za-z]','',x['Parcel ID'])
    td=x['Auction Type']=='TAXDEED'; cz=x.get('cityzip') or ''
    p=getp(county,f,address=x.get('Property Address'),city=cz.split(',')[0].strip(),luc=pa.get('luc'),lucdesc=pa.get('lucdesc'),owner=pa.get('owner'),market=money(pa.get('market')),assessed=money(pa.get('assessed')),lot=money(pa.get('lot')),bldg=money(pa.get('bldg')))
    sig(p,type='Tax deed auction scheduled' if td else 'Foreclosure auction scheduled',date=datetime.datetime.strptime(x['date'],'%m/%d/%Y').date().isoformat(),
        case=x.get('Case #')+(f" (cert {x.get('Certificate #')})" if td else ''),amount=money(x.get('Opening Bid') if td else x.get('Final Judgment Amount')),amount_label='Opening bid' if td else 'Final judgment',
        url=f"https://{x['site']}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={x['date']}",pts=35)
    if td: p['tax_deed_app']=f"Yes - tax deed application filed; auction {x['date']} (case {x.get('Case #')})"
# 2 MDC delinquent ads
for f,o in json.load(open('mdc_delinq_ci.json')).items():
    p=getp('Miami-Dade',f,**mdinfo(f))
    yrs=set();tot26=0
    for ad,lst in o['ads'].items():
        for e in lst:
            yrs.add(e['yr'])
            if ad=='2026': tot26+=e['amt'] or 0
        amt=sum(e['amt'] or 0 for e in lst)
        sig(p,type=f'Delinquent tax - on {ad} delinquent-tax ad',date=('2026-05-20' if ad=='2026' else '2025-05-28'),case='Ad #'+', #'.join(e['adno']+f" (TY{e['yr']})" for e in lst),
            amount=amt,amount_label=f'Advertised delinquent amount ({ad} ad)',url=MDPDF26 if ad=='2026' else MDPDF25,pts=0)
    p['tax']=dict(on26='2026' in o['ads'],on25='2025' in o['ads'],years=sorted(yrs),amt26=tot26 if '2026' in o['ads'] else None,amt25=sum(e['amt'] or 0 for e in o['ads'].get('2025',[])) or None)
# 3 Broward delinquent ads
for ad,fn in (('2026','bw_delinq_recs.json'),('2025','bw_delinq_recs_2025.json')):
    by=collections.defaultdict(list)
    for r in json.load(open(fn)): by[r['folio']].append(r)
    for f,lst in by.items():
        v=cad.get(f)
        if ad=='2025' and ('BW:'+f) not in P: continue  # 2025-only Broward parcels: no land-use lookup, skip
        if ad=='2026' and not (v and v['DOR_UC'] and 10<=int(v['DOR_UC'])<=49): continue
        p=getp('Broward',f,**bwinfo(f))
        sig(p,type=f'Delinquent tax - on {ad} delinquent-tax ad',date=('2026-04-21' if ad=='2026' else '2025-04-15'),case='Ad #'+', #'.join(e['adno']+f" (TY{e['yr']})" for e in lst),
            amount=sum(e['amt'] for e in lst),amount_label=f'Advertised delinquent amount ({ad} ad)',url=BW26 if ad=='2026' else BW25,pts=0)
        t=p.setdefault('tax',dict(on26=False,on25=False,years=[],amt26=None,amt25=None))
        t['on'+ad[2:]]=True; t['years']=sorted(set(t['years'])|{e['yr'] for e in lst}); t['amt'+ad[2:]]=sum(e['amt'] for e in lst)
# 4 CCVIOL
by=collections.defaultdict(list)
for x in json.load(open('ccviol_liens.json')):
    f=x['FOLIO'].strip()
    if f in C: by[f].append(x)
for f,cs in by.items():
    p=getp('Miami-Dade',f,**mdinfo(f))
    for c in cs:
        st=c['STAT_DESC'].strip(); lr=(c['LN_RECDATE'] or '').strip()
        d=None
        for fmt in ('%m/%d/%Y','%Y-%m-%d'):
            try: d=datetime.datetime.strptime(lr,fmt).date();break
            except: pass
        if not d and c['CASE_DATE']: d=datetime.datetime.fromtimestamp(c['CASE_DATE']/1000,datetime.UTC).date()
        sig(p,type='Code enforcement lien (MDC)' if st=='Lien' else 'Code enforcement lis pendens (MDC Active LP)',date=d.isoformat() if d else None,case=c['CASE_NUM'].strip(),amount=None,amount_label='',
            url=CCV.format(c['CASE_NUM'].strip()),note=f"Problem: {(c['PROBLEM_DESC'] or '').strip()}; lien rec {lr or 'n/a'} {('Bk '+c['LN_RECBOOK'].strip()+' Pg '+c['LN_RECPAGE'].strip()) if c['LN_RECBOOK'].strip() else ''}",pts=20)
# 5 City of Miami recert
for x in json.load(open('com_recert.json')):
    f=x['FolioNumber']
    if f not in C: continue
    p=getp('Miami-Dade',f,**mdinfo(f))
    if any(s['type'].startswith('Building recert') and s['case']==x['PlanNumber'] for s in p['signals']): continue
    sig(p,type='Building recertification overdue (City of Miami 40/50-yr, pending/NOT approved)',date=x['SubmittedDate'] and datetime.datetime.fromtimestamp(x['SubmittedDate']/1000).date().isoformat(),
        case=x['PlanNumber'] or '',amount=None,amount_label='',url=REC.format(f),note=f"Recert year {x['RecertificateYear']}; bldg #{x['BuildingNumber']}; plan status {x['PlanStatus']}; yr built {x['YearBuilt']}",pts=15 if int(x['RecertificateYear'])<=2022 else 10)
# 6 Unsafe structures (address match)
def norm(a): 
    a=re.sub(r'\b(AKA|BLDG?|BLD)\b.*$','',a.upper()); a=a.replace('TERR','TER').replace(' AV ',' AVE ')
    return re.sub(r'\s+',' ',a).strip()
A=collections.defaultdict(list)
for f,v in C.items(): A[norm(v.get('TRUE_SITE_ADDR') or '')].append(f)
us=json.load(open('usb/usb_oct14.json'))
seen=set()
for u in us:
    n=norm(u['Property Address'])
    for f in A.get(n,[]):
        if (f,n) in seen: continue
        seen.add((f,n)); p=getp('Miami-Dade',f,**mdinfo(f))
        sig(p,type='Unsafe structure - repair or demolish hearing (MDC Unsafe Structures Board)',date='2026-10-14',case=u['Case No.'],amount=None,amount_label='',url=USB,note=u['Action']+'; owner on notice: '+u['Owner of Record'],pts=25)
for u in json.load(open('usb/usb_agendas.json')):
    n=norm(u['addr'])
    for f in A.get(n,[]):
        if (f,n) in seen: continue
        seen.add((f,n)); p=getp('Miami-Dade',f,**mdinfo(f))
        d=re.search(r'(2026-\d\d-\d\d)',u['file'])
        sig(p,type='Unsafe structure case on MDC Unsafe Structures Board agenda',date=d.group(1) if d else None,case='',amount=None,amount_label='',url='https://www.miamidade.gov/resources/economy/board-and-code/unsafe-structures/'+u['file'],note='Listed address '+u['addr'],pts=20)
# 7 FDEP closed gas
sf=set()
for x in json.load(open('gas_matched.json')):
    pp=x['parcel']
    if not pp: continue
    code=pp.get('luc') or ''; desc=(pp.get('lucdesc') or '').upper()
    if not (code[:2] in('26','10') or 'CONVENIENCE' in desc): continue
    a=x['attributes']; county='Miami-Dade' if a['COUNTY']=='MIAMI-DADE' else 'Broward'
    if pp['folio'] in sf: continue
    sf.add(pp['folio'])
    p=getp(county,pp['folio'],address=pp.get('site'),city=pp.get('muni'),luc=code,lucdesc=pp.get('lucdesc'),owner=pp.get('owner'),market=money(pp.get('market')),assessed=money(pp.get('assessed')),lot=money(pp.get('lot')),bldg=money(pp.get('bldg')),fdep=True)
    p['fdep']=True
    sig(p,type=f"Closed gas station (FDEP tank facility {a['FACILITY_STATUS']})",date=None,case=f"FDEP {a['FACILITY_ID']}",amount=None,amount_label='',url=a['DOCUMENTS'] or 'https://ca.dep.state.fl.us/arcgis/rest/services/OpenData/DWM_STCM/MapServer/1',
        note=f"'{a['FACILITY_NAME']}' {a['FACILITY_STATUS']}; no open retail station within ~80 m; cleanup {a['FACILITY_CLEANUP_STATUS'] or 'n/a'}",pts=10)
# 8 manual news
from enrich import md
for f,typ,d,case,url,note,pts in [
 ('0141050080380','Foreclosure lawsuit filed (Ocean Bank v. Aurora Investment & Holdings LLC)','2026-07-30','Miami-Dade circuit (number masked on UniCourt)','https://unicourt.com/case/fl-mda5-case7j27b32514aa7e-129398','Aurora operates the station; fee owner Lejeune Westar Petroleum LLC - may target leasehold',30),
 ('3660050670010','Fast-food closure - Popeyes franchisee Sailormen Inc. Ch.11 lease rejection','2026-06-30','Sailormen Inc. Ch.11','https://www.jacksonville.com/story/news/2026/06/30/florida-popeyes-franchisee-bankruptcy-closings/90735448007/','Shopping-center parcel (South Dade Shopping LLC) - pad lease opportunity, landlord not distressed',10)]:
    n=md(f); p=getp('Miami-Dade',f,**mdinfo(f)); 
    for a,b in dict(market=money(n.get('market')),assessed=money(n.get('assessed')),lot=money(n.get('lot')),bldg=money(n.get('bldg'))).items(): p.setdefault(a,b)
    sig(p,type=typ,date=d,case=case,amount=None,amount_label='',url=url,note=note,pts=pts)
json.dump(P,open('parcels_v2.json','w'),default=str)
print(len(P),collections.Counter(p['county'] for p in P.values()))
print(collections.Counter(s['type'] for p in P.values() for s in p['signals']).most_common())
