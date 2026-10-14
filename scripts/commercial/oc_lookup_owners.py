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

