
(() => {
"use strict";
const $ = id => document.getElementById(id);
const PFC = window.PFCounty, DP = PFC.dp, HAS = PFC.has;   /* active county (counties.js): data folder, layers, storage keys */
const fmt = new Intl.NumberFormat('en-US');
const money = v => v>=1e9 ? '$'+(v/1e9).toFixed(1)+'B' : v>=1e6 ? '$'+(v/1e6).toFixed(v>=1e7?1:2).replace(/\.?0+$/,'')+'M' : v>=1e3 ? '$'+Math.round(v/1e3)+'K' : '$'+fmt.format(v);
const dollars = v => '$'+fmt.format(v);
const SQFT_AC = 43560;
const DAY0 = Date.UTC(1900,0,1);
const today = Math.floor((Date.now()-DAY0)/86400000);
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const dt = d => new Date(DAY0+d*86400000);
const dateStr = d => { if(!d) return ''; const t=dt(d); return (t.getUTCMonth()+1)+'/'+t.getUTCDate()+'/'+t.getUTCFullYear(); };
const monYr = d => { const t=dt(d); return MON[t.getUTCMonth()]+' '+t.getUTCFullYear(); };
const folioFmt = f => f.length===13 ? f.slice(0,2)+'-'+f.slice(2,6)+'-'+f.slice(6,9)+'-'+f.slice(9) : f;
const acres = sf => sf>=SQFT_AC*10 ? fmt.format(Math.round(sf/SQFT_AC))+' acres' : (sf/SQFT_AC).toFixed(2)+' acres';
const esc = s => String(s).replace(/[&<>"]/g, ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
/* distress signals: bit order matches scripts/build_distress.py SIG (0-11) + soft owner/property bits set in build_data.py (12-15) */
const DSIG=[['FC','Foreclosure sale','hot'],['LP','Lis pendens','hot'],['TD','Tax deed','hot'],['TC','Tax certificates','warm'],['TX','Delinquent taxes','warm'],['US','Unsafe structure','hot'],['BV','Building violation','warm'],['CC','Code case','warm'],['LN','Lien','warm'],['RC','Recert overdue','warm'],['PR','Probate / estate','hot'],['DC','Owner deceased','hot']];
const DSOFT=[[12,'Absentee / out of state'],[13,'Owned 20+ years'],[14,'Low building value'],[15,'No homestead']];
const DBIT=Object.fromEntries(DSIG.map((d,i)=>[d[0],i]));
/* vacancy / neglect hint: bit order matches scripts/vacancy_lib.py VSIG (points shown are the defaults; see README) */
const VSIG=[['NA','No homestead + absentee',15],['US','Unsafe structure case',25],['NG','Neglect code case',15],['FR','Foreclosure registry',12],['XP','Expired / revoked permit',8],['NP','No permit in city data window',6],['LO','Owned 20+ years',5],['LB','Building < 20% of value',8],['TX','Tax delinquent',10],['ES','Estate / deceased',8],['OV','Other open case',4],['RP','Recent permit',-15]];
const VBIT=Object.fromEntries(VSIG.map((d,i)=>[d[0],i]));
/* permits & code cases: bit order of the pack column 'pcs' (scripts/permit_lib.py PCS); PCOV = per-city coverage table (meta.permitCov) */
let PCOV={};
const PCS=[['PO','Open permit'],['PX','Expired / revoked permit'],['P5','Permit in last 5 yrs'],['PN','No permit in city data window'],['CO','Open code case'],['C5','Code case in last 5 yrs'],['CL','Code lien / fines'],['PC','City has permit data']];
const PBIT=Object.fromEntries(PCS.map((d,i)=>[d[0],i]));
const pcsText=g=>{ const a=[]; for(let b=0;b<7;b++) if(g&(1<<b)) a.push(PCS[b][1]); return a.join(', '); };
const pcsCodes=g=>{ const a=[]; for(let b=0;b<7;b++) if(g&(1<<b)) a.push(PCS[b][0]); return a.join(' '); };
const VS_STEPS=[[0,'Any'],[25,'25+ possible'],[40,'40+ likely'],[60,'60+ strong']];
const vsTone=v=>v>=60?'v3':v>=40?'v2':v>=25?'v1':'v0';
const vsWord=v=>v>=60?'Strong vacancy hint':v>=40?'Likely vacant / neglected':v>=25?'Possibly vacant':'';
const DS_STEPS=[[0,'Any score'],[20,'20+'],[35,'35+'],[50,'50+ (hot)'],[70,'70+']];
const dsTone=v=>v>=50?'s4':v>=35?'s3':v>=20?'s2':v>0?'s1':'s0';
let DIST=null, distP=null;
/* owner portfolios (data/owners.json.gz from scripts/owners_lib.py; parcel -> group id in the 'og' column) */
let OWN=null, ownP=null;
const loadOwners=()=>OWN?Promise.resolve(OWN):(ownP||(ownP=(async()=>{ if(!META.ownersFile) return null; const r=await fetch(DP+META.ownersFile+'?v='+META.ver); if(!r.ok) throw new Error('Owner data did not load');
  const j=JSON.parse(dec.decode(await gunzip(new Uint8Array(await r.arrayBuffer()))));
  OWN={n:Uint32Array.from(j.n), nd:Uint32Array.from(j.nd), nc:Uint32Array.from(j.nc), mv:Float64Array.from(j.mv), fl:Uint8Array.from(j.fl), name:j.name, nv:j.nv}; return OWN; })().catch(e=>{ ownP=null; throw e; })));
const OGFL=[[1,'Government'],[2,'Bank / lender'],[4,'Association, church or non-profit'],[8,'Large holder (200+ parcels)']];
const ogFlags=f=>OGFL.filter(([b])=>f&b).map(x=>x[1]);
const loadDistress=()=>distP||(distP=(async()=>{ if(!META.distressFile) return null; const r=await fetch(DP+META.distressFile+'?v='+META.ver); if(!r.ok) throw new Error('Distress data did not load'); DIST=JSON.parse(dec.decode(await gunzip(new Uint8Array(await r.arrayBuffer())))); return DIST; })().catch(e=>{ distP=null; throw e; }));
const FLAG = {homestead:1, oos:2, absz:4, corp:8, trust:16, govt:32, estate:64, senior:128};
const MZ_MIAMI=[['T3','Sub-urban (single family, duplex)'],['T4','General urban (small apartments)'],['T5','Urban center (up to 5 stories)'],['T6','Urban core (8+ stories)'],['CI','Civic institution'],['CS','Civic space'],['D1','Work place'],['D2','Industrial'],['D3','Waterfront industrial']];
const MZ_COUNTY=[['RU-1','Single family'],['RU-2','Duplex'],['RU-TH','Townhouse'],['RU-3','Small multifamily'],['RU-4','Apartments'],['RU-5','Residential / office'],['EU','Estates'],['BU','Business'],['IU','Industrial'],['GU','Interim'],['PAD','Planned area development']];
const OWNER_KINDS = [['all','All owners'],['person','Individuals'],['corp','Companies & organizations'],['trust','Trusts']];
const OWNER_ROWS = [
  ['homestead','Owner lives there (homestead)'],['oos','Owner mails from out of state'],['absz',window.PFCounty&&PFCounty.cfg.area?'Absentee: owner mails outside '+PFCounty.cfg.area:'Owner mails to a different ZIP'],
  ['corp','Owned by a company or organization'],['trust','Owned by a trust'],['estate','Estate or heirs'],['senior','Senior exemption']];
/* transfer / owner-situation filters (derived per pack, see fxRel / fxLife): relative transfer (family sale in the last 3 years), life estate owner, death recorded.
   Miami-Dade: relative = unqualified sale in the last 3 years whose grantor shares a surname with a different owner (roll grantor names); death = Clerk death certificate / probate decedent match (distress layer).
   Monroe: relative = FDOR sale code 30 (affiliated parties) on the latest sale (pack column sx); no Clerk death data, so the death row is hidden there (the 'Estate or heirs' owner row still reads the roll names). */
const FX_ROWS=[['fam','Relative transfer in the last 3 years'],['famoos','Relative transfer + owner mails from out of state'],['life','Life estate owner'],['death','Death recorded (owner deceased)']];
const FX_YEARS=3, LIFE_RE=/\bLIFE\s+(EST(ATE)?|TENANT|TENANCY)\b|\bL\/E\b|\bLE\b(?=\s*(\||&|$))/;
const fxAvail=k=>k==='death'?HAS('distress'):true;
const fxTri=(v,on)=>on==='yes'?!!v:on==='no'?!v:true;
const dec = new TextDecoder();

/* plain-language categories */
const TYPES = [
  ['vacant','Vacant land','vacant'],['sf','Single family','res'],['th','Townhouse','res'],['mf29','2–9 units','multi'],
  ['apt10','10+ unit apartments','multi'],['condo','Condo units','res'],['mixed','Mixed use','com'],['com','Commercial','com'],
  ['ind','Industrial','ind'],['mobile','Mobile home','res'],['inst','Church, school, nonprofit','gov'],['gov','Government','gov'],['other','Other','ind']];
const TYPE_LABEL = Object.fromEntries(TYPES.map(t=>[t[0],t[1]])), TYPE_TONE = Object.fromEntries(TYPES.map(t=>[t[0],t[2]]));
function luType(s){
  const code=parseInt(s.slice(0,4),10)||0, u=s.toUpperCase();
  if(/CONDOMINIUM|COOPERATIVE/.test(u)) return 'condo';
  if(code===0) return 'other';
  if(/GOVERN/.test(u) || (code>=8000 && code<9000)) return 'gov';
  if(/VACANT|ACREAGE NOT CLASSIFIED/.test(u)) return 'vacant';
  const g=Math.floor(code/100);
  if(g===1) return 'sf'; if(g===2) return 'mobile'; if(g===3) return 'apt10';
  if(g===4) return /TOWNHOUSE/.test(u)?'th':'other';
  if(g===6) return 'inst'; if(g===8) return 'mf29';
  if(g===12) return 'mixed';
  if(g>=10 && g<=39) return 'com';
  if(g>=41 && g<=49) return 'ind';
  if(g>=70 && g<=79) return 'inst';
  return 'other';
}
const ZONES = [
  ['sf','Single family','res'],['duplex','Duplex','res'],['th','Townhouse','res'],['mf','Multifamily','multi'],['mixed','Mixed use / urban','com'],
  ['com','Commercial','com'],['ind','Industrial','ind'],['pud','Planned development','gov'],['interim','Interim (no final zoning)','gov'],['civic','Civic, parks, special','gov'],['other','Unclassified','ind']];
const ZONE_LABEL = Object.fromEntries(ZONES.map(z=>[z[0],z[1]])), ZONE_TONE = Object.fromEntries(ZONES.map(z=>[z[0],z[2]]));
function zGroup(s){
  const code=parseInt(s,10)||0, u=s.toUpperCase();
  if(!code || !/[A-Z]/.test(u.replace(/^\S+\s*-\s*/,''))) return 'other';
  if(code===1900 || (code>=5400&&code<=5600) || code===9300 || code===9400 || code===9450) return 'pud';
  if(code===9301||code===9302) return 'mf';
  if(code>=100 && code<=2700) return 'sf';
  if(code===2800) return 'th';
  if(code>=5700 && code<=5900) return 'duplex';
  if((code>=3000 && code<=4700) || code===4900 || code===5100) return 'mf';
  if(code>=4800 && code<=4802) return 'mixed';
  if(code>=5000 && code<=5300) return /MIX/.test(u)?'mixed':'com';
  if(code>=6000 && code<7000) return /MIX|UC |URBAN|CORE|TOWN CENTER|TRANSIT|DKUC|MAIN STREET|RESIDENTIAL|RES \/|ARTS|MARKET|OVERTOWN|HIGH DENS|CEN-PED|PERFORMING|UNIVERSITY|DESIGN D|NBHD/.test(u)?'mixed':'com';
  if(code===7610) return 'mixed';
  if(code>=7000 && code<7800) return 'ind';
  if(code===8900) return 'interim';
  if(code===9500) return 'com';
  return 'civic';
}
const KEEP_UP = new Set(['UC','PUD','CRA','MC','MM','MO','MD','MCS','MCI','MCD','AD','ID','RM','RML','SD','DKUC','HT','I','II','III','TOD','LLC','MH-1','DRI','CB','PDR']);
function nice(s){
  let t=s.replace(/^\S+\s*-\s*/,'').replace(/\s+/g,' ').trim();
  if(!t) return '';
  t=t.replace(/\bU\/A\b/g,'units/acre').replace(/\bSGL\b/g,'SINGLE').replace(/\bFAM\b/g,'FAMILY').replace(/\bSQF?T?\b/g,'SQ FT').replace(/\bCONDOMINUM\b/g,'CONDOMINIUM');
  return t.split(' ').map(w=>{ const W=w.replace(/[(),]/g,''); if(KEEP_UP.has(W)||/\d/.test(w)||w==='units/acre') return w; return w.charAt(0)+w.slice(1).toLowerCase(); }).join(' ');
}
const luNice = s => nice('X - '+s.replace(/^\S+\s*-\s*/,'').split(':')[0]);

/* data */
let META=null; const PACKS=[]; let D=null, LU_T=null, Z_G=null;
let results=new Uint32Array(0);
const S = { mr:{rate:new Set(),tier:new Set(),rogo:new Set(),sig:new Set(),avoid:new Set(),zt:new Set()}, cont:false, hideSent:false, hasPhone:false, traced:'', cm:0, cgas:false, cent:'', due:false, stage:'', pf:false, pb:'', asm:false, asmUp:false, asmGroup:0, tier:'any', rules:{...window.PFTeardown.DEFAULT_RULES}, lotz:new Set(), cons:new Set(), ap:false, send:new Set(), mzSel:new Set(), mzOpen:new Set(['Miami','Miami-Dade County']), og:0, ogf:'', saved:false, pcs:new Set(), vsig:new Set(), svSt:new Set(), dsig:new Set(), types:new Set(), zones:new Set(), exZ:new Set(), exL:new Set(), flags:{}, fx:{}, owner:'all', sort:'lot_d', view:'cards', bbox:null };
S.mt={tax:new Set(),min:0};   // Monroe unpaid-tax filter (chips + minimum balance)
let facet = {lc:null, zc:null, mc:null, kc:null, dc:null};
let MZ=null, MZ_UP=null;
/* teardown rule, zone rules (data/zoning-rules.json), construction + adverse possession (data/extras.json.gz) */
const TD=window.PFTeardown, EXTRA_VER='z20261012b';
let ZR=null, ZREC=null, LU_CODE=null, EX=null, CNMAP=null, APSET=null;
const CN_CATS=[[1,'Concrete block (CBS)'],[2,'Wood frame'],[3,'Other masonry / brick'],[4,'Steel / reinforced concrete'],[5,'Other'],[0,'Unknown']];
const CN_LABEL=Object.fromEntries(CN_CATS);
const LOTZ=[['split','Lot could be split'],['minok','Lot meets zone minimum'],['below','Lot under zone minimum']];
const RULE_IDS=[['td_corp','exclude_corp_years',1],['td_land','min_land_share',100],['td_yb','max_year_built',1],['td_um','min_unit_multiple',1],['td_qm','min_sqft_multiple',1],['td_sm','min_story_multiple',1],['td_split','lot_split_factor',1]];
const RULE_KEYS=['min_land_share','max_year_built','min_unit_multiple','min_sqft_multiple','min_story_multiple','lot_split_factor','enforce_min_lot','exclude_corp_years'];
const parseAmt=v=>{ v=String(v==null?'':v).trim().toLowerCase().replace(/[$,\s]/g,''); if(!v) return null; const m=/^(-?\d*\.?\d+)([km]?)$/.exec(v); if(!m) return null; let x=parseFloat(m[1]); if(m[2]==='k') x*=1e3; if(m[2]==='m') x*=1e6; return isFinite(x)?Math.round(x*100)/100:null; };
const fmtAmt=v=>v==null||v===''?'':v>=1e6&&v%1e4===0?(v/1e6)+'m':v>=1e3&&v%1e3===0?(v/1e3)+'k':String(v);
const MONEY_IDS=new Set(['mvMin','mvMax','spMin','spMax']);
async function loadZoneRules(){
  if(HAS('zoning')||HAS('mzoning')) try{ const r=await fetch(DP+'zoning-rules.json?v='+META.ver+'-'+EXTRA_VER); if(r.ok) ZR=await r.json(); }catch(e){}
  ZREC=MZ.map((e,i)=>{ const r=ZR&&e&&ZR.rules[e[1]+'|'+String(e[0]).toUpperCase()]; if(!r) return null; const n=v=>v==null||v===''?null:+v;
    return {upa:n(r[0]),stories:n(r[1]),min_lot_sf:n(r[2]),lot_cov:n(r[3]),far:n(r[4]),height_ft:n(r[5]),zt:r[6]||null,sf:r[6]?(r[6]==='sf'?1:0):null,pd:!!r[7]||r[6]==='pad',src:r[8]||''}; });
  LU_CODE=D.landuse.map(s=>{ const m=/^\s*(\d{4})/.exec(s); return m?parseInt(m[1],10):-1; });
  if(HAS('construction')) try{ const r=await fetch(DP+'extras.json.gz?v='+META.ver+'-'+EXTRA_VER); if(r.ok){ const u8=new Uint8Array(await r.arrayBuffer()); EX=JSON.parse(dec.decode(u8[0]===0x1f&&u8[1]===0x8b?await gunzip(u8):u8)); } }catch(e){}
  if(EX){ CNMAP=new Map(); for(const [k,s] of Object.entries(EX.cn.groups)){ const m=parseInt(k,10); let v=0; for(const t of s.split(',')){ v+=parseInt(t,36); CNMAP.set(v,m); } } APSET=new Set(EX.ap.folios); }
}
/* per-pack zoning upside (rule-independent) + tier / split (depends on S.rules) */
function prepPack(p){
  if(!p||p.td||!ZREC) return; const c=p.c, n=p.n;
  const um=new Float32Array(n), qm=new Float32Array(n), sm=new Float32Array(n), al=new Float32Array(n), below=new Int8Array(n), zmin=new Float32Array(n), sfz=new Int8Array(n);
  for(let i=0;i<n;i++){ const z=ZREC[c.mz[i]]; um[i]=qm[i]=sm[i]=al[i]=zmin[i]=NaN; below[i]=-1; sfz[i]=-1; if(!z) continue;
    const lot=c.lot[i], eu=Math.max(c.units[i],1), es=Math.max(c.stories[i],1), bl=c.sqft[i];
    if(z.upa>0&&lot>0){ const a=Math.floor(lot/SQFT_AC*z.upa+1e-9); al[i]=a; um[i]=Math.round(a/eu*10)/10; }
    if(z.stories>0) sm[i]=Math.round(z.stories/es*10)/10;
    let x=null; if(lot>0){ if(z.far>0) x=lot*z.far; else if(z.lot_cov>0&&z.stories>0) x=lot*Math.min(z.lot_cov,100)/100*z.stories; }
    if(x!=null&&bl>0) qm[i]=Math.round(Math.floor(x)/bl*10)/10;
    if(!z.pd&&z.min_lot_sf>0&&lot>0){ below[i]=lot<z.min_lot_sf?1:0; zmin[i]=z.min_lot_sf; if(z.sf!=null) sfz[i]=z.sf; } }
  const cn=new Uint8Array(n), ap=new Uint8Array(n);
  if(CNMAP||APSET){ const f=strCol(p,'folio'); for(let i=0;i<n;i++){ if(CNMAP){ const v=CNMAP.get(+f[i]); if(v) cn[i]=v; } if(APSET&&APSET.has(f[i])) ap[i]=1; } }
  p.td={um,qm,sm,al,below,zmin,sfz,tier:new Uint8Array(n),split:new Int8Array(n),key:''}; p.cn=cn; p.ap=ap;
}
function tierPack(p){
  if(!p||!p.td) return; const r=S.rules, key=JSON.stringify(r); if(p.td.key===key) return; const t=p.td, c=p.c, f=r.lot_split_factor;
  for(let i=0;i<p.n;i++){ t.tier[i]=TD.tierFast(LU_CODE[c.landuse[i]],c.land[i],c.mkt[i],c.yb[i],t.um[i],t.qm[i],t.sm[i],t.below[i]===1,r,(c.flags[i]&8)&&c.sd1[i]?(today-c.sd1[i])/365.25:Infinity);
    const mn=t.zmin[i]; t.split[i]=(mn>0&&t.sfz[i]>=0)?((t.sfz[i]===1&&c.lot[i]>=f*mn)?1:0):-1; }
  t.key=key;
}
/* relative transfer / life estate derived columns (cached per pack) */
const FX_STOP=new Set(['JR','SR','II','III','IV','LE','REM','ETAL','ETUX','TR','TRS','TRUSTEE','EST','ESTATE','OF','THE','AND','DEC','DECD','DECEASED','JTRS','HEIRS','UX','VIR','ET','AL','W','H']);
function fxPersons(s){ const out=[]; for(const seg of String(s||'').split(/\s*\|\s*|\s*&\s*/)){ const t=seg.toUpperCase().replace(/[^A-Z ]+/g,' ').split(/\s+/).filter(Boolean); while(t.length&&FX_STOP.has(t[t.length-1])) t.pop(); while(t.length&&FX_STOP.has(t[0])) t.shift(); if(t.length<2) continue; out.push({k:t[0]+' '+t[t.length-1],sur:t[t.length-1]}); } return out; }
function fxRel(p){
  if(p.fxRel) return p.fxRel; const c=p.c, n=p.n, out=new Uint8Array(n), lim=today-Math.round(FX_YEARS*365.25);
  if(c.sx){ for(let i=0;i<n;i++) if((c.sx[i]&1) && c.sd1[i]>=lim && !(c.flags[i]&(8|16|32))) out[i]=1; return p.fxRel=out; }   // Monroe: FDOR sale code 30
  if(!p.s.grantor){ if(p.idx!=null && !p.fxLoading){ p.fxLoading=true; loadDetail(p.idx).then(()=>{ p.fxLoading=false; schedule(0); }); toast('Loading transfer data…'); } return null; }
  const ow=strCol(p,'owner'), gr=strCol(p,'grantor');
  for(let i=0;i<n;i++){ if(c.sq1[i]!==2 || c.sd1[i]<lim || (c.flags[i]&(8|16|32))) continue; const g=gr[i]; if(!g) continue;
    const op=fxPersons(ow[i]); if(!op.length) continue; const sur=new Set(op.map(x=>x.sur)), keys=new Set(op.map(x=>x.k));
    for(const x of fxPersons(g)) if(sur.has(x.sur) && !keys.has(x.k)){ out[i]=1; break; } }
  return p.fxRel=out;
}
function fxLife(p){ if(p.fxLife) return p.fxLife; const ow=strCol(p,'owner'), out=new Uint8Array(p.n), sx=p.c.sx; for(let i=0;i<p.n;i++) if(LIFE_RE.test(ow[i]) || (sx&&(sx[i]&2))) out[i]=1; return p.fxLife=out; }
function zoneOf(p,i){ return ZREC?ZREC[p.c.mz[i]]:null; }
function tdEval(p,i){ const c=p.c; return TD.evaluate({code:LU_CODE[c.landuse[i]],land:c.land[i],total:c.mkt[i],yb:c.yb[i],lot:c.lot[i],units:c.units[i],stories:c.stories[i],bldg:c.sqft[i],corpHeld:(c.flags[i]&8)&&c.sd1[i]?(today-c.sd1[i])/365.25:null},zoneOf(p,i)||{},S.rules); }
/* Assemblages (data/asm.json.gz, scripts/build_assemblages.py): adjoining parcels, same zoning, 2+ owners, each with a reason to sell.
   Loaded on demand (filter / preset / a few seconds after start for card badges); outlines (data/asm-polys.json.gz) only for the map. */
const HIST={last:0,url:null,restoring:false};
/* Clerk / auction signals (data/signals.json.gz, scripts/build_signals.py): open pre-foreclosure, probate filed (+match confidence), auction max bid */
const SIG_VER='s1'; let SIG=null, sigP=null; const PFM=new Map(), PBM=new Map(), AUM=new Map();
const PB_DOC={PRO:'Probate order of distribution',PAD:'Probate & administration filed',DCE:'Death certificate (estate of) recorded',CP:'Probate case filed'};
const ymd=n=>n?String(n).replace(/^(\d{4})(\d\d)(\d\d)$/,'$1-$2-$3'):'';
const mdy=n=>{ const t=String(n); return t.slice(4,6)+'/'+t.slice(6,8)+'/'+t.slice(0,4); };
function loadSignals(){ return sigP||(sigP=(async()=>{ const o=await gzJSON(DP+'signals.json.gz?v='+META.ver+'-'+SIG_VER);
  o.pf.forEach(r=>PFM.set(r[0],r)); o.pb.forEach(r=>PBM.set(r[0],r)); o.au.forEach(r=>{ const a=AUM.get(r[0])||[]; a.push(r); a.sort((x,y)=>x[1]-y[1]); AUM.set(r[0],a); }); SIG=o; PACKS.forEach(sigIndexPack); return o; })().catch(e=>{ sigP=null; throw e; })); }
function sigIndexPack(p){ if(!p||!SIG||p.sg) return; const f=strCol(p,'folio'), g=new Uint8Array(p.n); for(let i=0;i<p.n;i++){ const k=f[i]; let v=0; if(PFM.has(k)) v|=1; const b=PBM.get(k); if(b) v|=b[4]==='H'?2:4; if(AUM.has(k)) v|=8; g[i]=v; } p.sg=g; }
const PF_KIND={H:'HOA / condo lien foreclosure',M:'Mortgage foreclosure',O:'Other lis pendens'};
function pfTip(r){ return `Lis pendens recorded ${ymd(r[1])}${r[3]?', case '+r[3]:''}${r[2]?' (Clerk CFN '+r[2]+')':''}. ${PF_KIND[r[5]]||''}. Match: ${r[4]==='H'?'high':'medium'} confidence. No later cancellation, dismissal or certificate of title in the Clerk files we hold, no foreclosure sale held for the case and no transfer of the parcel since. Verify with the Clerk before acting.`; }
function pbTip(r){ return `${PB_DOC[r[2]]||r[2]}${r[5]?' ('+r[5]+')':''} recorded ${ymd(r[1])}${r[3]?' (Clerk '+r[3]+')':''}. Match: ${r[4]==='H'?'high':'medium'} confidence (folio, legal description, address or decedent name vs owner). Verify with the Clerk before acting.`; }
function clerkBadges(folio){ if(!SIG) return ''; let h=''; const a=PFM.get(folio), b=PBM.get(folio);
  if(a) h+=`<span class="hot pfb" title="${esc(pfTip(a))}">Pre-foreclosure ${ymd(a[1])}</span>`;
  if(b) h+=`<span class="warm pbb" title="${esc(pbTip(b))}">${b[2]==='PRO'?'Order of distribution':'Probate filed'} ${ymd(b[1])}${b[4]==='M'?' (medium match)':''}</span>`;
  return h; }
const auMax=r=>r[6]>0?dollars(r[6]):r[7]===1?'Hidden':r[2]==='T'?'n/a (tax deed)':'Not posted';
function auLine(folio){ const a=AUM.get(folio); if(!a) return ''; const r=a[0];
  return `<div class="line auline"><span class="k">Auction</span><span class="v" title="${esc((r[2]==='F'?'Foreclosure sale':'Tax deed sale')+' '+mdy(r[1])+', case '+r[3]+'. Plaintiff max bid is what the lender will bid up to; most plaintiffs hide it until the sale. Source: miamidade.realforeclose.com')}">${mdy(r[1])} · ${r[2]==='F'?'judgment '+(r[4]?money(r[4]):'–'):'opening '+(r[5]?money(r[5]):'–')} · max bid <b>${esc(auMax(r))}</b></span></div>`; }
function clerkHTML(folio){ if(!SIG) return ''; const a=PFM.get(folio), b=PBM.get(folio), au=AUM.get(folio)||[]; if(!a&&!b&&!au.length) return '';
  const li=[]; if(a) li.push(`<li><span class="dtag hot">Pre-foreclosure</span> <b>Open lis pendens</b> · ${ymd(a[1])}${a[3]?`<br><span class="mono">${esc(a[3])}</span>`:''}<small>${esc(pfTip(a))}</small></li>`);
  if(b) li.push(`<li><span class="dtag warm">Probate filed</span> <b>${esc(PB_DOC[b[2]]||b[2])}</b> · ${ymd(b[1])} · ${b[4]==='H'?'high':'medium'} match<small>${esc(pbTip(b))}</small></li>`);
  au.forEach(r=>li.push(`<li class="aumax"><span class="dtag hot">Auction</span> <b>${r[2]==='F'?'Foreclosure sale':'Tax deed sale'} ${mdy(r[1])}</b> · ${r[2]==='F'?'final judgment '+(r[4]?dollars(r[4]):'–'):'opening bid '+(r[5]?dollars(r[5]):'–')} · plaintiff max bid <b>${esc(auMax(r))}</b><br><span class="mono">${esc(r[3])}</span> <a href="https://www.miamidade.realforeclose.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=${mdy(r[1])}" target="_blank" rel="noopener">auction day ↗</a></li>`));
  return `<ul class="dlist clerk">${li.join('')}</ul><div class="note">Clerk records through ${ymd(SIG.meta.pf.to)}, auctions pulled ${esc(String(SIG.meta.auctionsPulled||'').replace('T',' '))}.</div>`; }
/* Commercial distress (data/commercial.json.gz, scripts/commercial/): Commercial Data bot list for Miami-Dade with its build3 score,
   live county-taxes.net payoff reads, OpenCorporates/Sunbiz owner entity status and FDEP closed gas stations */
const CM_VER='m1'; let CM=null, cmP=null; const CMM=new Map();
function loadCommercial(){ return cmP||(cmP=(async()=>{ const o=await gzJSON(DP+'commercial.json.gz?v='+META.ver+'-'+CM_VER);
  for(const f in o.rows) CMM.set(f,o.rows[f]); CM=o; PACKS.forEach(cmIndexPack); return o; })().catch(e=>{ cmP=null; throw e; })); }
function cmIndexPack(p){ if(!p||!CM||p.cm) return; const f=strCol(p,'folio'), a=new Uint8Array(p.n), b=new Uint8Array(p.n);
  for(let i=0;i<p.n;i++){ const r=CMM.get(f[i]); if(!r) continue; a[i]=Math.max(1,Math.min(255,r.s)); b[i]=(r.gas?1:0)|(r.ent==='Inactive'?2:0)|(r.ent==='Dissolved'?4:0)|(r.due>0?8:0); } p.cm=a; p.cx=b; }
const shortRead=d=>{ const m=/^(\d{4})-(\d\d)-(\d\d)/.exec(d||''); return m?new Date(+m[1],m[2]-1,+m[3]).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}):''; };
function cmTax(r){ if(!r||!r.chk) return ''; return r.due>0?`${dollars(r.due)} due${r.lpy?' · last paid TY'+r.lpy:''}${r.npo?' · '+dollars(r.npo)+' not payable online':''}`:`Paid · $0 due${r.lpy?' · last paid TY'+r.lpy:''}`; }
const ENT_TIP={Active:'Owner entity active in the Florida registry (OpenCorporates mirror of Sunbiz)',Inactive:'Owner is a foreign (out-of-state) entity whose Florida registration is inactive / revoked; confirm on Sunbiz',Dissolved:'Owner is a Florida entity shown inactive: likely dissolved or administratively dissolved; confirm on Sunbiz','Not found':'No matching Florida entity found',Mixed:'Several registry matches, some active and some inactive'};
function cmBadges(folio){ const r=CM&&CMM.get(folio); if(!r) return ''; let h=`<span class="warm cmb" title="Commercial distress score (tax, code liens, recertification, unsafe structures, closed gas station, owner entity, bankruptcy). ${esc(r.cat||'')}">Comm. distress ${r.s}</span>`;
  if(r.gas) h+=`<span class="hot cgb" title="FDEP storage-tank facility CLOSED / ABANDONED at this parcel with no open station nearby">Closed gas station</span>`;
  if(r.ent==='Inactive'||r.ent==='Dissolved') h+=`<span class="hot entb" title="${esc(ENT_TIP[r.ent])}">Owner entity ${r.ent.toLowerCase()}</span>`; return h; }
function cmLine(folio){ const r=CM&&CMM.get(folio); if(!r||!r.chk) return ''; return `<div class="line cmtax"><span class="k" title="Read live from the tax collector (county-taxes.net)">Tax payoff</span><span class="v">${cmTax(r)} <small class="note">read ${esc(shortRead(r.chk))}</small></span></div>`; }
function cmHTML(folio){ const r=CM&&CMM.get(folio); if(!r) return ''; const li=[];
  li.push(`<li><span class="dtag warm">Score ${r.s}</span> <b>Commercial distress</b> · ${esc(r.t||'')}<small>Signals: ${esc(r.cat||'none')}</small></li>`);
  if(r.chk) li.push(`<li class="cmlive"><span class="dtag ${r.due>0?'hot':''}">Live tax</span> <b>${r.due>0?'Payoff '+dollars(r.due):'Paid, $0 due'}</b> · read ${esc(shortRead(r.chk))}<br>Last paid year: <b>${esc(r.lpy||'–')}</b>${r.npo?` · not payable online: <b>${dollars(r.npo)}</b>`:''}${r.yrs?` · ${r.yrs} unpaid year${r.yrs>1?'s':''}`:''}<small>${esc(r.certs||'')}${r.tda?' · Tax deed application: '+esc(r.tda):''}</small></li>`);
  if(r.ent) li.push(`<li><span class="dtag ${r.ent==='Inactive'||r.ent==='Dissolved'?'hot':''}">Owner entity</span> <b>${esc(r.ent)}</b><small>${esc(ENT_TIP[r.ent]||'')}${r.entSrc?' · '+esc(r.entSrc):''}</small></li>`);
  if(r.gas) li.push(`<li><span class="dtag hot">Closed gas station</span> <b>FDEP tank facility closed / abandoned</b><small>State storage-tank list (FDEP STCM); no open station within 80 m.</small></li>`);
  return `<h3>Commercial distress</h3><ul class="dlist cmlist">${li.join('')}</ul><div class="note">Commercial list built ${esc(CM.meta.built)}. Live tax amounts are as of the read date shown; confirm with the tax collector before acting.</div>`; }
/* comps value estimate (data/comps.json.gz, scripts/build_comps.py): PA-qualified sales in the last 6 months, same land use, nearby */
const COMP_VER='c2', CP_STEPS_C=[1,2,3,5], CP_STEPS=[0.5,1,2], CP_SIZE=[2,4], CP_MIN=3; let CP=null, cpP=null;
function loadComps(){ return cpP||(cpP=(async()=>{ const o=await gzJSON(DP+'comps.json.gz?v='+META.ver+'-'+COMP_VER), grid=new Map();
  o.rows.forEach((r,k)=>{ const key=Math.floor(r[1]/1000)*100000+Math.floor(r[2]/1000); let a=grid.get(key); if(!a) grid.set(key,a=[]); a.push(k); r.luN=parseInt(r[7],10); });
  o.grid=grid; CP=o; return o; })().catch(e=>{ cpP=null; throw e; })); }
/* commercial / industrial (DOR 10xx-49xx): sales are rare, so match the use family and widen to 5 mi / 24 months */
const cpCom=lu=>lu>=1000&&lu<5000, CP_FAM=c=>{ const d=Math.floor(c/100); return d===10?'vac':d<=16?'ret':d<=19?'off':d<=22?'rest':d===26?'gas':d===27?'auto':d===39?'hotel':d===40?'vacind':d>=41?'ind':'oth'+d; };
const cpMiles=(la1,lo1,la2,lo2)=>{ const dy=(la2-la1)*69.05, dx=(lo2-lo1)*69.05*Math.cos(la1*Math.PI/180); return Math.sqrt(dx*dx+dy*dy); };
const quant=(a,q)=>{ const x=(a.length-1)*q, b=Math.floor(x); return a[b]+(a[Math.min(b+1,a.length-1)]-a[b])*(x-b); };
function compsOf(p,i){
  if(!CP||!p.geo) return null; const la=p.geo.lat[i], lo=p.geo.lon[i]; if(!isFinite(la)||la<20) return null;
  const c=p.c, lu=LU_CODE?LU_CODE[c.landuse[i]]:parseInt(D.landuse[c.landuse[i]],10), sf=c.sqft[i], lot=c.lot[i], useB=sf>0, size=useB?sf:lot; if(!(size>0)||!(lu>0)) return null;
  const com=cpCom(lu), fam=com?CP_FAM(lu):'', STEPS=com?CP_STEPS_C:CP_STEPS, G=com?8:3;
  const me=getStr(p,'folio',i), cn=p.cn?p.cn[i]:0, la5=la*1e5, lo5=lo*1e5, cx=Math.floor(la5/1000), cy=Math.floor(lo5/1000), cand=[];
  for(let dx=-G;dx<=G;dx++) for(let dy=-G;dy<=G;dy++){ const a=CP.grid.get((cx+dx)*100000+cy+dy); if(!a) continue;
    for(const k of a){ const r=CP.rows[k]; if((com?(!cpCom(r.luN)||CP_FAM(r.luN)!==fam||r[3]<0):r.luN!==lu)||r[0]===me) continue; if(!com&&r[3]<CP.meta.cutoff) continue; const z=useB?r[5]:r[6]; if(!(z>0)||(useB?false:r[5]>0)) continue;
      const mi=cpMiles(la,lo,r[1]/1e5,r[2]/1e5); if(mi>STEPS[STEPS.length-1]) continue; cand.push({r,mi,ppsf:r[4]/z,sr:z/size,lr:useB&&lot>0&&r[6]>0?r[6]/lot:1}); } }
  let use=[], rad=0, band=0;
  for(const B of CP_SIZE){ for(const R of STEPS){ use=cand.filter(x=>x.mi<=R&&x.sr>=1/B&&x.sr<=B&&x.lr>=1/(2*B)&&x.lr<=2*B); rad=R; if(use.length>=CP_MIN) break; } band=B; if(use.length>=CP_MIN) break; }
  let sameCn=false; if(cn&&CNMAP&&use.length>=CP_MIN){ const s2=use.filter(x=>CNMAP.get(+x.r[0])===cn); if(s2.length>=CP_MIN){ use=s2; sameCn=true; } }
  use.sort((a,b)=>a.mi-b.mi);
  const out={n:use.length,rad,band,useB,size,sameCn,com,comps:use.slice(0,8),cash:use.filter(x=>x.r[8]===1).length,fin:use.filter(x=>x.r[8]===0).length};
  if(use.length<CP_MIN) return out;
  const v=use.map(x=>x.ppsf).sort((a,b)=>a-b); out.med=quant(v,.5); out.ppsf=out.med; out.lo=Math.round(quant(v,.25)*size/1000)*1000; out.hi=Math.round(quant(v,.75)*size/1000)*1000; out.est=Math.round(out.med*size/1000)*1000; return out; }
function cpWhy(c){ return `Median ${c.useB?'$ per building sq ft':'$ per lot sq ft'} of ${c.n} arm's-length sales within ${c.rad} mi in the last ${c.com?(CP.meta.commMonths||24):CP.meta.months} months, ${c.com?'same commercial use family (retail / office / restaurant / gas / auto / hotel / industrial / vacant)':'same land use'}, ${c.useB?'building':'lot'} size within ${c.band===2?'half to double':'a quarter to 4×'} this one${c.useB?' (lot within '+(2*c.band)+'×)':''}${c.sameCn?', same construction':''} (Property Appraiser qualified sales through ${ymd(CP.meta.newest)}), × this ${c.useB?'building':'lot'} size. Range = middle half of those sales. ${cpCash(c)}`; }
function cpCash(c){ const u=c.n-c.cash-c.fin; return u===c.n?'Cash vs financed: not in the roll data.':`${c.cash} cash, ${c.fin} financed${u?', '+u+' unknown':''}.`; }
function compsInner(p,i){ if(!CP) return '<span class="note">Loading comps…</span>'; if(!p.geo){ loadGeo(p.idx).then(()=>{ if(p.geo) fillComps(); }).catch(()=>{}); return '<span class="note">Loading map points…</span>'; } const c=compsOf(p,i);
  if(!c) return '<span class="note">No comps for this use</span>'; if(!c.est) return `<span class="note" title="${esc(cpWhy(c))}">Not enough comps (${c.n})</span>`;
  return `<span title="${esc(cpWhy(c))}"><b>${money(c.lo)}–${money(c.hi)}</b>${c.com?` · <b class="ppsf">$${c.ppsf.toFixed(c.ppsf<10?2:0)}/sf ${c.useB?'bldg':'lot'}</b>`:''} · ${c.n} sales ≤${c.rad} mi${c.hi>2*c.lo?' · wide range':''}</span>`; }
function compsLine(id){ const p=P(id), i=I(id); return `<div class="line cpline"><span class="k" title="Value estimate from comparable sales">Comps</span><span class="v cpbox" data-ci="${id}">${compsInner(p,i)}</span></div>`; }
function fillComps(){ document.querySelectorAll('.cpbox').forEach(n=>{ const id=+n.dataset.ci; n.innerHTML=compsInner(P(id),I(id)); }); }
function compsDrawer(p,i){ if(!CP||!p.geo) return '<div class="note">Comparable sales are loading. Reopen in a moment.</div>'; const c=compsOf(p,i);
  if(!c) return '<div class="note">No comparable sales: this parcel has no size or location for an estimate.</div>';
  const rows=c.comps.map(x=>{ const r=x.r; return `<tr><td>${esc(r[10]||folioFmt(r[0]))}</td><td>${ymd(r[3])}</td><td>${dollars(r[4])}</td><td>$${(x.ppsf).toFixed(x.ppsf<10?2:0)}</td><td>${x.mi.toFixed(2)} mi</td><td>${r[8]===1?'Cash':r[8]===0?'Financed':'–'}</td></tr>`; }).join('');
  return `<div class="dl">${c.est?`<div class="k">Estimate</div><div class="v"><b>${dollars(c.est)}</b><small>Range ${dollars(c.lo)} – ${dollars(c.hi)}${c.com?` · median $${c.ppsf.toFixed(c.ppsf<10?2:0)} per ${c.useB?'building':'lot'} sq ft`:''}</small></div>`:`<div class="k">Estimate</div><div class="v">Not enough comps (${c.n} of ${CP_MIN} needed within ${(c.com?CP_STEPS_C:CP_STEPS).slice(-1)[0]} mi)</div>`}<div class="k">Financing</div><div class="v">${esc(cpCash(c))}</div></div>
    ${rows?`<table class="covt cpt"><thead><tr><th>Sale</th><th>Date</th><th>Price</th><th>$/sf</th><th>Away</th><th>Cash</th></tr></thead><tbody>${rows}</tbody></table>`:''}<div class="note">${esc(c.est?cpWhy(c):'Sales: Property Appraiser qualified (arm\'s-length) sales, last '+CP.meta.months+' months, same land use.')} Not an appraisal.</div>`; }
const ASM_VER='a2';
let ASM=null, asmP=null; const APOLY=new Map(), apolyP=new Map();
const gzJSON=async url=>{ const r=await fetch(url); if(!r.ok) throw new Error('HTTP '+r.status); const u8=new Uint8Array(await r.arrayBuffer()); return JSON.parse(dec.decode(u8[0]===0x1f&&u8[1]===0x8b?await gunzip(u8):u8)); };
function asmDecode(o){ const nul=v=>v<0?null:v, groups=[], byFolio=new Map(), byId=new Map();
  o.g.forEach((a,j)=>{ const g={id:a[0],score:a[1],upside:a[2]===1,owners:a[3],muni:o.munis[a[4]],zone:o.zones[a[5]],lot:a[6],units:nul(a[7]),partsB:nul(a[8]),gain:a[9],sqft:nul(a[10]),sqftGain:a[11],unlock:a[12]===1,below:a[13],minSize:a[14],meets:a[15]===1,streets:a.slice(16).map(x=>o.streets[x]),mem:[]};
    for(const t of o.m[j].split(',')){ const [f,b,sl]=t.split('.'); g.mem.push([f,parseInt(b,16),+sl]); byFolio.set(f,j); }
    groups.push(g); byId.set(g.id,j); });
  return {meta:o.meta,mot:o.mot,gt:o.gt,groups,byFolio,byId}; }
function loadAsm(){ if(!HAS('asm')) return Promise.resolve(null); return asmP||(asmP=(async()=>{ ASM=asmDecode(await gzJSON(DP+'asm.json.gz?v='+META.ver+'-'+ASM_VER)); PACKS.forEach(asmIndexPack); return ASM; })().catch(e=>{ asmP=null; throw e; })); }
function loadTile(t){ const key=ASM.meta.tiles[t]; if(!apolyP.has(t)) apolyP.set(t,gzJSON(DP+'asm-polys/'+key+'.json.gz?v='+META.ver+'-'+ASM_VER).then(o=>{ o.j.forEach((j,x)=>APOLY.set(j,o.p[x])); }).catch(e=>{ apolyP.delete(t); throw e; })); return apolyP.get(t); }
function asmIndexPack(p){ if(!p||!ASM||p.asmG) return; const f=strCol(p,'folio'), g=new Int32Array(p.n).fill(-1); for(let i=0;i<p.n;i++){ const x=ASM.byFolio.get(f[i]); if(x!==undefined) g[i]=x; } p.asmG=g; }
const asmOf=(p,i)=>ASM&&p.asmG&&p.asmG[i]>=0?ASM.groups[p.asmG[i]]:null;
async function ensureAsm(){ if(!HAS('asm')){ S.asm=false; return; } if(!S.asm||ASM) return; $('asmSrc').textContent='Loading assemblage groups…'; try{ await loadAsm(); }catch(e){ toast('Assemblage data did not load: '+e.message); S.asm=false; } renderAsmSrc(); }
function renderAsmSrc(){ if(ASM) $('asmSrc').textContent=`${fmt.format(ASM.meta.groups)} groups (${fmt.format(ASM.meta.members)} parcels), ${fmt.format(ASM.meta.upside)} with a combined-site upside. Built ${ASM.meta.built}.`; }
function asmMotText(b){ return ASM.mot.filter(([m])=>(b&m)&&!(m===2&&(b&1))).map(x=>x[1]); }
function asmMix(g){ const sb=new Array(g.owners).fill(0), cnt={}; for(const [,b,sl] of g.mem) sb[sl]|=b; let rec=0; sb.forEach(b=>{ asmMotText(b).forEach(t=>cnt[t]=(cnt[t]||0)+1); if(b&256) rec++; });
  const ord=Object.fromEntries(ASM.mot.map((m,x)=>[m[1],x])); const out=Object.entries(cnt).sort((x,y)=>y[1]-x[1]||ord[x[0]]-ord[y[0]]); if(rec) out.push(['recent buyer',rec]); return out; }
function asmReason(g){ const n=g.mem.length, fi=v=>fmt.format(Math.round(v));
  const where=g.streets.length===1?`${n} lots side by side on ${g.streets[0]}`:g.streets.length>1?`${n} adjoining lots on ${g.streets.join(' & ')}`:`${n} adjoining lots`;
  const parts=[`${g.owners} owners, ${where} (${g.zone}, ${fi(g.lot)} sf combined).`];
  if(g.unlock) parts.push(`${g.below} of the lots ${g.below===1?'is':'are'} under the ${fi(g.minSize)} sf zone minimum on ${g.below===1?'its':'their'} own; together they clear it.`);
  if(!g.meets) parts.push(`Even combined, the site is under the ${fi(g.minSize)} sf zone minimum.`);
  else if(g.units!=null) parts.push(g.gain>0?`Combined site allows ${fi(g.units)} units vs ${fi(g.partsB)} building the lots separately (+${fi(g.gain)}).`:`Combined site allows ${fi(g.units)} units, the same as separately: the play is one larger site.`);
  else if(g.sqft!=null) parts.push(`Combined site allows ~${fi(g.sqft)} sf buildable${g.sqftGain>=2500?` (+${fi(g.sqftGain)} vs separately)`:''}.`);
  parts.push('Owners: '+asmMix(g).map(x=>x[1]+' '+x[0]).join(', ')+'.'); return parts.join(' '); }
function asmBadge(p,i){ const g=asmOf(p,i); return g?`<button type="button" class="asmb" data-asmshow="${g.id}" title="${esc(asmReason(g))}">Assemblage #${g.id} · ${g.mem.length} lots · ${g.owners} owners · score ${g.score}${g.upside?' · upside':''}</button>`:''; }
function asmHTML(p,i){ const g=asmOf(p,i); if(!g) return '';
  const ids=folioIds(g.mem.map(m=>m[0]));
  const li=g.mem.map(([f,b])=>{ const id=ids.get(f); const a=id!=null?getStr(P(id),'addr',I(id))||'No street address':f; return `<li>${id!=null?`<button type="button" class="lnk" data-asmone="${id}">${esc(a)}</button>`:esc(a)} <small>${esc(asmMotText(b).join(', '))}</small></li>`; }).join('');
  return `<h3>Assemblage #${g.id}</h3><div class="asmbox"><p>${esc(asmReason(g))}</p><div class="dl"><div class="k">Score</div><div class="v">${g.score} of 100${g.upside?' · combined-site upside':''}</div><div class="k">Combined lot</div><div class="v">${fmt.format(g.lot)} sq ft · ${(g.lot/SQFT_AC).toFixed(2)} acres</div>${g.units!=null?`<div class="k">Units allowed</div><div class="v">${fmt.format(g.units)} combined vs ${fmt.format(g.partsB)} separately</div>`:''}</div><ol class="asmlist">${li}</ol>
    <div class="links"><button type="button" class="btn" data-asmshow="${g.id}">Show this group</button><button type="button" class="btn" data-asmmap="${g.id}">Group on the map</button></div></div>`; }
/* map outlines for assemblage members */
let asmLayer=null;
const asmHint=t=>{ const el=$('mapHint'); el.textContent=el.textContent.replace(/ · Assemblage:.*$/,'')+' · Assemblage: '+t; };
async function drawAsmOutlines(){
  if(!LMAP) return; if(!asmLayer) asmLayer=L.layerGroup().addTo(LMAP); asmLayer.clearLayers();
  if(!S.asm||!ASM||S.view!=='map') return;
  const b=LMAP.getBounds(), want=new Set();
  if(S.asmGroup){ const j=ASM.byId.get(S.asmGroup); if(j!=null) want.add(j); }
  else { if(LMAP.getZoom()<15){ asmHint('zoom in to see group outlines.'); return; }
    for(let j=0;j<results.length && want.size<1500;j++){ const id=results[j], p=P(id), i=I(id); if(!p.asmG||p.asmG[i]<0||!p.geo) continue; const la=p.geo.lat[i], lo=p.geo.lon[i]; if(la>=b.getSouth()&&la<=b.getNorth()&&lo>=b.getWest()&&lo<=b.getEast()) want.add(p.asmG[i]); } }
  try{ await Promise.all([...new Set([...want].map(j=>ASM.gt[j]))].map(loadTile)); }catch(e){ asmHint('outlines did not load.'); return; }
  asmLayer.clearLayers(); const sc=1e6, all=[];
  for(const j of want){ const g=ASM.groups[j]; for(const enc of APOLY.get(j)||[]){ const ll=[]; let x=0,y=0; for(let k=0;k<enc.length;k+=2){ x+=enc[k]; y+=enc[k+1]; ll.push([y/sc,x/sc]); } if(ll.length>2){ asmLayer.addLayer(L.polygon(ll,{className:'asmpoly',color:'#FC4C02',weight:2,fillColor:g.upside?'#FC4C02':'#00B2BD',fillOpacity:.18}).bindTooltip(`Assemblage #${g.id} · score ${g.score}`)); all.push(...ll); } } }
  if(S.asmGroup && all.length && drawAsmOutlines.fitted!==S.asmGroup){ drawAsmOutlines.fitted=S.asmGroup; LMAP.fitBounds(L.latLngBounds(all).pad(0.6),{maxZoom:19,animate:false}); }
  asmHint(`${fmt.format(want.size)} group${want.size===1?'':'s'} outlined${S.asmGroup?'':' in view'}.`);
}
/* Send to: tag parcels for the call center / door knocker (this browser only) */
const SKS=window.PFSkip.store, SKU=window.PFSkipUI;
const SEND_KEY=PFC.key('pf.send.v1');
const TEAMS=[{k:'sms',label:'Text / SMS',noun:'text / SMS team',prefix:'TextSMS',act:'text'},{k:'cc',label:'Call center',noun:'call center',prefix:'CallCenter',act:'call'},{k:'dk',label:'Door knock',noun:'door knock',prefix:'DoorKnock',act:'door'},{k:'ml',label:'Mail',noun:'mail list',prefix:'Mail',act:'mailer'}];
const teamOf=k=>TEAMS.find(t=>t.k===k);
const SEND=(()=>{ let o={}; try{ o=JSON.parse(localStorage.getItem(SEND_KEY)||'{}')||{}; }catch(e){} return {tags:o.tags&&typeof o.tags==='object'?o.tags:{}, sent:o.sent&&typeof o.sent==='object'?o.sent:{}}; })();
let SEND_PENDING=null;
const saveSend=()=>{ try{ localStorage.setItem(SEND_KEY,JSON.stringify(SEND)); }catch(e){ toast("Couldn't save the tags in this browser."); } };
const isTagged=(f,k)=>!!(SEND.tags[f]&&SEND.tags[f][k]);
const sentOf=(f,k)=>SEND.sent[f]&&SEND.sent[f][k]||null;
const wasSent=f=>!!(SEND.sent[f]&&Object.keys(SEND.sent[f]).length);
const contacted=f=>wasSent(f)||(()=>{ const x=SV.get(f); return !!(x&&x.acts&&x.acts.some(a=>a.type!=='note')); })();
function contSet(){ const o=new Set(Object.keys(SEND.sent).filter(wasSent)); for(const x of SV.list()) if(x.acts&&x.acts.some(a=>a.type!=='note')) o.add(x.folio); return o; }
/* main CSV export -> "Mark these N as sent to" bar (sticky, brand orange) */
let EXP_PENDING=null;
function renderExpBar(){ const el=$('expBar'); if(!el) return; if(!EXP_PENDING){ el.hidden=true; el.innerHTML=''; return; } const n=EXP_PENDING.folios.length; el.hidden=false;
  el.innerHTML=`<span><b>Exported ${EXP_PENDING.what?esc(EXP_PENDING.what):fmt.format(n)+' '+(n===1?'property':'properties')}.</b> Mark these ${fmt.format(n)} as sent ${EXP_PENDING.day} to:</span><select id="expTeam" aria-label="Sent to which list">${TEAMS.map(t=>`<option value="${t.k}" ${t.k===(EXP_PENDING.team||'')?'selected':''}>${t.label}</option>`).join('')}</select><button type="button" class="btn" id="expMark">Mark as sent</button><button type="button" class="btn ghost" id="expSkip">Not now</button>`; }
const ACT_CAP=2000;
function expMark(k){ const P0=EXP_PENDING; EXP_PENDING=null; renderExpBar(); if(!P0) return; const t=teamOf(k), iso=new Date().toISOString(), td=todayDay(), list=P0.list||'Export '+P0.day;
  P0.folios.forEach(f=>{ (SEND.sent[f]||(SEND.sent[f]={}))[k]={d:P0.day,t:iso,list}; }); saveSend();
  let lg=0; SV.batch(()=>{ for(const f of P0.folios){ if(lg>=ACT_CAP) break; SV.logActivity(f,{type:t.act,d:td,outcome:'Sent to list',note:`${t.label} · ${list}`},savedInfo(P0.ids.get(f))); lg++; } });
  P0.folios.forEach(refreshSendUi); renderSend(); toast(`Marked ${fmt.format(P0.folios.length)} as sent ${P0.day} to ${t.label}`+(lg<P0.folios.length?` (activity logged on the first ${fmt.format(lg)})`:'')); if(S.cont||S.hideSent) run(); }
const tagCount=k=>Object.values(SEND.tags).filter(r=>r&&r[k]).length;
const dayStr=d=>{ d=new Date(d); return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'); };
function sendBtns(folio){ return `<span class="sendtools">${TEAMS.map(t=>{ const on=isTagged(folio,t.k); return `<button type="button" class="sbtn ${on?'on':''}" data-sendtag="${t.k}" data-folio="${folio}" aria-pressed="${on}" title="${on?`On the ${t.noun} list (tagged ${dayStr(SEND.tags[folio][t.k])}). Click to remove`:`Add this property to the ${t.noun} list`}">${t.label}</button>`; }).join('')}</span>`; }
function sentBadges(folio){ return TEAMS.map(t=>{ const s=sentOf(folio,t.k); return s?`<span class="sentb" title="Exported to the ${t.noun} list ${s.list?'“'+esc(s.list)+'” ':''}on ${s.d}. It won't be exported to the ${t.noun} again unless you retag it or press Re-send.">${t.label} · Sent ${s.d} <button type="button" class="resend" data-resend="${t.k}" data-folio="${folio}">Re-send</button></span>`:''; }).join(''); }
const mzTokens = q => q.toUpperCase().split(/[\s,;]+/).map(t=>t.trim()).filter(Boolean);
const mzKey=i=>MZ[i]?MZ[i][1]+'|'+MZ_UP[i]:'';
function mzAllow(q){ const toks=mzTokens(q); if(!toks.length && !S.mzSel.size) return null; const a=new Uint8Array(MZ.length); for(let i=1;i<MZ.length;i++){ const c=MZ_UP[i]; if(S.mzSel.size && S.mzSel.has(mzKey(i))){ a[i]=1; continue; } for(const t of toks){ if(c===t || c.startsWith(t)){ a[i]=1; break; } } } return a; }

const IDB=(()=>{ let dbp=null;
  const open=()=>dbp||(dbp=new Promise((res,rej)=>{ try{ const r=indexedDB.open('mdpf',1); r.onupgradeneeded=()=>r.result.createObjectStore('f'); r.onsuccess=()=>res(r.result); r.onerror=()=>rej(r.error); r.onblocked=()=>rej(new Error('blocked')); }catch(e){ rej(e); } }));
  const withTimeout=(pr,ms)=>Promise.race([pr,new Promise(r=>setTimeout(()=>r(null),ms))]);
  async function get(k){ try{ const db=await withTimeout(open(),1500); if(!db) return null; return await withTimeout(new Promise(res=>{ const q=db.transaction('f').objectStore('f').get(k); q.onsuccess=()=>res(q.result||null); q.onerror=()=>res(null); }),3000); }catch(e){ return null; } }
  async function put(k,v){ try{ const db=await withTimeout(open(),1500); if(db) db.transaction('f','readwrite').objectStore('f').put(v,k); }catch(e){} }
  async function prune(ver){ try{ const db=await withTimeout(open(),1500); if(!db) return; const r=db.transaction('f','readwrite').objectStore('f').openCursor(); r.onsuccess=()=>{ const cur=r.result; if(!cur) return; const k=String(cur.key), mine=k.startsWith(PFC.id+':')||(PFC.id===PFC.DEFAULT&&!/^[a-z-]+:/.test(k)); if(mine&&!k.startsWith(PFC.id+':'+ver+'/')) cur.delete(); cur.continue(); }; }catch(e){} }
  return {get,put,prune}; })();
async function fetchAll(files, onBytes){
  const bufs = await Promise.all(files.map(async f => {
    const key=PFC.id+':'+META.ver+'/'+f, hit=await IDB.get(key);
    if(hit && hit.byteLength){ onBytes(hit.byteLength); return new Uint8Array(hit); }
    const r = await fetch(DP+f+'?v='+META.ver); if(!r.ok) throw new Error('Could not load '+f+' ('+r.status+')');
    if(!r.body){ const b=new Uint8Array(await r.arrayBuffer()); onBytes(b.length); return b; }
    const rd=r.body.getReader(), chunks=[]; let len=0;
    for(;;){ const {done,value}=await rd.read(); if(done) break; chunks.push(value); len+=value.length; onBytes(value.length); }
    const out=new Uint8Array(len); let o=0; for(const c of chunks){out.set(c,o);o+=c.length;} if(!(navigator.serviceWorker&&navigator.serviceWorker.controller)) IDB.put(key,out.buffer); return out;
  }));
  const all=new Uint8Array(bufs.reduce((a,b)=>a+b.length,0)); let o=0; for(const b of bufs){all.set(b,o);o+=b.length;} return all;
}
async function gunzip(u8){
  if(u8[0]===0x1f && u8[1]===0x8b){ const ds=new Blob([u8]).stream().pipeThrough(new DecompressionStream('gzip')); return new Uint8Array(await new Response(ds).arrayBuffer()); }
  return u8;
}
const TA={uint8:Uint8Array,uint16:Uint16Array,uint32:Uint32Array};
function parsePack(u8,name,idx){
  const buf=u8.buffer, base=u8.byteOffset, hl=new DataView(buf,base,4).getUint32(0,true);
  const hdr=JSON.parse(dec.decode(u8.subarray(4,4+hl))), start=4+hl, c={}, s={};
  for(const col of hdr.cols){
    if(col.type==='str') s[col.name]={bytes:u8.subarray(start+col.offset,start+col.offset+col.bytes),off:null,all:null};
    else { const T=TA[col.type]; c[col.name]=new T(buf,base+start+col.offset,col.bytes/T.BYTES_PER_ELEMENT); }
  }
  return {name,idx,n:hdr.n,c,s};
}
function strOffsets(sc,n){ if(sc.off) return sc.off; const off=new Uint32Array(n+1),b=sc.bytes; let k=1; for(let i=0;i<b.length;i++) if(b[i]===10) off[k++]=i+1; off[n]=b.length+1; sc.off=off; return off; }
function getStr(p,col,i){ const sc=p.s[col]; if(sc.all) return sc.all[i]; const off=strOffsets(sc,p.n); return dec.decode(sc.bytes.subarray(off[i],off[i+1]-1)); }
function strCol(p,col){ const sc=p.s[col]; if(!sc.all) sc.all=dec.decode(sc.bytes).split('\n'); return sc.all; }
async function loadPack(i,label){
  const pk=META.packs[i]; let got=0;
  $('loadbox').hidden=false; $('loadMsg').textContent=label; $('loadBar').style.width='0%';
  const raw=await fetchAll(pk.files,n=>{ got+=n; $('loadBar').style.width=Math.min(100,got/pk.bytes*100).toFixed(1)+'%'; $('loadSub').textContent=(got/1e6).toFixed(1)+' of '+(pk.bytes/1e6).toFixed(1)+' MB'; });
  $('loadMsg').textContent=label;
  $('loadSub').textContent='Unpacking…';
  PACKS[i]=parsePack(await gunzip(raw),pk.name,i); prepPack(PACKS[i]); if(ASM) asmIndexPack(PACKS[i]);
  $('loadbox').hidden=true;
}
const DET=[];
function loadDetail(i){
  if(!PACKS[i]) return Promise.resolve();
  if(DET[i]) return DET[i];
  const pk=META.packs[i];
  DET[i]=(async()=>{ const u8=await gunzip(await fetchAll(pk.detail,()=>{})); const d=parsePack(u8,pk.name,i); Object.assign(PACKS[i].c,d.c); Object.assign(PACKS[i].s,d.s); PACKS[i].det=true; })();
  DET[i].catch(()=>{ DET[i]=null; });
  return DET[i];
}
const ensureDetail=()=>Promise.all(PACKS.map((p,i)=>p&&!p.det?loadDetail(i):null));
const P=id=>PACKS[id>>>24], I=id=>id&0xFFFFFF;

/* saved properties (storage lives in saved.js -> window.PFSaved) */
const SV=window.PFSaved;
const STAR_SVG='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.8l2.8 5.9 6.4.8-4.7 4.4 1.2 6.4L12 17.2l-5.7 3.1 1.2-6.4L2.8 9.5l6.4-.8z"/></svg>';
const stKey=s=>String(s).toLowerCase().replace(/[^a-z]+/g,'-');
const svDate=iso=>{ const d=new Date(iso); return isNaN(d)?'':MON[d.getMonth()]+' '+d.getDate()+', '+d.getFullYear(); };
function starHTML(id,folio,extra=''){ const on=SV.has(folio); return `<button type="button" class="star ${on?'on':''} ${extra}" data-star="${folio}" data-id="${id}" aria-pressed="${on}" aria-label="${on?'Remove from saved':'Save property'}" title="${on?'Saved · click to remove':'Save this property'}">${STAR_SVG}</button>`; }
function savedInfo(id){ const p=P(id), i=I(id), c=p.c; return {addr:getStr(p,'addr',i), city:D.city[c.city[i]]||'', zip:D.zip[c.zip[i]]||'', pack:p.name}; }
let SVIDX={key:'',ids:new Map()};      // folio -> id for saved folios present in the loaded packs
function savedIdx(){
  const key=SV.rev+':'+PACKS.map(p=>p?1:0).join('');
  if(SVIDX.key===key) return SVIDX.ids;
  const want=new Set(SV.list().map(x=>x.folio)), ids=new Map();
  if(want.size) for(const p of PACKS){ if(!p) continue; const a=strCol(p,'folio'), base=p.idx*16777216; for(let i=0;i<a.length;i++) if(want.has(a[i])){ ids.set(a[i],base+i); if(ids.size===want.size) break; } }
  SVIDX={key,ids}; return ids;
}
async function ensureSavedPacks(){
  if(PACKS[1]||!SV.count()) return;
  const ids=savedIdx(), need=SV.list().some(x=>x.pack==='condo'||!ids.has(x.folio));
  if(need){ try{ await loadPack(1,'Loading condo units for your saved list…'); }catch(e){ toast('Condo units did not load: '+e.message); } }
}

/* state */
const NUM_IDS=['lotMin','lotMax','sfMin','sfMax','ybMin','ybMax','unMin','unMax','bdMin','stMax','lsMin','lsMax','hdMin','hdMax','spMin','spMax'];
const ADV_IDS=NUM_IDS.slice(2);
const MONEY_STEPS=[0,50e3,100e3,150e3,200e3,300e3,400e3,500e3,750e3,1e6,1.5e6,2e6,3e6,5e6,10e6,25e6];
const num=id=>parseAmt($(id).value);
function readState(){
  const st={}; NUM_IDS.forEach(id=>st[id]=num(id));
  st.mvMin=num('mvMin'); st.mvMax=num('mvMax');
  st.mzq=$('mzq').value.trim(); st.q=$('q').value.trim(); st.qScope=$('qScope').value; st.city=$('city').value; st.zips=$('zips').value; st.cra=$('cra').value;
  st.hideGov=$('hideGov').checked; st.noBldg=$('noBldg').checked; st.qualOnly=$('qualOnly').checked;
  st.types=[...S.types]; st.zones=[...S.zones]; st.exZ=[...S.exZ].map(i=>D.zoning[i]); st.exL=[...S.exL].map(i=>D.landuse[i]);
  st.cont=S.cont; st.hideSent=S.hideSent; st.hasPhone=S.hasPhone; st.traced=S.traced; st.cm=S.cm; st.cgas=S.cgas; st.cent=S.cent; st.dsig=[...S.dsig]; st.dsMin=+$('dsMin').value||0; st.flags={...S.flags}; st.fx={...S.fx}; st.owner=S.owner; st.sort=S.sort; st.view=S.view; st.bbox=S.bbox; st.saved=S.saved; st.svSt=[...S.svSt]; st.ogMin=+$('ogMin').value||0; st.ogDist=$('ogDist').checked; st.ogInst=$('ogInst').checked; st.ogf=S.ogf; st.vsig=[...S.vsig]; st.pcs=[...S.pcs]; st.vsMin=+$('vsMin').value||0; st.vsMine=$('vsMine').checked; st.tier=S.tier; st.rules={...S.rules}; st.lotz=[...S.lotz]; st.cons=[...S.cons]; st.ap=S.ap; st.pf=S.pf; st.pb=S.pb; st.due=S.due; st.stage=S.stage; st.send=[...S.send]; st.asm=S.asm; st.asmUp=S.asmUp; st.asmGroup=S.asmGroup; st.mzSel=[...S.mzSel]; st.mr=mrRead(); return st;
}
function save(){ const st=readState(); try{ localStorage.setItem(PFC.key('mdpf.v2'),JSON.stringify(st)); }catch(e){} writeHash(st); }
function applyState(st){
  NUM_IDS.forEach(id=>$(id).value=st[id]==null?'':(MONEY_IDS.has(id)?fmtAmt(st[id]):st[id]));
  $('mvMin').value=st.mvMin?fmtAmt(st.mvMin):''; $('mvMax').value=st.mvMax?fmtAmt(st.mvMax):'';
  S.cont=!!st.cont; S.hideSent=!!st.hideSent; S.hasPhone=!!st.hasPhone; S.traced=['y','n'].includes(st.traced)?st.traced:''; S.cm=[1,20,35,50].includes(+st.cm)?+st.cm:0; S.cgas=!!st.cgas; S.cent=['in','dis'].includes(st.cent)?st.cent:'';
  S.tier=['basic','strong'].includes(st.tier)?st.tier:'any'; if(st.rules&&typeof st.rules==='object') S.rules=sanRules(st.rules); S.lotz=new Set((st.lotz||[]).filter(k=>LOTZ.some(x=>x[0]===k))); S.cons=new Set((st.cons||[]).map(Number).filter(k=>k in CN_LABEL)); S.ap=!!st.ap; S.due=!!st.due; S.stage=SV.STAGES.includes(st.stage)?st.stage:''; S.pf=!!st.pf; S.pb=['hm','h'].includes(st.pb)?st.pb:''; S.send=new Set((st.send||[]).filter(k=>teamOf(k))); S.asm=!!st.asm; S.asmUp=!!st.asmUp; S.asmGroup=+st.asmGroup||0; S.mzSel=new Set(st.mzSel||[]); renderRules();
  $('mzq').value=st.mzq||''; $('q').value=st.q||''; $('qScope').value=st.qScope||'ao'; $('city').value=st.city||''; $('zips').value=st.zips||''; $('cra').value=st.cra||'';
  $('hideGov').checked=st.hideGov!==false; $('noBldg').checked=!!st.noBldg; $('qualOnly').checked=!!st.qualOnly;
  S.types=new Set(st.types||[]); S.zones=new Set(st.zones||[]); S.dsig=new Set((st.dsig||[]).filter(k=>k in DBIT)); $('dsMin').value=DS_STEPS.some(x=>x[0]===+st.dsMin)?String(+st.dsMin):'0';
  S.exZ=new Set((st.exZ||[]).map(v=>D.zoning.indexOf(v)).filter(i=>i>=0)); S.exL=new Set((st.exL||[]).map(v=>D.landuse.indexOf(v)).filter(i=>i>=0));
  S.owner=OWNER_KINDS.some(o=>o[0]===st.owner)?st.owner:'all'; S.flags={}; OWNER_ROWS.forEach(([k])=>{ S.flags[k]=(st.flags&&st.flags[k])||'any'; $('ow_'+k).value=S.flags[k]; });
  S.fx={}; FX_ROWS.forEach(([k])=>{ const v=st.fx&&st.fx[k]; S.fx[k]=fxAvail(k)&&(v==='yes'||v==='no')?v:'any'; const el=$('fx_'+k); if(el) el.value=S.fx[k]; });
  S.sort=SORT_MAP[st.sort]?st.sort:'lot_d'; $('sortSel').value=S.sort; S.view=['cards','table','map','pipe'].includes(st.view)?st.view:(S.view||'cards');
  $('ogMin').value=[0,2,3,5,10,25].includes(+st.ogMin)?String(+st.ogMin):'0'; $('ogDist').checked=!!st.ogDist; $('ogInst').checked=!!st.ogInst;
  if((st.ogf||'')!==S.ogf){ S.ogf=st.ogf||''; S.og=0; } $('ogRow').hidden=!S.ogf;
  S.vsig=new Set((st.vsig||[]).filter(k=>k in VBIT)); S.pcs=new Set((st.pcs||[]).filter(k=>k in PBIT)); $('vsMin').value=VS_STEPS.some(x=>x[0]===+st.vsMin)?String(+st.vsMin):'0'; $('vsMine').checked=!!st.vsMine;
  S.saved=!!st.saved; S.svSt=new Set((st.svSt||[]).filter(x=>SV.STATUSES.includes(x)));
  S.bbox=Array.isArray(st.bbox)&&st.bbox.length===4&&st.bbox.every(Number.isFinite)?st.bbox:null; $('areaRow').hidden=!S.bbox;
  mrApply(st.mr);
}

function sanRules(r){ const o={...TD.DEFAULT_RULES}; for(const k of RULE_KEYS){ if(k==='enforce_min_lot'){ if(r[k]!=null) o[k]=!!r[k]; } else { const v=+r[k]; if(r[k]!=null&&r[k]!==''&&isFinite(v)&&v>=0) o[k]=v; } } return o; }
function renderRules(){ if(!$('td_land')) return; for(const [id,k,mul] of RULE_IDS){ if(document.activeElement!==$(id)) $(id).value=String(Math.round(S.rules[k]*mul*100)/100); } $('td_minlot').checked=!!S.rules.enforce_min_lot; }
function readRules(){ const r={...S.rules}; for(const [id,k,mul] of RULE_IDS){ const v=parseAmt($(id).value); if(v!=null&&v>=0) r[k]=v/mul; } r.enforce_min_lot=$('td_minlot').checked; S.rules=r; }
const rulesDefault=()=>RULE_KEYS.every(k=>S.rules[k]===TD.DEFAULT_RULES[k]);
/* filtering */
function textMatcher(st){
  if(!st.q) return null;
  const q=st.q.toUpperCase().replace(/\s+/g,' '), digits=q.replace(/[^0-9]/g,'');
  const qa=q.replace(/[\s-]/g,''), alnumF=PFC.id==='broward' && /^\d{6}[A-Z]{2}\d{4}$/.test(qa);   // Broward condo folios carry letters (474131AA0010)
  const folioMode = st.qScope==='ao' && (alnumF || (/^[\d\s-]+$/.test(q) && digits.length>=5));
  const cols = folioMode?['folio'] : st.qScope==='ao'?['addr','owner'] : [st.qScope];
  const needle = folioMode?(alnumF?qa:digits):q;
  return p=>{ const hit=new Uint8Array(p.n); for(const col of cols){ if(!p.s[col]){ loadDetail(p.idx).then(()=>schedule(0)); toast('Loading mailing and legal data…'); continue; } const a=strCol(p,col); for(let i=0;i<p.n;i++) if(!hit[i] && a[i].includes(needle)) hit[i]=1; } return hit; };
}
function allowLU(){ if(!S.types.size && !S.exL.size) return null; const a=new Uint8Array(D.landuse.length); for(let i=0;i<a.length;i++) a[i]=(!S.types.size||S.types.has(LU_T[i])) && (!S.exL.size||S.exL.has(i)) ? 1:0; return a; }
function allowZ(){ if(!S.zones.size && !S.exZ.size) return null; const a=new Uint8Array(D.zoning.length); for(let i=0;i<a.length;i++) a[i]=(!S.zones.size||S.zones.has(Z_G[i])) && (!S.exZ.size||S.exZ.has(i)) ? 1:0; return a; }

function run(){
  const st=readState(); save();
  const zipSet=new Set(st.zips.split(/[\s,;]+/).map(z=>z.trim().slice(0,5)).filter(Boolean).map(z=>D.zip.indexOf(z)));
  const cityI=st.city?D.city.indexOf(st.city):-1, craI=st.cra?D.cra.indexOf(st.cra):-1;
  let fMust=0,fNot=0; for(const [k] of OWNER_ROWS){ if(st.flags[k]==='yes') fMust|=FLAG[k]; else if(st.flags[k]==='no') fNot|=FLAG[k]; }
  if(st.hideGov) fNot|=FLAG.govt;
  const lA=allowLU(), zA=allowZ();
  const govLU = st.hideGov? Uint8Array.from(LU_T,t=>t==='gov'?1:0) : null;
  const lc=new Uint32Array(D.landuse.length), zc=new Uint32Array(D.zoning.length);
  const tm=textMatcher(st);
  const hdMinD=st.hdMin!=null?st.hdMin*365.25:null, hdMaxD=st.hdMax!=null?st.hdMax*365.25:null;
  const lsMin=st.lsMin!=null?st.lsMin/100:null, lsMax=st.lsMax!=null?st.lsMax/100:null;
  const incCondo=S.types.has('condo');
  const wantK = {all:-1,person:0,corp:1,trust:2}[S.owner]; const kc=new Uint32Array(4);
  const mA = mzAllow(st.mzq||''); const mc=new Uint32Array(MZ.length);
  let sigMask=0; for(const k of S.dsig) sigMask|=1<<DBIT[k]; const dsMin=st.dsMin||0, dc=new Uint32Array(DSIG.length+1);
  const ogF=S.ogf?(S.og||-1):0, ogMin=st.ogMin||0, ogDist=st.ogDist?2:0, useOg=!!((ogMin||ogDist)&&OWN), exInst=useOg&&!st.ogInst;
  if((ogMin||ogDist||st.sort==='og_d'||st.sort==='ogd_d') && !OWN) loadOwners().then(()=>schedule(0)).catch(()=>{});
  let vsMask=0; for(const k of S.vsig) vsMask|=1<<VBIT[k]; const vsMin=st.vsMin||0, vc=new Uint32Array(VSIG.length+1);
  let pcMask=0; for(const k of S.pcs) pcMask|=1<<PBIT[k]; const pcc=new Uint32Array(PCS.length+1);
  const mine=st.vsMine?new Set([...savedIdx()].filter(([f])=>{ const x=SV.get(f); return x&&x.vacant; }).map(([,id])=>id)):null;
  const bb=S.bbox; if(bb && PACKS.some(p=>p&&!p.geo)){ ensureGeo().then(()=>schedule(0)); }
  const tierW=S.tier==='strong'?2:S.tier==='basic'?1:0, tcn=new Uint32Array(3), lzSel=S.lotz, lzc={split:0,minok:0,below:0}, cnSel=S.cons, cnc=new Uint32Array(6);
  const sendSet=S.send.size?new Set(Object.keys(SEND.tags).filter(f=>[...S.send].some(k=>SEND.tags[f][k]))):null, apOnly=S.ap; let apN=0; const outSet=outFolios(), phoneSet=S.hasPhone?SKS.phoneSet():null, trSet=S.traced?SKS.tracedSet():null, cSet=S.cont||S.hideSent?contSet():null, sentAny=S.hideSent?new Set(Object.keys(SEND.sent).filter(wasSent)):null; const cmMin=S.cm, cgOn=S.cgas, ceMask=S.cent==='dis'?4:S.cent?6:0, pfOn=S.pf, pbMask=S.pb==='h'?2:S.pb?6:0; let pfN=0, pbN=0;
  const asmOn=S.asm&&!!ASM, asmUp=S.asmUp, asmJ=S.asmGroup&&ASM?ASM.byId.get(S.asmGroup):undefined, asmSeen=asmOn?new Set():null;
  const MRs=HAS('mscreen')?mrPrep():null;
  const fxF=S.fx, wantRel=fxF.fam!=='any'||fxF.famoos!=='any', wantLife=fxF.life!=='any', wantDeath=fxF.death!=='any'&&HAS('distress'), fxOn=wantRel||wantLife||wantDeath, DCB=1<<DBIT.DC;
  let out=new Uint32Array(1<<20), m=0;
  for(const p of PACKS){
    if(!p || (p.name==='condo' && !incCondo && !ogF && !mine)) continue;
    prepPack(p); tierPack(p); const TDc=p.td, TT=TDc?TDc.tier:new Uint8Array(p.n), TS=TDc?TDc.split:new Int8Array(p.n), TB=TDc?TDc.below:new Int8Array(p.n), CNa=p.cn||new Uint8Array(p.n), APa=p.ap||new Uint8Array(p.n), SGa=(sigIndexPack(p),p.sg||new Uint8Array(p.n)), CMa=(cmIndexPack(p),p.cm||new Uint8Array(p.n)), CXa=p.cx||new Uint8Array(p.n), FO=sendSet||outSet||cSet||phoneSet||trSet?strCol(p,'folio'):null; if(ASM) asmIndexPack(p); const AGa=p.asmG||null;
    let REL=null, LIF=null; if(wantRel){ REL=fxRel(p); if(!REL) continue; } if(wantLife) LIF=fxLife(p);
    const c=p.c, n=p.n, base=p.idx*16777216, hits=tm?tm(p):null, gl=bb&&p.geo?p.geo:null, VS=c.vscore||new Uint8Array(n), VG=c.vsig||new Uint16Array(n), PG=c.pcs||new Uint16Array(n);
    if(bb && !gl) continue;
    for(let i=0;i<n;i++){
      if(hits && !hits[i]) continue;
      if(ogF && c.og[i]!==ogF) continue;
      if(mine && !mine.has(base+i)) continue;
      if(sendSet && !sendSet.has(FO[i])) continue;
      if(outSet && !outSet.has(FO[i])) continue;
      if(S.cont && !cSet.has(FO[i])) continue; if(sentAny && sentAny.has(FO[i])) continue;
      if(phoneSet && !phoneSet.has(FO[i])) continue; if(trSet && (S.traced==='y')!==trSet.has(FO[i])) continue;
      if(apOnly && !APa[i]) continue;
      if(cmMin && CMa[i]<cmMin) continue; if(cgOn && !(CXa[i]&1)) continue; if(ceMask && !(CXa[i]&ceMask)) continue;
      if(pfOn && !(SGa[i]&1)) continue; if(pbMask && !(SGa[i]&pbMask)) continue;
      if(asmOn){ const gx=AGa?AGa[i]:-1; if(gx<0) continue; if(asmJ!==undefined && gx!==asmJ) continue; if(asmUp && !ASM.groups[gx].upside) continue; }
      if(vsMin && VS[i]<vsMin) continue;
      if(MRs && !mrPass(MRs,c,i)) continue;
      if(useOg){ const g=c.og[i]; if(!g || (ogMin && OWN.n[g]<ogMin) || (ogDist && OWN.nd[g]<ogDist) || (exInst && OWN.fl[g])) continue; }
      if(gl){ const la=gl.lat[i], lo=gl.lon[i]; if(!(la>=bb[0]&&la<=bb[2]&&lo>=bb[1]&&lo<=bb[3])) continue; }
      if(cityI>=0 && c.city[i]!==cityI) continue;
      if(zipSet.size && !zipSet.has(c.zip[i])) continue;
      if(craI>=0 && c.cra[i]!==craI) continue;
      const lot=c.lot[i]; if(st.lotMin!=null && lot<st.lotMin) continue; if(st.lotMax!=null && lot>st.lotMax) continue;
      const mv=c.mkt[i]; if(st.mvMin && mv<st.mvMin) continue; if(st.mvMax && mv>st.mvMax) continue;
      const sf=c.sqft[i]; if(st.sfMin!=null && sf<st.sfMin) continue; if(st.sfMax!=null && sf>st.sfMax) continue;
      if(st.noBldg && (sf>0 || c.bldg[i]>0)) continue;
      const yb=c.yb[i]; if(st.ybMin!=null && (!yb||yb<st.ybMin)) continue; if(st.ybMax!=null && (!yb||yb>st.ybMax)) continue;
      if(st.unMin!=null && c.units[i]<st.unMin) continue; if(st.unMax!=null && c.units[i]>st.unMax) continue;
      if(st.bdMin!=null && c.beds[i]<st.bdMin) continue; if(st.stMax!=null && c.stories[i]>st.stMax) continue;
      if(lsMin!=null||lsMax!=null){ if(!mv) continue; const r=c.land[i]/mv; if(lsMin!=null&&r<lsMin) continue; if(lsMax!=null&&r>lsMax) continue; }
      if(hdMinD!=null||hdMaxD!=null){ const d=c.sd1[i], held=d?today-d:99999; if(hdMinD!=null&&held<hdMinD) continue; if(hdMaxD!=null&&held>hdMaxD) continue; }
      if(st.spMin!=null && c.sale1[i]<st.spMin) continue; if(st.spMax!=null && c.sale1[i]>st.spMax) continue;
      if(st.qualOnly && c.sq1[i]!==1) continue;
      const fl=c.flags[i]; if((fl&fMust)!==fMust || (fl&fNot)) continue;
      if(fxOn){ const rel=REL?REL[i]:0; if(wantRel && (!fxTri(rel,fxF.fam) || !fxTri(rel&&(fl&2),fxF.famoos))) continue; if(wantLife && !fxTri(LIF[i],fxF.life)) continue; if(wantDeath && !fxTri(c.dsig[i]&DCB,fxF.death)) continue; }
      if(dsMin && c.dscore[i]<dsMin) continue;
      const sg=c.dsig[i], fsg=sigMask&&!(sg&sigMask)?1:0;
      const li=c.landuse[i], zi=c.zoning[i];
      if(govLU && govLU[li]) continue;
      const mi=c.mz[i];
      const fu=lA&&!lA[li]?1:0, fz=zA&&!zA[zi]?1:0, fm=mA&&!mA[mi]?1:0;
      const kind = fl&8 ? 1 : fl&16 ? 2 : fl&32 ? 3 : 0, fk = wantK>=0 && kind!==wantK ? 1:0;
      const tv=TT[i], ft=tierW&&tv<tierW?1:0, lsp=TS[i]===1, lok=TB[i]===0, lbl=TB[i]===1, flz=lzSel.size&&!((lzSel.has('split')&&lsp)||(lzSel.has('minok')&&lok)||(lzSel.has('below')&&lbl))?1:0, cv=CNa[i], fcn=cnSel.size&&!cnSel.has(cv)?1:0;
      const nf=fu+fz+fm+fk+ft+flz+fcn;
      const vg=VG[i], fvs=vsMask&&!(vg&vsMask)?1:0, pg=PG[i], fpc=pcMask&&!(pg&pcMask)?1:0;
      if(nf===0 && !fvs && sg&4095){ for(let b=0;b<12;b++) if(sg&(1<<b)) dc[b]++; if(!fsg) dc[12]++; }
      if(nf===0 && !fsg && vg){ for(let b=0;b<VSIG.length;b++) if(vg&(1<<b)) vc[b]++; }
      if(nf===0 && !fsg && !fvs && pg){ for(let b=0;b<PCS.length;b++) if(pg&(1<<b)) pcc[b]++; }
      if(fsg||fvs||fpc) continue;
      if(nf===0){ kc[kind]++; lc[li]++; zc[zi]++; mc[mi]++; tcn[tv]++; if(lsp) lzc.split++; if(lok) lzc.minok++; if(lbl) lzc.below++; cnc[cv]++; if(APa[i]) apN++; if(SGa[i]&1) pfN++; if(SGa[i]&6) pbN++; if(asmSeen) asmSeen.add(AGa[i]); if(m===out.length){const o2=new Uint32Array(m*2);o2.set(out);out=o2;} out[m++]=base+i; }
      else if(nf===1){ if(fu) lc[li]++; else if(fz) zc[zi]++; else if(fm) mc[mi]++; else if(ft) tcn[tv]++; else if(flz){ if(lsp) lzc.split++; if(lok) lzc.minok++; if(lbl) lzc.below++; } else if(fcn) cnc[cv]++; else kc[kind]++; }
    }
  }
  results=out.subarray(0,m); facet={lc,zc,kc,mc,dc,vc,pcc,tcn,lzc,cnc,apN,pfN,pbN,asmGroups:asmSeen?asmSeen.size:0};
  if(S.saved){ const ids=savedIdx(), r=[]; for(const x of SV.list()){ const id=ids.get(x.folio); if(id!=null && (!S.svSt.size||S.svSt.has(x.status))) r.push(id); } results=Uint32Array.from(r); }
  renderSavedUI();
  doSort(); renderChips(); renderSummary(); renderAdvCount(st); renderResults(true);
}

/* sorting */
const SORTS=[
  ['ds_d','Highest distress score','dscore',-1],['cm_d','Commercial distress score','cm',-1],['vs_d','Most likely vacant / neglected','vscore',-1],['sv_d','Recently saved','saved',-1],['ogd_d','Owner\'s distressed parcels','ogd',-1],['og_d','Owner\'s portfolio size','ogn',-1],['lot_d','Biggest lot first','lot',-1],['lot_a','Smallest lot first','lot',1],
  ['mv_a','Lowest value first','mkt',1],['mv_d','Highest value first','mkt',-1],
  ['held_d','Owned the longest','sd1',1],['sold_d','Sold most recently','sd1',-1],
  ['yb_a','Oldest building first','yb',1],['lp_d','Most value in the land','landpct',-1],['un_d','Most units','units',-1],['asm_d','Assemblage score (groups together)','asm',-1],['um_d','Highest unit multiple (zoning ÷ existing)','um',-1],['au_d','Most units allowed by zoning','al',-1],['qm_d','Highest buildable sq ft multiple','qm',-1],['ppl_a','Lowest value per lot sq ft','ppl',1],
  ['bld_a','Best buildability first (green to red)','bld',1],['tx_d','Most unpaid tax years (then balance)','txy',-1],['td_a','Soonest tax deed auction','txd',1],['addr_a','Address A–Z','addr',1]];
const SORT_MAP=Object.fromEntries(SORTS.map(s=>[s[0],s]));
function doSort(){
  if(!results.length) return;
  const [, , k, dir]=SORT_MAP[S.sort]||SORTS[0];
  if(k==='addr'){
    if(results.length>200000){ toast('Address sorting works on up to 200,000 results. Narrow the filters first.'); return; }
    const arr=Array.from(results), cache=new Map(), g=id=>{let s=cache.get(id); if(s===undefined){s=getStr(P(id),'addr',I(id)); cache.set(id,s);} return s;};
    arr.sort((a,b)=>{const x=g(a),y=g(b); return x<y?-dir:x>y?dir:0;}); results=Uint32Array.from(arr); return;
  }
  const n=results.length, key=new Float64Array(n);
  if(k==='ogn'||k==='ogd'){ if(!OWN){ loadOwners().then(()=>{ doSort(); renderResults(true); }).catch(()=>{}); return; } const A=k==='ogn'?OWN.n:OWN.nd, inst=$('ogInst').checked;   // banks / government / big institutions rank last unless included
    for(let j=0;j<n;j++){ const id=results[j], c=P(id).c, i=I(id), g=c.og[i]; key[j]=(g&&!(OWN.fl[g]&&!inst)?A[g]:(k==='ogn'?1:(c.dsig[i]&4095?1:0)))*256+c.dscore[i]; } }
  else if(k==='saved'){ for(let j=0;j<n;j++){ const id=results[j], it=SV.get(getStr(P(id),'folio',I(id))); key[j]=it?Date.parse(it.savedAt):0; } }
  else for(let j=0;j<n;j++){ const id=results[j], c=P(id).c, i=I(id);
    key[j] = k==='cm' ? (()=>{ const a=P(id).cm; return a&&a[i]?a[i]*256+c.dscore[i]:-1; })() : k==='asm' ? (()=>{ const g=asmOf(P(id),i); return g?g.score*1e6+(1e6-g.id):-1; })() : (k==='um'||k==='al'||k==='qm') ? (()=>{ const t=P(id).td; const v=t?t[k][i]:NaN; return v===v?v:-1; })() : k==='bld' ? ((c.bld&&c.bld[i]||9)*1e9-c.lot[i]) : k==='txy' ? (c.txy?c.txy[i]*1e10+c.txb[i]:0) : k==='txd' ? (c.txd&&c.txd[i]?c.txd[i]:99999) : k==='vscore' ? (c.vscore?c.vscore[i]:0) : k==='landpct' ? (c.mkt[i]?c.land[i]/c.mkt[i]:-1) : k==='yb' ? (c.yb[i]||9999) : k==='ppl' ? (c.lot[i]&&c.mkt[i]?c.mkt[i]/c.lot[i]:1e12) : c[k][i]; }
  const idx=new Uint32Array(n); for(let i=0;i<n;i++) idx[i]=i;
  const k2=k==='dscore'?(j=>{ const id=results[j]; return P(id).c.mkt[I(id)]; }):k==='vscore'?(j=>{ const id=results[j]; return P(id).c.dscore[I(id)]; }):null;
  idx.sort((a,b)=>(key[a]-key[b])*dir || (k2?k2(b)-k2(a):0) || a-b);
  const r2=new Uint32Array(n); for(let i=0;i<n;i++) r2[i]=results[idx[i]]; results=r2;
}

/* chips & summary */
const short=n=> n>=1e6?(n/1e6).toFixed(1)+'M' : n>=1e4?Math.round(n/1e3)+'K' : fmt.format(n);
function renderChips(){
  if(HAS('mscreen')) mrRender();
  const tc={}, zc={};
  for(let i=0;i<D.landuse.length;i++) tc[LU_T[i]]=(tc[LU_T[i]]||0)+facet.lc[i];
  for(let i=0;i<D.zoning.length;i++) zc[Z_G[i]]=(zc[Z_G[i]]||0)+facet.zc[i];
  const hideGov=$('hideGov').checked;
  $('types').innerHTML=TYPES.filter(([k])=>!(hideGov&&k==='gov')).map(([k,l])=>{ const n=tc[k]||0, on=S.types.has(k);
    const cnt = (k==='condo' && !on) ? '' : `<span class="n">${short(n)}</span>`;
    return `<button type="button" class="chip ${on?'on':''} ${!n&&!on&&k!=='condo'?'zero':''}" data-t="${k}" aria-pressed="${on}">${l}${cnt}</button>`; }).join('');
  $('zones').innerHTML=ZONES.map(([k,l])=>{ const n=zc[k]||0, on=S.zones.has(k);
    return `<button type="button" class="chip ${on?'on':''} ${!n&&!on?'zero':''}" data-z="${k}" aria-pressed="${on}">${l}<span class="n">${short(n)}</span></button>`; }).join('');
  const lm=num('lotMin'), lx=num('lotMax');
  $('lotChips').querySelectorAll('.chip').forEach(b=>{ const v=+b.dataset.v; b.classList.toggle('on', lx==null && (v===0? lm==null : lm===v)); });
  const toks=mzTokens($('mzq').value);
  const mzCount=t=>{ let n=0; for(let i=1;i<MZ.length;i++){ const c=MZ_UP[i]; if(c===t||c.startsWith(t)) n+=facet.mc[i]; } return n; };
  for(const [host,list] of [['mzMiami',MZ_MIAMI],['mzCounty',MZ_COUNTY]]){
    $(host).innerHTML=list.map(([t,l])=>{ const on=toks.includes(t), n=mzCount(t); return `<button type="button" class="chip ${on?'on':''} ${!n&&!on?'zero':''}" data-mz="${t}" aria-pressed="${on}" title="${esc(l)}">${t}<span class="n">${short(n)}</span></button>`; }).join('');
  }
  renderMzCities();
  const tcn=facet.tcn||[0,0,0]; $('tcBasic').textContent=short(tcn[1]+tcn[2]); $('tcStrong').textContent=short(tcn[2]);
  $('tierSeg').querySelectorAll('button').forEach(b=>{ const on=b.dataset.tier===S.tier; b.classList.toggle('on',on); b.setAttribute('aria-pressed',on); });
  const lzc=facet.lzc||{}; $('lotz').innerHTML=LOTZ.map(([k,l])=>{ const on=S.lotz.has(k), n=lzc[k]||0; return `<button type="button" class="chip ${on?'on':''} ${!n&&!on?'zero':''}" data-lz="${k}" aria-pressed="${on}">${l}<span class="n">${short(n)}</span></button>`; }).join('');
  const cnc=facet.cnc||[]; $('cnChips').innerHTML=EX?CN_CATS.map(([k,l])=>{ const on=S.cons.has(k), n=cnc[k]||0; return `<button type="button" class="chip ${on?'on':''} ${!n&&!on?'zero':''}" data-cn="${k}" aria-pressed="${on}">${l}<span class="n">${short(n)}</span></button>`; }).join(''):'<span class="note">Construction data did not load.</span>';
  $('apCount').textContent=EX?'('+fmt.format(facet.apN||0)+')':''; $('apOnly').checked=S.ap; $('pfCount').textContent=SIG?'('+fmt.format(facet.pfN||0)+')':''; $('pbCount').textContent=SIG?'('+fmt.format(facet.pbN||0)+')':''; $('pfOnly').checked=S.pf; $('contOnly').checked=S.cont; $('hideSent').checked=S.hideSent; $('contCount').textContent='('+fmt.format(contSet().size)+')'; $('stHasPhone').checked=S.hasPhone; $('stTraced').checked=S.traced==='y'; $('stNotTraced').checked=S.traced==='n'; $('stPhoneCount').textContent='('+fmt.format(SKS.phoneCount())+')'; $('stTracedCount').textContent='('+fmt.format(SKS.count())+')'; $('cmMin').value=String(S.cm); $('cgasOnly').checked=S.cgas; $('centSel').value=S.cent; $('cmCount').textContent=CM?'('+fmt.format(CM.meta.n)+' on the list)':''; $('dueOnly').checked=S.due; $('stageSel').value=S.stage; $('dueCount').textContent='('+fmt.format(dueCount())+')'; $('pbSel').value=S.pb;
  renderSend();
  $('asmOn').classList.toggle('on',S.asm); $('asmOn').setAttribute('aria-pressed',S.asm); $('asmUp').checked=S.asmUp;
  $('asmN').textContent=S.asm&&ASM?fmt.format(facet.asmGroups||0)+' groups':ASM?fmt.format(ASM.meta.groups)+' groups':'';
  { const g=S.asmGroup&&ASM&&ASM.byId.has(S.asmGroup)?ASM.groups[ASM.byId.get(S.asmGroup)]:null; $('asmRow').hidden=!S.asmGroup; if(g) $('asmLabel').textContent=`Only assemblage #${g.id}: ${asmReason(g)}`; }
  const kc=facet.kc, kAll=kc[0]+kc[1]+kc[2]+kc[3], kN={all:kAll,person:kc[0],corp:kc[1],trust:kc[2]};
  $('ownerKind').innerHTML=OWNER_KINDS.map(([k,l])=>`<button type="button" data-k="${k}" class="${S.owner===k?'on':''}" aria-pressed="${S.owner===k}">${l}<span class="n">${short(kN[k])}</span></button>`).join('');
  renderFacet('zoning'); renderFacet('landuse');
  const dcn=facet.dc||[]; $('dsigs').innerHTML=DSIG.map(([k,l],b)=>{ const on=S.dsig.has(k), n=dcn[b]||0; return `<button type="button" class="chip dchip ${on?'on':''} ${!n&&!on?'zero':''}" data-sig="${k}" aria-pressed="${on}">${l}<span class="n">${short(n)}</span></button>`; }).join('');
  const pcn=facet.pcc||[]; $('pcsigs').innerHTML=PCS.map(([k,l],b)=>{ const on=S.pcs.has(k), n=pcn[b]||0; return `<button type="button" class="chip vchip pchip ${on?'on':''} ${!n&&!on?'zero':''}" data-pc="${k}" aria-pressed="${on}">${l}<span class="n">${short(n)}</span></button>`; }).join('');
  const vcn=facet.vc||[]; $('vsigs').innerHTML=VSIG.map(([k,l,pt],b)=>{ const on=S.vsig.has(k), n=vcn[b]||0; return `<button type="button" class="chip vchip ${pt<0?'neg':''} ${on?'on':''} ${!n&&!on?'zero':''}" data-vs="${k}" aria-pressed="${on}" title="${pt>0?'+':''}${pt} points">${l}<span class="n">${short(n)}</span></button>`; }).join('');
}
function renderMzCities(){
  const host=$('mzCities'); if(!host) return; const by=new Map(), mc=facet.mc||[];
  for(let i=1;i<MZ.length;i++){ const e=MZ[i]; if(!e) continue; const j=e[1]; if(!by.has(j)) by.set(j,new Map()); const g=by.get(j), k=MZ_UP[i]; g.set(k,(g.get(k)||0)+(mc[i]||0)); }
  const order=['Miami','Miami-Dade County'], js=[...by.keys()].sort((a,b)=>{ const x=order.indexOf(a), y=order.indexOf(b); if(x>=0||y>=0) return (x<0?99:x)-(y<0?99:y); return a.localeCompare(b); });
  host.innerHTML='<div class="mzc-h">By city <span class="hint">tap a city to open it; picked codes count only in that city</span></div>'+js.map(j=>{ const g=by.get(j), codes=[...g.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])), tot=codes.reduce((s,x)=>s+x[1],0), sel=codes.filter(([k])=>S.mzSel.has(j+'|'+k)).length, open=S.mzOpen.has(j)||sel>0;
    return `<details class="mzc" data-j="${esc(j)}" ${open?'open':''}><summary>${esc(j==='Miami-Dade County'?'Unincorporated county':j)} <span class="c">${short(tot)} · ${codes.length} codes</span>${sel?` <span class="sel">${sel} picked</span>`:''}</summary><div class="chips">${codes.map(([k,n])=>{ const key=j+'|'+k, on=S.mzSel.has(key); return `<button type="button" class="chip ${on?'on':''} ${!n&&!on?'zero':''}" data-mzs="${esc(key)}" aria-pressed="${on}">${esc(k)}<span class="n">${short(n)}</span></button>`; }).join('')}</div></details>`; }).join('');
}
function median(a){ if(!a.length) return 0; a.sort(); return a[a.length>>1]; }
function renderSummary(){
  const n=results.length; let oos=0, corp=0;
  const lots=new Float64Array(n), mvs=new Float64Array(n); let ln=0, mn=0;
  for(let j=0;j<n;j++){ const id=results[j], c=P(id).c, i=I(id); if(c.lot[i]) lots[ln++]=c.lot[i]; if(c.mkt[i]) mvs[mn++]=c.mkt[i]; const f=c.flags[i]; if(f&2) oos++; if(f&8) corp++; }
  const ml=median(lots.subarray(0,ln)), mm=median(mvs.subarray(0,mn));
  $('sCount').textContent=fmt.format(n); $('liveCount').textContent=fmt.format(n); $('liveCount').classList.remove('busy');
  const bits=[];
  if(ml) bits.push(`Typical lot <b>${fmt.format(Math.round(ml))} sq ft</b> (${acres(ml)})`);
  if(mm) bits.push(`typical value <b>${money(mm)}</b>`);
  if(n) bits.push(`<b>${fmt.format(oos)}</b> out-of-state owners`);
  if(corp) bits.push(`<b>${fmt.format(corp)}</b> owned by companies`);
  let hot=0; for(let j=0;j<n;j++){ const id=results[j]; if(P(id).c.dscore[I(id)]>=50) hot++; } if(hot) bits.push(`<b>${fmt.format(hot)}</b> with a distress score of 50+`);
  if(S.asm&&ASM) bits.push(`in <b>${fmt.format(facet.asmGroups||0)}</b> assemblage groups`);
  $('summary').innerHTML=bits.join(' · ');
}
function renderAdvCount(st){
  const k=ADV_IDS.filter(id=>st[id]!=null).length + (st.noBldg?1:0) + (st.qualOnly?1:0) + (st.cra?1:0) + (st.qScope!=='ao'?1:0) + S.exZ.size + S.exL.size + Object.values(S.flags).filter(v=>v!=='any').length;
  $('advCount').hidden=!k; $('advCount').textContent=k+' on';
  const main=(st.cont?1:0)+(st.hideSent?1:0)+(st.hasPhone?1:0)+(st.traced?1:0)+(st.cm?1:0)+(st.cgas?1:0)+(st.cent?1:0)+(st.bbox?1:0)+(st.q?1:0)+(st.city?1:0)+(st.zips.trim()?1:0)+(st.mzq?1:0)+S.types.size+S.zones.size+(st.lotMin!=null||st.lotMax!=null?1:0)+(st.mvMin||st.mvMax?1:0)+(S.owner!=='all'?1:0)+S.dsig.size+(st.dsMin?1:0)+S.vsig.size+S.pcs.size+(st.vsMin?1:0)+(st.vsMine?1:0)+(S.ogf?1:0)+(st.ogMin?1:0)+(st.ogDist?1:0)+(S.tier!=='any'?1:0)+mrCount()+S.lotz.size+S.cons.size+(S.ap?1:0)+(S.pf?1:0)+(S.pb?1:0)+(S.due?1:0)+(S.stage?1:0)+(S.asm?1:0)+(S.asmUp?1:0)+S.send.size+S.mzSel.size+(rulesDefault()?0:1);
  let badBox=0; HASH_NUM.forEach(id=>{ const el=$(id), v=el.value.trim(), bad=!!v && parseAmt(v)==null; if(bad) badBox++; if(bad) { el.setAttribute('aria-invalid','true'); el.title='Not a number. Try 500k, 1.2m or 750000'; } else if(el.hasAttribute('aria-invalid')){ el.removeAttribute('aria-invalid'); el.title=''; } });
  const tot=k+main; $('onCount').hidden=!tot; $('resetBtn').disabled=!tot&&!badBox; $('onCount').textContent=tot+(tot===1?' filter on':' filters on');
  if(S.saved){ $('onCount').hidden=false; $('onCount').textContent='Saved list · filters paused'; }
}
function renderFacet(f){
  const isZ=f==='zoning', list=$(f+'List'), find=$(f+'Find').value.trim().toUpperCase(), cnt=isZ?facet.zc:facet.lc, vals=D[f], set=isZ?S.exZ:S.exL;
  const items=[]; for(let i=0;i<vals.length;i++){ const v=vals[i]; if(find && !v.toUpperCase().includes(find)) continue; const c=cnt?cnt[i]:0; if(!c && !set.has(i) && !find) continue; items.push([i,v,c]); }
  items.sort((a,b)=>(set.has(b[0])-set.has(a[0]))||b[2]-a[2]);
  list.innerHTML=items.slice(0,300).map(([i,v,c])=>`<label class="${c?'':'zero'}"><input type="checkbox" data-f="${f}" data-i="${i}" ${set.has(i)?'checked':''}><span class="nm" title="${esc(v)}">${esc(v)}</span><span class="ct">${fmt.format(c)}</span></label>`).join('') || '<div class="note" style="padding:9px">No matches.</div>';
}

/* cards */
const PAGE=60; let shown=0;
function ownerBadges(fl){
  const b=[]; if(fl&64) b.push('<span class="hot">Estate / heirs</span>'); if(fl&2) b.push('<span class="warm">Out-of-state owner</span>'); else if((fl&4) && !(fl&1)) b.push('<span>'+(HAS('mscreen')?'Absentee (mails outside '+PFC.cfg.area+')':'Absentee owner')+'</span>');
  if(fl&8) b.push('<span>Company / organization</span>'); if(fl&16) b.push('<span>Trust</span>'); if(fl&1) b.push('<span>Owner lives there</span>'); if(fl&128) b.push('<span>Senior</span>'); return b.join('');
}
function mzLabel(mi){ const e=MZ[mi]; if(!e) return ''; const bits=[]; if(e[4]) bits.push(e[4]+' stories'); if(e[3]&&+e[3]>0) bits.push(e[3]+' units/acre'); return e[2]+(bits.length?' ('+bits.join(', ')+')':''); }
function mzHTML(mi){ const e=MZ[mi]; if(!e) return ''; return `<span class="mzcode">${esc(e[0])}</span> · ${esc(mzLabel(mi))}`; }
function sigBadges(sg){ let h=''; for(let b=0;b<12;b++) if((sg&(1<<b)) && !(HAS('mtax')&&(b===2||b===3||b===4))) h+=`<span class="${DSIG[b][2]}">${DSIG[b][1]}</span>`; return h; }
const vacBadge=(c,i)=>{ const v=c.vscore?c.vscore[i]:0; return v>=25?`<span class="vac ${vsTone(v)}" title="Vacancy / neglect hint ${v} of 100 (public records only)">${v>=40?'Likely vacant':'Possibly vacant'} · ${v}</span>`:''; };
const vsigText=vg=>{ const a=[]; for(let b=0;b<VSIG.length;b++) if(vg&(1<<b)) a.push(VSIG[b][1]); return a.join(', '); };
const scoreBadge=(v,big)=>`<span class="dscore ${dsTone(v)}${big?' big':''}" title="Distress score ${v} of 100">${v}</span>`;
/* FEMA flood zone badge (counties with the flood layer keep the zone label in the 'cra' column / D.cra) */
const floodTag=(c,i)=>{ if(!HAS('flood')) return ''; const z=D.cra[c.cra[i]]||''; return /^V/.test(z)?'<span class="tt hot" title="'+esc(z)+'">Flood VE</span>':/^A/.test(z)?'<span class="tt warm" title="'+esc(z)+'">Flood '+esc(z.split(' ')[0])+'</span>':''; };
function cardHTML(id){
  const p=P(id), i=I(id), c=p.c;
  const addr=getStr(p,'addr',i)||'No street address', lu=D.landuse[c.landuse[i]], zn=D.zoning[c.zoning[i]], t=LU_T[c.landuse[i]], zg=Z_G[c.zoning[i]];
  const lot=c.lot[i], sf=c.sqft[i], mv=c.mkt[i], yb=c.yb[i], un=c.units[i], bd=c.beds[i];
  const bldgS = sf? [yb?'Built '+yb:'', un>1?un+' units':bd?bd+' bd / '+(c.baths[i]/10)+' ba':''].filter(Boolean).join(' · ') : 'Land only';
  const sale = c.sd1[i]? `${monYr(c.sd1[i])}${c.sale1[i]>100?' for '+money(c.sale1[i]):''} · owned ${Math.max(0,Math.floor((today-c.sd1[i])/365.25))} yrs` : 'No sale on record';
  const folio=getStr(p,'folio',i), sv=SV.get(folio);
  return `<article class="card ${sv?'is-saved':''}" data-id="${id}" data-folio="${folio}" tabindex="0" aria-label="${esc(addr)}. Open details">
    <div class="tags"><span class="tt ${TYPE_TONE[t]}">${TYPE_LABEL[t]}</span>${HAS('zoning')?`<span class="tt ${ZONE_TONE[zg]}">Zoned ${ZONE_LABEL[zg].toLowerCase()}</span>`:''}${floodTag(c,i)}${tdTag(p,i)}${HAS('mscreen')?mrBadge(c,i):''}${HAS('mtax')?mtBadge(c,i):''}<span class="tr">${c.dscore[i]?scoreBadge(c.dscore[i]):''}${starHTML(id,folio)}</span></div>
    ${sv?`<div class="svline"><span class="spill st-${stKey(sv.status)}">${esc(sv.status)}</span>${sv.vacant?'<span class="spill vmine" title="You marked it as looking vacant / damaged">Looks vacant (you)</span>':''}<span class="svd">Saved ${svDate(sv.savedAt)}</span>${sv.note||sv.cond?`<span class="svn" title="${esc([sv.note,sv.cond].filter(Boolean).join(' · '))}">${esc(sv.note||sv.cond)}</span>`:''}</div>`:''}
    <div><h3>${esc(addr)}</h3><div class="city">${esc(D.city[c.city[i]])}, FL ${D.zip[c.zip[i]]}</div></div>
    <div class="facts">
      <div><div class="k">Lot</div><div class="v">${!lot?'–':lot>=100000?acres(lot):fmt.format(lot)+' sf'}</div><div class="s">${!lot?'Shared lot':lot>=100000?short(lot)+' sq ft':acres(lot)}</div></div>
      <div><div class="k">Building</div><div class="v">${sf?fmt.format(sf)+' sf':'None'}</div><div class="s">${esc(bldgS)}</div></div>
      <div><div class="k">Value</div><div class="v">${mv?money(mv):'–'}</div><div class="s">${mv&&c.land[i]?Math.round(c.land[i]/mv*100)+'% is land':'&nbsp;'}</div></div>
    </div>
    ${HAS('zoning')?`<div class="line"><span class="k">Zoning</span><span class="v" title="${esc(zn)}">${mzHTML(c.mz[i]) || esc(nice(zn)||'Not listed')}</span></div>`:HAS('flood')?`<div class="line"><span class="k">Flood</span><span class="v">${esc(D.cra[c.cra[i]]||'Not mapped')}</span></div>`:''}
    ${HAS('mscreen')?`<div class="line"><span class="k">Zoning</span><span class="v">${MZ[c.mz[i]]?mzHTML(c.mz[i]):esc(nice(zn)||'Not listed')}</span></div>`:''}
    <div class="line uline"><span class="k">Use</span><span class="v" title="${esc(lu)}">${esc(luNice(lu))}</span></div>
    <div class="line"><span class="k">Sold</span><span class="v">${sale}</span></div>
    <div class="line"><span class="k">Owner</span><span class="v">${esc(getStr(p,'owner',i).split(' | ')[0])}</span></div>
    ${HAS('mscreen')?mrCardLine(c,i):''}${HAS('mtax')?mtCardLine(c,i):''}${upLine(p,i)}
    ${compsLine(id)}${cmLine(folio)}${auLine(folio)}${outLine(folio)}${SKU.cardLine(folio)}
    <div class="sendline">${sendBtns(folio)}${sentBadges(folio)}${p.ap&&p.ap[i]?'<span class="hot apb" title="Adverse possession claim noted in the Property Appraiser legal description">Adverse possession</span>':''}</div>
    <div class="ob">${dueBadge(folio)}${clerkBadges(folio)}${cmBadges(folio)}${c.og[i]&&OWN?`<span class="pf" title="Same owner (name or mailing address) across the county">Owner has ${fmt.format(OWN.n[c.og[i]])}${OWN.nd[c.og[i]]?' · '+fmt.format(OWN.nd[c.og[i]])+' distressed':''}</span>`:''}${asmBadge(p,i)}${vacBadge(c,i)}${sigBadges(c.dsig[i])}${ownerBadges(c.flags[i]&~(c.dsig[i]&1024?64:0))}</div>
  </article>`;
}
function tdTag(p,i){ const t=p.td?p.td.tier[i]:0; return t===2?'<span class="tt tds" title="Strong teardown under your rule">Strong teardown</span>':t===1?'<span class="tt tdb" title="Teardown (basic) under your rule">Teardown</span>':''; }
function upLine(p,i){ const t=p.td; if(!t) return ''; const b=[]; const r1=v=>Math.round(v*10)/10, al=t.al[i], um=r1(t.um[i]), qm=r1(t.qm[i]), sp=t.split[i];
  if(al===al) b.push(`<b>${fmt.format(al)}</b> units allowed${um===um?` (${um}×)`:''}`); else if(qm===qm) b.push(`buildable <b>${qm}×</b> the building`);
  if(t.below[i]===1) b.push('<span class="warmt">lot under zone min</span>'); else if(sp===1) b.push('<span class="okt">could be split</span>');
  return b.length?`<div class="line"><span class="k">Upside</span><span class="v">${b.join(' · ')}</span></div>`:''; }
function renderResults(reset){
  const n=results.length, cardsOn=S.view==='cards', mapOn=S.view==='map', tableOn=S.view==='table', pipeOn=S.view==='pipe';
  $('empty').hidden=n>0 || mapOn || pipeOn;
  $('vCards').classList.toggle('on',cardsOn); $('vTable').classList.toggle('on',tableOn); $('vMap').classList.toggle('on',mapOn); $('vPipe').classList.toggle('on',pipeOn);
  $('cards').hidden=!cardsOn||!n; $('tablebox').hidden=!tableOn||!n; $('mapbox').hidden=!mapOn; $('pipebox').hidden=!pipeOn;
  if(pipeOn){ $('moreRow').hidden=true; if(reset) $('cards').innerHTML=''; renderPipe(); return; }
  if(mapOn){ $('moreRow').hidden=true; if(reset) $('cards').innerHTML=''; showMap(reset); return; }
  if(cardsOn){
    if(reset){ $('cards').innerHTML=''; shown=0; }
    const end=Math.min(n,shown+PAGE); let h=''; for(let j=shown;j<end;j++) h+=cardHTML(results[j]);
    $('cards').insertAdjacentHTML('beforeend',h); shown=end;
    $('moreRow').hidden=shown>=n; $('showMore').textContent=`Show more (${fmt.format(n-shown)} left)`;
  } else { $('moreRow').hidden=true; renderTable(reset); }
}

/* table */
const COLS=[
  {h:'<span class="sr">Saved</span>★',cls:'stc'},{h:'Address',s:'addr_a'},{h:'Score',num:true,s:'ds_d'},{h:'Signals'},{h:'Vacancy',num:true,s:'vs_d'},{h:'Permits & cases'},{h:'Property'},{h:'City zoning'},{h:'Zoning type'},{h:'Lot sq ft',num:true,s:'lot_d'},{h:'Acres',num:true,s:'lot_d'},
  {h:'Building sq ft',num:true},{h:'Units',num:true,s:'un_d'},{h:'Built',num:true,s:'yb_a'},{h:'Value',num:true,s:'mv_d'},
  {h:'Land %',num:true,s:'lp_d'},{h:'Last sale',num:true,s:'sold_d'},{h:'Sale price',num:true},{h:'Owner'},{h:'Phones / email',cls:'stcol'}];
function renderHead(){ $('thead').innerHTML=COLS.map(c=>`<th data-s="${c.s||''}" class="${c.num?'num':''} ${c.cls||''} ${c.s&&S.sort===c.s?'sorted':''}" scope="col">${c.h}</th>`).join(''); }
const sigCodes=sg=>{ const a=[]; for(let b=0;b<12;b++) if(sg&(1<<b)) a.push(DSIG[b][0]); return a.join(' '); };
const sigText=sg=>{ const a=[]; for(let b=0;b<12;b++) if(sg&(1<<b)) a.push(DSIG[b][1]); for(const [b,l] of DSOFT) if(sg&(1<<b)) a.push(l); return a.join(', '); };
function rowHTML(id){
  const p=P(id), i=I(id), c=p.c, mv=c.mkt[i];
  const folio=getStr(p,'folio',i), sv=SV.get(folio);
  return `<tr data-id="${id}" class="${sv?'is-saved':''}"><td class="stc">${starHTML(id,folio)}</td><td class="addr">${esc(getStr(p,'addr',i)||'No street address')}<small>${esc(D.city[c.city[i]])} ${D.zip[c.zip[i]]}${sv?` · <span class="spill st-${stKey(sv.status)}">${esc(sv.status)}</span>`:''}</small></td>
  <td class="num">${c.dscore[i]?scoreBadge(c.dscore[i]):'–'}</td><td class="sigs" title="${esc(sigText(c.dsig[i]))}">${esc(sigCodes(c.dsig[i]))||'–'}</td><td class="num" title="${esc(vsigText(c.vsig?c.vsig[i]:0))}">${c.vscore&&c.vscore[i]?`<span class="vnum ${vsTone(c.vscore[i])}">${c.vscore[i]}</span>`:'–'}${sv&&sv.vacant?' <span class="vmine" title="You marked it vacant / damaged">●</span>':''}</td><td class="sigs" title="${esc(pcsText(c.pcs?c.pcs[i]:0))}">${esc(pcsCodes(c.pcs?c.pcs[i]:0))||'–'}</td>
  <td>${TYPE_LABEL[LU_T[c.landuse[i]]]}</td><td title="${esc(mzLabel(c.mz[i]))}"><span class="mzcode">${MZ[c.mz[i]]?esc(MZ[c.mz[i]][0]):'–'}</span></td><td title="${esc(D.zoning[c.zoning[i]])}">${esc(nice(D.zoning[c.zoning[i]])||'–')}</td>
  <td class="num">${c.lot[i]?fmt.format(c.lot[i]):'–'}</td><td class="num">${c.lot[i]?(c.lot[i]/SQFT_AC).toFixed(2):'–'}</td>
  <td class="num">${c.sqft[i]?fmt.format(c.sqft[i]):'–'}</td><td class="num">${c.units[i]||'–'}</td><td class="num">${c.yb[i]||'–'}</td>
  <td class="num">${mv?dollars(mv):'–'}</td><td class="num">${mv?Math.round(c.land[i]/mv*100)+'%':'–'}</td>
  <td class="num">${dateStr(c.sd1[i])||'–'}</td><td class="num">${c.sale1[i]?dollars(c.sale1[i]):'–'}</td><td>${esc(getStr(p,'owner',i))}</td><td class="stcell">${SKU.cellHTML(folio)}</td></tr>`;
}
const ROWH=40; let lastRange='';
function renderTable(reset){
  const sc=$('scroller'); if(reset){ sc.scrollTop=0; lastRange=''; renderHead(); }
  const total=results.length, vh=sc.clientHeight||600;
  const first=Math.max(0,Math.floor(sc.scrollTop/ROWH)-10), last=Math.min(total,first+Math.ceil(vh/ROWH)+20);
  const key=first+':'+last+':'+total; if(!reset && key===lastRange) return; lastRange=key;
  let h=`<tr class="spacer"><td colspan="${COLS.length}" style="height:${first*ROWH}px"></td></tr>`;
  for(let j=first;j<last;j++) h+=rowHTML(results[j]);
  h+=`<tr class="spacer"><td colspan="${COLS.length}" style="height:${(total-last)*ROWH}px"></td></tr>`;
  $('tbody').innerHTML=h;
}

/* distress score breakdown (mirrors build_distress.py points() + build_data.py soft signals; see README) */
function scoreParts(p,i,folio){
  const c=p.c, fl=c.flags[i], sg=c.dsig[i], parts=[];
  const hp=(DIST&&DIST.pts&&DIST.pts[folio])||{};
  for(const [k,v] of Object.entries(hp)) parts.push([DSIG[DBIT[k]][1],v]);
  if((fl&64) && !hp.PR) parts.push(['Estate / heirs in the owner name', hp.DC?7:15]);
  const soft=[]; const gov=fl&32, corp=fl&8;
  if(fl&2) soft.push(['Out-of-state owner',6]); else if(fl&4) soft.push([HAS('mscreen')?'Absentee owner (mails outside '+PFC.cfg.area+')':'Absentee owner (mails to another ZIP)',4]);
  const yrs=c.sd1[i]?(today-c.sd1[i])/365.25:0; if(yrs>=20) soft.push(['Owned 20+ years',5]); else if(yrs>=10) soft.push(['Owned 10+ years',2]);
  const bv=c.bldg[i], mv=c.mkt[i]; if(bv>0&&mv>0&&bv/mv<0.2) soft.push(['Building under 20% of value (teardown)',6]); else if(!bv&&c.lot[i]>0&&!corp&&!gov) soft.push(['Vacant lot',3]);
  if(!(fl&1)&&!corp&&!gov) soft.push(['No homestead exemption',3]);
  let st=soft.reduce((a,b)=>a+b[1],0); if(st>20) soft.push(['Owner/property signals capped at 20',20-st]);
  const vs=c.vscore?c.vscore[i]:0; if(vs>=40) soft.push([`Vacancy / neglect hint ${vs} (capped soft signal)`, vs>=60?8:5]);
  return parts.concat(soft);
}
function distressHTML(p,i,folio){
  const c=p.c, v=c.dscore[i], sg=c.dsig[i];
  const recs=(DIST&&DIST.recs[folio])||[];
  const parts=scoreParts(p,i,folio), tot=parts.reduce((a,b)=>a+b[1],0);
  if(!v && !recs.length) return `<h3>Distress signals</h3><div class="note">No foreclosure, tax, code, lien or probate records matched this folio${DIST?' (data built '+esc(DIST.built)+')':''}.</div>`;
  const order=Object.fromEntries(DSIG.map((d,k)=>[d[0],k]));
  const items=recs.slice().sort((a,b)=>order[a[0]]-order[b[0]]||(b[1]>a[1]?1:-1)).map(r=>{ const [code,date,title,amt,ref,url,extra]=r;
    return `<li><span class="dtag ${DSIG[order[code]][2]}">${esc(DSIG[order[code]][1])}</span> <b>${esc(title)}</b>${date?' · '+esc(date):''}${amt?' · '+dollars(Math.round(amt)):''}${ref?`<br><span class="mono">${esc(ref)}</span>`:''}${extra?`<small>${esc(extra)}</small>`:''}${url?` <a href="${esc(url)}" target="_blank" rel="noopener">source ↗</a>`:''}</li>`; }).join('');
  return `<h3>Distress signals ${scoreBadge(v,true)}</h3>
    <div class="dbreak">${parts.map(([l,n])=>`<div><span>${esc(l)}</span><b>${n>0?'+':''}${n}</b></div>`).join('')}<div class="tot"><span>Distress score${tot>100?' (capped at 100)':''}</span><b>${v}</b></div></div>
    ${items?`<ul class="dlist">${items}</ul>`:''}
    <div class="note">Records matched to this folio from public sources. Confirm status at the source before acting: cases close and liens get released.</div>`;
}

/* permit / code-case data coverage per city (meta.permitCov, built by scripts/merge_permits.py + permit_lib.py) */
function covShort(cv,kind){
  if(!cv) return 'Not covered';
  const lv=cv[kind+'_level'], from=cv[kind+'_from'], src=cv[kind+'_src'];
  if(lv==='none'||!from) return cv.status==='none'?'None (no public source)':cv.status==='portal'?'None (portal not machine-readable)':'None';
  return `Since ${from.slice(0,7)}${lv==='half'?' (5-8 yrs)':lv==='recent'?' (under 5 yrs)':''} - ${src}`;
}
function covHTML(cv,folio){
  if(!cv) return '<div class="note">No permit-coverage information for this city.</div>';
  const pl=cv.permit_level, cl=cv.code_level, esc2=esc, link=cv.portal?` <a href="${esc2(cv.portal)}" target="_blank" rel="noopener">${esc2(cv.tech||'portal')} ↗</a>`:'';
  const pTxt = pl==='full'||pl==='half' ? `Permit history is covered since <b>${esc2(cv.permit_from.slice(0,7))}</b> (${cv.permit_years} yrs) from ${esc2(cv.permit_src)}. “No permit” counts toward the vacancy hint${pl==='half'?' at half weight (window is under 8 yrs)':''}.`
    : pl==='recent' ? `Only <b>${cv.permit_years} yrs</b> of permit history (since ${esc2(cv.permit_from.slice(0,7))}) from ${esc2(cv.permit_src)}. Too short to say “no permit”, so absence of a permit is <b>not</b> used in the vacancy hint.`
    : `<b>No public permit data</b> for ${esc2(cv.city)}${cv.reason?': '+esc2(cv.reason):''}. Absence of a permit is <b>not</b> used in the vacancy hint.${link}`;
  const cTxt = cl==='none' ? `<b>No public code-case data</b> for ${esc2(cv.city)}${cv.code_note?' ('+esc2(cv.code_note)+')':''}.` : `Code cases covered since <b>${esc2(cv.code_from.slice(0,7))}</b> from ${esc2(cv.code_src)}.`;
  return `<div class="pcov"><div>${pTxt}</div><div>${cTxt}</div></div>`;
}
function permitsHTML(p,i,folio){
  const c=p.c, cv=PCOV[folio.slice(0,2)], lp=c.lperm?c.lperm[i]:0, n5=c.pn5?c.pn5[i]:0, co=c.cn_open?c.cn_open[i]:0, c5=c.cn5?c.cn5[i]:0;
  const pcs=c.pcs?c.pcs[i]:0, ps=getStr(p,'psum',i), cs=getStr(p,'csum',i);
  const dl=[['Last permit', lp?`<b>${dateStr(lp)}</b>${ps?`<small>${esc(ps)}</small>`:''}`:''],['Permits, last 5 yrs', n5?String(n5):''],['Code cases', cs?`${co?`<b>${co} open</b> · `:''}${c5} in the last 5 yrs<small>${esc(cs)}</small>`:''],['Flags', pcsText(pcs&127)]].filter(x=>x[1]);
  return `<h3>Permits &amp; code cases</h3>${dl.length?`<div class="dl">${dl.map(([k,v])=>`<div class="k">${k}</div><div class="v">${v}</div>`).join('')}</div>`:'<div class="note">No permits or code cases on record for this parcel in the sources we cover.</div>'}
    <div class="pcovbox" data-cov="${esc(folio.slice(0,2))}"><div class="note"><b>Permit data coverage — ${esc(cv?cv.city:'this city')}</b></div>${covHTML(cv,folio)}</div>`;
}
/* vacancy / condition hint (mirrors scripts/vacancy_lib.py) */
function vacParts(c,i,folio){
  const vg=c.vsig?c.vsig[i]:0, fl=c.flags[i], yb=c.yb[i], parts=[];
  for(let b=0;b<VSIG.length;b++){ if(!(vg&(1<<b))) continue; let [k,l,pt]=VSIG[b];
    if(k==='NA'){ pt=fl&2?18:15; l=fl&2?'No homestead + owner mails from out of state':'No homestead + owner mails elsewhere (absentee)'; }
    if(k==='NP'){ const cv=PCOV[folio.slice(0,2)]||{}, half=cv.permit_level==='half', y=(cv.permit_from||'').slice(0,4)||'?', old=yb&&yb<=1970; pt=half?(old?5:3):(old?10:6); l=`${old?`Built ${yb}, no`:'No'} permit on record since ${y} (${cv.city||'city'} permit data${half?', 5-8 yr window: half points':''})`; }
    if(k==='US') l='Open unsafe structure case'; if(k==='NG') l='Neglect-type code case (overgrowth / junk / abandoned / upkeep / minimum housing / unsecured pool)';
    if(k==='FR') l='Foreclosure registry code case (registration required)'; if(k==='XP') l='Expired or revoked permit (no newer permit)'; if(k==='LB') l='Building worth under 20% of the total value';
    if(k==='TX') l='Tax delinquent (certificate, tax deed or unpaid taxes)'; if(k==='ES') l='Estate / probate / owner deceased'; if(k==='OV') l='Other open code or building case';
    if(k==='RP') l='Permit issued in the last 24 months (someone is working on it)';
    parts.push([l,pt]); }
  if(!(vg&1) && c.bldg[i]>0 && !(fl&1) && !(fl&8) && !(fl&32)) parts.push(['No homestead exemption (owner mail at the property)',5]);
  return parts;
}
function vacancyHTML(p,i,folio){
  const c=p.c, v=c.vscore?c.vscore[i]:0, g=p.geo, la=g?g.lat[i]:NaN, lo=g?g.lon[i]:NaN, hasG=isFinite(la)&&la>20;
  const parts=vacParts(c,i,folio), raw=parts.reduce((a,b)=>a+b[1],0), lp=c.lperm?c.lperm[i]:0, cityCov=false;
  const sv=SV.get(folio), d=0.0011, bbox=hasG?[lo-d*1.25,la-d*0.8,lo+d*1.25,la+d*0.8].map(x=>x.toFixed(6)).join(','):'';
  const aerial=hasG?`<a class="aerial" href="https://www.google.com/maps/@?api=1&map_action=map&center=${la.toFixed(6)},${lo.toFixed(6)}&zoom=20&basemap=satellite" target="_blank" rel="noopener" title="Open satellite view in Google Maps"><img alt="Aerial photo of the parcel (Esri World Imagery)" loading="lazy" width="400" height="256" src="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox=${bbox}&bboxSR=4326&imageSR=3857&size=400,256&format=jpg&f=image"><span class="pin" aria-hidden="true"></span><small>Aerial: Esri World Imagery (dates vary) · open satellite ↗</small></a>`:'';
  const links=hasG?`<div class="links vlinks"><a href="https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${la.toFixed(6)},${lo.toFixed(6)}" target="_blank" rel="noopener">Street View ↗</a><a href="https://www.google.com/maps/@?api=1&map_action=map&center=${la.toFixed(6)},${lo.toFixed(6)}&zoom=20&basemap=satellite" target="_blank" rel="noopener">Satellite ↗</a></div>`:'';
  const cvv=PCOV[folio.slice(0,2)], permit=lp?`Last permit on record: <b>${dateStr(lp)}</b>`:(cvv&&(cvv.permit_level==='full'||cvv.permit_level==='half'))?`No permit on record since ${cvv.permit_from.slice(0,4)} (${esc(cvv.city)} permit data)`:'Permit history for this city is not covered, so "no permit" is not scored';
  if(!c.bldg[i]) return `<h3>Vacancy &amp; condition</h3><div class="note">No building on record, so there is no vacancy hint.</div>${aerial}${links}`;
  return `<h3>Vacancy &amp; condition ${v?`<span class="vnum big ${vsTone(v)}" title="Vacancy / neglect hint ${v} of 100">${v}</span>`:''}</h3>
    ${v>=25?`<div class="vword ${vsTone(v)}">${vsWord(v)}</div>`:''}
    ${parts.length?`<div class="dbreak">${parts.map(([l,n])=>`<div><span>${esc(l)}</span><b>${n>0?'+':''}${n}</b></div>`).join('')}<div class="tot"><span>Vacancy hint${raw>100?' (capped at 100)':raw<0?' (floored at 0)':''}</span><b>${v}</b></div></div>`:'<div class="note">No vacancy or neglect signals in the public records.</div>'}
    <div class="note">${permit}. ${sv&&sv.vacant?'<b>You marked it as looking vacant / damaged.</b> ':''}A hint from public records only (no utility data is published) — drive by or check Street View before acting.</div>
    ${aerial}${links}`;
}

/* detail drawer */
function finHTML(folio){
  const LS=window.PFLenders; if(!LS) return '';
  const ds=LS.dealsFor(folio); if(!ds.length && !SV.has(folio)) return '';
  const need=ds.reduce((a,d)=>Math.max(a,d.requested),0), com=ds.reduce((a,d)=>a+d.committed,0);
  return `<h3>Financing</h3>${ds.length?`<div class="note">Needed ${dollars(need)} · committed ${dollars(com)}</div><ul class="finlist">${ds.map(d=>{ const l=LS.lender(d.lenderId); return `<li><button type="button" class="lnk" data-findeal="${d.id}">${esc(l?LS.lenderLabel(l):'No lender yet')}</button> <span class="spill st-${stKey(d.stage)}">${esc(d.stage)}</span><small>requested ${dollars(d.requested)} · committed ${dollars(d.committed)}${d.note?' · '+esc(d.note):''}</small></li>`; }).join('')}</ul>`:'<div class="note">No lender linked yet.</div>'}
    <button type="button" class="btn" data-finadd="${folio}">+ Add lender / deal</button>`;
}
/* outreach (stored on the saved item by saved.js): stage, next follow-up, activity log */
const todayDay=()=>new Date().toLocaleDateString('en-CA');
const ACT_LABEL=Object.fromEntries(SV.ACT_TYPES);
const shortDay=d=>d?new Date(d+'T12:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric'}):'';
function dueBadge(folio){ const d=SV.dueState(folio,todayDay()); if(!d) return ''; return `<span class="hot dueb" title="Next follow-up ${esc(SV.get(folio).next)}">${d.overdue?'Overdue '+d.days+'d':'Due today'}</span>`; }
function outLine(folio){ const x=SV.get(folio); if(!x) return ''; const lt=SV.lastTouch(folio); if(x.stage==='New'&&!lt&&!x.next) return '';
  return `<div class="line outline"><span class="k">Pipeline</span><span class="v"><b>${esc(x.stage)}</b>${lt?' · last '+esc(ACT_LABEL[lt.type].toLowerCase())+' '+shortDay(lt.d):''}${x.next?' · next '+shortDay(x.next):''}</span></div>`; }
function outInner(folio){ const x=SV.get(folio)||{stage:'New',next:'',acts:[]}, lt=SV.lastTouch(folio), t=todayDay();
  return `<div class="outrow"><label class="svl">Stage <select id="outStage">${SV.STAGES.map(s=>`<option ${s===x.stage?'selected':''}>${s}</option>`).join('')}</select></label>
    <label class="svl">Next follow-up <input type="date" id="outNext" value="${esc(x.next)}"></label>${dueBadge(folio)}</div>
    <div class="note">${lt?`Last touch: ${esc(ACT_LABEL[lt.type])} ${esc(lt.d)}${lt.outcome?' · '+esc(lt.outcome):''}`:'No contact logged yet.'}</div>
    <div class="outlog"><select id="actType" aria-label="Activity">${SV.ACT_TYPES.map(([k,l])=>`<option value="${k}">${l}</option>`).join('')}</select><input type="date" id="actDate" value="${t}" aria-label="Activity date">
      <select id="actOutcome" aria-label="Outcome">${SV.OUTCOMES.map(o=>`<option value="${esc(o)}">${o?esc(o):'Outcome…'}</option>`).join('')}</select><input type="text" id="actNote" maxlength="2000" placeholder="Note (optional)" aria-label="Activity note"><button class="btn primary" type="button" id="actAdd">Log</button></div>
    ${x.acts.length?`<ul class="actlist">${x.acts.map(a=>`<li data-act="${esc(a.id)}"><b>${esc(ACT_LABEL[a.type])}</b> ${esc(a.d)}${a.outcome?' · '+esc(a.outcome):''}${a.note?`<small>${esc(a.note)}</small>`:''} <button type="button" class="lnk" data-actdel="${esc(a.id)}">Delete</button></li>`).join('')}</ul>`:''}
    <div class="note">Logging an activity saves the property to your saved list. Back up from the Pipeline view.</div>`; }
function outreachHTML(id,folio){ return `<h3>Outreach</h3><div class="outbox" id="outBox" data-folio="${folio}" data-id="${id}">${outInner(folio)}</div>`; }
function outFolios(){ if(!S.due&&!S.stage) return null; const t=todayDay(), out=new Set(); for(const x of SV.list()){ if(S.due&&!SV.dueState(x.folio,t)) continue; if(S.stage&&x.stage!==S.stage) continue; out.add(x.folio); } return out; }
function dueCount(){ const t=todayDay(); let n=0; for(const x of SV.list()) if(SV.dueState(x.folio,t)) n++; return n; }
function renderPipe(){ const ids=savedIdx(), t=todayDay(), by=Object.fromEntries(SV.STAGES.map(s=>[s,[]]));
  for(const x of SV.list()) by[x.stage].push(x);
  const key=x=>{ const d=SV.dueState(x.folio,t); return [d?0:1, x.next||'9999', x.updatedAt]; };
  $('pipeCols').innerHTML=SV.STAGES.map(s=>{ const a=by[s].sort((p,q)=>{ const A=key(p),B=key(q); return A[0]-B[0]||(A[1]<B[1]?-1:A[1]>B[1]?1:0)||(B[2]<A[2]?-1:1); });
    return `<section class="pcol" data-stage="${esc(s)}"><h3>${esc(s)} <span class="n">${a.length}</span></h3>${a.map(x=>{ const id=ids.get(x.folio), lt=SV.lastTouch(x.folio);
      return `<button type="button" class="pitem" data-pipe="${x.folio}" ${id==null?'data-missing="1"':''}><b>${esc(x.addr||folioFmt(x.folio))}</b><span>${esc(x.city||'')}</span><small>${lt?'Last '+esc(ACT_LABEL[lt.type].toLowerCase())+' '+shortDay(lt.d):'No contact yet'}${x.next?' · next '+shortDay(x.next):''}</small>${dueBadge(x.folio)}</button>`; }).join('')||'<div class="note">None</div>'}</section>`; }).join('');
  const n=SV.count(), d=dueCount(); $('pipeInfo').textContent=n?`${fmt.format(n)} saved properties · ${fmt.format(d)} follow-up${d===1?'':'s'} due today or overdue`:'Nothing in your pipeline yet. Save a property or log an activity in its details.'; }
function savedBoxHTML(id,folio){
  const sv=SV.get(folio);
  if(!sv) return `<div class="svbox off"><button type="button" class="btn svsave" data-star="${folio}" data-id="${id}" aria-pressed="false">${STAR_SVG}Save this property</button><span class="note">Keep it on your saved list with a status and notes.</span></div>`;
  return `<div class="svbox"><div class="svhead"><button type="button" class="btn svsave on" data-star="${folio}" data-id="${id}" aria-pressed="true" title="Remove from saved">${STAR_SVG}Saved</button><span class="note">Saved ${svDate(sv.savedAt)}${sv.updatedAt!==sv.savedAt?' · edited '+svDate(sv.updatedAt):''}</span></div>
    <label class="svl" for="svStatusSel">Status</label><select id="svStatusSel">${SV.STATUSES.map(s=>`<option ${s===sv.status?'selected':''}>${s}</option>`).join('')}</select>
    <label class="svl" for="svNote">Notes</label><textarea id="svNote" rows="3" placeholder="Called owner, left voicemail…" maxlength="5000">${esc(sv.note)}</textarea>
    <label class="check svvac"><input type="checkbox" id="svVacant" ${sv.vacant?'checked':''}> Looks vacant / damaged</label>
    <label class="svl" for="svCond">Condition note</label><textarea id="svCond" rows="2" placeholder="Boarded windows, tall grass, roof tarp…" maxlength="2000">${esc(sv.cond||'')}</textarea>
    <span class="note" id="svNoteMsg">Notes save automatically in this browser.</span></div>`;
}

function teardownHTML(p,i){
  const z=zoneOf(p,i), ev=tdEval(p,i), r=S.rules, nf=v=>v==null?'':fmt.format(v);
  const verdict=ev.strong?'<span class="tt tds">Strong teardown</span>':ev.basic?'<span class="tt tdb">Teardown (basic)</span>':'<span class="tt">Not a teardown</span>';
  const zr=z?[z.min_lot_sf?nf(z.min_lot_sf)+' sf min lot':'',z.upa?z.upa+' units/acre':'',z.far?'FAR '+z.far:'',z.stories?z.stories+' stories':'',z.height_ft?z.height_ft+' ft':'',z.lot_cov?z.lot_cov+'% coverage':''].filter(Boolean).join(' · '):'';
  return `<h3>Teardown & zoning upside</h3><div class="dl">${[
    ['Verdict', verdict+(ev.reasons.length?`<small>${esc(ev.reasons.join('; '))}</small>`:`<small>Meets your rule: land ≥ ${Math.round(r.min_land_share*100)}%, built ≤ ${r.max_year_built}${ev.strong?', zoning allows the multiple':''}</small>`)],
    ['Zone rules', zr?esc(zr)+(z.src?`<small>Source: ${esc(z.src)} · confirm with the city</small>`:''):'Not confirmed for this code'],
    ['Units allowed', ev.allowed!=null?`${fmt.format(ev.allowed)} (${ev.um}× the ${Math.max(p.c.units[i],1)} there now)`:''],
    ['Buildable sq ft', ev.sqft!=null?`${fmt.format(ev.sqft)} sf by ${ev.basis}${ev.qm!=null?` (${ev.qm}× the building)`:''}`:''],
    ['Story multiple', ev.sm!=null?ev.sm+'×':''],
    ['Lot vs zone minimum', ev.below==null?'':ev.below?'<b>Under</b> the zone minimum':ev.split?`Meets it, and is ≥ ${r.lot_split_factor}× (could be split)`:'Meets it']
  ].filter(x=>x[1]!=='').map(([k,v])=>`<div class="k">${k}</div><div class="v">${v}</div>`).join('')}</div>`;
}
async function openDrawer(id,opts){
  if(OGMAP){ OGMAP.remove(); OGMAP=null; }
  if(!P(id).det){ toast('Loading details…'); try{ await Promise.all([loadDetail(P(id).idx), loadGeo(P(id).idx).catch(()=>{})]); }catch(e){ toast('Details did not load. Try again.'); return; } }
  if(!P(id).geo){ try{ await loadGeo(P(id).idx); }catch(e){} }
  if(!ASM){ try{ await loadAsm(); }catch(e){} }
  if(!CP){ try{ await loadComps(); }catch(e){} }
  if(P(id).c.dsig[I(id)] && !DIST){ try{ await loadDistress(); }catch(e){ toast('Distress details did not load.'); } }
  const p=P(id), i=I(id), c=p.c, folio=getStr(p,'folio',i), addr=getStr(p,'addr',i)||'No street address';
  const city=D.city[c.city[i]], zip=D.zip[c.zip[i]], fl=c.flags[i], mv=c.mkt[i], zn=D.zoning[c.zoning[i]], lu=D.landuse[c.landuse[i]];
  const rows=pairs=>pairs.filter(x=>x[1]!==''&&x[1]!=null).map(([k,v])=>`<div class="k">${k}</div><div class="v">${v}</div>`).join('');
  const gq=encodeURIComponent(addr+', '+city+', FL '+zip);
  const owner=[]; OWNER_ROWS.forEach(([k,l])=>{ if(fl&FLAG[k]) owner.push(l); }); if(fl&32) owner.push('Government owner');
  const g=p.geo, la=g?g.lat[i]:NaN, lo=g?g.lon[i]:NaN, hasG=isFinite(la)&&la>20;
  const oname=getStr(p,'owner',i).split(' | ')[0], og=c.og[i];
  if(og && !OWN){ try{ await loadOwners(); }catch(e){} }
  const prv=c.prv?c.prv[i]:0, chg=(prv&&mv)?Math.round((mv-prv)/prv*100):null;
  const dn=deedCount(p,i), multi=dn>1&&c.sale1[i]>1000;
  const sale3=c.sd3&&c.sd3[i]? dateStr(c.sd3[i])+(c.sale3[i]>100?' for '+dollars(c.sale3[i]):'') : '';
  $('drawerHost').innerHTML=`<div class="scrim" id="scrim"></div><aside class="drawer" role="dialog" aria-modal="true" aria-label="Property details">
    <button class="btn" id="closeD" type="button" style="float:right">Close</button>
    <div class="note" style="font-family:var(--f-mono)">Folio ${folioFmt(folio)}</div>
    <h2>${esc(addr)}</h2><div class="sub">${esc(city)}, FL ${zip}</div>
    <div class="links">
      <a href="${PFC.cfg.paUrl(folio)}" target="_blank" rel="noopener">Property Appraiser page ↗</a>
      <a href="https://www.google.com/maps/search/?api=1&query=${hasG&&!getStr(p,'addr',i)?la.toFixed(6)+','+lo.toFixed(6):gq}" target="_blank" rel="noopener">Google Maps ↗</a>
      ${hasG?`<a href="https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${la.toFixed(6)},${lo.toFixed(6)}" target="_blank" rel="noopener">Street View ↗</a>`:''}
      <button class="btn" type="button" id="copyFolio">Copy folio</button>
      <button class="btn" type="button" id="copyLink" title="Link that opens this property directly">Copy link</button>
      <button class="btn" type="button" id="onMap">Show on map</button>
    </div>
    <div class="sendline dsend">${sendBtns(folio)}${sentBadges(folio)}</div>
    <div id="savedBox" data-folio="${folio}" data-id="${id}">${savedBoxHTML(id,folio)}</div>
    ${SKU.drawerHTML(folio)}
    ${outreachHTML(id,folio)}
    <div id="finBox">${finHTML(folio)}</div>
    ${distressHTML(p,i,folio)}${clerkHTML(folio)}${cmHTML(folio)}
    ${vacancyHTML(p,i,folio)}
    ${HAS('mscreen')?(PFC.id==='broward'?bwPermitsHTML(p,i):mrPermitsHTML(p,i)):permitsHTML(p,i,folio)}
    ${HAS('mtax')?mtHTML(p,i):''}${HAS('mscreen')?mrHTML(p,i):''}${asmHTML(p,i)}${teardownHTML(p,i)}
    <h3>The property</h3><div class="dl">${rows([
      ['What it is', `${TYPE_LABEL[LU_T[c.landuse[i]]]}<small>${esc(lu)}</small>`],
      ['City zoning', MZ[c.mz[i]] ? `<span class="mzcode">${esc(MZ[c.mz[i]][0])}</span> · ${esc(MZ[c.mz[i]][1])}<small>${esc(mzLabel(c.mz[i]))}${MZ[c.mz[i]][5]?' · min lot '+fmt.format(+MZ[c.mz[i]][5])+' sq ft':''}</small>` : 'Not found on the zoning map'],
      ['Zoning type (appraiser)', HAS('mscreen')?'':`${ZONE_LABEL[Z_G[c.zoning[i]]]}${nice(zn)?' · '+esc(nice(zn)):''}<small>${esc(zn)}</small>`],
      ['Lot size', c.lot[i]? fmt.format(c.lot[i])+' sq ft · '+(c.lot[i]/SQFT_AC).toFixed(3)+' acres':'Not listed'],
      ['Building', c.sqft[i]?fmt.format(c.sqft[i])+' sq ft living area':'No building on record'],
      ['Beds / baths', (c.beds[i]||c.baths[i])? c.beds[i]+' beds / '+(c.baths[i]/10)+' baths':''],
      ['Units', c.units[i]||''],['Stories', c.stories[i]||''],['Year built', c.yb[i]||''],
      ['Buildings on the lot', c.bcount&&c.bcount[i]>1?c.bcount[i]:''],
      ['Construction', p.cn&&EX?(p.cn[i]?esc(CN_LABEL[p.cn[i]]):'<span class="note">Unknown</span>')+'<small>Main building, Property Appraiser building details</small>':''],
      ['Adverse possession', p.ap&&p.ap[i]?'<b>Claim noted</b><small>F.S. 95.18 / DR-452, from the Property Appraiser legal description</small>':''],
      [HAS('flood')?'FEMA flood zone':'Redevelopment area', esc(D.cra[c.cra[i]]||'')],['Legal description', esc(getStr(p,'legal',i))]])}</div>
    <h3>${META.rollYear||''} values</h3><div class="dl">${rows([
      ['Market value', dollars(mv)],['Land', dollars(c.land[i])+(mv?`<small>${Math.round(c.land[i]/mv*100)}% of the total</small>`:'')],['Building', dollars(c.bldg[i])],
      ['Assessed (capped)', dollars(c.assd[i])],['Taxable (county)', dollars(c.taxable[i])],
      ['Value per lot sq ft', (mv&&c.lot[i])?'$'+(mv/c.lot[i]).toFixed(2):''],['Value per building sq ft', (mv&&c.sqft[i])?'$'+Math.round(mv/c.sqft[i]):''],
      ['Last year\'s value', prv? dollars(prv)+(chg!==null?`<small class="${chg>=0?'up':'down'}">${chg>=0?'+':''}${chg}% this year</small>`:''):''],
      ['Last sale vs today', (c.sale1[i]>1000&&mv&&c.sq1[i]===1&&!multi)? `Value is ${(mv/c.sale1[i]).toFixed(1)}× the last market sale price` : '']])}</div>
    <h3>Value estimate (comps)</h3>${compsDrawer(p,i)}
    <h3>Sales</h3><div class="dl">${rows([
      ['Last sale', c.sd1[i]? dateStr(c.sd1[i])+' for '+dollars(c.sale1[i])+(c.sq1[i]===1?'<small>Market sale</small>':c.sq1[i]===2?'<small>Not a market sale (family transfer, deed fix, etc.)</small>':'') : 'None on record'],
      ['Owned for', c.sd1[i]? ((today-c.sd1[i])/365.25).toFixed(1)+' years':''],
      ['Sold by', esc(c.sd1[i]&&p.s.grantor?getStr(p,'grantor',i):'')],
      ['Deed (book-page)', c.sd1[i]&&p.s.book&&getStr(p,'book',i)? esc(getStr(p,'book',i))+(dn>1?`<small>This deed covered ${fmt.format(dn)} parcels${multi?', so the price is likely for all of them':''}</small>`:''):''],
      ['Sale before that', c.sd2[i]? dateStr(c.sd2[i])+' for '+dollars(c.sale2[i])+(c.sq2&&c.sq2[i]===2?'<small>Not a market sale</small>':'') : ''],
      ['Earlier sale', sale3]])}</div>
    <h3>Owner</h3><div class="dl">${rows([
      ['Name', esc(getStr(p,'owner',i)).replace(/ \| /g,'<br>')],['Mailing address', esc(getStr(p,'mail',i))],['About the owner', owner.join(', ')||'Nothing flagged'],
      ['Portfolio', og&&OWN? `<b>${fmt.format(OWN.n[og])} properties</b> · ${money(OWN.mv[og]*1000)} total · ${fmt.format(OWN.nd[og])} with distress records <button type="button" class="lnk" id="ownerOpen">Open owner portfolio</button>${ogFlags(OWN.fl[og]).length?`<small>Flagged: ${ogFlags(OWN.fl[og]).join(', ')} (left out of portfolio filters unless included)</small>`:''}<small>Grouped by owner name${OWN.nv[og]>1?' ('+OWN.nv[og]+' spellings/entities)':''} and shared mailing address.</small>` : 'Only property under this owner']])}</div>
  </aside>`;
  const close=()=>{ $('drawerHost').innerHTML=''; MAP_SEL=-1; if(mapLayer) mapLayer.redraw(); };
  $('scrim').onclick=close; $('closeD').onclick=close; $('copyFolio').onclick=()=>copy(folio,'Folio copied'); $('copyLink').onclick=()=>copy(folioLink(folio),'Link copied'); $('closeD').focus();
  $('onMap').onclick=()=>{ close(); MAP_SEL=id; MAP_FOCUS=id; S.view='map'; save(); renderResults(true); };
  if($('ownerOpen')) $('ownerOpen').onclick=()=>openOwner(og,id);
  if(opts&&opts.backOwner){ const b=document.createElement('button'); b.type='button'; b.className='btn back'; b.textContent='← Owner portfolio'; b.style.float='right'; b.onclick=()=>openOwner(opts.backOwner); $('closeD').after(b); }
  if(!hasG && !p.geo) loadGeo(p.idx).catch(()=>{});
  MAP_SEL=id; if(mapLayer) mapLayer.redraw();
}
document.addEventListener('keydown',e=>{ if(e.key==='Escape' && $('drawerHost').innerHTML){ $('drawerHost').innerHTML=''; MAP_SEL=-1; if(mapLayer) mapLayer.redraw(); } });

/* owner portfolio panel */
let OGMAP=null;
async function ownerIds(g){
  await loadOwners(); if(OWN.nc[g] && !PACKS[1]) await loadPack(1,'Loading condo units…');
  const ids=[]; for(const p of PACKS){ if(!p) continue; const a=p.c.og, base=p.idx*16777216; for(let i=0;i<p.n;i++) if(a[i]===g) ids.push(base+i); }
  ids.sort((x,y)=>P(y).c.dscore[I(y)]-P(x).c.dscore[I(x)] || P(y).c.mkt[I(y)]-P(x).c.mkt[I(x)]); return ids;
}
const exportName=(kind,n)=>{ const d=new Date(); return `miami-dade-${kind}-${n}-${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}.csv`; };
async function exportIds(ids,kind,btn){
  const lab=btn?btn.textContent:''; if(btn){ btn.disabled=true; btn.textContent='Preparing…'; }
  try{ await ensureDetail(); await ensureGeo(); await loadDistress(); await loadAsm().catch(()=>{}); await new Promise(r=>setTimeout(r,30));
    const url=URL.createObjectURL(buildCSV(ids)), a=document.createElement('a'); a.href=url; a.download=exportName(kind,ids.length); document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),60000); toast(fmt.format(ids.length)+' properties exported');
    const fl=[], im=new Map(); for(let j=0;j<ids.length;j++){ const f=getStr(P(ids[j]),'folio',I(ids[j])); fl.push(f); im.set(f,ids[j]); } EXP_PENDING={folios:fl,ids:im,day:dayStr(new Date())}; renderExpBar(); }
  catch(e){ toast('Export failed: '+(e&&e.message||e)); }
  if(btn){ btn.disabled=false; btn.textContent=lab; }
}
async function showOwnerAs(g,view){
  const ids=await ownerIds(g); if(!ids.length) return;
  $('drawerHost').innerHTML=''; if(OGMAP){ OGMAP.remove(); OGMAP=null; }
  clearIdea(); applyState({...BLANK(), hideGov:false, sort:'ds_d', view, ogf:getStr(P(ids[0]),'folio',I(ids[0]))}); S.og=g; renderOgRow(); run();
  $('results').scrollIntoView({block:'start'});
}
async function openOwner(g,backId){
  toast('Loading owner portfolio…');
  let ids; try{ ids=await ownerIds(g); }catch(e){ toast('Owner data did not load: '+e.message); return; }
  await Promise.all([...new Set(ids.map(id=>id>>>24))].map(k=>Promise.all([loadDetail(k).catch(()=>{}),loadGeo(k).catch(()=>{})])));
  if(OGMAP){ OGMAP.remove(); OGMAP=null; }
  let mv=0, held=0, nh=0, oos=0, dist=0, hs=0; const types=new Map(), sig=new Array(12).fill(0), names=new Map(), mails=new Map(), cities=new Map();
  for(const id of ids){ const p=P(id), i=I(id), c=p.c; mv+=c.mkt[i]; if(c.sd1[i]){ held+=(today-c.sd1[i])/365.25; nh++; } if(c.flags[i]&2) oos++; if(c.flags[i]&1) hs++;
    const t=TYPE_LABEL[LU_T[c.landuse[i]]]; types.set(t,(types.get(t)||0)+1); const sg=c.dsig[i]; if(sg&4095) dist++; for(let b=0;b<12;b++) if(sg&(1<<b)) sig[b]++;
    const on=getStr(p,'owner',i).split(' | ')[0]; names.set(on,(names.get(on)||0)+1); const ct=D.city[c.city[i]]; cities.set(ct,(cities.get(ct)||0)+1);
    if(p.s.mail){ const m=getStr(p,'mail',i); if(m) mails.set(m,(mails.get(m)||0)+1); } }
  const top=(m,k)=>[...m.entries()].sort((a,b)=>b[1]-a[1]).slice(0,k);
  const fl=ogFlags(OWN.fl[g]), LIM=400;
  const rowsH=ids.slice(0,LIM).map(id=>{ const p=P(id), i=I(id), c=p.c; return `<div class="ogitem"><button type="button" class="ogopen" data-id="${id}"><b>${esc(getStr(p,'addr',i)||'No street address')}</b><small>${TYPE_LABEL[LU_T[c.landuse[i]]]} · ${esc(D.city[c.city[i]])} · ${c.mkt[i]?money(c.mkt[i]):'–'}${c.dsig[i]&4095?' · '+esc(sigCodes(c.dsig[i]&4095)):''}</small></button>${c.dscore[i]?scoreBadge(c.dscore[i]):''}${starHTML(id,getStr(p,'folio',i))}</div>`; }).join('');
  $('drawerHost').innerHTML=`<div class="scrim" id="scrim"></div><aside class="drawer ogdrawer" role="dialog" aria-modal="true" aria-label="Owner portfolio">
    <button class="btn" id="closeD" type="button" style="float:right">Close</button>${backId!=null?'<button class="btn back" id="ogBack" type="button" style="float:right;margin-right:8px">← Property</button>':''}
    <div class="note eyebrow">Owner portfolio</div>
    <h2>${esc(OWN.name[g])}</h2>
    <div class="sub">${fmt.format(ids.length)} properties in ${esc(PFC.cfg.name)}${fl.length?` · <span class="flagged">${esc(fl.join(', '))}</span>`:''}</div>
    <div class="ogstats">
      <div><div class="k">Properties</div><div class="v">${fmt.format(ids.length)}</div><small>${OWN.nc[g]?fmt.format(OWN.nc[g])+' condo units':'&nbsp;'}</small></div>
      <div><div class="k">Market value</div><div class="v">${money(mv)}</div><small>${dollars(mv)}</small></div>
      <div><div class="k">Distressed</div><div class="v">${fmt.format(dist)}</div><small>with public-record signals</small></div>
      <div><div class="k">Avg years held</div><div class="v">${nh?(held/nh).toFixed(1):'–'}</div><small>${fmt.format(oos)} mailed out of state · ${fmt.format(hs)} homestead</small></div>
    </div>
    <div class="links">
      <button class="btn" type="button" id="ogMapBtn">Show all on map</button><button class="btn" type="button" id="ogTblBtn">Show all in table</button>
      <button class="btn primary" type="button" id="ogCsv">Export CSV</button><button class="btn" type="button" id="ogCopy">Copy folios</button>
    </div>
    <div id="ogMap" class="ogmap" aria-label="Map of this owner's properties"></div>
    <h3>What they own</h3><div class="ogchips">${top(types,20).map(([t,n])=>`<span>${esc(t)} <b>${fmt.format(n)}</b></span>`).join('')}</div>
    <div class="ogchips muted">${top(cities,8).map(([t,n])=>`<span>${esc(t)} <b>${fmt.format(n)}</b></span>`).join('')}</div>
    <h3>Distress across the portfolio</h3>${sig.some(Boolean)?`<div class="ogchips">${DSIG.map(([k,l,t],b)=>sig[b]?`<span class="${t}">${esc(l)} <b>${fmt.format(sig[b])}</b></span>`:'').join('')}</div>`:'<div class="note">No public-record distress signals on any of these parcels.</div>'}
    <h3>Names and mailing addresses</h3><div class="dl">
      <div class="k">Owner names</div><div class="v">${top(names,8).map(([t,n])=>`${esc(t)} <small style="display:inline">(${n})</small>`).join('<br>')}${names.size>8?`<small>+${names.size-8} more names</small>`:''}</div>
      <div class="k">Mails to</div><div class="v">${mails.size?top(mails,4).map(([t,n])=>`${esc(t)} <small style="display:inline">(${n})</small>`).join('<br>'):'–'}</div></div>
    <div class="note">Grouped by normalized owner name (companies and trusts) or name + mailing address (individuals), plus names that share a specific mailing address (up to 12 names per group, so registered-agent and law-firm addresses don't chain unrelated owners). Check the Sunbiz record before treating entities as one owner.</div>
    <h3>Their properties ${ids.length>LIM?`<small class="note">(top ${LIM} by distress score; use Show all in table for the rest)</small>`:''}</h3>
    <div class="oglist">${rowsH}</div>
  </aside>`;
  const close=()=>{ if(OGMAP){ OGMAP.remove(); OGMAP=null; } $('drawerHost').innerHTML=''; };
  $('scrim').onclick=close; $('closeD').onclick=close; $('closeD').focus();
  if($('ogBack')) $('ogBack').onclick=()=>openDrawer(backId);
  $('ogMapBtn').onclick=()=>showOwnerAs(g,'map'); $('ogTblBtn').onclick=()=>showOwnerAs(g,'table');
  $('ogCsv').onclick=e=>exportIds(ids,'owner',e.currentTarget);
  $('ogCopy').onclick=()=>copy(ids.map(id=>getStr(P(id),'folio',I(id))).join('\n'),fmt.format(ids.length)+' folios copied');
  $('drawerHost').querySelector('.oglist').addEventListener('click',e=>{ if(e.target.closest('[data-star]')) return; const b=e.target.closest('.ogopen'); if(b) openDrawer(+b.dataset.id,{backOwner:g}); });
  try{ await loadLeaflet(); if(!$('ogMap')) return; if(!TONE_RGB) toneSetup();
    const dark=matchMedia('(prefers-color-scheme: dark)').matches && document.documentElement.dataset.theme!=='light';
    OGMAP=L.map('ogMap',{zoomControl:true,attributionControl:true,preferCanvas:true});
    L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${dark?'Dark':'Light'}_Gray_Base/MapServer/tile/{z}/{y}/{x}`,{maxZoom:20,maxNativeZoom:16,attribution:'Esri'}).addTo(OGMAP);
    const pts=[]; for(const id of ids.slice(0,5000)){ const p=P(id), g2=p.geo, i=I(id); if(!g2||!(g2.lat[i]>20)) continue; const ll=[g2.lat[i],g2.lon[i]]; pts.push(ll);
      L.circleMarker(ll,{radius:5,weight:1,color:'#0C0E10',fillColor:SC_RGB[scIdx(p.c.dscore[i])].css,fillOpacity:.9}).bindTooltip(esc(getStr(p,'addr',i)||'No street address')).on('click',()=>openDrawer(id,{backOwner:g})).addTo(OGMAP); }
    if(pts.length) OGMAP.fitBounds(pts,{padding:[18,18],maxZoom:16}); else OGMAP.setView(PFC.cfg.center,10);
  }catch(e){ const m=$('ogMap'); if(m) m.textContent='The map did not load.'; }
}

/* export */
function toast(msg){ const t=document.createElement('div'); t.className='toast'; t.textContent=msg; document.body.appendChild(t); setTimeout(()=>t.remove(),2600); }
async function copy(text,ok){
  try{ await navigator.clipboard.writeText(text); toast(ok); }
  catch(e){ const ta=document.createElement('textarea'); ta.value=text; document.body.appendChild(ta); ta.select(); try{ document.execCommand('copy'); toast(ok); }catch(_){ toast('Copying was blocked here.'); } ta.remove(); }
}
const csvq=s=>/[",\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;
function distCSV(folio){ const r=DIST&&DIST.recs[folio]; if(!r) return ['','']; return [csvq(r.map(x=>[x[0],x[1],x[2],x[4],x[3]?'$'+Math.round(x[3]):''].filter(Boolean).join(' ')).join('; ')), csvq([...new Set(r.map(x=>x[5]).filter(Boolean))].join(' '))]; }
function savedCSV(folio){ const x=SV.get(folio); return x?['Y',csvq(x.status),x.savedAt.slice(0,10),csvq(x.note),x.vacant?'Y':'',csvq(x.cond||'')]:['','','','','',''];}
/* export rows: Folio always dashed 13-digit (Excel keeps it as text); Address never blank. When the roll has no site address
   (mostly vacant land), use the street of the nearest parcel that has one (geo pack), else a short legal description. */
let ADDR_GRID=null;
function addrGrid(){ if(ADDR_GRID) return ADDR_GRID; if(PACKS.some(p=>p&&!p.geo)) return null; const g=new Map();
  for(const p of PACKS){ if(!p) continue; for(let i=0;i<p.n;i++){ const la=p.geo.lat[i], lo=p.geo.lon[i]; if(!(la>20)) continue; const a=getStr(p,'addr',i); if(!a||!/^\d+[A-Z]?\s+\S/.test(a)) continue;
    const k=Math.floor(la*200)*100000+Math.floor(-lo*200); let b=g.get(k); if(!b) g.set(k,b=[]); b.push(la,lo,p.idx*16777216+i); } }
  return ADDR_GRID=g; }
function nearStreet(p,i){ const g=addrGrid(); if(!g) return ''; const la=p.geo.lat[i], lo=p.geo.lon[i]; if(!(la>20)) return '';
  const cx=Math.floor(la*200), cy=Math.floor(-lo*200); let best=1e9, id=-1;
  for(let dx=-1;dx<=1;dx++) for(let dy=-1;dy<=1;dy++){ const b=g.get((cx+dx)*100000+cy+dy); if(!b) continue; for(let k=0;k<b.length;k+=3){ const d=(b[k]-la)**2+((b[k+1]-lo)*0.9)**2; if(d<best){ best=d; id=b[k+2]; } } }
  return id<0?'':getStr(P(id),'addr',I(id)).replace(/^\d+[A-Z]?(-\d+)?\s+/,''); }
const folio13=f=>{ if(PFC.id==='broward') return String(f||'').toUpperCase(); const d=String(f||'').replace(/\D/g,''); if(!d) return ''; if(PFC.id!==PFC.DEFAULT) return d.length===14?d.slice(0,8)+'-'+d.slice(8):d; return folioFmt(d.padStart(13,'0')); };
const EXPSTAT={real:0,near:0,legal:0,use:0};
function exportAddr(p,i){ const a=getStr(p,'addr',i).trim(); if(a){ EXPSTAT.real++; return a; }
  const use=TYPE_LABEL[LU_T[p.c.landuse[i]]]||'Parcel', st=nearStreet(p,i); if(st){ EXPSTAT.near++; return `No site address – ${use}, near ${st}`; }
  const lg=(p.det?getStr(p,'legal',i):'').replace(/\s+/g,' ').trim(); if(lg){ EXPSTAT.legal++; return `No site address – ${use}, ${lg.length>48?lg.slice(0,48)+'…':lg}`; }
  EXPSTAT.use++; return `No site address – ${use}`; }
/* mailing string -> [street, city, state, zip]. Packs hold one mail string ("1420 NW NORTH RIVER DR STE 430, MIAMI, FL 33125[-3027]").
   Only a US "…, CITY, ST 12345[-6789]" tail is split; foreign / unparseable strings stay whole in the street column with blank parts.
   Zips stay strings; 3-4 digit zips of the 0-prefixed states (some Monroe rows lost the leading zero) are left-padded back to 5. */
const US_ST=new Set('AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR VI GU AS MP AA AE AP'.split(' ')), ZERO_ST=new Set(['CT','MA','ME','NH','NJ','RI','VT','PR','VI','AE']);
function splitMail(s){ s=String(s||'').replace(/\s+/g,' ').trim(); if(!s) return ['','','',''];
  const pt=s.split(/\s*,\s*/); if(pt.length<3) return [s,'','',''];
  const m=pt[pt.length-1].match(/^([A-Za-z]{2})\.? (\d{3,5})(?:-?(\d{4}))?$/), city=pt[pt.length-2], st=m&&m[1].toUpperCase();
  if(!m||!US_ST.has(st)||!city||/\d/.test(city)||!pt.slice(0,-2).join('').trim()) return [s,'','',''];
  let z=m[2]; if(z.length<5){ if(!ZERO_ST.has(st)) return [s,'','','']; z=z.padStart(5,'0'); }
  return [pt.slice(0,-2).join(', '),city,st,z+(m[3]?'-'+m[3]:'')]; }
const propZip=z=>{ z=String(z||'').trim(); return /^\d{5}(-\d{4})?$/.test(z)?z:''; };
// columns: Owner Name, Property Address, Property City, Property State, Property Zip, Property County, Mailing Address, Mailing City, Mailing State, Mailing Zip, Folio
function contactRow(owner,addr,city,zip,mail,folio){ return [csvq(owner),csvq(addr),csvq(city),'FL',propZip(zip),csvq(PFC.cfg.name),...splitMail(mail).map(csvq),folio].join(','); }
function exportRow(p,i){ const c=p.c; return contactRow(getStr(p,'owner',i).split(' | ').filter(Boolean).join('; '),exportAddr(p,i),D.city[c.city[i]]||'',D.zip[c.zip[i]]||'',getStr(p,'mail',i),folio13(getStr(p,'folio',i))); }
const EXP_HEAD='Owner Name,Property Address,Property City,Property State,Property Zip,Property County,Mailing Address,Mailing City,Mailing State,Mailing Zip,Folio\n';
function buildCSV(ids=results){
  // export = contact list only (main export and Send to lists): see EXP_HEAD
  const parts=[EXP_HEAD]; let buf=''; for(const k in EXPSTAT) EXPSTAT[k]=0;
  for(let j=0;j<ids.length;j++){
    const id=ids[j], p=P(id), i=I(id);
    buf+=exportRow(p,i)+'\n';
    if(buf.length>1e6){ parts.push(buf); buf=''; }
  }
  parts.push(buf); return new Blob(parts,{type:'text/csv'});
}
function tdCSV(p,i){ const z=zoneOf(p,i)||{}, t=p.td, ev=tdEval(p,i), f=getStr(p,'folio',i), nn=v=>v===v&&v!=null?v:'';
  return [ev.strong?'Strong':ev.basic?'Teardown':'',csvq(ev.reasons.join('; ')),z.min_lot_sf||'',z.upa||'',z.stories||'',z.far||'',t?nn(t.al[i]):'',t?nn(Math.round(t.um[i]*10)/10):'',t?nn(Math.round(t.qm[i]*10)/10):'',t&&t.below[i]>=0?(t.below[i]?'Under':'Meets'):'',t&&t.split[i]===1?'Y':'',p.cn&&EX?csvq(CN_LABEL[p.cn[i]]):'',p.ap&&p.ap[i]?'Y':'',isTagged(f,'cc')?'Y':'',isTagged(f,'dk')?'Y':'',...asmCSV(p,i)]; }
function asmCSV(p,i){ const g=asmOf(p,i); return g?[g.id,g.score,g.mem.length,g.owners,g.lot,g.units==null?'':g.units,g.gain,g.upside?'Y':'',csvq(asmReason(g))]:['','','','','','','','','']; }
$('exportBtn').onclick=async()=>{ if(results.length) return exportIds(results,S.saved?'saved':S.ogf?'owner':'properties',$('exportBtn'));
  if(!results.length){ toast('Nothing to export yet.'); return; }
  const btn=$('exportBtn'); btn.disabled=true; btn.textContent='Preparing…';
  try{ await ensureDetail(); await ensureGeo(); await loadDistress(); await loadAsm().catch(()=>{}); }catch(e){ toast('Export data did not load. Try again.'); btn.disabled=false; btn.textContent='Export CSV'; return; }
  btn.textContent='Building CSV…'; await new Promise(r=>setTimeout(r,30));
  try{
    const d=new Date(), name=`miami-dade-${S.saved?'saved':'properties'}-${results.length}-${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}.csv`;
    const url=URL.createObjectURL(buildCSV()), a=document.createElement('a'); a.href=url; a.download=name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),60000); toast(fmt.format(results.length)+' properties exported');
  }catch(e){ toast('Export failed: '+(e&&e.message||e)); }
  btn.disabled=false; btn.textContent='Export CSV';
};
$('linkBtn').onclick=()=>{ save(); copy(location.href,'Link copied. It reopens this exact search.'); };
$('copyBtn').onclick=()=>{ const n=Math.min(results.length,50000), a=new Array(n); for(let j=0;j<n;j++){ const id=results[j]; a[j]=getStr(P(id),'folio',I(id)); } copy(a.join('\n'),(n<results.length?'First ':'')+fmt.format(n)+' folios copied'); };

/* shareable URL hash */
const HASH_NUM=NUM_IDS.concat(['mvMin','mvMax']);
function writeHash(st){
  try{
    const h=new URLSearchParams();
    if(st.q) h.set('q',st.q); if(st.qScope&&st.qScope!=='ao') h.set('in',st.qScope);
    if(st.city) h.set('city',st.city); if(st.zips&&st.zips.trim()) h.set('zip',st.zips.trim()); if(st.cra) h.set('cra',st.cra); if(st.mzq) h.set('code',st.mzq);
    if(st.types.length) h.set('type',st.types.join(',')); if(st.zones.length) h.set('zone',st.zones.join(','));
    if(st.exZ.length) h.set('pz',st.exZ.map(v=>v.split(' - ')[0]).join(','));
    if(st.exL.length) h.set('lu',st.exL.map(v=>v.split(' - ')[0]).join(','));
    if(st.owner&&st.owner!=='all') h.set('owner',st.owner);
    if(st.dsig&&st.dsig.length) h.set('sig',st.dsig.join(',')); if(st.dsMin) h.set('ds',st.dsMin);
    if(st.vsig&&st.vsig.length) h.set('vsig',st.vsig.join(',')); if(st.pcs&&st.pcs.length) h.set('pcs',st.pcs.join(',')); if(st.vsMin) h.set('vs',st.vsMin); if(st.vsMine) h.set('vme','1');
    OWNER_ROWS.forEach(([k])=>{ const v=st.flags[k]; if(v==='yes'||v==='no') h.set('o_'+k,v); });
    FX_ROWS.forEach(([k])=>{ const v=st.fx&&st.fx[k]; if(v==='yes'||v==='no') h.set('x_'+k,v); });
    HASH_NUM.forEach(id=>{ if(st[id]!=null && st[id]!=='' && !(id.startsWith('mv')&&!st[id])) h.set(id,st[id]); });
    if(!st.hideGov) h.set('gov','1'); if(st.noBldg) h.set('land','1'); if(st.qualOnly) h.set('mkt','1');
    if(st.sort&&st.sort!=='lot_d') h.set('sort',st.sort); if(st.view&&st.view!=='cards') h.set('view',st.view);
    if(st.bbox) h.set('area',st.bbox.join(',')); mrHashWrite(h,st);
    if(st.ogf) h.set('ogf',st.ogf); if(st.ogMin) h.set('ogn',st.ogMin); if(st.ogDist) h.set('ogd','1'); if(st.ogInst) h.set('ogi','1');
    if(st.tier&&st.tier!=='any') h.set('td',st.tier); if(st.lotz&&st.lotz.length) h.set('lotz',st.lotz.join(',')); if(st.cons&&st.cons.length) h.set('cn',st.cons.join(',')); if(st.ap) h.set('ap','1'); if(st.send&&st.send.length) h.set('send',st.send.join(',')); if(st.mzSel&&st.mzSel.length) h.set('mzs',st.mzSel.join(';')); if(st.asm) h.set('asm','1'); if(st.asmUp) h.set('asmup','1'); if(st.asmGroup) h.set('asmg',st.asmGroup);
    if(st.rules&&!RULE_KEYS.every(k=>st.rules[k]===TD.DEFAULT_RULES[k])) h.set('tdr',RULE_KEYS.map(k=>k==='enforce_min_lot'?(st.rules[k]?1:0):st.rules[k]).join(','));
    if(st.due) h.set('due','1'); if(st.stage) h.set('stage',st.stage); if(st.pf) h.set('pf','1'); if(st.cm) h.set('cm',String(st.cm)); if(st.cont) h.set('cont','1'); if(st.hideSent) h.set('hs','1'); if(st.hasPhone) h.set('ph','1'); if(st.traced) h.set('trc',st.traced); if(st.cgas) h.set('cgas','1'); if(st.cent) h.set('cent',st.cent); if(st.pb) h.set('pb',st.pb); if(st.saved) h.set('saved','1'); if(st.saved&&st.svSt&&st.svSt.length) h.set('sst',st.svSt.join(','));
    const str=h.toString(), want=str?'#'+str:'';
    // a new history entry once the search has been still for a moment (so Back undoes a filter step, not each keystroke)
    if(location.hash!==want){ const now=Date.now(), push=!HIST.restoring && now-HIST.last>1200; HIST.last=now;
      history[push?'pushState':'replaceState'](null,'',want||(location.pathname+location.search)); }
    HIST.url=location.hash;
  }catch(e){}
}
function parseHash(){
  const raw=location.hash.replace(/^#/,''); if(!raw) return null;
  const h=new URLSearchParams(raw); if(![...h.keys()].length) return null;
  const list=k=>(h.get(k)||'').split(',').map(x=>x.trim()).filter(Boolean);
  const byCode=(dict,codes)=>codes.map(code=>dict.find(v=>v.split(' - ')[0]===code)).filter(Boolean);
  const st={...BLANK()};
  st.q=h.get('q')||''; st.qScope=h.get('in')||'ao'; st.city=h.get('city')||''; st.zips=h.get('zip')||''; st.cra=h.get('cra')||''; st.mzq=h.get('code')||'';
  st.types=list('type'); st.zones=list('zone'); st.exZ=byCode(D.zoning,list('pz')); st.exL=byCode(D.landuse,list('lu'));
  st.dsig=list('sig'); st.dsMin=+h.get('ds')||0; st.vsig=list('vsig'); st.pcs=list('pcs'); st.vsMin=+h.get('vs')||0; st.vsMine=h.get('vme')==='1';
  st.fx={}; FX_ROWS.forEach(([k])=>{ const v=h.get('x_'+k); if(v==='yes'||v==='no') st.fx[k]=v; });
  st.owner=h.get('owner')||'all'; st.flags={}; OWNER_ROWS.forEach(([k])=>{ const v=h.get('o_'+k); if(v==='yes'||v==='no') st.flags[k]=v; });
  HASH_NUM.forEach(id=>{ const v=h.get(id); st[id]=(v==null||v==='')?null:(isFinite(+v)?+v:null); });
  st.hideGov=h.get('gov')!=='1'; st.noBldg=h.get('land')==='1'; st.qualOnly=h.get('mkt')==='1';
  st.sort=h.get('sort')||'lot_d'; st.view=h.get('view')||'cards';
  st.ogf=(h.get('ogf')||'').replace(/\D/g,''); st.ogMin=+h.get('ogn')||0; st.ogDist=h.get('ogd')==='1'; st.ogInst=h.get('ogi')==='1';
  st.saved=h.get('saved')==='1'; st.svSt=list('sst');
  st.tier=h.get('td')||'any'; st.lotz=list('lotz'); st.cons=list('cn').map(Number); st.ap=h.get('ap')==='1'; st.due=h.get('due')==='1'; st.stage=h.get('stage')||''; st.pf=h.get('pf')==='1'; st.cm=+h.get('cm')||0; st.cont=h.get('cont')==='1'; st.hideSent=h.get('hs')==='1'; st.hasPhone=h.get('ph')==='1'; st.traced=['y','n'].includes(h.get('trc'))?h.get('trc'):''; st.cgas=h.get('cgas')==='1'; st.cent=h.get('cent')||''; st.pb=h.get('pb')||''; st.send=list('send'); st.mzSel=(h.get('mzs')||'').split(';').filter(Boolean); st.asm=h.get('asm')==='1'; st.asmUp=h.get('asmup')==='1'; st.asmGroup=+h.get('asmg')||0;
  const tr=(h.get('tdr')||'').split(','); if(tr.length===RULE_KEYS.length||tr.length===RULE_KEYS.length-1){ st.rules={}; RULE_KEYS.forEach((k,j)=>{ if(j>=tr.length) st.rules[k]=TD.DEFAULT_RULES[k]; else st.rules[k]=k==='enforce_min_lot'?tr[j]==='1':+tr[j]; }); }
  const a=list('area').map(Number); st.bbox=a.length===4&&a.every(Number.isFinite)?a:null; mrHashRead(h,st,list);
  return st;
}


/* ===== Monroe County: buildability screen, ROGO / Tier, environment, signals (data/monroe/*, scripts/counties/monroe/) =====
   Packs carry bld (1 green, 2 yellow, 3 red), tier, rogo, env (bitmask), sigm (bitmask); detail carries the reasons text ("R~text¦Y~text¦G~text¦i~text").
   SCREENING TOOL only - built from public map layers; confirm with Monroe County / city planning. */
const MR_RATE=[['G','Green','Likely buildable','No blockers found'],['Y','Yellow','Needs work',(PFC.cfg.planning||{}).rateY||''],['R','Red','Blocked / unlikely',(PFC.cfg.planning||{}).rateR||'']];
const MR_TIER=[[1,'Tier I'],[2,'Tier II'],[3,'Tier III'],[4,'Tier III-A'],[0,'City / none']];
const MR_ROGO=[[1,'ROGO awarded'],[2,'Applied, not awarded'],[3,'Dedicated (retired)'],[4,'Dedication record'],[0,'No record']];
const MR_SIG=[['rogo_award','ROGO awarded',4096],['vacant','Vacant lot',512],['teardown','Teardown',16384],['dup','Duplex / multifamily zoning',2048],['absentee','Owner mails outside '+(PFC.cfg.area||'the area'),256],['fc_open',PFC.id==='broward'?'Foreclosure auction scheduled':'Foreclosure case open',1],['pr_open','Probate case open',4],['taxdeed',PFC.id==='broward'?'Tax-deed sale scheduled':'Tax-deed notice',16],['code','Code case',32]].filter(x=>!(PFC.id==='broward'&&['rogo_award','pr_open','code'].includes(x[0])));
const MR_AVOID=(PFC.id==='broward'?x=>x.filter(y=>y[0]==='ve'):x=>x)([['wet','Wetland / mangrove / water',4|8|16|16384],['fnai','Conservation land',1],['ff','Florida Forever',2],['upland','Hammock / pineland',32],['cbrs','CBRS',64],['species','Protected species',128|256],['ve','Flood VE',-1]]);
const MR_ZT=[['sf','Single-family'],['duplex','Duplex'],['mf','Multifamily'],['mixed','Mixed use'],['com','Commercial'],['ind','Industrial / marine'],['civic','Public'],['other','Conservation / other'],['none','No digital map']];
const MT_CHIPS=[['any','Tax delinquent'],['y2','2+ years unpaid'],['y3','3+ years unpaid'],['cert','Investor holds a certificate'],['county','County-held certificate']].concat(HAS('mtdeed')?[['deed','Tax deed auction upcoming'],['applied','Tax deed applied for']]:[]);
const MT_MIN=[[0,'Any balance'],[1000,'$1,000+'],[5000,'$5,000+'],[10000,'$10,000+'],[25000,'$25,000+'],[50000,'$50,000+'],[100000,'$100,000+']];
const MR_BITS=Object.fromEntries(MR_SIG.map(([k,,b])=>[k,b])), MR_AV=Object.fromEntries(MR_AVOID.map(([k,,b])=>[k,b]));
const MR_ENVL=[[1,'Conservation land'],[2,'Florida Forever'],[4,'Freshwater wetland'],[8,'Estuarine wetland'],[16,'Mangrove / marsh'],[32,'Hammock / pineland'],[64,'CBRS'],[128,'Protected species'],[256,'Key deer area'],[512,'Historic district'],[1024,'Substantial damage'],[16384,'Open water']];
const mrArr=(a,ok)=>[...(a||[])].filter(x=>ok.includes(x));
function mrRead(){ const m=S.mr; return {rate:[...m.rate],tier:[...m.tier],rogo:[...m.rogo],sig:[...m.sig],avoid:[...m.avoid],zt:[...m.zt],tax:[...S.mt.tax],txmin:S.mt.min}; }
function mrApply(st){ st=st||{}; const m=S.mr; m.rate=new Set(mrArr(st.rate,['G','Y','R'])); m.tier=new Set((st.tier||[]).map(Number).filter(x=>MR_TIER.some(t=>t[0]===x))); m.rogo=new Set((st.rogo||[]).map(Number).filter(x=>MR_ROGO.some(t=>t[0]===x)));
  m.sig=new Set(mrArr(st.sig,MR_SIG.map(x=>x[0]))); m.avoid=new Set(mrArr(st.avoid,MR_AVOID.map(x=>x[0]))); m.zt=new Set(mrArr(st.zt,MR_ZT.map(x=>x[0])));
  S.mt.tax=new Set(HAS('mtax')?mrArr(st.tax,MT_CHIPS.map(x=>x[0])):[]); S.mt.min=HAS('mtax')&&MT_MIN.some(x=>x[0]===+st.txmin)?+st.txmin:0; }
function mrHashWrite(h,st){ const m=st.mr; if(!m) return; if(m.rate.length) h.set('bld',m.rate.join('')); if(m.tier.length) h.set('mtier',m.tier.join(',')); if(m.rogo.length) h.set('mrogo',m.rogo.join(',')); if(m.sig.length) h.set('msig',m.sig.join(',')); if(m.avoid.length) h.set('mavoid',m.avoid.join(',')); if(m.zt.length) h.set('mzt',m.zt.join(',')); if(m.tax&&m.tax.length) h.set('mtax',m.tax.join(',')); if(m.txmin) h.set('mtmin',m.txmin); }
function mrHashRead(h,st,list){ st.mr={rate:(h.get('bld')||'').split('').filter(x=>'GYR'.includes(x)),tier:list('mtier'),rogo:list('mrogo'),sig:list('msig'),avoid:list('mavoid'),zt:list('mzt'),tax:list('mtax'),txmin:+h.get('mtmin')||0}; }
const mrCount=()=>HAS('mscreen')?S.mr.rate.size+S.mr.tier.size+S.mr.rogo.size+S.mr.sig.size+S.mr.avoid.size+S.mr.zt.size+(HAS('mtax')?S.mt.tax.size+(S.mt.min?1:0):0):0;
function mrPrep(){ const m=S.mr; if(!mrCount()) return null; let sg=0, av=0, ve=false; for(const k of m.sig) sg|=MR_BITS[k]; for(const k of m.avoid){ if(k==='ve') ve=true; else av|=MR_AV[k]; }
  const rate=new Uint8Array(4); for(const k of m.rate) rate['_GYR'.indexOf(k)]=1;
  let zt=null; if(m.zt.size){ zt=new Uint8Array(MZ.length); for(let j=0;j<MZ.length;j++){ const z=j&&ZREC&&ZREC[j]?ZREC[j].zt:null; zt[j]=m.zt.has(j===0||!z?'none':z)?1:0; } }
  const veI=ve?new Uint8Array(D.cra.length).map((_,j)=>/^V/.test(D.cra[j]||'')?1:0):null;
  let tx=null; if(HAS('mtax')&&(S.mt.tax.size||S.mt.min)){ const T=S.mt.tax; tx={y:T.has('y3')?3:T.has('y2')?2:1,cert:T.has('cert'),co:T.has('county'),deed:T.has('deed'),app:T.has('applied'),min:S.mt.min}; }
  return {rate:m.rate.size?rate:null,tier:m.tier.size?m.tier:null,rogo:m.rogo.size?m.rogo:null,sg,av,zt,veI,tx}; }
function mrPass(R,c,i){ if(R.rate && !R.rate[c.bld[i]]) return false; if(R.tier && !R.tier.has(c.tier[i])) return false; if(R.rogo && !R.rogo.has(c.rogo[i])) return false;
  if(R.sg && !(c.sigm[i]&R.sg)) return false; if(R.av && (c.env[i]&R.av)) return false; if(R.veI && R.veI[c.cra[i]]) return false; if(R.zt && !R.zt[c.mz[i]]) return false;
  if(R.tx){ const t=R.tx, f=c.txf[i]; if(c.txy[i]<t.y || (t.cert&&!(f&1)) || (t.co&&!(f&2)) || (t.deed&&!(f&32)) || (t.app&&!(f&64)) || (t.min&&c.txb[i]<t.min)) return false; } return true; }
const mrChip=(g,k,l,on,n)=>`<button type="button" class="chip ${on?'on':''} ${n===0&&!on?'zero':''}" data-mr="${g}:${k}" aria-pressed="${on}">${l}${n==null?'':`<span class="n">${short(n)}</span>`}</button>`;
function mrRender(){ if(!$('mrGrp')||!results) return; const m=S.mr, cnt={rate:{},tier:{},rogo:{},sig:{},avoid:{},zt:{},tax:{}};
  const sigB=MR_SIG, avB=MR_AVOID; for(let j=0;j<results.length;j++){ const id=results[j], p=P(id), i=I(id), c=p.c; const b='_GYR'[c.bld[i]]; cnt.rate[b]=(cnt.rate[b]||0)+1; cnt.tier[c.tier[i]]=(cnt.tier[c.tier[i]]||0)+1; cnt.rogo[c.rogo[i]]=(cnt.rogo[c.rogo[i]]||0)+1;
    const sg=c.sigm[i]; for(const [k,,bt] of sigB) if(sg&bt) cnt.sig[k]=(cnt.sig[k]||0)+1; const ev=c.env[i]; for(const [k,,bt] of avB){ if(k==='ve'? /^V/.test(D.cra[c.cra[i]]||'') : (ev&bt)) cnt.avoid[k]=(cnt.avoid[k]||0)+1; }
    const z=c.mz[i]&&ZREC&&ZREC[c.mz[i]]?ZREC[c.mz[i]].zt:'none'; cnt.zt[z]=(cnt.zt[z]||0)+1;
    if(c.txy&&c.txy[i]){ const y=c.txy[i], f=c.txf[i]; cnt.tax.any=(cnt.tax.any||0)+1; if(y>=2) cnt.tax.y2=(cnt.tax.y2||0)+1; if(y>=3) cnt.tax.y3=(cnt.tax.y3||0)+1; if(f&1) cnt.tax.cert=(cnt.tax.cert||0)+1; if(f&2) cnt.tax.county=(cnt.tax.county||0)+1; if(f&32) cnt.tax.deed=(cnt.tax.deed||0)+1; if(f&64) cnt.tax.applied=(cnt.tax.applied||0)+1; } }
  $('mrRate').innerHTML=MR_RATE.map(([k,l,s])=>mrChip('rate',k,`<span class="mrdot ${k}"></span>${l}<small> ${s}</small>`,m.rate.has(k),cnt.rate[k]||0)).join('');
  $('mrTier').innerHTML=MR_TIER.map(([k,l])=>mrChip('tier',k,l,m.tier.has(k),cnt.tier[k]||0)).join('');
  $('mrRogo').innerHTML=MR_ROGO.map(([k,l])=>mrChip('rogo',k,l,m.rogo.has(k),cnt.rogo[k]||0)).join('');
  $('mrSig').innerHTML=MR_SIG.map(([k,l])=>mrChip('sig',k,l,m.sig.has(k),cnt.sig[k]||0)).join('');
  $('mrAvoid').innerHTML=MR_AVOID.map(([k,l])=>mrChip('avoid',k,l,m.avoid.has(k),cnt.avoid[k]||0)).join('');
  $('mrZt').innerHTML=MR_ZT.map(([k,l])=>mrChip('zt',k,l,m.zt.has(k),cnt.zt[k]||0)).join('');
  if(HAS('mtax')&&$('mtChips')){ if(META.tax){ const M=META.tax; $('mtNote').innerHTML=`<b>Source:</b> ${esc(M.source||'')}. Certificate holders cannot contact owners for 2 years after April 1 of the issue year (FS 197.432(13)); that rule is for certificate holders. Next ${esc(PFC.cfg.name)} certificate sale: ${esc(M.nextCertSale||'')}.`; } $('mtChips').innerHTML=MT_CHIPS.map(([k,l])=>mrChip('tax',k,l,S.mt.tax.has(k),cnt.tax[k]||0)).join(''); const sel=$('mtMin'); if(!sel.options.length) sel.innerHTML=MT_MIN.map(([v,l])=>`<option value="${v}">${l}</option>`).join(''); sel.value=String(S.mt.min); } }
function mrWire(){ const g=$('mrGrp'); if(!g) return;
  if(PFC.id==='broward'){ $('mrHint').innerHTML='A green / yellow / red screen from city zoning (where the city publishes it), the county land use plan and FEMA flood. <b>Screening tool only. Confirm with county or city planning.</b>'; $('mrNote').innerHTML='<b>Screening tool, not a determination.</b> Always confirm zoning and buildability with the city planning / zoning department.'; } g.addEventListener('click',e=>{ const b=e.target.closest('[data-mr]'); if(!b) return; const [grp,k]=b.dataset.mr.split(':'); const set=S.mr[grp], v=(grp==='tier'||grp==='rogo')?+k:k; set.has(v)?set.delete(v):set.add(v); clearIdea(); run(); });
  $('clrMr').onclick=()=>{ for(const k of Object.keys(S.mr)) S.mr[k].clear(); clearIdea(); run(); };
  const tg=$('mtGrp'); if(tg){ tg.addEventListener('click',e=>{ const b=e.target.closest('[data-mr^="tax:"]'); if(!b) return; const k=b.dataset.mr.split(':')[1], T=S.mt.tax; T.has(k)?T.delete(k):T.add(k); clearIdea(); run(); });
    $('mtMin').addEventListener('change',()=>{ S.mt.min=+$('mtMin').value||0; clearIdea(); run(); }); $('clrMt').onclick=()=>{ S.mt.tax.clear(); S.mt.min=0; clearIdea(); run(); }; } }
const MR_TONE={1:'G',2:'Y',3:'R'};
const mrBadge=(c,i)=>{ const b=c.bld?c.bld[i]:0; if(!b) return ''; const t=MR_TONE[b], l=MR_RATE.find(x=>x[0]===t); return `<span class="mrb ${t}" title="Buildability screen: ${l[1]} - ${l[2]}. Screening only; confirm with county / city planning.">Build ${l[1]}</span>`; };
function mrCardLine(c,i){ const bits=[]; const t=c.tier[i]; if(t) bits.push(['','Tier I','Tier II','Tier III','Tier III-A','Military'][t]); const r=c.rogo[i]; if(r===1) bits.push('<b>ROGO awarded</b>'); else if(r===2) bits.push('ROGO applied'); else if(r===3) bits.push('<span class="mrneg">ROGO dedicated</span>');
  const e=c.env[i]; for(const [b,l] of MR_ENVL) if((e&b) && [1,4,8,16,16384,128,256].includes(b)) { bits.push(`<span class="mrneg">${l}</span>`); if(bits.length>5) break; }
  const sg=c.sigm[i]; if(sg&1) bits.push('<span class="hot">Foreclosure case</span>'); if(sg&4) bits.push('<span class="hot">Probate case</span>'); if(sg&16) bits.push('<span class="hot">Tax-deed notice</span>'); if(sg&2048) bits.push('Duplex-capable zoning');
  return bits.length?`<div class="line mrline"><span class="k">Screen</span><span class="v">${bits.join(' · ')}</span></div>`:''; }
function mrHTML(p,i){ const c=p.c, b=c.bld?c.bld[i]:0; if(!b) return ''; const t=MR_TONE[b], l=MR_RATE.find(x=>x[0]===t); const raw=p.s.reasons?getStr(p,'reasons',i):''; const items=raw?raw.split('¦').map(x=>{ const j=x.indexOf('~'); return [x.slice(0,j),x.slice(j+1)]; }):[]; if(HAS('mtax')&&c.txy&&c.txy[i]) items.push(['i',`Unpaid property taxes: ${mtYrs(c.txy[i])} since ${c.txo[i]}, ${dollars(c.txb[i])} owed (see Unpaid property taxes above). Taxes do not change the rating; the lien runs with the land.`]);
  const ICON={R:'✕',Y:'!',G:'✓',i:'·'}, LAB={R:'Blocker',Y:'Caution',G:'Positive',i:'Note'}; const zi=p.s.zinfo?getStr(p,'zinfo',i):'', rt=p.s.rogo_txt?getStr(p,'rogo_txt',i):'';
  const jur=MZ[c.mz[i]]?MZ[c.mz[i]][1]:D.city[c.city[i]];
  return `<h3>Buildability screen</h3>
  <div class="mrhead"><span class="mrb ${t} big">${l[1]} · ${l[2]}</span></div>
  <div class="mrnote"><b>Screening tool, not a determination.</b> Built from public map layers (${PFC.id==='broward'?'city zoning where published, the county land use plan and FEMA flood':'zoning, ROGO / Tier, conservation lands, wetlands, habitat, CBRS, FEMA flood'}) and the property roll. <b>Confirm with ${PFC.cfg.planning.who.replace(/&/g,'&amp;')}</b> before you rely on it.</div>
  <ul class="mrlist">${items.map(([s,x])=>`<li class="mr-${s}"><span class="mri" title="${LAB[s]}">${ICON[s]}</span><span>${esc(x)}</span></li>`).join('')||'<li class="mr-i"><span class="mri">·</span><span>Reasons load with the property details.</span></li>'}</ul>
  <div class="dl">${rows2(HAS('rogo')?[['Tier',c.tier[i]?['','Tier I (Natural Area)','Tier II (Big Pine Key / No Name Key)','Tier III (infill)','Tier III-A (Special Protection Area)','Military'][c.tier[i]]:'City (no county Tier) or not mapped'],['ROGO / allocation',rt?esc(rt):(c.rogo[i]?esc(MR_ROGO.find(x=>x[0]===c.rogo[i])[1]):'No allocation record')],
    ['Environment',MR_ENVL.filter(([bt])=>c.env[i]&bt).map(x=>x[1]).join(', ')],['Zoning notes',esc(zi)],['Planning contact',jur==='Key West'?'<a href="https://www.cityofkeywest-fl.gov/Departments/Planning" target="_blank" rel="noopener">City of Key West Planning</a>':jur==='Marathon'?'<a href="https://www.cityofmarathonfl.gov/planning" target="_blank" rel="noopener">City of Marathon Planning</a>':jur==='Islamorada'?'<a href="https://www.islamorada.fl.us/305/Planning-Development-Services" target="_blank" rel="noopener">Islamorada Planning</a>':'<a href="https://www.monroecounty-fl.gov/186/Planning-Environmental-Resources" target="_blank" rel="noopener">Monroe County Planning &amp; Environmental Resources</a> · <a href="https://www.monroecounty-fl.gov/1024/ROGO-NROGO" target="_blank" rel="noopener">ROGO / NROGO</a>']]:[['Zoning source',esc(zi)],['Planning contact','<a href="https://www.broward.org/Planning/Pages/Default.aspx" target="_blank" rel="noopener">Broward County Planning</a> · city planning / zoning department for '+esc(D.city[c.city[i]]||'this city')]])}</div>`; }
const rows2=pairs=>pairs.filter(x=>x[1]!==''&&x[1]!=null).map(([k,v])=>`<div class="k">${k}</div><div class="v">${v}</div>`).join('');
function bwPermitsHTML(p,i){ const ds=p.s.dsum?getStr(p,'dsum',i):''; const dl=[['Scheduled sales',ds?esc(ds):'']];
  return `<h3>Auctions &amp; legal notices</h3>${dl.some(x=>x[1])?`<div class="dl">${rows2(dl)}</div>`:'<div class="note">No scheduled foreclosure or tax-deed sale found for this parcel.</div>'}
  <div class="note">Coverage: scheduled foreclosure and tax-deed sales come from the Broward Clerk's public auction sites (broward.realforeclose.com / realtaxdeed.com). Unpaid taxes, tax certificates and upcoming tax-deed auctions come from the Tax Collector downloads (see Unpaid property taxes). Not loaded because they are not publicly downloadable: lis pendens and probate cases (reCAPTCHA / Cloudflare), code violations, permits and unsafe structures (per-property city portals).</div>`; }
/* Unpaid property taxes (Monroe + Broward; county Tax Collector downloads, see scripts/counties/<county>/add_tax.py). Pack cols: txy delinquent years, txo oldest year, txb balance $,
   txf flags (1 investor cert, 2 county-held, 4 current-year bill unpaid [Monroe], 8 tax-bill owner differs [Monroe], 16 3+ certs, 32 tax-deed auction scheduled [Broward], 64 tax-deed application [Broward]),
   txd next tax-deed sale day [Broward]; detail str taxs (o owner, y year, c current, h county-held, d deed auction, a account). */
const MTX=()=>META.tax||{};
const mtYrs=n=>n+(n===1?' year':' years');
const mtDay=d=>{ const x=new Date(Date.UTC(1900,0,1)+d*864e5); return x.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'}); };
const mtIsCounty=b=>b==='99999'||/^BROWARD COUNTY\b/i.test(b||'');
const mtBadge=(c,i)=>{ const n=c.txy?c.txy[i]:0, f=c.txf?c.txf[i]:0; let h='';
  if(c.txd&&c.txd[i]&&(f&32)) h+=`<span class="tt taxb t3" title="Tax deed auction scheduled ${mtDay(c.txd[i])}. The owner can still redeem before the sale.">Tax deed auction ${mtDay(c.txd[i]).replace(/, \d{4}$/,'')}</span>`;
  if(!n) return h; return h+`<span class="tt taxb ${n>=3?'t3':n>=2?'t2':''}" title="Unpaid property taxes: ${mtYrs(n)} (oldest ${c.txo[i]}), ${dollars(c.txb[i])} owed${f&2?', county holds a certificate':f&1?', investor holds a certificate':''}. ${esc(MTX().source||'')}.">Tax delinquent · ${n} yr${n>1?'s':''}</span>`; };
const mtCardLine=(c,i)=>{ const n=c.txy?c.txy[i]:0; if(!n) return ''; const f=c.txf[i]; return `<div class="line mtline"><span class="k">Taxes</span><span class="v"><span class="hot">${mtYrs(n)} unpaid</span> since ${c.txo[i]} · ${dollars(c.txb[i])}${f&32?' · <b>tax deed auction '+mtDay(c.txd[i])+'</b>':f&64?' · tax deed applied for':''}${f&2?' · county-held certificate':f&1?' · certificate sold':''}</span></div>`; };
function mtParse(raw){ const o={owner:'',oaddr:'',yrs:[],cur:null,held:[],acc:'',deed:null}; for(const it of (raw||'').split('¦')){ const a=it.split('~'); if(a[0]==='o'){ o.owner=a[1]||''; o.oaddr=a[2]||''; } else if(a[0]==='y') o.yrs.push({y:+a[1],bal:+a[2],cert:a[3]||'',bid:a[4]||'',st:a[5]||''}); else if(a[0]==='c') o.cur={y:+a[1],bal:+a[2]}; else if(a[0]==='h') o.held.push({y:+a[1],cert:a[2]||'',price:+a[3]}); else if(a[0]==='d') o.deed={date:a[1]||'',who:a[2]||'',app:a[3]||'',yr:a[4]||''}; else if(a[0]==='a') o.acc=a[1]||''; } return o; }
function mtCertLine(x){ const cty=mtIsCounty(x.bid), amt=x.bal?' · '+dollars(x.bal):'';
  const who=x.st==='Surrendered'?'certificate surrendered (tax deed process)':x.st==='Redeemed'?'certificate redeemed into the tax deed process':cty?'<b>county-held</b>':x.st==='Transferred'?'investor (transferred)':'sold to an investor';
  return `${x.y}: ${who}${x.cert?' · cert #'+esc(x.cert):''}${x.bid&&!cty&&/^\d+$/.test(x.bid)?' · bidder #'+esc(x.bid):x.bid&&!cty&&x.st!=='Surrendered'&&x.st!=='Redeemed'?' · '+esc(x.bid):''}${amt}`; }
function mtHTML(p,i){ const c=p.c, n=c.txy?c.txy[i]:0, f=c.txf?c.txf[i]:0, M=MTX(), asof=esc(M.asofLabel||''), nxt=esc(M.nextCertSale||''), cn=PFC.cfg.name;
  const src=`<div class="note">Source: ${esc(M.source||cn+' County Tax Collector')} (public download), as of <b>${asof}</b>. Balances are as reported on that date and change daily; confirm the payoff with the Tax Collector before you rely on them.</div>`;
  if(!n && !(f&4) && !(f&32)) return `<h3>Unpaid property taxes</h3><div class="note">No unpaid taxes on this parcel in the Tax Collector report (${asof}).</div>${src}`;
  const t=mtParse(p.s&&p.s.taxs?getStr(p,'taxs',i):''), certs=t.yrs.filter(x=>x.cert||(x.bid&&x.st)||(x.bid&&!x.st)), yl=t.yrs.map(x=>x.y);
  const cl=certs.map(mtCertLine), nocert=t.yrs.filter(x=>!x.cert&&!x.bid).map(x=>x.y), unk=t.yrs.filter(x=>!x.bal).length;
  const dl=[]; if(f&32&&t.deed) dl.push(['Tax deed auction',`<b>${t.deed.date?mtDay(Math.round((Date.parse(t.deed.date+'T00:00:00Z')-Date.UTC(1900,0,1))/864e5)):''}</b> · tax year ${esc(t.deed.yr)} · applicant ${esc(t.deed.who)}${t.deed.app?' · application #'+esc(t.deed.app):''}<small>The owner can redeem until the sale. Check the county tax deed sale site for the current status.</small>`]);
  else if(f&64) dl.push(['Tax deed','Application on file (Applied / Certified); no auction date in the report yet']);
  if(n){ dl.push(['Years delinquent',`<b>${n}</b> (${yl.join(', ')}) · oldest ${c.txo[i]}`],['Total balance',`<b>${dollars(c.txb[i])}</b> across ${mtYrs(n)}${unk?`<small>${unk} older ${unk>1?'years carry':'year carries'} no amount in the report, so the total can be higher.</small>`:''}`],
      ['Tax certificate',certs.length?`${cl.join('<br>')}${nocert.length?'<br>No certificate: '+nocert.join(', '):''}`:'None on record (certificates are sold each May)']);
    if(t.held.length) dl.push(['County-held certificate',t.held.map(h=>`${h.y} · cert #${esc(h.cert)} · price to purchase ${dollars(h.price)}`).join('<br>')]); }
  if(f&4) dl.push([`Current-year (${M.currentYear||''}) bill`,`${t.cur?dollars(t.cur.bal):''} unpaid. Not delinquent yet (delinquent after Mar 31, ${(M.currentYear||0)+1}); not counted in the years above.`]);
  dl.push(['Tax-bill owner',t.owner?esc(t.owner)+(t.oaddr?'<small>'+esc(t.oaddr)+'</small>':''):''],['Tax account',t.acc?esc(t.acc):'']);
  return `<h3>Unpaid property taxes</h3><div class="mrhead">${n?`<span class="mrb R big">Tax delinquent · ${mtYrs(n)}</span>`:`<span class="mrb Y big">${f&32?'Tax deed auction scheduled':'Current-year bill unpaid'}</span>`}${f&32&&n?' <span class="mrb R big">Tax deed auction</span>':''}${f&2?' <span class="mrb Y big">County-held certificate</span>':''}</div>
  <div class="dl">${rows2(dl)}</div>${f&8?`<div class="note"><b>Owner name differs:</b> the name on the tax bill is not the owner on the current Property Appraiser roll. The property may have changed hands; the unpaid taxes stay with the land. Verify before you contact anyone.</div>`:''}
  <div class="note"><b>Who can contact the owner:</b> under FS 197.432(13), a <b>tax-certificate holder</b> may not initiate contact with the owner to encourage or demand payment until 2 years after April 1 of the year the certificate was issued. That rule is for certificate holders; it is not a general ban on anyone approaching the owner. Not legal advice. <b>Next ${esc(cn)} tax-certificate sale: ${nxt}.</b></div>${src}`; }
function mrPermitsHTML(p,i){ const c=p.c, ps=getStr(p,'psum',i), cs=getStr(p,'csum',i), sg=c.sigm[i];
  const dl=[['County permits (legacy, to 9/2022)',ps?esc(ps):''],['Code cases',cs?esc(cs):''],['Tax deed',sg&16?'Tax-deed application advertised Feb-Mar 2026 (Keys Weekly legal notices; sale 3/25/2026). Check the Clerk tax-deed sale site for the current status.':'']];
  return `<h3>Permits, code cases &amp; legal notices</h3>${dl.some(x=>x[1])?`<div class="dl">${rows2(dl)}</div>`:'<div class="note">Nothing on record in the public sources covered.</div>'}
  <div class="note">Coverage: Monroe County legacy permits (before 10/2022) and county code cases (before 2024) come from MCeSearch where it could be fetched; newer county permits and the Key West / Marathon / Islamorada permit systems are per-property portals (no bulk download). Marathon code cases come from magistrate hearing agendas. Clerk foreclosure / probate cases are matched by name (precision first). Tax-collector delinquent lists are behind Cloudflare, so unpaid taxes are not loaded.</div>`; }

/* owner portfolio (same first owner name) */
/* how many loaded parcels share this parcel's last deed (same book-page and sale date): flags bulk sales */
function deedCount(p0,i0){
  if(!p0.s.book||!p0.c.sd1[i0]) return 0; const bk=getStr(p0,'book',i0), d=p0.c.sd1[i0]; if(!bk) return 0; let n=0;
  for(const p of PACKS){ if(!p||!p.det||!p.s.book) continue; const a=strCol(p,'book'), sd=p.c.sd1;
    for(let i=0;i<a.length;i++) if(sd[i]===d && a[i]===bk) n++; }
  return n;
}

/* map view */
let LMAP=null, mapLayer=null, MAP_SEL=-1, MAP_FOCUS=-1, MAP_NOFIT=false, lastFitKey='', leafletP=null, SX=null, SY=null, SN=0, tipEl=null;
const loadLeaflet=()=>leafletP||(leafletP=new Promise((res,rej)=>{
  if(window.L) return res();
  const l=document.createElement('link'); l.rel='stylesheet'; l.href='vendor/leaflet/leaflet.css'; document.head.appendChild(l);
  const s=document.createElement('script'); s.src='vendor/leaflet/leaflet.js'; s.onload=()=>res(); s.onerror=()=>{ leafletP=null; rej(new Error('The map library did not load')); }; document.head.appendChild(s);
}));
const GEOP=[];
function loadGeo(i){
  if(!PACKS[i]||PACKS[i].geo) return Promise.resolve();
  if(GEOP[i]) return GEOP[i];
  const pk=META.packs[i]; if(!pk.geo) return Promise.resolve();
  GEOP[i]=(async()=>{
    const d=parsePack(await gunzip(await fetchAll(pk.geo,()=>{})),pk.name,i), n=d.n, la=d.c.lat, lo=d.c.lon;
    const G0=META.geoOrigin||[24,-81.5];   // pack stores (lat-G0[0])*1e6, (lon-G0[1])*1e6
    const lat=new Float32Array(n), lon=new Float32Array(n), mx=new Float64Array(n), my=new Float64Array(n);
    for(let k=0;k<n;k++){
      if(!la[k]){ lat[k]=NaN; lon[k]=NaN; mx[k]=NaN; my[k]=NaN; continue; }
      const a=la[k]/1e6+G0[0], b=lo[k]/1e6+G0[1], s=Math.sin(a*Math.PI/180);
      lat[k]=a; lon[k]=b; mx[k]=(b+180)/360; my[k]=0.5-Math.log((1+s)/(1-s))/(4*Math.PI);
    }
    PACKS[i].geo={lat,lon,mx,my};
  })();
  GEOP[i].catch(()=>{ GEOP[i]=null; });
  return GEOP[i];
}
const ensureGeo=()=>Promise.all(PACKS.map((p,i)=>p&&!p.geo?loadGeo(i):null));
const TONES=[['vacant','Vacant land'],['res','Homes & condos'],['multi','Multifamily'],['com','Commercial & mixed'],['ind','Industrial & other'],['gov','Civic & government']];
let TONE_RGB=null, LU_TONE=null, MAP_COLOR='type', SC_RGB=null;
const SC_TONES=[['s0','No signals'],['s1','1–19'],['s2','20–34'],['s3','35–49'],['s4','50+']];
const scIdx=v=>v>=50?4:v>=35?3:v>=20?2:v>0?1:0;
function legendSetup(){ if(!TONE_RGB) return; $('mapLegend').innerHTML = (MAP_COLOR==='score' ? '<span class="lt">Distress score</span>'+SC_TONES.map(([t,l],k)=>`<span><i style="background:${SC_RGB[k].css}"></i>${l}</span>`).join('') : TONES.map(([t,l],k)=>`<span><i style="background:${TONE_RGB[k].css}"></i>${l}</span>`).join('')) + (SV.count()?'<span><i class="svring"></i>Saved</span>':''); }
function toneSetup(){
  const cs=getComputedStyle(document.documentElement);
  TONE_RGB=TONES.map(([t])=>{ const hex=(cs.getPropertyValue('--t-'+t).trim()||'#888888').replace('#',''); const v=parseInt(hex.length===3?hex.split('').map(x=>x+x).join(''):hex,16); return {css:'#'+hex, r:(v>>16)&255, g:(v>>8)&255, b:v&255}; });
  const ti=Object.fromEntries(TONES.map(([t],k)=>[t,k])); LU_TONE=Uint8Array.from(LU_T,t=>ti[TYPE_TONE[t]]||0);
  SC_RGB=SC_TONES.map(([t])=>{ const hex=(cs.getPropertyValue('--'+t).trim()||'#888888').replace('#',''); const v=parseInt(hex,16); return {css:'#'+hex, r:(v>>16)&255, g:(v>>8)&255, b:v&255}; });
  legendSetup();
}
function makeDotLayer(){
  return L.Layer.extend({
    onAdd(map){ this._map=map; const c=this._c=L.DomUtil.create('canvas','dotlayer leaflet-zoom-animated'); map.getPanes().overlayPane.appendChild(c);
      map.on('moveend resize',this.redraw,this); map.on('zoomanim',this._anim,this); this.redraw(); },
    onRemove(map){ L.DomUtil.remove(this._c); map.off('moveend resize',this.redraw,this); map.off('zoomanim',this._anim,this); },
    _anim(e){ const m=this._map, scale=m.getZoomScale(e.zoom), off=m._latLngBoundsToNewLayerBounds(m.getBounds(),e.zoom,e.center).min; L.DomUtil.setTransform(this._c,off,scale); },
    redraw(){ if(this._map) drawDots(this); return this; }
  });
}
function drawDots(layer){
  const map=layer._map, c=layer._c, size=map.getSize(), dpr=Math.min(2,window.devicePixelRatio||1);
  L.DomUtil.setPosition(c,map.containerPointToLayerPoint([0,0]));
  const cw=Math.max(1,Math.round(size.x*dpr)), ch=Math.max(1,Math.round(size.y*dpr));
  if(c.width!==cw||c.height!==ch){ c.width=cw; c.height=ch; } c.style.width=size.x+'px'; c.style.height=size.y+'px';
  const ctx=c.getContext('2d'); ctx.setTransform(1,0,0,1,0,0); ctx.clearRect(0,0,cw,ch);
  if(!TONE_RGB) toneSetup();
  const z=map.getZoom(), scale=256*Math.pow(2,z), o=map.project(map.containerPointToLatLng([0,0]),z), ox=o.x, oy=o.y;
  const n=results.length; if(!SX||SX.length<n){ SX=new Float32Array(Math.max(n,4096)); SY=new Float32Array(Math.max(n,4096)); }
  let vis=0, nogeo=0;
  const W=size.x, H=size.y;
  if(n>25000){
    const img=ctx.createImageData(cw,ch), d32=new Uint32Array(img.data.buffer), s=Math.max(1,Math.round((z>=15?3.2:z>=13?2.4:z>=11?1.8:1.3)*dpr)), h=s>>1;
    const byS=MAP_COLOR==='score', col=(byS?SC_RGB:TONE_RGB).map(t=>(255<<24)|(t.b<<16)|(t.g<<8)|t.r);
    for(let j=n-1;j>=0;j--){ const id=results[j], p=P(id), g=p.geo; if(!g){ nogeo++; SX[j]=-1e9; continue; } const i=I(id);
      const x=g.mx[i]*scale-ox, y=g.my[i]*scale-oy; SX[j]=x; SY[j]=y; if(!(x>=-4&&y>=-4&&x<W+4&&y<H+4)) continue; vis++;
      const px=Math.round(x*dpr)-h, py=Math.round(y*dpr)-h, cc=col[byS?scIdx(p.c.dscore[i]):LU_TONE[p.c.landuse[i]]];
      for(let yy=py;yy<py+s;yy++){ if(yy<0||yy>=ch) continue; const row=yy*cw; for(let xx=px;xx<px+s;xx++){ if(xx>=0&&xx<cw) d32[row+xx]=cc; } } }
    ctx.putImageData(img,0,0);
  } else {
    ctx.setTransform(dpr,0,0,dpr,0,0); const r=z>=16?6:z>=14?5:z>=12?4:3, stroke=getComputedStyle(document.documentElement).getPropertyValue('--surface').trim()||'#fff';
    ctx.lineWidth=1; ctx.strokeStyle=stroke; const byS=MAP_COLOR==='score';
    for(let j=n-1;j>=0;j--){ const id=results[j], p=P(id), g=p.geo; if(!g){ nogeo++; SX[j]=-1e9; continue; } const i=I(id);
      const x=g.mx[i]*scale-ox, y=g.my[i]*scale-oy; SX[j]=x; SY[j]=y; if(!(x>=-8&&y>=-8&&x<W+8&&y<H+8)) continue; vis++;
      ctx.beginPath(); ctx.arc(x,y,r,0,6.2832); ctx.fillStyle=byS?SC_RGB[scIdx(p.c.dscore[i])].css:TONE_RGB[LU_TONE[p.c.landuse[i]]].css; ctx.fill(); if(r>=4) ctx.stroke(); }
  }
  SN=n;
  if(SV.count()){ const ids=savedIdx(), brand=getComputedStyle(document.documentElement).getPropertyValue('--brand').trim()||'#FC4C02'; ctx.setTransform(dpr,0,0,dpr,0,0); ctx.lineWidth=2.5; ctx.strokeStyle=brand;
    for(const id of ids.values()){ const p=P(id), g=p&&p.geo, i=I(id); if(!g||!(g.lat[i]>20)) continue; const x=g.mx[i]*scale-ox, y=g.my[i]*scale-oy; if(x<-10||y<-10||x>W+10||y>H+10) continue; ctx.beginPath(); ctx.arc(x,y,z>=14?9:7,0,6.2832); ctx.stroke(); } }
  if(MAP_SEL>=0){ const p=P(MAP_SEL), g=p&&p.geo, i=I(MAP_SEL); if(g&&g.lat[i]>20){ const x=g.mx[i]*scale-ox, y=g.my[i]*scale-oy; ctx.setTransform(dpr,0,0,dpr,0,0); ctx.lineWidth=3; ctx.strokeStyle=getComputedStyle(document.documentElement).getPropertyValue('--danger').trim()||'#c00'; ctx.beginPath(); ctx.arc(x,y,11,0,6.2832); ctx.stroke(); } }
  $('mapHint').textContent = !n ? 'Nothing matches these filters.' : `${fmt.format(n)} on the map${vis<n?' · '+fmt.format(vis)+' in view':''}${nogeo?' · loading points…':''} · click a dot for details`;
}
function nearest(pt,rad){
  let best=-1, bd=rad*rad; for(let j=0;j<SN;j++){ const dx=SX[j]-pt.x, dy=SY[j]-pt.y, d=dx*dx+dy*dy; if(d<bd){ bd=d; best=j; } }
  return [best,bd];
}
function onMapClick(e){
  const pt=e.containerPoint, z=LMAP.getZoom(), [best,bd]=nearest(pt,z>=14?10:8); if(best<0) return;
  const stack=[]; const lim=Math.sqrt(bd)+1.5; for(let j=0;j<SN && stack.length<400;j++){ const dx=SX[j]-SX[best], dy=SY[j]-SY[best]; if(dx*dx+dy*dy<=1.5*1.5 || (Math.hypot(SX[j]-pt.x,SY[j]-pt.y)<=lim && Math.hypot(dx,dy)<2)) stack.push(j); }
  if(stack.length<=1){ const id=results[best], p=P(id), i=I(id);   // single property: small popup with open + save
    L.popup({maxWidth:300,className:'stackpop',autoPanPaddingTopLeft:[20,70]}).setLatLng(e.latlng).setContent(`<div class="stacklist"><div class="stackitem"><button type="button" class="stackopen" data-id="${id}"><b>${esc(getStr(p,'addr',i)||'No street address')}</b><small>${TYPE_LABEL[LU_T[p.c.landuse[i]]]} · ${p.c.mkt[i]?money(p.c.mkt[i]):'–'} · open details</small></button>${starHTML(id,getStr(p,'folio',i))}</div></div>`).openOn(LMAP); return; }
  const items=stack.slice(0,60).map(j=>{ const id=results[j], p=P(id), i=I(id), c=p.c; return `<div class="stackitem"><button type="button" class="stackopen" data-id="${id}"><b>${esc(getStr(p,'addr',i)||'No street address')}</b><small>${TYPE_LABEL[LU_T[c.landuse[i]]]} · ${c.mkt[i]?money(c.mkt[i]):'–'}</small></button>${starHTML(id,getStr(p,'folio',i))}</div>`; }).join('');
  L.popup({maxWidth:300,className:'stackpop',autoPanPaddingTopLeft:[20,70]}).setLatLng(e.latlng).setContent(`<div class="stacklist"><div class="note">${fmt.format(stack.length)}${stack.length>=400?'+':''} properties at this spot${stack.length>60?' (first 60 shown)':''}</div>${items}</div>`).openOn(LMAP);
}
let moveRaf=0, lastMove=null;
function onMapMove(e){
  lastMove=e.containerPoint; if(moveRaf) return;
  moveRaf=requestAnimationFrame(()=>{ moveRaf=0; if(!tipEl) return; if(SN>300000||!lastMove){ tipEl.hidden=true; return; }
    const [best]=nearest(lastMove,8); LMAP.getContainer().style.cursor=best>=0?'pointer':'';
    if(best<0){ tipEl.hidden=true; return; } const id=results[best], p=P(id), i=I(id);
    tipEl.textContent=(getStr(p,'addr',i)||'No street address')+' · '+(p.c.mkt[i]?money(p.c.mkt[i]):'–'); tipEl.style.left=SX[best]+'px'; tipEl.style.top=SY[best]+'px'; tipEl.hidden=false; });
}
function initMap(){
  const dark=document.documentElement.dataset.theme==='dark' || (document.documentElement.dataset.theme!=='light' && matchMedia('(prefers-color-scheme: dark)').matches);
  LMAP=L.map('map',{zoomControl:true,minZoom:7,maxZoom:19}).setView(PFC.cfg.center,PFC.id===PFC.DEFAULT?10:9);
  const esri=(svc,opt={})=>L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/${svc}/MapServer/tile/{z}/{y}/{x}`,{maxZoom:20,maxNativeZoom:svc.includes('Imagery')?19:16,
    attribution:'Tiles &copy; <a href="https://www.esri.com">Esri</a>, HERE, Garmin, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',...opt});
  const gray=dark?'Dark':'Light';
  const base={
    'Simple': L.layerGroup([esri(`Canvas/World_${gray}_Gray_Base`), esri(`Canvas/World_${gray}_Gray_Reference`,{zIndex:5})]),
    'Streets': L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,maxNativeZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}),
    'Satellite': L.layerGroup([esri('World_Imagery'), esri('Reference/World_Transportation',{opacity:.7}), esri('Reference/World_Boundaries_and_Places')])
  };
  base['Simple'].addTo(LMAP); L.control.layers(base,null,{position:'bottomright',collapsed:true}).addTo(LMAP);
  const Dot=makeDotLayer(); mapLayer=new Dot(); mapLayer.addTo(LMAP);
  tipEl=document.createElement('div'); tipEl.className='maptip'; tipEl.hidden=true; $('mapbox').appendChild(tipEl);
  LMAP.on('moveend',()=>{ if(S.asm) drawAsmOutlines(); });
  LMAP.on('click',onMapClick); LMAP.on('mousemove',onMapMove); LMAP.on('mouseout movestart zoomstart',()=>{ tipEl.hidden=true; });
  $('map').addEventListener('click',e=>{ if(e.target.closest('[data-star]')) return; const b=e.target.closest('.stackopen'); if(b){ LMAP.closePopup(); openDrawer(+b.dataset.id); } });
  toneSetup();
}
function fitResults(force){
  if(!LMAP) return; const n=results.length; if(!n) return;
  let key=n, x=0; for(let j=0;j<n;j++){ x=(x+results[j])%2147483647; } key=n+':'+x;
  if(!force && (key===lastFitKey || MAP_NOFIT)){ MAP_NOFIT=false; lastFitKey=key; return; } lastFitKey=key;
  const step=Math.max(1,Math.floor(n/60000)), la=[], lo=[];
  for(let j=0;j<n;j+=step){ const id=results[j], g=P(id).geo, i=I(id); if(g&&g.lat[i]>20){ la.push(g.lat[i]); lo.push(g.lon[i]); } }
  if(!la.length) return; la.sort((a,b)=>a-b); lo.sort((a,b)=>a-b);
  const q=a=>a.length>40?[a[Math.floor(a.length*0.005)],a[Math.ceil(a.length*0.995)-1]]:[a[0],a[a.length-1]];
  const [y0,y1]=q(la), [x0,x1]=q(lo);
  LMAP.fitBounds([[y0,x0],[y1,x1]],{padding:[36,36],maxZoom:17,animate:false});
}
async function showMap(reset){
  $('mapHint').textContent='Loading the map…';
  try{ await loadLeaflet(); }catch(e){ $('mapHint').textContent=e.message+'. Check the connection and try again.'; return; }
  if(!LMAP) initMap();
  LMAP.invalidateSize({animate:false});
  if(PACKS.some(p=>p&&!p.geo)){ $('mapHint').textContent='Loading map points…'; try{ await ensureGeo(); }catch(e){ $('mapHint').textContent='Map points did not load. Try again.'; return; } }
  if(S.view!=='map') return;
  LMAP.invalidateSize({animate:false});
  if(MAP_FOCUS>=0){ const id=MAP_FOCUS; MAP_FOCUS=-1; const p=P(id), g=p&&p.geo, i=I(id); if(g&&g.lat[i]>20){ lastFitKey=''; LMAP.setView([g.lat[i],g.lon[i]],18,{animate:false}); mapLayer.redraw(); return; } }
  if(reset && !(S.asm&&S.asmGroup)) fitResults(false);
  mapLayer.redraw(); drawAsmOutlines();
}

/* ideas */
const BLANK=()=>({hideGov:true,sort:'lot_d',flags:{},owner:'all'});
/* folio deep links: ?folio=0131130310040 or #folio=01-3113-031-0040 opens that property's card + details */
function deepFolio(){ const m=/[?&#]folio=([\w\-\s%]+)/i.exec(location.search+location.hash); if(!m) return ''; const d=decodeURIComponent(m[1]).replace(PFC.id==='broward'?/[^0-9A-Za-z]/g:/\D/g,'').toUpperCase(); return d.length>=4?d:''; }
const folioLink=f=>location.origin+location.pathname+'?folio='+f;
async function openDeep(f){
  const find=()=>{ for(let j=0;j<results.length;j++){ const id=results[j]; if((PFC.id==='broward'?getStr(P(id),'folio',I(id)).toUpperCase()===f:getStr(P(id),'folio',I(id)).replace(/\D/g,'').endsWith(f.length>=13?f:f.padStart(13,'0')))) return id; } return results.length===1?results[0]:-1; };
  let id=find(); if(id<0 && !S.types.has('condo')){ S.types=new Set(['condo']); await ensureCondo(); run(); id=find(); }
  if(id<0){ toast('Folio '+f+' was not found in this roll.'); return; }
  S.view='cards'; renderResults(true);
  const card=document.querySelector('.card[data-id="'+id+'"]'); if(card){ card.scrollIntoView({block:'center'}); card.classList.add('flash'); }
  openDrawer(id);
}
/* commercial presets by Property Appraiser DOR land use family (see CP_FAM) */
const LUF=fam=>D.landuse.filter((v,i)=>{ const c=LU_CODE[i]; return cpCom(c)&&CP_FAM(c)===fam; });
/* ideas that need a data layer the active county may not have (counties.js layers) */
const IDEA_NEED=[[/Buildable lots|Buildable teardowns|Duplex-zoned/,'mscreen'],[/ROGO/,'rogo'],[/Foreclosure auctions scheduled|Tax-deed sales scheduled/,'broward'],[/Hottest|Pre-foreclosure|Tax deeds|Unsafe|motivated owners/,'distress'],[/vacant \/ neglected/,'vacancy'],[/Strong teardowns|could be split/,'zoning'],[/Death recorded/,'distress'],[/Commercial distress|Closed gas/,'commercial'],[/Assemblages/,'asm'],[/^Tax delinquent/,'mtax'],[/^Tax deed auction/,'mtdeed']];
const ideaOk=l=>IDEA_NEED.every(([re,ly])=>!re.test(l)||HAS(ly));
const IDEAS=[
  ['🔥 Hottest leads', ()=>({...BLANK(), dsMin:50, sort:'ds_d'})],
  ['Pre-foreclosure & auctions', ()=>({...BLANK(), dsig:['LP','FC'], sort:'ds_d'})],
  ['Tax deeds & delinquent', ()=>({...BLANK(), dsig:['TD','TC'], dsMin:35, sort:'ds_d'})],
  ['Unsafe structures', ()=>({...BLANK(), dsig:['US'], sort:'ds_d'})],
  ['🏚 Likely vacant / neglected', ()=>({...BLANK(), vsMin:40, sort:'vs_d'})],
  ['🏘 Multi-property motivated owners', ()=>({...BLANK(), ogMin:2, ogDist:true, sort:'ogd_d'})],
  ['Owners with 5+ properties', ()=>({...BLANK(), ogMin:5, sort:'og_d'})],
  ['Vacant infill lots', ()=>({...BLANK(), types:['vacant'], lotMin:2500, lotMax:21780, sort:'lot_a'})],
  ['Houses on multifamily land', ()=>HAS('mscreen')?({...BLANK(), types:['sf'], mr:{zt:['mf']}, sort:'lot_d'}):({...BLANK(), types:['sf'], zones:['mf'], sort:'lot_d'})],
  ['Teardowns', ()=>({...BLANK(), tier:'basic', sort:'lp_d'})],
  ['Out-of-state owners, 15+ years', ()=>({...BLANK(), types:['sf','th','mf29','vacant'], hdMin:15, flags:{oos:'yes',homestead:'no'}, sort:'held_d'})],
  ['Estates and heirs', ()=>({...BLANK(), flags:{estate:'yes'}, sort:'held_d'})],
  ['Small multifamily (2–9 units)', ()=>({...BLANK(), types:['mf29'], flags:{homestead:'no'}, sort:'un_d'})],
  ['Big lots, 1 acre+', ()=>({...BLANK(), types:['sf','vacant'], lotMin:43560, sort:'lot_a'})],
  ['Family transfers (last 3 yrs)', ()=>({...BLANK(), types:['sf','th','mf29','vacant'], fx:{fam:'yes'}, sort:'sold_d'})],
  ['Family transfers, owner out of state', ()=>({...BLANK(), types:['sf','th','mf29','vacant'], fx:{famoos:'yes'}, sort:'sold_d'})],
  ['Life estate owners', ()=>({...BLANK(), fx:{life:'yes'}, sort:'held_d'})],
  ['Death recorded (owner deceased)', ()=>({...BLANK(), fx:{death:'yes'}, sort:'held_d'})],
  ['Tired landlords (absentee, 20+ yrs)', ()=>({...BLANK(), types:['sf','th','mf29'], hdMin:20, flags:{homestead:'no',absz:'yes'}, sort:'held_d'})],
  ['Lots owned from far away', ()=>({...BLANK(), types:['vacant'], lotMin:4000, flags:{absz:'yes'}, sort:'ppl_a'})],
  ['💥 Strong teardowns', ()=>({...BLANK(), tier:'strong', sort:'um_d'})],
  ['Lots that could be split', ()=>({...BLANK(), types:['sf','vacant'], lotz:['split'], sort:'lot_d'})],
  ['🏪 Commercial distress', ()=>({...BLANK(), cm:35, sort:'cm_d'})],
  ['⛽ Closed gas stations', ()=>({...BLANK(), cgas:true, sort:'cm_d'})],
  ['Gas stations', ()=>({...BLANK(), exL:LUF('gas'), sort:'lot_d'})],
  ['Warehouses & industrial', ()=>({...BLANK(), exL:LUF('ind'), sort:'lot_d'})],
  ['Retail stores & centers', ()=>({...BLANK(), exL:LUF('ret'), sort:'lot_d'})],
  ['Office buildings', ()=>({...BLANK(), exL:LUF('off'), sort:'lot_d'})],
  ['Restaurants & fast food', ()=>({...BLANK(), exL:LUF('rest'), sort:'lot_d'})],
  ['Hotels & motels', ()=>({...BLANK(), exL:LUF('hotel'), sort:'lot_d'})],
  ['Auto sales & repair', ()=>({...BLANK(), exL:LUF('auto'), sort:'lot_d'})],
  ['Vacant commercial land', ()=>({...BLANK(), exL:LUF('vac'), sort:'lot_d'})],
  ['🧩 Assemblages', ()=>({...BLANK(), asm:true, sort:'asm_d'})],
  ['Assemblages with combined-site upside', ()=>({...BLANK(), asm:true, asmUp:true, sort:'asm_d'})],
  ['Houses on lots under zone minimum', ()=>({...BLANK(), types:['sf'], lotz:['below'], sort:'lp_d'})],
  ['Buildable lots', ()=>({...BLANK(), types:['vacant'], mr:{rate:['G','Y']}, sort:'bld_a'})],
  ['Buildable lots, green only', ()=>({...BLANK(), types:['vacant'], mr:{rate:['G']}, sort:'bld_a'})],
  ['ROGO allocation awarded', ()=>({...BLANK(), mr:{sig:['rogo_award']}, sort:'bld_a'})],
  ['Buildable teardowns', ()=>({...BLANK(), mr:{rate:['G'], sig:['teardown']}, sort:'lp_d'})],
  ['Duplex-zoned lots & teardowns', ()=>({...BLANK(), mr:{sig:['dup'], rate:['G','Y']}, sort:'lot_d'})],
  ['Foreclosure auctions scheduled', ()=>({...BLANK(), mr:{sig:['fc_open']}, sort:'bld_a'})],
  ['Tax-deed sales scheduled', ()=>({...BLANK(), mr:{sig:['taxdeed']}, sort:'bld_a'})],
  ['Tax delinquent 2+ years', ()=>({...BLANK(), mr:{tax:['y2']}, sort:'tx_d'})],
  ['Tax deed auction upcoming', ()=>({...BLANK(), mr:{tax:['deed']}, sort:'td_a'})],
];
const LOT_CHIPS=[[0,'Any'],[5000,'5,000+ sf'],[7500,'7,500+ sf'],[10000,'10,000+ sf'],[21780,'½ acre+'],[43560,'1 acre+'],[217800,'5 acres+']];

/* saved: UI */
function renderSavedUI(){
  const n=SV.count(); $('savedCount').textContent=fmt.format(n); $('savedBtn').classList.toggle('on',S.saved); $('savedBtn').setAttribute('aria-pressed',S.saved);
  $('savedBar').hidden=!S.saved; document.body.classList.toggle('saved-mode',S.saved);
  if(!S.saved) return;
  const cnt={}; for(const x of SV.list()) cnt[x.status]=(cnt[x.status]||0)+1;
  $('svStatus').innerHTML=`<button type="button" class="chip ${!S.svSt.size?'on':''}" data-st="" aria-pressed="${!S.svSt.size}">All<span class="n">${fmt.format(n)}</span></button>`+SV.STATUSES.map(s=>{ const on=S.svSt.has(s), k=cnt[s]||0; return `<button type="button" class="chip ${on?'on':''} ${!k&&!on?'zero':''}" data-st="${esc(s)}" aria-pressed="${on}">${esc(s)}<span class="n">${k}</span></button>`; }).join('');
  const missing=n-savedIdx().size;
  $('svInfo').textContent=!n?'Nothing saved yet. Tap the ☆ on any property to save it.':`${fmt.format(n)} saved${missing?` · ${missing} not in the current data (still kept and exported)`:''}`;
}
function refreshFolio(folio){
  { const ob=$('outBox'); if(ob&&ob.dataset.folio===folio&&!(document.activeElement&&ob.contains(document.activeElement)&&['actNote','outNext','actDate'].includes(document.activeElement.id))) ob.innerHTML=outInner(folio); }
  if(S.view==='pipe') renderPipe();
  { const fb=$('finBox'), sb=$('savedBox'); if(fb&&sb&&sb.dataset.folio===folio) fb.innerHTML=finHTML(folio); }
  document.querySelectorAll(`[data-star="${folio}"]`).forEach(b=>{ const on=SV.has(folio); b.classList.toggle('on',on); b.setAttribute('aria-pressed',on); if(b.classList.contains('star')){ b.setAttribute('aria-label',on?'Remove from saved':'Save property'); b.title=on?'Saved · click to remove':'Save this property'; } });
  if(S.view==='cards'){ const el=document.querySelector(`#cards .card[data-folio="${folio}"]`); if(el){ const foc=document.activeElement&&el.contains(document.activeElement)&&document.activeElement.dataset.star; el.outerHTML=cardHTML(+el.dataset.id); if(foc){ const b=document.querySelector(`#cards .card[data-folio="${folio}"] [data-star]`); if(b) b.focus(); } } }
  if(S.view==='table'){ lastRange=''; renderTable(false); }
  const box=$('savedBox'); if(box && box.dataset.folio===folio && !(document.activeElement&&['svNote','svCond'].includes(document.activeElement.id))){ const foc=document.activeElement&&box.contains(document.activeElement)?document.activeElement.id||'star':''; box.innerHTML=savedBoxHTML(+box.dataset.id,folio); if(foc){ const t=foc==='star'?box.querySelector('[data-star]'):$(foc); if(t) t.focus(); } }
}
function download(name,blob){ const url=URL.createObjectURL(blob), a=document.createElement('a'); a.href=url; a.download=name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(url),60000); }
const stamp=()=>{ const d=new Date(); return d.getFullYear()+String(d.getMonth()+1).padStart(2,'0')+String(d.getDate()).padStart(2,'0'); };
function savedListCSV(){
  // same contact-only columns as every property export (EXP_HEAD)
  const ids=savedIdx(); for(const k in EXPSTAT) EXPSTAT[k]=0; const rows=SV.list().map(x=>{ const id=ids.get(x.folio);
    if(id!=null) return exportRow(P(id),I(id)); EXPSTAT.real++;
    return contactRow(x.owner||'',x.addr||'No site address',x.city||'',x.zip||'',x.mail||'',folio13(x.folio)); });
  return new Blob([EXP_HEAD+rows.join('\n')+(rows.length?'\n':'')],{type:'text/csv'});
}
function wireSaved(){
  document.addEventListener('click',e=>{ const b=e.target.closest('[data-star]'); if(!b) return; e.preventDefault(); e.stopPropagation();
    const f=b.dataset.star, on=SV.toggle(f,savedInfo(+b.dataset.id)); toast(SV.error||(on?'Saved':'Removed from saved')); });
  SV.onChange((why,folio)=>{
    if(why==='update'){ refreshFolio(folio); renderSavedUI(); return; }
    if(folio) refreshFolio(folio);
    legendSetup(); if(mapLayer) mapLayer.redraw();
    if(S.saved && why!=='add') ensureSavedPacks().then(run); else renderSavedUI();
  });
  $('savedBtn').onclick=async()=>{ S.saved=!S.saved; if(S.saved){ await ensureSavedPacks(); } clearIdea(); run(); if(S.saved) $('results').scrollIntoView({block:'start'}); };
  $('svBack').onclick=()=>{ S.saved=false; run(); };
  $('svStatus').addEventListener('click',e=>{ const b=e.target.closest('.chip'); if(!b) return; const s=b.dataset.st; if(!s) S.svSt.clear(); else S.svSt.has(s)?S.svSt.delete(s):S.svSt.add(s); run(); });
  $('svExportJson').onclick=()=>{ download(`parcel-finder-saved-${stamp()}.json`,new Blob([JSON.stringify(SV.exportJSON(),null,1)],{type:'application/json'})); toast(fmt.format(SV.count())+' saved properties exported'); };
  $('svExportCsv').onclick=async()=>{ await ensureSavedPacks(); try{ await ensureDetail(); await ensureGeo(); }catch(e){} download(`parcel-finder-saved-${stamp()}.csv`,savedListCSV()); toast(fmt.format(SV.count())+' saved properties exported'); };
  $('svImportLbl').addEventListener('keydown',e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); $('svImport').click(); } });
  $('svImport').addEventListener('change',async e=>{ const f=e.target.files&&e.target.files[0]; e.target.value=''; if(!f) return;
    try{ const r=SV.importJSON(JSON.parse(await f.text())); toast(`Imported: ${r.added} added, ${r.updated} updated, ${r.same} already up to date${r.bad?', '+r.bad+' skipped':''}`); await ensureSavedPacks(); run(); }
    catch(err){ toast('Import failed: '+(err.message||err)); } });
  // any search-filter interaction while the saved list is showing returns to the search
  const leave=e=>{ if(!S.saved) return; if(e.type==='click' && !e.target.closest('button,.chip,input[type=checkbox]')) return; S.saved=false; renderSavedUI(); };
  ['click','input','change'].forEach(t=>$('panel').addEventListener(t,leave,true));
  $('drawerHost').addEventListener('click',e=>{ const a=e.target.closest('[data-finadd]'), d=e.target.closest('[data-findeal]'); if(!a&&!d) return; const UI=window.PFLendersUI; if(!UI) return; $('drawerHost').innerHTML=''; MAP_SEL=-1; if(a) UI.addDeal(a.dataset.finadd); else UI.editDeal(d.dataset.findeal); });
  if(window.PFLenders) window.PFLenders.onChange(()=>{ const box=$('finBox'), sb=$('savedBox'); if(box&&sb) box.innerHTML=finHTML(sb.dataset.folio); });
  $('drawerHost').addEventListener('change',e=>{ if(e.target.id==='svVacant'){ const f=$('savedBox').dataset.folio; SV.update(f,{vacant:e.target.checked}); toast(e.target.checked?'Marked as looking vacant / damaged':'Vacant mark removed'); return; } if(e.target.id==='svStatusSel'){ const f=$('savedBox').dataset.folio; SV.update(f,{status:e.target.value}); toast('Status: '+e.target.value); } });
  let nt=null; $('drawerHost').addEventListener('input',e=>{ const id=e.target.id; if(id!=='svNote'&&id!=='svCond') return; const f=$('savedBox').dataset.folio, v=e.target.value; clearTimeout(nt); $('svNoteMsg').textContent='Saving…'; nt=setTimeout(()=>{ SV.update(f,id==='svNote'?{note:v}:{cond:v}); const m=$('svNoteMsg'); if(m) m.textContent=SV.error||'Saved in this browser.'; },400); });
}

/* send to: tagging, export, mark as sent */
function refreshSendUi(folio){ document.querySelectorAll(`.sendline`).forEach(el=>{ if(el.querySelector(`[data-folio="${folio}"]`)) el.innerHTML=sendBtns(folio)+sentBadges(folio)+(el.querySelector('.apb')?el.querySelector('.apb').outerHTML:''); }); renderSend(); }
function toggleSendTag(f,k){ if(!/^\d{13}$/.test(f)) return; const r=SEND.tags[f]||(SEND.tags[f]={}); let on;
  if(r[k]){ delete r[k]; if(!Object.keys(r).length) delete SEND.tags[f]; on=false; }
  else { r[k]=new Date().toISOString(); on=true; if(SEND.sent[f]&&SEND.sent[f][k]){ delete SEND.sent[f][k]; if(!Object.keys(SEND.sent[f]).length) delete SEND.sent[f]; } }
  saveSend(); toast(on?`Added to the ${teamOf(k).noun} list`:`Removed from the ${teamOf(k).noun} list`);
  if(S.send.size){ run(); return; } refreshSendUi(f); }
function resendTag(f,k){ if(!SEND.sent[f]) return; delete SEND.sent[f][k]; if(!Object.keys(SEND.sent[f]).length) delete SEND.sent[f]; const r=SEND.tags[f]||(SEND.tags[f]={}); if(!r[k]) r[k]=new Date().toISOString(); saveSend(); refreshSendUi(f); toast(`Back on the ${teamOf(k).noun} list`); }
function folioIds(fs){ const want=new Set(fs), ids=new Map(); if(want.size) for(const p of PACKS){ if(!p) continue; const a=strCol(p,'folio'), base=p.idx*16777216; for(let i=0;i<a.length;i++) if(want.has(a[i])){ ids.set(a[i],base+i); if(ids.size===want.size) break; } } return ids; }
function sendPlan(k){ const fs=Object.keys(SEND.tags).filter(f=>SEND.tags[f][k]).sort((a,b)=>SEND.tags[a][k]<SEND.tags[b][k]?-1:SEND.tags[a][k]>SEND.tags[b][k]?1:a<b?-1:1);
  const ids=folioIds(fs), rows=[]; let sent=0, missing=0; for(const f of fs){ if(sentOf(f,k)){ sent++; continue; } const id=ids.get(f); if(id==null){ missing++; continue; } rows.push(id); } return {rows,sent,missing,tagged:fs.length}; }
const defaultList=t=>t.prefix+'_'+dayStr(new Date());
function renderSend(){ const ch=$('sendChips'); if(!ch) return;
  ch.innerHTML=TEAMS.map(t=>{ const on=S.send.has(t.k), n=tagCount(t.k); return `<button type="button" class="chip ${on?'on':''} ${!n&&!on?'zero':''}" data-send="${t.k}" aria-pressed="${on}" title="Only properties tagged ${t.label}">${t.label}<span class="n">${fmt.format(n)}</span></button>`; }).join('');
  if(!PACKS[0]) return;
  TEAMS.forEach(t=>{ const p=sendPlan(t.k); $('sendInfo-'+t.k).textContent=`${fmt.format(p.rows.length)} ready`+(p.sent?` · ${fmt.format(p.sent)} already sent`:'')+(p.missing?` · ${fmt.format(p.missing)} not loaded`:''); $('listName-'+t.k).placeholder=defaultList(t); $('sendExp-'+t.k).disabled=!p.rows.length; });
  const el=$('sendBar'); if(!SEND_PENDING){ el.hidden=true; el.innerHTML=''; return; }
  const t=teamOf(SEND_PENDING.k), n=SEND_PENDING.folios.length; el.hidden=false;
  el.innerHTML=`<span><b>Exported ${fmt.format(n)} ${n===1?'property':'properties'}</b> for the ${t.noun} as ${esc(SEND_PENDING.list)}. Mark them as Sent ${SEND_PENDING.day} so they aren't exported to the ${t.noun} again?</span><button type="button" class="btn primary" data-sendmark="1">Mark as sent</button><button type="button" class="btn" data-sendmark="0">Not now</button>`; }
function sendMark(yes){ const P0=SEND_PENDING; SEND_PENDING=null;
  if(yes&&P0){ const iso=new Date().toISOString(); P0.folios.forEach(f=>{ if(!isTagged(f,P0.k)) return; (SEND.sent[f]||(SEND.sent[f]={}))[P0.k]={d:P0.day,t:iso,list:P0.list}; }); saveSend(); P0.folios.forEach(refreshSendUi);
    const td=todayDay(); let lg=0; SV.batch(()=>P0.folios.forEach(f=>{ if(SV.has(f)&&isTagged(f,P0.k)){ SV.logActivity(f,{type:teamOf(P0.k).act,d:td,outcome:'Sent to list',note:`${teamOf(P0.k).label} list ${P0.list}`}); lg++; } })); toast(`Marked ${fmt.format(P0.folios.length)} as Sent ${P0.day} for the ${teamOf(P0.k).noun}`); }
  renderSend(); }
async function exportSend(k){ const t=teamOf(k);
  if(!PACKS[1] && Object.keys(SEND.tags).some(f=>SEND.tags[f][k]&&!sentOf(f,k))){ const p0=sendPlan(k); if(p0.missing){ try{ await loadPack(1,'Loading condo units for your list…'); }catch(e){} } }
  const p=sendPlan(k); if(!p.rows.length){ toast(p.tagged?`Nothing new for the ${t.noun}: every tagged property is already sent. Use Re-send on a card to send one again.`:`No properties tagged ${t.label} yet.`); return; }
  const list=$('listName-'+k).value.trim()||defaultList(t), day=dayStr(new Date()), btn=$('sendExp-'+k);
  btn.disabled=true; try{ await ensureDetail(); await ensureGeo(); await loadDistress(); await loadAsm().catch(()=>{}); }catch(e){}
  download((list.replace(/[^\w.\-]+/g,'_').replace(/^_+|_+$/g,'')||t.prefix)+'.csv', buildCSV(Uint32Array.from(p.rows),{team:t,list}));
  SEND_PENDING={k,folios:p.rows.map(id=>getStr(P(id),'folio',I(id))),list,day}; btn.disabled=false; renderSend(); toast(`Exported ${fmt.format(p.rows.length)} for the ${t.noun}`); }
/* wiring */
let timer=null; const schedule=(ms=120)=>{ clearTimeout(timer); const lc=document.getElementById('liveCount'); if(lc) lc.classList.add('busy'); timer=setTimeout(run,ms); };
async function ensureOg(){
  const st={ogMin:+$('ogMin').value, ogDist:$('ogDist').checked};
  if(S.ogf || st.ogMin || st.ogDist || S.sort==='og_d' || S.sort==='ogd_d'){ try{ await loadOwners(); }catch(e){ toast(e.message); return; } }
  if(!S.ogf || S.og) return renderOgRow();
  const find=()=>{ for(const p of PACKS){ if(!p) continue; const a=strCol(p,'folio'); const i=a.indexOf(S.ogf); if(i>=0) return p.c.og[i]||-1; } return 0; };
  let g=find(); if(!g && !PACKS[1]){ try{ await loadPack(1,'Loading condo units…'); }catch(e){} g=find(); }
  if(g>0 && OWN.nc[g] && !PACKS[1]){ try{ await loadPack(1,'Loading condo units…'); }catch(e){} }
  S.og=g||-1; renderOgRow();
}
function renderOgRow(){ $('ogRow').hidden=!S.ogf; if(S.ogf) $('ogLabel').textContent=S.og>0&&OWN?`Only properties of ${OWN.name[S.og]} (${fmt.format(OWN.n[S.og])})`:'Only one owner\'s properties'; }
async function ensureCm(){ if(CM||!HAS('commercial')) return; try{ await loadCommercial(); }catch(e){ toast('Commercial data did not load: '+e.message); } }
async function ensureSig(){ if(SIG||!HAS('signals')) return; try{ await loadSignals(); renderSigSrc(); }catch(e){ toast('Clerk signal data did not load: '+e.message); } }
function renderSigSrc(){ if(!SIG) return; const m=SIG.meta; $('sigSrc').textContent=`${fmt.format(m.pf.n)} open pre-foreclosures (lis pendens ${ymd(m.pf.from)} – ${ymd(m.pf.to)}), ${fmt.format(m.pb.n)} probate filings (${fmt.format(m.pb.high)} high, ${fmt.format(m.pb.medium)} medium match), ${fmt.format(m.au.n)} upcoming auctions. Built ${m.built}.`; }
/* comps: card value estimate needs the comp sales + parcel points; loaded in the background after the first results */
let cpBusy=false; async function ensureComps(){ if(cpBusy||!HAS('comps')) return; cpBusy=true; try{ await loadComps(); fillComps(); for(const p of PACKS) if(p&&!p.geo){ await loadGeo(p.idx).catch(()=>{}); } fillComps(); }catch(e){} cpBusy=false; }
async function ensureCondo(){ if(S.types.has('condo') && !PACKS[1]){ try{ await loadPack(1,'Loading condo units…'); if(CP) setTimeout(ensureComps,0); }catch(e){ S.types.delete('condo'); toast(e.message); } } }
const clearIdea=()=>document.querySelectorAll('#ideas .chip').forEach(b=>b.classList.remove('on'));
function wire(){
  $('panel').addEventListener('input',e=>{ if(!e.target.closest('#ideas')) clearIdea(); });
  $('panel').addEventListener('click',e=>{ if(e.target.closest('.chip') && !e.target.closest('#ideas')) clearIdea(); });
  NUM_IDS.concat(['zips']).forEach(id=>$(id).addEventListener('input',()=>schedule()));
  ['mvMin','mvMax'].forEach(id=>$(id).addEventListener('input',()=>schedule(250)));
  ['city','cra','qScope','hideGov','noBldg','qualOnly'].forEach(id=>$(id).addEventListener('change',()=>{ clearIdea(); schedule(0); }));
  $('q').addEventListener('input',()=>schedule(250));
  $('types').addEventListener('click',async e=>{ const b=e.target.closest('.chip'); if(!b) return; const k=b.dataset.t; S.types.has(k)?S.types.delete(k):S.types.add(k); await ensureCondo(); run(); });
  $('dsigs').addEventListener('click',e=>{ const b=e.target.closest('.chip'); if(!b) return; const k=b.dataset.sig; S.dsig.has(k)?S.dsig.delete(k):S.dsig.add(k); run(); });
  $('dsMin').addEventListener('change',()=>{ clearIdea(); schedule(0); });
  $('clrDs').onclick=()=>{ S.dsig.clear(); $('dsMin').value='0'; clearIdea(); run(); };
  $('pcsigs').addEventListener('click',e=>{ const b=e.target.closest('.chip'); if(!b) return; const k=b.dataset.pc; S.pcs.has(k)?S.pcs.delete(k):S.pcs.add(k); run(); });
  $('clrPc').onclick=()=>{ S.pcs.clear(); clearIdea(); run(); };
  $('vsigs').addEventListener('click',e=>{ const b=e.target.closest('.chip'); if(!b) return; const k=b.dataset.vs; S.vsig.has(k)?S.vsig.delete(k):S.vsig.add(k); run(); });
  ['vsMin','vsMine'].forEach(id=>$(id).addEventListener('change',async()=>{ clearIdea(); if($('vsMine').checked) await ensureSavedPacks(); schedule(0); }));
  $('clrVs').onclick=()=>{ S.vsig.clear(); $('vsMin').value='0'; $('vsMine').checked=false; clearIdea(); run(); };
  $('mapColor').addEventListener('change',()=>{ MAP_COLOR=$('mapColor').value; try{ localStorage.setItem('mdpf.mapColor',MAP_COLOR); }catch(e){} legendSetup(); if(mapLayer) mapLayer.redraw(); });
  $('zones').addEventListener('click',e=>{ const b=e.target.closest('.chip'); if(!b) return; const k=b.dataset.z; S.zones.has(k)?S.zones.delete(k):S.zones.add(k); run(); });
  $('clrType').onclick=()=>{ S.types.clear(); S.exL.clear(); clearIdea(); run(); };
  $('ownerKind').addEventListener('click',e=>{ const b=e.target.closest('button[data-k]'); if(!b) return; S.owner=b.dataset.k; clearIdea(); run(); });
  $('mzq').addEventListener('input',()=>schedule(150));
  for(const h of ['mzMiami','mzCounty']) $(h).addEventListener('click',e=>{ const b=e.target.closest('.chip'); if(!b) return; const t=b.dataset.mz; let toks=mzTokens($('mzq').value); toks = toks.includes(t)? toks.filter(x=>x!==t) : toks.concat(t); $('mzq').value=toks.join(', '); run(); });
  $('clrMz').onclick=()=>{ $('mzq').value=''; S.mzSel.clear(); clearIdea(); run(); };
  $('mzCities').addEventListener('click',e=>{ const b=e.target.closest('.chip[data-mzs]'); if(!b) return; const k=b.dataset.mzs; S.mzSel.has(k)?S.mzSel.delete(k):S.mzSel.add(k); run(); });
  $('mzCities').addEventListener('toggle',e=>{ const d=e.target; if(!d.dataset||!d.dataset.j) return; d.open?S.mzOpen.add(d.dataset.j):S.mzOpen.delete(d.dataset.j); },true);
  $('lotz').addEventListener('click',e=>{ const b=e.target.closest('.chip'); if(!b) return; const k=b.dataset.lz; S.lotz.has(k)?S.lotz.delete(k):S.lotz.add(k); run(); });
  $('tierSeg').addEventListener('click',e=>{ const b=e.target.closest('button[data-tier]'); if(!b) return; S.tier=b.dataset.tier; clearIdea(); run(); });
  $('clrTd').onclick=()=>{ S.tier='any'; clearIdea(); run(); };
  RULE_IDS.forEach(([id])=>$(id).addEventListener('input',()=>{ readRules(); schedule(300); }));
  $('td_minlot').addEventListener('change',()=>{ readRules(); schedule(0); });
  $('tdReset').onclick=()=>{ S.rules={...TD.DEFAULT_RULES}; renderRules(); run(); toast('Teardown rule reset to the defaults'); };
  $('cnChips').addEventListener('click',e=>{ const b=e.target.closest('.chip[data-cn]'); if(!b) return; const k=+b.dataset.cn; S.cons.has(k)?S.cons.delete(k):S.cons.add(k); run(); });
  $('clrCn').onclick=()=>{ S.cons.clear(); clearIdea(); run(); };
  $('apOnly').addEventListener('change',()=>{ S.ap=$('apOnly').checked; clearIdea(); run(); });
  const cmCh=async()=>{ S.cm=+$('cmMin').value||0; S.cgas=$('cgasOnly').checked; S.cent=$('centSel').value; clearIdea(); if((S.cm||S.cgas||S.cent||S.sort==='cm_d')&&!CM){ try{ await loadCommercial(); }catch(e){ toast('Commercial data did not load: '+e.message); } } run(); };
  $('contOnly').addEventListener('change',()=>{ S.cont=$('contOnly').checked; clearIdea(); run(); });
  $('hideSent').addEventListener('change',()=>{ S.hideSent=$('hideSent').checked; clearIdea(); run(); });
  $('stHasPhone').addEventListener('change',()=>{ S.hasPhone=$('stHasPhone').checked; clearIdea(); run(); });
  $('stTraced').addEventListener('change',()=>{ S.traced=$('stTraced').checked?'y':''; clearIdea(); run(); });
  $('stNotTraced').addEventListener('change',()=>{ S.traced=$('stNotTraced').checked?'n':''; clearIdea(); run(); });
  $('clrSt').onclick=()=>{ S.hasPhone=false; S.traced=''; clearIdea(); run(); };
  $('tagAllTeam').innerHTML=TEAMS.map(t=>`<option value="${t.k}">${t.label}</option>`).join('');
  $('tagAll').onclick=()=>{ const k=$('tagAllTeam').value, t=teamOf(k), n=results.length; if(!n){ toast('No results to tag.'); return; } const CAP=20000;
    if(n>CAP){ toast(`Narrow the filters first: Tag all works on up to ${fmt.format(CAP)} results (${fmt.format(n)} now).`); return; }
    const iso=new Date().toISOString(); let add=0; for(let j=0;j<n;j++){ const f=getStr(P(results[j]),'folio',I(results[j])); const r=SEND.tags[f]||(SEND.tags[f]={}); if(!r[k]){ r[k]=iso; add++; } }
    saveSend(); renderSend(); renderResults(true); $('tagAllInfo').textContent=`${fmt.format(add)} newly tagged for ${t.label}`; toast(`Tagged ${fmt.format(n)} results for ${t.label} (${fmt.format(add)} new)`); };
  $('expBar').addEventListener('click',e=>{ if(e.target.id==='expMark') expMark($('expTeam').value); else if(e.target.id==='expSkip'){ EXP_PENDING=null; renderExpBar(); } });
  ['cmMin','cgasOnly','centSel'].forEach(k=>$(k).addEventListener('change',cmCh));
  $('pfOnly').addEventListener('change',async()=>{ S.pf=$('pfOnly').checked; clearIdea(); if(S.pf) await ensureSig(); run(); });
  $('pbSel').addEventListener('change',async()=>{ S.pb=$('pbSel').value; clearIdea(); if(S.pb) await ensureSig(); run(); });
  $('sendChips').addEventListener('click',e=>{ const b=e.target.closest('.chip[data-send]'); if(!b) return; const k=b.dataset.send; S.send.has(k)?S.send.delete(k):S.send.add(k); run(); });
  $('asmOn').onclick=async()=>{ S.asm=!S.asm; if(!S.asm) S.asmGroup=0; else if(S.sort==='lot_d'){ S.sort='asm_d'; $('sortSel').value='asm_d'; } clearIdea(); await ensureAsm(); run(); };
  $('asmUp').addEventListener('change',async()=>{ S.asmUp=$('asmUp').checked; if(S.asmUp) S.asm=true; clearIdea(); await ensureAsm(); run(); });
  $('clrAsm').onclick=()=>{ S.asm=false; S.asmUp=false; S.asmGroup=0; clearIdea(); run(); };
  $('asmBack').onclick=()=>{ S.asmGroup=0; run(); };
  document.addEventListener('click',async e=>{ const b=e.target.closest('[data-asmshow],[data-asmmap],[data-asmone]'); if(!b) return; e.preventDefault(); e.stopPropagation();
    if(b.dataset.asmone){ openDrawer(+b.dataset.asmone); return; }
    await loadAsm().catch(()=>{}); $('drawerHost').innerHTML=''; S.asm=true; S.asmGroup=+(b.dataset.asmshow||b.dataset.asmmap); S.sort='asm_d'; $('sortSel').value='asm_d'; clearIdea();
    if(b.dataset.asmmap){ S.view='map'; drawAsmOutlines.fitted=0; } run(); if(!b.dataset.asmmap) window.scrollTo(0,0); },true);
  $('clrSend').onclick=()=>{ S.send.clear(); clearIdea(); run(); };
  TEAMS.forEach(t=>{ $('sendExp-'+t.k).onclick=()=>exportSend(t.k); });
  $('sendBar').addEventListener('click',e=>{ const b=e.target.closest('[data-sendmark]'); if(b) sendMark(b.dataset.sendmark==='1'); });
  document.addEventListener('click',e=>{ const b=e.target.closest('[data-sendtag],[data-resend]'); if(!b) return; e.preventDefault(); e.stopPropagation(); b.dataset.sendtag?toggleSendTag(b.dataset.folio,b.dataset.sendtag):resendTag(b.dataset.folio,b.dataset.resend); },true);
  $('clrZone').onclick=()=>{ S.zones.clear(); S.exZ.clear(); clearIdea(); run(); };
  $('lotChips').innerHTML=LOT_CHIPS.map(([v,l])=>`<button type="button" class="chip" data-v="${v}">${l}</button>`).join('');
  $('lotChips').addEventListener('click',e=>{ const b=e.target.closest('.chip'); if(!b) return; const v=+b.dataset.v; $('lotMin').value=v||''; $('lotMax').value=''; run(); });
  ['zoning','landuse'].forEach(f=>{
    $(f+'Find').addEventListener('input',()=>renderFacet(f));
    $(f+'List').addEventListener('change',e=>{ const t=e.target; if(!t.dataset.f) return; const set=f==='zoning'?S.exZ:S.exL, i=+t.dataset.i; t.checked?set.add(i):set.delete(i); schedule(100); });
  });
  $('ideas').innerHTML=IDEAS.map(([l],i)=>ideaOk(l)?`<button type="button" class="chip" data-i="${i}">${l}</button>`:'').join('');
  $('ideas').addEventListener('click',async e=>{ const b=e.target.closest('.chip'); if(!b) return; applyState({...IDEAS[+b.dataset.i][1](), view:S.view, bbox:S.bbox}); await ensureAsm(); await ensureCondo(); await ensureOg(); run(); clearIdea(); b.classList.add('on'); });
  $('toResults').onclick=()=>{ const r=$('results'); const y=r.getBoundingClientRect().top+window.scrollY-($('stickybar').offsetHeight+16); window.scrollTo({top:y,behavior:'smooth'}); };
  if(HAS('mscreen')) mrWire();
  $('resetBtn').onclick=()=>{ applyState({...BLANK(), view:S.view}); clearIdea(); run(); };
  $('sortSel').addEventListener('change',async()=>{ S.sort=$('sortSel').value; if(S.sort.startsWith('og')) await ensureOg(); doSort(); save(); renderResults(true); });
  $('vCards').onclick=()=>{ S.view='cards'; save(); renderResults(true); };
  $('vTable').onclick=()=>{ S.view='table'; save(); renderResults(true); };
  $('vMap').onclick=()=>{ S.view='map'; save(); renderResults(true); };
  $('vPipe').onclick=async()=>{ S.view='pipe'; await ensureSavedPacks(); save(); renderResults(true); };
  $('pipeCols').addEventListener('click',async e=>{ const b=e.target.closest('[data-pipe]'); if(!b) return; await ensureSavedPacks(); const id=savedIdx().get(b.dataset.pipe); if(id==null){ toast('This property is not in the current data (still kept and exported).'); return; } openDrawer(id); });
  $('pipeExport').onclick=()=>$('svExportJson').click();
  $('pipeImportLbl').addEventListener('keydown',e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); $('svImport').click(); } });
  $('dueOnly').addEventListener('change',()=>{ S.due=$('dueOnly').checked; clearIdea(); run(); });
  $('stageSel').innerHTML='<option value="">Any</option>'+SV.STAGES.map(s=>`<option>${s}</option>`).join('');
  $('stageSel').addEventListener('change',()=>{ S.stage=$('stageSel').value; clearIdea(); run(); });
  $('clrOut').onclick=()=>{ S.due=false; S.stage=''; clearIdea(); run(); };
  $('drawerHost').addEventListener('change',e=>{ const ob=$('outBox'); if(!ob||!ob.contains(e.target)) return; const f=ob.dataset.folio, id=+ob.dataset.id;
    if(e.target.id==='outStage'||e.target.id==='outNext'){ if(!SV.has(f)) SV.add(f,savedInfo(id)); SV.update(f,e.target.id==='outStage'?{stage:e.target.value}:{next:e.target.value}); ob.innerHTML=outInner(f); toast(e.target.id==='outStage'?'Stage: '+e.target.value:(e.target.value?'Next follow-up '+e.target.value:'Follow-up cleared')); } });
  $('drawerHost').addEventListener('click',e=>{ const ob=$('outBox'); if(!ob||!ob.contains(e.target)) return; const f=ob.dataset.folio, id=+ob.dataset.id;
    if(e.target.id==='actAdd'){ const a=SV.logActivity(f,{type:$('actType').value,d:$('actDate').value,outcome:$('actOutcome').value,note:$('actNote').value.trim()},savedInfo(id)); toast(a?`${ACT_LABEL[a.type]} logged`:'Pick a valid date'); if(a){ ob.innerHTML=outInner(f); } return; }
    const d=e.target.closest('[data-actdel]'); if(d){ SV.removeActivity(f,d.dataset.actdel); ob.innerHTML=outInner(f); toast('Activity deleted'); } });
  $('clrArea').onclick=()=>{ S.bbox=null; $('areaRow').hidden=true; clearIdea(); run(); };
  $('mapArea').onclick=()=>{ if(!LMAP) return; const b=LMAP.getBounds(); S.bbox=[+b.getSouth().toFixed(6),+b.getWest().toFixed(6),+b.getNorth().toFixed(6),+b.getEast().toFixed(6)]; $('areaRow').hidden=false; clearIdea(); MAP_NOFIT=true; run(); };
  $('mapFit').onclick=()=>fitResults(true);
  const fromUrl=()=>{ if(location.hash===HIST.url) return; HIST.url=location.hash; const st=parseHash()||{...BLANK(), view:S.view}; HIST.restoring=true; applyState(st); clearIdea();
    ensureAsm().then(ensureCondo).then(ensureOg).then(()=>{ run(); HIST.restoring=false; HIST.last=Date.now(); }); };
  window.addEventListener('hashchange',fromUrl); window.addEventListener('popstate',fromUrl);
  ['ogMin','ogDist','ogInst'].forEach(id=>$(id).addEventListener('change',async()=>{ clearIdea(); await ensureOg(); run(); }));
  $('clrOg').onclick=()=>{ S.ogf=''; S.og=0; renderOgRow(); clearIdea(); run(); };
  $('showMore').onclick=()=>renderResults(false);
  $('cards').addEventListener('click',e=>{ if(e.target.closest('[data-star],[data-sendtag],[data-resend],[data-asmshow],.cmore,.obmore,.stl,[data-stgo]')) return; const c=e.target.closest('.card'); if(c) openDrawer(+c.dataset.id); });
  $('cards').addEventListener('keydown',e=>{ if((e.key==='Enter'||e.key===' ') && e.target.classList.contains('card')){ e.preventDefault(); openDrawer(+e.target.dataset.id); } });
  $('tbody').addEventListener('click',e=>{ if(e.target.closest('[data-star]')) return; const tr=e.target.closest('tr[data-id]'); if(tr) openDrawer(+tr.dataset.id); });
  wireSaved();
  $('thead').addEventListener('click',e=>{ const th=e.target.closest('th'); if(!th||!th.dataset.s) return; S.sort=th.dataset.s; $('sortSel').value=S.sort; doSort(); save(); renderResults(true); });
  let raf=0; $('scroller').addEventListener('scroll',()=>{ if(raf) return; raf=requestAnimationFrame(()=>{ raf=0; renderTable(false); }); });
  window.addEventListener('resize',()=>{ if(S.view==='table') renderTable(false); });
}

async function boot(){
  try{
    META=await (await fetch(DP+'meta.json')).json(); D=META.dicts; PCOV=(META.permitCov&&META.permitCov.cities)||{};
    MZ=D.mzone||[null]; MZ_UP=MZ.map(e=>e?String(e[0]).toUpperCase():''); LU_T=D.landuse.map(luType); Z_G=D.zoning.map(zGroup);
    $('srcCount').textContent=fmt.format(META.total); if(PFC.id!==PFC.DEFAULT){ $('srcLine').firstChild.nodeValue=`Every property on the ${PFC.cfg.roll}, `; const cl=document.querySelector('label[for="cra"]'); if(cl&&HAS('flood')) cl.textContent='FEMA flood zone'; } PFC.applyLayers(); $('srcDate').textContent=META.salesThrough||META.built;
    $('srcLine').title=`Downloaded from ${PFC.cfg.source} on ${META.built}. Newest recorded sale on the roll: ${META.salesThrough}. ${META.rollYear} values.`;
    $('footData').textContent=`Pulled ${META.built}; ${fmt.format(META.stats.farmland_removed)} farm parcels and ${fmt.format(META.stats.reference_removed)} reference-only folios left out.`;
    D.city.filter(Boolean).forEach(v=>{ const o=document.createElement('option'); o.value=v; o.textContent=v; $('city').appendChild(o); });
    D.cra.filter(Boolean).forEach(v=>{ const o=document.createElement('option'); o.value=v; o.textContent=v; $('cra').appendChild(o); });
    $('vsMin').innerHTML=VS_STEPS.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
    $('dsMin').innerHTML=DS_STEPS.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
    try{ MAP_COLOR=localStorage.getItem('mdpf.mapColor')==='score'?'score':'type'; }catch(e){} $('mapColor').value=MAP_COLOR;
    if(META.distress){ const d=META.distress; $('dsSrc').textContent=`Built ${META.built}. ${fmt.format(d.parcels_with_signals||0)} parcels have at least one record.`; }
    if(META.permitCov){ const pc=META.permitCov, cs=Object.entries(pc.cities).sort((a,b)=>a[1].city.localeCompare(b[1].city));
      const withP=cs.filter(([,c])=>c.permit_level==='full'||c.permit_level==='half').length, withC=cs.filter(([,c])=>c.code_level!=='none').length;
      $('pcSrc').textContent=`${withP} of ${cs.length} jurisdictions have 5+ years of public permit history; ${withC} have code-case data. Built ${pc.built||META.built}.`;
      const lv={full:'8+ yrs',half:'5-8 yrs',recent:'< 5 yrs',none:'none'};
      $('pcCov').innerHTML=`<table class="covt"><thead><tr><th>City</th><th>Permits</th><th>Code cases</th><th>Source</th></tr></thead><tbody>`+cs.map(([m,c])=>`<tr><td>${esc(c.city)}</td><td>${c.permit_from?`since ${esc(c.permit_from.slice(0,7))} (${lv[c.permit_level]})`:'none'}</td><td>${c.code_from?`since ${esc(c.code_from.slice(0,7))}`:'none'}</td><td>${c.portal?`<a href="${esc(c.portal)}" target="_blank" rel="noopener">${esc(c.tech||'portal')}</a>`:''}${c.reason?` <small>${esc(c.reason)}</small>`:''}</td></tr>`).join('')+'</tbody></table>'; }
    if(META.vacancy){ const v=META.vacancy; $('vsSrc').textContent=`${fmt.format(v.ge40)} parcels score 40+ (likely), ${fmt.format(v.ge60)} score 60+. Built ${META.built}.`; }
    if(META.owners){ const o=META.owners; $('ogSrc').textContent=`${fmt.format(o.groups)} owners hold 2+ properties; ${fmt.format(o.groups_2plus_distressed_non_institutional)} (excluding banks, government and big institutions) have 2+ parcels with public-record distress signals.`; }
    $('sortSel').innerHTML=SORTS.filter(s=>(s[0]!=='bld_a'||HAS('mscreen'))&&(s[0]!=='tx_d'||HAS('mtax'))&&(s[0]!=='td_a'||HAS('mtdeed'))).map(([k,l])=>`<option value="${k}">Sort: ${l}</option>`).join('');
    $('ownerGrid').innerHTML=OWNER_ROWS.map(([k,l])=>`<label for="ow_${k}">${l}</label><select id="ow_${k}"><option value="any">Either</option><option value="yes">Only</option><option value="no">Hide</option></select>`).join('');
    OWNER_ROWS.forEach(([k])=>$('ow_'+k).addEventListener('change',e=>{ S.flags[k]=e.target.value; clearIdea(); schedule(0); }));
    $('ownerGrid').insertAdjacentHTML('beforeend',FX_ROWS.filter(([k])=>fxAvail(k)).map(([k,l])=>`<label for="fx_${k}">${l}</label><select id="fx_${k}" data-fx="${k}"><option value="any">Either</option><option value="yes">Only</option><option value="no">Hide</option></select>`).join(''));
    FX_ROWS.forEach(([k])=>{ const el=$('fx_'+k); if(el) el.addEventListener('change',e=>{ S.fx[k]=e.target.value; clearIdea(); schedule(0); }); S.fx[k]=S.fx[k]||'any'; });
    $('ownerGrid').insertAdjacentHTML('afterend',`<div class="note fxnote" id="fxNote">${HAS('mscreen')?'Relative transfer = the latest sale is coded by the Florida DOR as between affiliated parties (family, corporate, business) within the last 3 years, owner is an individual. Life estate reads the owner names on the roll (LE, life estate, life tenant). No Clerk death records for '+PFC.cfg.name+' yet, so there is no death filter here (use Estate or heirs above).':'Relative transfer = an unqualified sale in the last 3 years where the seller shares a surname with a different owner (roll grantor names), owner is an individual. Life estate reads the owner names on the roll (LE, life estate, life tenant). Death recorded = Clerk death certificate or probate decedent matched to the owner.'} Verify before acting.</div>`);
    await loadZoneRules();
    if(ZR) $('tdSrc').textContent=`Zone rules for ${fmt.format(ZR.counts.matched)} of ${fmt.format(ZR.counts.codes)} city / county codes (min lot, density, FAR, stories).`;
    if(EX&&EX.cn.meta) $('cnSrc').textContent=`${fmt.format(EX.cn.meta.folios||0)} folios have a recorded category (${EX.cn.meta.source||''}).`;
    $('lotzNote').textContent='Lot vs the zone minimum lot size; “could be split” = single-family zone and lot ≥ your split factor × the minimum.';
    wire(); renderRules();
    const dlF=deepFolio(); let st=dlF?{...BLANK(),q:dlF,hideGov:false,view:'cards'}:parseHash(), fresh=false; if(!st){ try{ st=JSON.parse(localStorage.getItem(PFC.key('mdpf.v2'))||'null'); }catch(e){} }
    if(!st){ st=HAS('distress')?IDEAS[0][1]():{...BLANK()}; fresh=HAS('distress'); }
    applyState(st);
    const ownLoad=loadOwners().catch(()=>null);
    await loadPack(0,'Loading properties…');
    await ensureSig(); await ensureCm(); await ensureAsm(); await ensureCondo(); if(S.saved||S.view==='pipe'||S.due||S.stage||$('vsMine').checked) await ensureSavedPacks(); await ownLoad; await ensureOg();
    ['results','foot'].forEach(id=>$(id).hidden=false);
    run();
    if(fresh) document.querySelector('#ideas .chip').classList.add('on');
    if(dlF) await openDeep(dlF);
    setTimeout(ensureComps,300);
    /* small internal API for drive.js / lenders.js (same page, nothing leaves the browser) */
    const skInfo=id=>{ const p=P(id), i=I(id), c=p.c; return {folio:getStr(p,'folio',i), addr:getStr(p,'addr',i).trim(), city:D.city[c.city[i]]||'', zip:D.zip[c.zip[i]]||'', owner:getStr(p,'owner',i), mail:getStr(p,'mail',i), gov:!!(c.flags[i]&FLAG.govt)}; };
    const skBridge={ results:()=>results, info:skInfo, folioOf:id=>getStr(P(id),'folio',I(id)), folioOut:folio13, ensureDetail, order:PFC.cfg.nameOrder||'first-last', contacted, sentOf, toast, download, dayStr,
      loadAll:async()=>{ if(!PACKS[1]){ try{ await loadPack(1,'Loading condo units…'); }catch(e){} } await ensureDetail(); },
      scan:async(cb,prog)=>{ const cur={folio:'',addr:'',zip:'',gov:false}; let pk=null, ii=0; Object.defineProperties(cur,{owner:{get:()=>getStr(pk,'owner',ii),enumerable:true},mail:{get:()=>getStr(pk,'mail',ii),enumerable:true}});
        let total=0; for(const p of PACKS) if(p) total+=p.n; let done=0, nextY=0;
        for(const p of PACKS){ if(!p) continue; pk=p; const fo=strCol(p,'folio'), zc=p.c.zip, fl=p.c.flags;
          for(let i=0;i<p.n;i++){ ii=i; cur.folio=fo[i]; cur.addr=getStr(p,'addr',i); cur.zip=D.zip[zc[i]]||''; cur.gov=!!(fl[i]&FLAG.govt); cb(cur); done++; if(done>=nextY){ nextY=done+25000; if(prog) prog(Math.round(done/total*100)); await new Promise(r=>setTimeout(r,0)); } } }
        if(prog) prog(100); },
      setPending:o=>{ EXP_PENDING=o; renderExpBar(); }, showPhones:()=>{ S.hasPhone=true; S.saved=false; clearIdea(); run(); }, rerender:()=>{ run(); }, run };
    window.PF={skBridge, expStat:()=>({...EXPSTAT}), cmReady:()=>!!CM, cmMeta:()=>CM&&CM.meta, cmGet:f=>CMM.get(f)||null, cmMissing:async fs=>{ if(!PACKS[1]) await loadPack(1,'Loading condo units…'); const all=new Set(); PACKS.forEach(p=>{ if(p){ const c=strCol(p,'folio'); for(let i=0;i<p.n;i++) all.add(c[i]); } }); return fs.filter(f=>!all.has(f)); }, META,D,PACKS,P,I,getStr,LU_T,TYPE_LABEL,SV,esc,money,fmt,dollars,dateStr,monYr,folioFmt,today,toast,savedInfo,loadGeo,loadLeaflet,openDrawer,scoreBadge,vacBadge,sigBadges,ensureSavedPacks,savedIdx,stKey,svDate,download,stamp,csvq,
      setSaved:on=>{ S.saved=!!on; run(); }, rerun:()=>run(),
      // test hook: total + an evenly spaced sample of the current results with the raw fields filters use
      sample:(k=300)=>{ const n=results.length, out=[], step=Math.max(1,Math.floor(n/k)); for(let j=0;j<n&&out.length<k;j+=step){ const id=results[j], p=P(id), i=I(id), c=p.c, mz=D.mzone[c.mz[i]]||[], g=asmOf(p,i);
        out.push({folio:getStr(p,'folio',i), owner:getStr(p,'owner',i), addr:getStr(p,'addr',i), city:D.city[c.city[i]], zip:D.zip[c.zip[i]], lu:D.landuse[c.landuse[i]], type:LU_T[c.landuse[i]], mzCode:mz[0]||'', mzJur:mz[1]||'',
          mkt:c.mkt[i], land:c.land[i], lot:c.lot[i], yb:c.yb[i], units:c.units[i], flags:c.flags[i], dsig:c.dsig[i], dscore:c.dscore[i], sd1:c.sd1[i], sale1:c.sale1[i], og:c.og[i],
          tier:p.td?p.td.tier[i]:null, ap:p.ap?p.ap[i]:0, stage:(SV.get(getStr(p,'folio',i))||{}).stage||null, due:!!SV.dueState(getStr(p,'folio',i),todayDay()), sg:p.sg?p.sg[i]:0, cmd:CMM.get(getStr(p,'folio',i))||null, pf:PFM.get(getStr(p,'folio',i))||null, pb:PBM.get(getStr(p,'folio',i))||null, au:AUM.get(getStr(p,'folio',i))||null, comps:(()=>{ const x=compsOf(p,i); return x?{n:x.n,rad:x.rad,band:x.band,useB:x.useB,size:x.size,sameCn:x.sameCn,com:!!x.com,ppsf:x.ppsf||0,lo:x.lo||0,hi:x.hi||0,est:x.est||0}:null; })(), asm:g?{id:g.id,upside:g.upside,muni:g.muni}:null}); } return {n, rows:out, dbit:DBIT, sort:S.sort}; },
      sigMeta:()=>SIG&&SIG.meta, compsMeta:()=>CP&&CP.meta, compsReady:()=>!!CP&&PACKS.every(p=>!p||!!p.geo), ensureComps};
    document.dispatchEvent(new Event('pf:ready')); window.PF_READY=true;
    if('serviceWorker' in navigator && /^https?:$/.test(location.protocol)) { const hadCtl=!!navigator.serviceWorker.controller; navigator.serviceWorker.register('sw.js',{updateViaCache:'none'}).then(r=>{ r.update().catch(()=>{}); }).catch(()=>{});
      navigator.serviceWorker.addEventListener('controllerchange',()=>{ if(!hadCtl||document.getElementById('swUpd')) return; const b=document.createElement('div'); b.id='swUpd'; b.className='swupd'; b.innerHTML='A new version of Parcel Finder is ready. <button type="button">Reload</button>'; b.querySelector('button').onclick=()=>location.reload(); document.body.appendChild(b); }); }
    IDB.prune(META.ver);
    setTimeout(()=>{ loadDetail(0).catch(()=>{}); },1500);
    setTimeout(()=>{ loadGeo(0).catch(()=>{}); },4000);
    setTimeout(()=>{ if(!ASM&&HAS('asm')) loadAsm().then(()=>{ renderAsmSrc(); if(S.view==='cards') renderResults(true); renderChips(); }).catch(()=>{}); },6000);
  }catch(e){ $('loadMsg').textContent='The property data did not load.'; $('loadSub').textContent=String(e.message||e)+'. Reload the page to try again.'; }
}
boot();
})();
