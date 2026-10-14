import re
def dor2(p):
    c=str(p.get('luc') or '')
    if p['county']=='Broward' and len(c)==3: return c[1:]
    return c[:2]
def ptype(p):
    c=dor2(p); d=(p.get('lucdesc') or '').upper(); fdep=p.get('fdep')
    condo=(('CONDO' in d or 'TOTAL VALUE' in d) and p['county']=='Miami-Dade') or bool(p.get('bw_condo') and c not in ('10','40'))
    ind=c.isdigit() and 40<=int(c)<=49
    if c=='26' or 'SERVICE STATION' in d: t,cr='gas station',True
    elif c=='22' or 'FAST FOOD' in d or 'DRIVE-IN' in d: t,cr='fast food',True
    elif 'CONVENIENCE' in d: t,cr='convenience store',True
    elif c=='21': t,cr='restaurant (freestanding/sit-down)',True
    elif c=='10' and fdep: t,cr='vacant commercial (former gas station)',True
    elif c=='11': t,cr='retail store',True
    elif c=='16': t,cr='strip / shopping center',True
    elif c=='10': t,cr='vacant commercial land',False
    elif c=='12': t,cr='mixed use (store/office/residential)',False
    elif c=='27': t,cr='auto sales/repair',False
    elif c=='39': t,cr='hotel/motel',False
    elif c in ('17','18','19'): t,cr='office',False
    elif c=='28': t,cr='parking lot / mobile home park',False
    elif c in('48',): t,cr=('mini-storage' if 'MINI' in d or 'SELF' in d else 'warehouse / distribution / storage'),False
    elif c=='49': t,cr='open storage / industrial yard',False
    elif c=='41': t,cr='light manufacturing / flex',False
    elif c in ('42','43','44','45','46','47'): t,cr='heavy industrial / processing',False
    elif c=='40': t,cr='vacant industrial land',False
    elif c in('13','14','15'): t,cr='department store / supermarket / regional center',False
    elif c in('23','24','25'): t,cr='financial / insurance / service shop',False
    elif c in('29','30','31','32','33','34','35','36','37','38'): t,cr='other commercial (wholesale/florist/recreation etc.)',False
    elif c=='20': t,cr='airport/marina/terminal',False
    else: t,cr='other commercial',False
    if condo:
        t='commercial condo unit ('+t+')'; cr=False
    return t,cr,ind,condo
def cats(p):
    s=set()
    for x in p['signals']:
        t=x['type']
        if t.startswith('Delinquent tax'): s.add('tax')
        elif 'auction' in t: s.add('auction')
        elif t.startswith('Code enforcement'): s.add('code')
        elif t.startswith('Building recert'): s.add('recert')
        elif t.startswith('Unsafe'): s.add('unsafe')
        elif t.startswith('Closed gas'): s.add('closed_gas')
        elif t.startswith('Owner entity'): s.add('entity')
        elif 'ankrupt' in t: s.add('bankruptcy')
        else: s.add('news/court')
    return s
