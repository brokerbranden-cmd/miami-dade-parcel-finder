import json,re,time,requests,urllib.parse,os,html
from classify import *
P=json.load(open('parcels_v2.json'))
ENT=re.compile(r'\b(LLC|L L C|INC|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLLP|LLP|PLLC|INCORPORATED|LIMITED|PARTNERSHIP|ENTERPRISES|HOLDINGS)\b')
def amt(p):
    t=p.get('tax') or {}; return (t.get('amt26') or 0)
rank=[]
for k,p in P.items():
    t,cr,ind,condo=ptype(p); cs=cats(p)
    if not(cr or ind or len(cs)>=2): continue
    o=(p.get('owner') or '').split(';')[0].strip()
    if not ENT.search(o.upper()): continue
    rank.append((-(len(cs)>=2), -(cr or ind), -amt(p), o))
rank.sort()
owners=[];seen=set()
for r in rank:
    if r[3] not in seen: seen.add(r[3]); owners.append(r[3])
print(len(owners),flush=True)
out=json.load(open('oc_status.json')) if os.path.exists('oc_status.json') else {}
UA={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'}
def n(s): 
    s=html.unescape(s).upper().replace('&','AND')
    s=re.sub(r'\bL\.?\s?L\.?\s?C\.?','LLC',s); s=re.sub(r'\bINCORPORATED\b','INC',s);s=re.sub(r'\bCORPORATION\b','CORP',s);s=re.sub(r'\bCOMPANY\b','CO',s)
    return re.sub(r'[^A-Z0-9]','',s)
fails=0
for i,o in enumerate(owners):
    if o in out: continue
    q=re.sub(r'[^A-Za-z0-9& ]',' ',o)
    url='https://opencorporates.com/companies/us_fl?q='+urllib.parse.quote_plus(q)
    try:
        r=requests.get(url,headers=UA,timeout=30)
    except Exception as e:
        time.sleep(10);continue
    if r.status_code!=200:
        fails+=1; print('HTTP',r.status_code,o,flush=True)
        if fails>5: break
        time.sleep(30); continue
    res=re.findall(r'company_search_result ([a-z ]*)" href="(/companies/us_fl/[^"]+)"[^>]*>([^<]*)<',r.text)
    m=[x for x in res if n(x[2])==n(o)]
    if not m: m=[x for x in res if n(x[2]).startswith(n(o)) and len(n(o))>=12]
    if m:
        st=sorted(set('Active' if x[0].strip()=='active' else 'Inactive' for x in m))
        out[o]=dict(status='/'.join(st),matches=[dict(name=html.unescape(x[2]),url='https://opencorporates.com'+x[1],active=x[0].strip()=='active') for x in m[:3]],search=url)
    else: out[o]=dict(status='Not found (FL)',matches=[],search=url)
    if i%20==0:
        json.dump(out,open('oc_status.json','w'),indent=0); print(i,o,out[o]['status'],flush=True)
    time.sleep(2.0)
json.dump(out,open('oc_status.json','w'),indent=0); print('done',len(out),flush=True)
