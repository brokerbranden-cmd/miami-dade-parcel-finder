import json,re,sys,os
SRC=sys.argv[1] if len(sys.argv)>1 else '/workspace/taxreader/results.jsonl'
MANUAL={}  # Branden's manual reads (kept unless a reader result exists)
if os.path.exists('live_tax_manual.json'): MANUAL=json.load(open('live_tax_manual.json'))
CSS=re.compile(r'(\.[a-zA-Z0-9_-]+(\s*,\s*\.[a-zA-Z0-9_-]+)*\s*\{[^}]*\}\s*)+')
def clean(s):
    s=CSS.sub(' ',s); s=s.replace('Print (PDF) Downloading...','').replace('Loading Add to Cart','').replace('Add to Cart','')
    return [c.strip() for c in s.split('\t')]
def money(s):
    m=re.search(r'\$([\d,]+\.\d\d)',s or ''); return float(m.group(1).replace(',','')) if m else None
def parse(r):
    hist=[clean(x) for x in r['hist']['rows']]; duetxt=CSS.sub(' ',r['due']['text'])
    total=None
    m=re.search(r'Total amount due:?\s*\$([\d,]+\.\d\d)',duetxt,re.I)
    if m: total=float(m.group(1).replace(',',''))
    elif re.search(r'paid in full|nothing due',duetxt,re.I): total=0.0
    npo=None; m=re.search(r'Not payable online:?\s*\$([\d,]+\.\d\d)',duetxt,re.I)
    if m: npo=float(m.group(1).replace(',',''))
    bills=[];certs=[];tdas=[];cur=None
    for c in hist:
        c=[x for x in c]
        first=c[0] if c else ''
        m=re.match(r'^(\d{4})\b.*\bbill\b',first,re.I)
        if m:
            cur=m.group(1); rest=' | '.join(c[1:])
            amt=money(c[1]) if len(c)>1 else None
            st='Unpaid' if 'Unpaid' in rest else ('Paid' if re.search(r'\bPaid \$',rest) else ('No Balance Due' if 'No Balance Due' in rest else rest[:40]))
            bills.append(dict(year=cur,label=first,amount=amt,status=st,not_payable_online='Not payable online' in rest,raw=rest[:200]))
            continue
        m=re.match(r'^(\d{4})\b',first)
        if m and len(first)<=6: cur=m.group(1); continue
        m=re.match(r'^Certificate #\s*(\S+)',first)
        if m:
            fm=re.search(r'Face \$([\d,]+\.\d\d)',' '.join(c)); rm=re.search(r'Rate ([\d.]+)%',' '.join(c))
            certs.append(dict(number=m.group(1),year=cur,status=c[1] if len(c)>1 else '',issue_or_status_date=c[2] if len(c)>2 else '',face=float(fm.group(1).replace(',','')) if fm else None,rate=float(rm.group(1)) if rm else None))
            continue
        m=re.match(r'^Tax Deed Application #\s*(\S+)',first)
        if m: tdas.append(dict(number=m.group(1),status=c[1] if len(c)>1 else '',date=c[2] if len(c)>2 else '',year=cur))
    if total is None:
        m=re.search(r'Total Amount Due\s*\$([\d,]+\.\d\d)',' '.join(' '.join(c) for c in hist))
        if m: total=float(m.group(1).replace(',',''))
    unpaid={}
    for b in bills:
        if (b['status']=='Unpaid' and (b['amount'] or 0)>0) or b['not_payable_online']:
            unpaid[b['year']]=round(unpaid.get(b['year'],0)+(b['amount'] or 0),2)
    out_certs=[x for x in certs if not re.search(r'Redeemed|Cancel|Paid',x['status'],re.I)]
    seen=set();oc=[]
    for x in out_certs:
        if x['number'] not in seen: seen.add(x['number']);oc.append(x)
    act=[t for t in tdas if not re.search(r'Paid off|Redeemed|Cancel|Withdrawn',t['status'],re.I)]
    td=None
    if act:
        t=act[0]; td=dict(number=t['number'],status=t['status'],date=t['date'])
    paid=[int(b['year']) for b in bills if b['status']=='Paid' and (b['amount'] or 0)==0]
    return dict(total_due=total,years={y:(v or None) for y,v in sorted(unpaid.items())},not_payable_online=npo,certificates=[dict(number=x['number'],year=x['year'],issued=x['issue_or_status_date'],face=x['face'],rate=x['rate'],status=x['status']) for x in oc],
        certificates_all=certs,tax_deed_app=td,tax_deed_apps_all=tdas,last_paid_year=str(max(paid)) if paid else None,checked_at=r['checked_at'],
        source='Live read via county-taxes.net (Branden PC reader) '+r['final_url'])
L=dict(MANUAL); n=0;nf=0;bad=0
for l in open(SRC,encoding='utf-8'):
    try: r=json.loads(l)
    except Exception: bad+=1; continue
    if not r.get('ok'): continue
    if not r.get('found'): nf+=1; continue
    try:
        if 'hist' in r: L[r['key']]=parse(r); n+=1
    except Exception as e: bad+=1; print('parse err',r['key'],e)
json.dump(L,open('live_tax.json','w'),indent=0)
print('parsed',n,'not found',nf,'bad',bad,'total live',len(L))
