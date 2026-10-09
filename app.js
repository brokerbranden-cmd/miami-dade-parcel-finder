
(() => {
"use strict";
const $ = id => document.getElementById(id);
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
const VSIG=[['NA','No homestead + absentee',15],['US','Unsafe structure case',25],['NG','Neglect code case',15],['FR','Foreclosure registry',12],['XP','Expired / revoked permit',8],['NP','No permit since 2014',6],['LO','Owned 20+ years',5],['LB','Building < 20% of value',8],['TX','Tax delinquent',10],['ES','Estate / deceased',8],['OV','Other open case',4],['RP','Recent permit',-15]];
const VBIT=Object.fromEntries(VSIG.map((d,i)=>[d[0],i]));
const VS_STEPS=[[0,'Any'],[25,'25+ possible'],[40,'40+ likely'],[60,'60+ strong']];
const vsTone=v=>v>=60?'v3':v>=40?'v2':v>=25?'v1':'v0';
const vsWord=v=>v>=60?'Strong vacancy hint':v>=40?'Likely vacant / neglected':v>=25?'Possibly vacant':'';
const DS_STEPS=[[0,'Any score'],[20,'20+'],[35,'35+'],[50,'50+ (hot)'],[70,'70+']];
const dsTone=v=>v>=50?'s4':v>=35?'s3':v>=20?'s2':v>0?'s1':'s0';
let DIST=null, distP=null;
/* owner portfolios (data/owners.json.gz from scripts/owners_lib.py; parcel -> group id in the 'og' column) */
let OWN=null, ownP=null;
const loadOwners=()=>OWN?Promise.resolve(OWN):(ownP||(ownP=(async()=>{ if(!META.ownersFile) return null; const r=await fetch('data/'+META.ownersFile+'?v='+META.ver); if(!r.ok) throw new Error('Owner data did not load');
  const j=JSON.parse(dec.decode(await gunzip(new Uint8Array(await r.arrayBuffer()))));
  OWN={n:Uint32Array.from(j.n), nd:Uint32Array.from(j.nd), nc:Uint32Array.from(j.nc), mv:Float64Array.from(j.mv), fl:Uint8Array.from(j.fl), name:j.name, nv:j.nv}; return OWN; })().catch(e=>{ ownP=null; throw e; })));
const OGFL=[[1,'Government'],[2,'Bank / lender'],[4,'Association, church or non-profit'],[8,'Large holder (200+ parcels)']];
const ogFlags=f=>OGFL.filter(([b])=>f&b).map(x=>x[1]);
const loadDistress=()=>distP||(distP=(async()=>{ if(!META.distressFile) return null; const r=await fetch('data/'+META.distressFile+'?v='+META.ver); if(!r.ok) throw new Error('Distress data did not load'); DIST=JSON.parse(dec.decode(await gunzip(new Uint8Array(await r.arrayBuffer())))); return DIST; })().catch(e=>{ distP=null; throw e; }));
const FLAG = {homestead:1, oos:2, absz:4, corp:8, trust:16, govt:32, estate:64, senior:128};
const MZ_MIAMI=[['T3','Sub-urban (single family, duplex)'],['T4','General urban (small apartments)'],['T5','Urban center (up to 5 stories)'],['T6','Urban core (8+ stories)'],['CI','Civic institution'],['CS','Civic space'],['D1','Work place'],['D2','Industrial'],['D3','Waterfront industrial']];
const MZ_COUNTY=[['RU-1','Single family'],['RU-2','Duplex'],['RU-TH','Townhouse'],['RU-3','Small multifamily'],['RU-4','Apartments'],['RU-5','Residential / office'],['EU','Estates'],['BU','Business'],['IU','Industrial'],['GU','Interim'],['PAD','Planned area development']];
const OWNER_KINDS = [['all','All owners'],['person','Individuals'],['corp','LLCs & companies'],['trust','Trusts']];
const OWNER_ROWS = [
  ['homestead','Owner lives there (homestead)'],['oos','Owner mails from out of state'],['absz','Owner mails to a different ZIP'],
  ['corp','Owned by an LLC or company'],['trust','Owned by a trust'],['estate','Estate or heirs'],['senior','Senior exemption']];
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
const S = { og:0, ogf:'', saved:false, vsig:new Set(), svSt:new Set(), dsig:new Set(), types:new Set(), zones:new Set(), exZ:new Set(), exL:new Set(), flags:{}, owner:'all', sort:'lot_d', view:'cards', bbox:null };
let facet = {lc:null, zc:null, mc:null, kc:null, dc:null};
let MZ=null, MZ_UP=null;
const mzTokens = q => q.toUpperCase().split(/[\s,;]+/).map(t=>t.trim()).filter(Boolean);
function mzAllow(q){ const toks=mzTokens(q); if(!toks.length) return null; const a=new Uint8Array(MZ.length); for(let i=1;i<MZ.length;i++){ const c=MZ_UP[i]; for(const t of toks){ if(c===t || c.startsWith(t)){ a[i]=1; break; } } } return a; }

const IDB=(()=>{ let dbp=null;
  const open=()=>dbp||(dbp=new Promise((res,rej)=>{ try{ const r=indexedDB.open('mdpf',1); r.onupgradeneeded=()=>r.result.createObjectStore('f'); r.onsuccess=()=>res(r.result); r.onerror=()=>rej(r.error); r.onblocked=()=>rej(new Error('blocked')); }catch(e){ rej(e); } }));
  const withTimeout=(pr,ms)=>Promise.race([pr,new Promise(r=>setTimeout(()=>r(null),ms))]);
  async function get(k){ try{ const db=await withTimeout(open(),1500); if(!db) return null; return await withTimeout(new Promise(res=>{ const q=db.transaction('f').objectStore('f').get(k); q.onsuccess=()=>res(q.result||null); q.onerror=()=>res(null); }),3000); }catch(e){ return null; } }
  async function put(k,v){ try{ const db=await withTimeout(open(),1500); if(db) db.transaction('f','readwrite').objectStore('f').put(v,k); }catch(e){} }
  async function prune(ver){ try{ const db=await withTimeout(open(),1500); if(!db) return; const r=db.transaction('f','readwrite').objectStore('f').openCursor(); r.onsuccess=()=>{ const cur=r.result; if(!cur) return; if(!String(cur.key).startsWith(ver+'/')) cur.delete(); cur.continue(); }; }catch(e){} }
  return {get,put,prune}; })();
async function fetchAll(files, onBytes){
  const bufs = await Promise.all(files.map(async f => {
    const key=META.ver+'/'+f, hit=await IDB.get(key);
    if(hit && hit.byteLength){ onBytes(hit.byteLength); return new Uint8Array(hit); }
    const r = await fetch('data/'+f); if(!r.ok) throw new Error('Could not load '+f+' ('+r.status+')');
    if(!r.body){ const b=new Uint8Array(await r.arrayBuffer()); onBytes(b.length); return b; }
    const rd=r.body.getReader(), chunks=[]; let len=0;
    for(;;){ const {done,value}=await rd.read(); if(done) break; chunks.push(value); len+=value.length; onBytes(value.length); }
    const out=new Uint8Array(len); let o=0; for(const c of chunks){out.set(c,o);o+=c.length;} IDB.put(key,out.buffer); return out;
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
  PACKS[i]=parsePack(await gunzip(raw),pk.name,i);
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
const num=id=>{ const v=$(id).value.trim(); if(v==='') return null; const n=Number(v); return isFinite(n)?n:null; };
function readState(){
  const st={}; NUM_IDS.forEach(id=>st[id]=num(id));
  st.mvMin=+$('mvMin').value||null; st.mvMax=+$('mvMax').value||null;
  st.mzq=$('mzq').value.trim(); st.q=$('q').value.trim(); st.qScope=$('qScope').value; st.city=$('city').value; st.zips=$('zips').value; st.cra=$('cra').value;
  st.hideGov=$('hideGov').checked; st.noBldg=$('noBldg').checked; st.qualOnly=$('qualOnly').checked;
  st.types=[...S.types]; st.zones=[...S.zones]; st.exZ=[...S.exZ].map(i=>D.zoning[i]); st.exL=[...S.exL].map(i=>D.landuse[i]);
  st.dsig=[...S.dsig]; st.dsMin=+$('dsMin').value||0; st.flags={...S.flags}; st.owner=S.owner; st.sort=S.sort; st.view=S.view; st.bbox=S.bbox; st.saved=S.saved; st.svSt=[...S.svSt]; st.ogMin=+$('ogMin').value||0; st.ogDist=$('ogDist').checked; st.ogInst=$('ogInst').checked; st.ogf=S.ogf; st.vsig=[...S.vsig]; st.vsMin=+$('vsMin').value||0; st.vsMine=$('vsMine').checked; return st;
}
function save(){ const st=readState(); try{ localStorage.setItem('mdpf.v2',JSON.stringify(st)); }catch(e){} writeHash(st); }
function applyState(st){
  NUM_IDS.forEach(id=>$(id).value=st[id]==null?'':st[id]);
  $('mvMin').value=st.mvMin||0; $('mvMax').value=st.mvMax||0;
  $('mzq').value=st.mzq||''; $('q').value=st.q||''; $('qScope').value=st.qScope||'ao'; $('city').value=st.city||''; $('zips').value=st.zips||''; $('cra').value=st.cra||'';
  $('hideGov').checked=st.hideGov!==false; $('noBldg').checked=!!st.noBldg; $('qualOnly').checked=!!st.qualOnly;
  S.types=new Set(st.types||[]); S.zones=new Set(st.zones||[]); S.dsig=new Set((st.dsig||[]).filter(k=>k in DBIT)); $('dsMin').value=DS_STEPS.some(x=>x[0]===+st.dsMin)?String(+st.dsMin):'0';
  S.exZ=new Set((st.exZ||[]).map(v=>D.zoning.indexOf(v)).filter(i=>i>=0)); S.exL=new Set((st.exL||[]).map(v=>D.landuse.indexOf(v)).filter(i=>i>=0));
  S.owner=OWNER_KINDS.some(o=>o[0]===st.owner)?st.owner:'all'; S.flags={}; OWNER_ROWS.forEach(([k])=>{ S.flags[k]=(st.flags&&st.flags[k])||'any'; $('ow_'+k).value=S.flags[k]; });
  S.sort=SORT_MAP[st.sort]?st.sort:'lot_d'; $('sortSel').value=S.sort; S.view=['cards','table','map'].includes(st.view)?st.view:(S.view||'cards');
  $('ogMin').value=[0,2,3,5,10,25].includes(+st.ogMin)?String(+st.ogMin):'0'; $('ogDist').checked=!!st.ogDist; $('ogInst').checked=!!st.ogInst;
  if((st.ogf||'')!==S.ogf){ S.ogf=st.ogf||''; S.og=0; } $('ogRow').hidden=!S.ogf;
  S.vsig=new Set((st.vsig||[]).filter(k=>k in VBIT)); $('vsMin').value=VS_STEPS.some(x=>x[0]===+st.vsMin)?String(+st.vsMin):'0'; $('vsMine').checked=!!st.vsMine;
  S.saved=!!st.saved; S.svSt=new Set((st.svSt||[]).filter(x=>SV.STATUSES.includes(x)));
  S.bbox=Array.isArray(st.bbox)&&st.bbox.length===4&&st.bbox.every(Number.isFinite)?st.bbox:null; $('areaRow').hidden=!S.bbox;
}

/* filtering */
function textMatcher(st){
  if(!st.q) return null;
  const q=st.q.toUpperCase().replace(/\s+/g,' '), digits=q.replace(/[^0-9]/g,'');
  const folioMode = st.qScope==='ao' && /^[\d\s-]+$/.test(q) && digits.length>=5;
  const cols = folioMode?['folio'] : st.qScope==='ao'?['addr','owner'] : [st.qScope];
  const needle = folioMode?digits:q;
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
  const mine=st.vsMine?new Set([...savedIdx()].filter(([f])=>{ const x=SV.get(f); return x&&x.vacant; }).map(([,id])=>id)):null;
  const bb=S.bbox; if(bb && PACKS.some(p=>p&&!p.geo)){ ensureGeo().then(()=>schedule(0)); }
  let out=new Uint32Array(1<<20), m=0;
  for(const p of PACKS){
    if(!p || (p.name==='condo' && !incCondo && !ogF && !mine)) continue;
    const c=p.c, n=p.n, base=p.idx*16777216, hits=tm?tm(p):null, gl=bb&&p.geo?p.geo:null, VS=c.vscore||new Uint8Array(n), VG=c.vsig||new Uint16Array(n);
    if(bb && !gl) continue;
    for(let i=0;i<n;i++){
      if(hits && !hits[i]) continue;
      if(ogF && c.og[i]!==ogF) continue;
      if(mine && !mine.has(base+i)) continue;
      if(vsMin && VS[i]<vsMin) continue;
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
      if(dsMin && c.dscore[i]<dsMin) continue;
      const sg=c.dsig[i], fsg=sigMask&&!(sg&sigMask)?1:0;
      const li=c.landuse[i], zi=c.zoning[i];
      if(govLU && govLU[li]) continue;
      const mi=c.mz[i];
      const fu=lA&&!lA[li]?1:0, fz=zA&&!zA[zi]?1:0, fm=mA&&!mA[mi]?1:0;
      const kind = fl&8 ? 1 : fl&16 ? 2 : fl&32 ? 3 : 0, fk = wantK>=0 && kind!==wantK ? 1:0;
      const nf=fu+fz+fm+fk;
      const vg=VG[i], fvs=vsMask&&!(vg&vsMask)?1:0;
      if(nf===0 && !fvs && sg&4095){ for(let b=0;b<12;b++) if(sg&(1<<b)) dc[b]++; if(!fsg) dc[12]++; }
      if(nf===0 && !fsg && vg){ for(let b=0;b<VSIG.length;b++) if(vg&(1<<b)) vc[b]++; }
      if(fsg||fvs) continue;
      if(nf===0){ kc[kind]++; lc[li]++; zc[zi]++; mc[mi]++; if(m===out.length){const o2=new Uint32Array(m*2);o2.set(out);out=o2;} out[m++]=base+i; }
      else if(nf===1){ if(fu) lc[li]++; else if(fz) zc[zi]++; else if(fm) mc[mi]++; else kc[kind]++; }
    }
  }
  results=out.subarray(0,m); facet={lc,zc,kc,mc,dc,vc};
  if(S.saved){ const ids=savedIdx(), r=[]; for(const x of SV.list()){ const id=ids.get(x.folio); if(id!=null && (!S.svSt.size||S.svSt.has(x.status))) r.push(id); } results=Uint32Array.from(r); }
  renderSavedUI();
  doSort(); renderChips(); renderSummary(); renderAdvCount(st); renderResults(true);
}

/* sorting */
const SORTS=[
  ['ds_d','Highest distress score','dscore',-1],['vs_d','Most likely vacant / neglected','vscore',-1],['sv_d','Recently saved','saved',-1],['ogd_d','Owner\'s distressed parcels','ogd',-1],['og_d','Owner\'s portfolio size','ogn',-1],['lot_d','Biggest lot first','lot',-1],['lot_a','Smallest lot first','lot',1],
  ['mv_a','Lowest value first','mkt',1],['mv_d','Highest value first','mkt',-1],
  ['held_d','Owned the longest','sd1',1],['sold_d','Sold most recently','sd1',-1],
  ['yb_a','Oldest building first','yb',1],['lp_d','Most value in the land','landpct',-1],['un_d','Most units','units',-1],['ppl_a','Lowest value per lot sq ft','ppl',1],
  ['addr_a','Address A–Z','addr',1]];
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
    key[j] = k==='vscore' ? (c.vscore?c.vscore[i]:0) : k==='landpct' ? (c.mkt[i]?c.land[i]/c.mkt[i]:-1) : k==='yb' ? (c.yb[i]||9999) : k==='ppl' ? (c.lot[i]&&c.mkt[i]?c.mkt[i]/c.lot[i]:1e12) : c[k][i]; }
  const idx=new Uint32Array(n); for(let i=0;i<n;i++) idx[i]=i;
  const k2=k==='dscore'?(j=>{ const id=results[j]; return P(id).c.mkt[I(id)]; }):k==='vscore'?(j=>{ const id=results[j]; return P(id).c.dscore[I(id)]; }):null;
  idx.sort((a,b)=>(key[a]-key[b])*dir || (k2?k2(b)-k2(a):0) || a-b);
  const r2=new Uint32Array(n); for(let i=0;i<n;i++) r2[i]=results[idx[i]]; results=r2;
}

/* chips & summary */
const short=n=> n>=1e6?(n/1e6).toFixed(1)+'M' : n>=1e4?Math.round(n/1e3)+'K' : fmt.format(n);
function renderChips(){
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
  const kc=facet.kc, kAll=kc[0]+kc[1]+kc[2]+kc[3], kN={all:kAll,person:kc[0],corp:kc[1],trust:kc[2]};
  $('ownerKind').innerHTML=OWNER_KINDS.map(([k,l])=>`<button type="button" data-k="${k}" class="${S.owner===k?'on':''}" aria-pressed="${S.owner===k}">${l}<span class="n">${short(kN[k])}</span></button>`).join('');
  renderFacet('zoning'); renderFacet('landuse');
  const dcn=facet.dc||[]; $('dsigs').innerHTML=DSIG.map(([k,l],b)=>{ const on=S.dsig.has(k), n=dcn[b]||0; return `<button type="button" class="chip dchip ${on?'on':''} ${!n&&!on?'zero':''}" data-sig="${k}" aria-pressed="${on}">${l}<span class="n">${short(n)}</span></button>`; }).join('');
  const vcn=facet.vc||[]; $('vsigs').innerHTML=VSIG.map(([k,l,pt],b)=>{ const on=S.vsig.has(k), n=vcn[b]||0; return `<button type="button" class="chip vchip ${pt<0?'neg':''} ${on?'on':''} ${!n&&!on?'zero':''}" data-vs="${k}" aria-pressed="${on}" title="${pt>0?'+':''}${pt} points">${l}<span class="n">${short(n)}</span></button>`; }).join('');
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
  $('summary').innerHTML=bits.join(' · ');
}
function renderAdvCount(st){
  const k=ADV_IDS.filter(id=>st[id]!=null).length + (st.noBldg?1:0) + (st.qualOnly?1:0) + (st.cra?1:0) + (st.qScope!=='ao'?1:0) + S.exZ.size + S.exL.size + Object.values(S.flags).filter(v=>v!=='any').length;
  $('advCount').hidden=!k; $('advCount').textContent=k+' on';
  const main=(st.bbox?1:0)+(st.q?1:0)+(st.city?1:0)+(st.zips.trim()?1:0)+(st.mzq?1:0)+S.types.size+S.zones.size+(st.lotMin!=null||st.lotMax!=null?1:0)+(st.mvMin||st.mvMax?1:0)+(S.owner!=='all'?1:0)+S.dsig.size+(st.dsMin?1:0)+S.vsig.size+(st.vsMin?1:0)+(st.vsMine?1:0)+(S.ogf?1:0)+(st.ogMin?1:0)+(st.ogDist?1:0);
  const tot=k+main; $('onCount').hidden=!tot; $('onCount').textContent=tot+(tot===1?' filter on':' filters on'); $('resetBtn').disabled=!tot;
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
  const b=[]; if(fl&64) b.push('<span class="hot">Estate / heirs</span>'); if(fl&2) b.push('<span class="warm">Out-of-state owner</span>'); else if((fl&4) && !(fl&1)) b.push('<span>Absentee owner</span>');
  if(fl&8) b.push('<span>LLC / company</span>'); if(fl&16) b.push('<span>Trust</span>'); if(fl&1) b.push('<span>Owner lives there</span>'); if(fl&128) b.push('<span>Senior</span>'); return b.join('');
}
function mzLabel(mi){ const e=MZ[mi]; if(!e) return ''; const bits=[]; if(e[4]) bits.push(e[4]+' stories'); if(e[3]&&+e[3]>0) bits.push(e[3]+' units/acre'); return e[2]+(bits.length?' ('+bits.join(', ')+')':''); }
function mzHTML(mi){ const e=MZ[mi]; if(!e) return ''; return `<span class="mzcode">${esc(e[0])}</span> · ${esc(mzLabel(mi))}`; }
function sigBadges(sg){ let h=''; for(let b=0;b<12;b++) if(sg&(1<<b)) h+=`<span class="${DSIG[b][2]}">${DSIG[b][1]}</span>`; return h; }
const vacBadge=(c,i)=>{ const v=c.vscore?c.vscore[i]:0; return v>=25?`<span class="vac ${vsTone(v)}" title="Vacancy / neglect hint ${v} of 100 (public records only)">${v>=40?'Likely vacant':'Possibly vacant'} · ${v}</span>`:''; };
const vsigText=vg=>{ const a=[]; for(let b=0;b<VSIG.length;b++) if(vg&(1<<b)) a.push(VSIG[b][1]); return a.join(', '); };
const scoreBadge=(v,big)=>`<span class="dscore ${dsTone(v)}${big?' big':''}" title="Distress score ${v} of 100">${v}</span>`;
function cardHTML(id){
  const p=P(id), i=I(id), c=p.c;
  const addr=getStr(p,'addr',i)||'No street address', lu=D.landuse[c.landuse[i]], zn=D.zoning[c.zoning[i]], t=LU_T[c.landuse[i]], zg=Z_G[c.zoning[i]];
  const lot=c.lot[i], sf=c.sqft[i], mv=c.mkt[i], yb=c.yb[i], un=c.units[i], bd=c.beds[i];
  const bldgS = sf? [yb?'Built '+yb:'', un>1?un+' units':bd?bd+' bd / '+(c.baths[i]/10)+' ba':''].filter(Boolean).join(' · ') : 'Land only';
  const sale = c.sd1[i]? `${monYr(c.sd1[i])}${c.sale1[i]>100?' for '+money(c.sale1[i]):''} · owned ${Math.max(0,Math.floor((today-c.sd1[i])/365.25))} yrs` : 'No sale on record';
  const folio=getStr(p,'folio',i), sv=SV.get(folio);
  return `<article class="card ${sv?'is-saved':''}" data-id="${id}" data-folio="${folio}" tabindex="0" aria-label="${esc(addr)}. Open details">
    <div class="tags"><span class="tt ${TYPE_TONE[t]}">${TYPE_LABEL[t]}</span><span class="tt ${ZONE_TONE[zg]}">Zoned ${ZONE_LABEL[zg].toLowerCase()}</span><span class="tr">${c.dscore[i]?scoreBadge(c.dscore[i]):''}${starHTML(id,folio)}</span></div>
    ${sv?`<div class="svline"><span class="spill st-${stKey(sv.status)}">${esc(sv.status)}</span>${sv.vacant?'<span class="spill vmine" title="You marked it as looking vacant / damaged">Looks vacant (you)</span>':''}<span class="svd">Saved ${svDate(sv.savedAt)}</span>${sv.note||sv.cond?`<span class="svn" title="${esc([sv.note,sv.cond].filter(Boolean).join(' · '))}">${esc(sv.note||sv.cond)}</span>`:''}</div>`:''}
    <div><h3>${esc(addr)}</h3><div class="city">${esc(D.city[c.city[i]])}, FL ${D.zip[c.zip[i]]}</div></div>
    <div class="facts">
      <div><div class="k">Lot</div><div class="v">${!lot?'–':lot>=100000?acres(lot):fmt.format(lot)+' sf'}</div><div class="s">${!lot?'Shared lot':lot>=100000?short(lot)+' sq ft':acres(lot)}</div></div>
      <div><div class="k">Building</div><div class="v">${sf?fmt.format(sf)+' sf':'None'}</div><div class="s">${esc(bldgS)}</div></div>
      <div><div class="k">Value</div><div class="v">${mv?money(mv):'–'}</div><div class="s">${mv&&c.land[i]?Math.round(c.land[i]/mv*100)+'% is land':'&nbsp;'}</div></div>
    </div>
    <div class="line"><span class="k">Zoning</span><span class="v" title="${esc(zn)}">${mzHTML(c.mz[i]) || esc(nice(zn)||'Not listed')}</span></div>
    <div class="line"><span class="k">Use</span><span class="v" title="${esc(lu)}">${esc(luNice(lu))}</span></div>
    <div class="line"><span class="k">Sold</span><span class="v">${sale}</span></div>
    <div class="line"><span class="k">Owner</span><span class="v">${esc(getStr(p,'owner',i).split(' | ')[0])}</span></div>
    <div class="ob">${c.og[i]&&OWN?`<span class="pf" title="Same owner (name or mailing address) across the county">Owner has ${fmt.format(OWN.n[c.og[i]])}${OWN.nd[c.og[i]]?' · '+fmt.format(OWN.nd[c.og[i]])+' distressed':''}</span>`:''}${vacBadge(c,i)}${sigBadges(c.dsig[i])}${ownerBadges(c.flags[i]&~(c.dsig[i]&1024?64:0))}</div>
  </article>`;
}
function renderResults(reset){
  const n=results.length, cardsOn=S.view==='cards', mapOn=S.view==='map', tableOn=S.view==='table';
  $('empty').hidden=n>0 || mapOn;
  $('vCards').classList.toggle('on',cardsOn); $('vTable').classList.toggle('on',tableOn); $('vMap').classList.toggle('on',mapOn);
  $('cards').hidden=!cardsOn||!n; $('tablebox').hidden=!tableOn||!n; $('mapbox').hidden=!mapOn;
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
  {h:'<span class="sr">Saved</span>★',cls:'stc'},{h:'Address',s:'addr_a'},{h:'Score',num:true,s:'ds_d'},{h:'Signals'},{h:'Vacancy',num:true,s:'vs_d'},{h:'Property'},{h:'City zoning'},{h:'Zoning type'},{h:'Lot sq ft',num:true,s:'lot_d'},{h:'Acres',num:true,s:'lot_d'},
  {h:'Building sq ft',num:true},{h:'Units',num:true,s:'un_d'},{h:'Built',num:true,s:'yb_a'},{h:'Value',num:true,s:'mv_d'},
  {h:'Land %',num:true,s:'lp_d'},{h:'Last sale',num:true,s:'sold_d'},{h:'Sale price',num:true},{h:'Owner'}];
function renderHead(){ $('thead').innerHTML=COLS.map(c=>`<th data-s="${c.s||''}" class="${c.num?'num':''} ${c.cls||''} ${c.s&&S.sort===c.s?'sorted':''}" scope="col">${c.h}</th>`).join(''); }
const sigCodes=sg=>{ const a=[]; for(let b=0;b<12;b++) if(sg&(1<<b)) a.push(DSIG[b][0]); return a.join(' '); };
const sigText=sg=>{ const a=[]; for(let b=0;b<12;b++) if(sg&(1<<b)) a.push(DSIG[b][1]); for(const [b,l] of DSOFT) if(sg&(1<<b)) a.push(l); return a.join(', '); };
function rowHTML(id){
  const p=P(id), i=I(id), c=p.c, mv=c.mkt[i];
  const folio=getStr(p,'folio',i), sv=SV.get(folio);
  return `<tr data-id="${id}" class="${sv?'is-saved':''}"><td class="stc">${starHTML(id,folio)}</td><td class="addr">${esc(getStr(p,'addr',i)||'No street address')}<small>${esc(D.city[c.city[i]])} ${D.zip[c.zip[i]]}${sv?` · <span class="spill st-${stKey(sv.status)}">${esc(sv.status)}</span>`:''}</small></td>
  <td class="num">${c.dscore[i]?scoreBadge(c.dscore[i]):'–'}</td><td class="sigs" title="${esc(sigText(c.dsig[i]))}">${esc(sigCodes(c.dsig[i]))||'–'}</td><td class="num" title="${esc(vsigText(c.vsig?c.vsig[i]:0))}">${c.vscore&&c.vscore[i]?`<span class="vnum ${vsTone(c.vscore[i])}">${c.vscore[i]}</span>`:'–'}${sv&&sv.vacant?' <span class="vmine" title="You marked it vacant / damaged">●</span>':''}</td>
  <td>${TYPE_LABEL[LU_T[c.landuse[i]]]}</td><td title="${esc(mzLabel(c.mz[i]))}"><span class="mzcode">${MZ[c.mz[i]]?esc(MZ[c.mz[i]][0]):'–'}</span></td><td title="${esc(D.zoning[c.zoning[i]])}">${esc(nice(D.zoning[c.zoning[i]])||'–')}</td>
  <td class="num">${c.lot[i]?fmt.format(c.lot[i]):'–'}</td><td class="num">${c.lot[i]?(c.lot[i]/SQFT_AC).toFixed(2):'–'}</td>
  <td class="num">${c.sqft[i]?fmt.format(c.sqft[i]):'–'}</td><td class="num">${c.units[i]||'–'}</td><td class="num">${c.yb[i]||'–'}</td>
  <td class="num">${mv?dollars(mv):'–'}</td><td class="num">${mv?Math.round(c.land[i]/mv*100)+'%':'–'}</td>
  <td class="num">${dateStr(c.sd1[i])||'–'}</td><td class="num">${c.sale1[i]?dollars(c.sale1[i]):'–'}</td><td>${esc(getStr(p,'owner',i))}</td></tr>`;
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
  if(fl&2) soft.push(['Out-of-state owner',6]); else if(fl&4) soft.push(['Absentee owner (mails to another ZIP)',4]);
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

/* vacancy / condition hint (mirrors scripts/vacancy_lib.py) */
function vacParts(c,i,folio){
  const vg=c.vsig?c.vsig[i]:0, fl=c.flags[i], yb=c.yb[i], parts=[];
  for(let b=0;b<VSIG.length;b++){ if(!(vg&(1<<b))) continue; let [k,l,pt]=VSIG[b];
    if(k==='NA'){ pt=fl&2?18:15; l=fl&2?'No homestead + owner mails from out of state':'No homestead + owner mails elsewhere (absentee)'; }
    if(k==='NP'){ pt=yb&&yb<=1970?10:6; l=yb&&yb<=1970?`Built ${yb}, no City of Miami permit on record since 2014`:'No City of Miami permit on record since 2014'; }
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
  const parts=vacParts(c,i,folio), raw=parts.reduce((a,b)=>a+b[1],0), lp=c.lperm?c.lperm[i]:0, cityCov=folio.slice(0,2)==='01';
  const sv=SV.get(folio), d=0.0011, bbox=hasG?[lo-d*1.25,la-d*0.8,lo+d*1.25,la+d*0.8].map(x=>x.toFixed(6)).join(','):'';
  const aerial=hasG?`<a class="aerial" href="https://www.google.com/maps/@?api=1&map_action=map&center=${la.toFixed(6)},${lo.toFixed(6)}&zoom=20&basemap=satellite" target="_blank" rel="noopener" title="Open satellite view in Google Maps"><img alt="Aerial photo of the parcel (Esri World Imagery)" loading="lazy" width="400" height="256" src="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox=${bbox}&bboxSR=4326&imageSR=3857&size=400,256&format=jpg&f=image"><span class="pin" aria-hidden="true"></span><small>Aerial: Esri World Imagery (dates vary) · open satellite ↗</small></a>`:'';
  const links=hasG?`<div class="links vlinks"><a href="https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${la.toFixed(6)},${lo.toFixed(6)}" target="_blank" rel="noopener">Street View ↗</a><a href="https://www.google.com/maps/@?api=1&map_action=map&center=${la.toFixed(6)},${lo.toFixed(6)}&zoom=20&basemap=satellite" target="_blank" rel="noopener">Satellite ↗</a></div>`:'';
  const permit=lp?`Last permit on record: <b>${dateStr(lp)}</b>`:cityCov?'No City of Miami permit on record (2014–today)':(folio.slice(0,2)==='30'?'No County permit in the last 2 years (older County permits are not published)':'Permit history is not published for this city');
  if(!c.bldg[i]) return `<h3>Vacancy &amp; condition</h3><div class="note">No building on record, so there is no vacancy hint.</div>${aerial}${links}`;
  return `<h3>Vacancy &amp; condition ${v?`<span class="vnum big ${vsTone(v)}" title="Vacancy / neglect hint ${v} of 100">${v}</span>`:''}</h3>
    ${v>=25?`<div class="vword ${vsTone(v)}">${vsWord(v)}</div>`:''}
    ${parts.length?`<div class="dbreak">${parts.map(([l,n])=>`<div><span>${esc(l)}</span><b>${n>0?'+':''}${n}</b></div>`).join('')}<div class="tot"><span>Vacancy hint${raw>100?' (capped at 100)':raw<0?' (floored at 0)':''}</span><b>${v}</b></div></div>`:'<div class="note">No vacancy or neglect signals in the public records.</div>'}
    <div class="note">${permit}. ${sv&&sv.vacant?'<b>You marked it as looking vacant / damaged.</b> ':''}A hint from public records only (no utility data is published) — drive by or check Street View before acting.</div>
    ${aerial}${links}`;
}

/* detail drawer */
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

async function openDrawer(id,opts){
  if(OGMAP){ OGMAP.remove(); OGMAP=null; }
  if(!P(id).det){ toast('Loading details…'); try{ await Promise.all([loadDetail(P(id).idx), loadGeo(P(id).idx).catch(()=>{})]); }catch(e){ toast('Details did not load. Try again.'); return; } }
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
      <a href="https://apps.miamidadepa.gov/propertysearch/#/?folio=${folio}" target="_blank" rel="noopener">Property Appraiser page ↗</a>
      <a href="https://www.google.com/maps/search/?api=1&query=${hasG&&!getStr(p,'addr',i)?la.toFixed(6)+','+lo.toFixed(6):gq}" target="_blank" rel="noopener">Google Maps ↗</a>
      ${hasG?`<a href="https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${la.toFixed(6)},${lo.toFixed(6)}" target="_blank" rel="noopener">Street View ↗</a>`:''}
      <button class="btn" type="button" id="copyFolio">Copy folio</button>
      <button class="btn" type="button" id="onMap">Show on map</button>
    </div>
    <div id="savedBox" data-folio="${folio}" data-id="${id}">${savedBoxHTML(id,folio)}</div>
    ${distressHTML(p,i,folio)}
    ${vacancyHTML(p,i,folio)}
    <h3>The property</h3><div class="dl">${rows([
      ['What it is', `${TYPE_LABEL[LU_T[c.landuse[i]]]}<small>${esc(lu)}</small>`],
      ['City zoning', MZ[c.mz[i]] ? `<span class="mzcode">${esc(MZ[c.mz[i]][0])}</span> · ${esc(MZ[c.mz[i]][1])}<small>${esc(mzLabel(c.mz[i]))}${MZ[c.mz[i]][5]?' · min lot '+fmt.format(+MZ[c.mz[i]][5])+' sq ft':''}</small>` : 'Not found on the zoning map'],
      ['Zoning type (appraiser)', `${ZONE_LABEL[Z_G[c.zoning[i]]]}${nice(zn)?' · '+esc(nice(zn)):''}<small>${esc(zn)}</small>`],
      ['Lot size', c.lot[i]? fmt.format(c.lot[i])+' sq ft · '+(c.lot[i]/SQFT_AC).toFixed(3)+' acres':'Not listed'],
      ['Building', c.sqft[i]?fmt.format(c.sqft[i])+' sq ft living area':'No building on record'],
      ['Beds / baths', (c.beds[i]||c.baths[i])? c.beds[i]+' beds / '+(c.baths[i]/10)+' baths':''],
      ['Units', c.units[i]||''],['Stories', c.stories[i]||''],['Year built', c.yb[i]||''],
      ['Buildings on the lot', c.bcount&&c.bcount[i]>1?c.bcount[i]:''],
      ['Redevelopment area', esc(D.cra[c.cra[i]]||'')],['Legal description', esc(getStr(p,'legal',i))]])}</div>
    <h3>${META.rollYear||''} values</h3><div class="dl">${rows([
      ['Market value', dollars(mv)],['Land', dollars(c.land[i])+(mv?`<small>${Math.round(c.land[i]/mv*100)}% of the total</small>`:'')],['Building', dollars(c.bldg[i])],
      ['Assessed (capped)', dollars(c.assd[i])],['Taxable (county)', dollars(c.taxable[i])],
      ['Value per lot sq ft', (mv&&c.lot[i])?'$'+(mv/c.lot[i]).toFixed(2):''],['Value per building sq ft', (mv&&c.sqft[i])?'$'+Math.round(mv/c.sqft[i]):''],
      ['Last year\'s value', prv? dollars(prv)+(chg!==null?`<small class="${chg>=0?'up':'down'}">${chg>=0?'+':''}${chg}% this year</small>`:''):''],
      ['Last sale vs today', (c.sale1[i]>1000&&mv&&c.sq1[i]===1&&!multi)? `Value is ${(mv/c.sale1[i]).toFixed(1)}× the last market sale price` : '']])}</div>
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
  $('scrim').onclick=close; $('closeD').onclick=close; $('copyFolio').onclick=()=>copy(folio,'Folio copied'); $('closeD').focus();
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
  try{ await ensureDetail(); await ensureGeo(); await loadDistress(); await new Promise(r=>setTimeout(r,30));
    const url=URL.createObjectURL(buildCSV(ids)), a=document.createElement('a'); a.href=url; a.download=exportName(kind,ids.length); document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),60000); toast(fmt.format(ids.length)+' properties exported'); }
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
    <div class="sub">${fmt.format(ids.length)} properties in Miami-Dade${fl.length?` · <span class="flagged">${esc(fl.join(', '))}</span>`:''}</div>
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
    if(pts.length) OGMAP.fitBounds(pts,{padding:[18,18],maxZoom:16}); else OGMAP.setView([25.7,-80.35],10);
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
function buildCSV(ids=results){
  const head=['Folio','Address','City','ZIP','Property Type','City Zoning','Zoning Jurisdiction','Zoning Description','Zoning Group','Appraiser Zoning','Land Use','Lot SqFt','Acres','Living SqFt','Beds','Baths','Units','Stories','Year Built','Land Value','Building Value','Market Value','Assessed Value','Land Share %','Last Sale Date','Last Sale Price','Market Sale','Prior Sale Date','Prior Sale Price','Owner','Owner Type','Mailing Address','Homestead','Out of State Owner','Mails to Other ZIP','LLC/Company','Trust','Estate/Heirs','CRA','Legal','Senior Exemption','Taxable Value (County)','Prior Year Value','Sold By','Deed Book-Page','Latitude','Longitude','Property Appraiser Link','Distress Score','Distress Signals','Signal Details','Signal Sources','Vacancy Hint','Vacancy Signals','Last Permit On Record','Saved','Saved Status','Saved Date','Saved Note','Marked Vacant/Damaged','Condition Note'];
  const parts=[head.join(',')+'\n']; let buf='';
  for(let j=0;j<ids.length;j++){
    const id=ids[j], p=P(id), i=I(id), c=p.c, fl=c.flags[i], mv=c.mkt[i];
    buf+=[getStr(p,'folio',i),csvq(getStr(p,'addr',i)),csvq(D.city[c.city[i]]),D.zip[c.zip[i]],csvq(TYPE_LABEL[LU_T[c.landuse[i]]]),(MZ[c.mz[i]]?csvq(MZ[c.mz[i]][0]):''),(MZ[c.mz[i]]?csvq(MZ[c.mz[i]][1]):''),csvq(mzLabel(c.mz[i])),csvq(ZONE_LABEL[Z_G[c.zoning[i]]]),csvq(D.zoning[c.zoning[i]]),csvq(D.landuse[c.landuse[i]]),
      c.lot[i],(c.lot[i]/SQFT_AC).toFixed(3),c.sqft[i],c.beds[i],c.baths[i]/10,c.units[i],c.stories[i],c.yb[i]||'',
      c.land[i],c.bldg[i],mv,c.assd[i],mv?Math.round(c.land[i]/mv*100):'',dateStr(c.sd1[i]),c.sale1[i]||'',c.sq1[i]===1?'Y':c.sq1[i]===2?'N':'',
      dateStr(c.sd2[i]),c.sale2[i]||'',csvq(getStr(p,'owner',i)),fl&8?'LLC/Company':fl&16?'Trust':fl&32?'Government':'Individual',csvq(getStr(p,'mail',i)),
      fl&1?'Y':'',fl&2?'Y':'',fl&4?'Y':'',fl&8?'Y':'',fl&16?'Y':'',fl&64?'Y':'',csvq(D.cra[c.cra[i]]||''),csvq(getStr(p,'legal',i)),
      fl&128?'Y':'',c.taxable[i],c.prv[i]||'',csvq(getStr(p,'grantor',i)),getStr(p,'book',i),p.geo&&p.geo.lat[i]>20?p.geo.lat[i].toFixed(6):'',p.geo&&p.geo.lat[i]>20?p.geo.lon[i].toFixed(6):'','https://apps.miamidadepa.gov/propertysearch/#/?folio='+getStr(p,'folio',i),
      c.dscore[i],csvq(sigText(c.dsig[i])),...distCSV(getStr(p,'folio',i)),c.vscore?c.vscore[i]:'',csvq(vsigText(c.vsig?c.vsig[i]:0)),c.lperm?dateStr(c.lperm[i]):'',...savedCSV(getStr(p,'folio',i))].join(',')+'\n';
    if(buf.length>1e6){ parts.push(buf); buf=''; }
  }
  parts.push(buf); return new Blob(parts,{type:'text/csv'});
}
$('exportBtn').onclick=async()=>{ if(results.length) return exportIds(results,S.saved?'saved':S.ogf?'owner':'properties',$('exportBtn'));
  if(!results.length){ toast('Nothing to export yet.'); return; }
  const btn=$('exportBtn'); btn.disabled=true; btn.textContent='Preparing…';
  try{ await ensureDetail(); await ensureGeo(); await loadDistress(); }catch(e){ toast('Export data did not load. Try again.'); btn.disabled=false; btn.textContent='Export CSV'; return; }
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
    if(st.vsig&&st.vsig.length) h.set('vsig',st.vsig.join(',')); if(st.vsMin) h.set('vs',st.vsMin); if(st.vsMine) h.set('vme','1');
    OWNER_ROWS.forEach(([k])=>{ const v=st.flags[k]; if(v==='yes'||v==='no') h.set('o_'+k,v); });
    HASH_NUM.forEach(id=>{ if(st[id]!=null && st[id]!=='' && !(id.startsWith('mv')&&!st[id])) h.set(id,st[id]); });
    if(!st.hideGov) h.set('gov','1'); if(st.noBldg) h.set('land','1'); if(st.qualOnly) h.set('mkt','1');
    if(st.sort&&st.sort!=='lot_d') h.set('sort',st.sort); if(st.view&&st.view!=='cards') h.set('view',st.view);
    if(st.bbox) h.set('area',st.bbox.join(','));
    if(st.ogf) h.set('ogf',st.ogf); if(st.ogMin) h.set('ogn',st.ogMin); if(st.ogDist) h.set('ogd','1'); if(st.ogInst) h.set('ogi','1');
    if(st.saved) h.set('saved','1'); if(st.saved&&st.svSt&&st.svSt.length) h.set('sst',st.svSt.join(','));
    const str=h.toString(), want=str?'#'+str:'';
    if(location.hash!==want) history.replaceState(null,'',want||(location.pathname+location.search));
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
  st.dsig=list('sig'); st.dsMin=+h.get('ds')||0; st.vsig=list('vsig'); st.vsMin=+h.get('vs')||0; st.vsMine=h.get('vme')==='1';
  st.owner=h.get('owner')||'all'; st.flags={}; OWNER_ROWS.forEach(([k])=>{ const v=h.get('o_'+k); if(v==='yes'||v==='no') st.flags[k]=v; });
  HASH_NUM.forEach(id=>{ const v=h.get(id); st[id]=(v==null||v==='')?null:(isFinite(+v)?+v:null); });
  st.hideGov=h.get('gov')!=='1'; st.noBldg=h.get('land')==='1'; st.qualOnly=h.get('mkt')==='1';
  st.sort=h.get('sort')||'lot_d'; st.view=h.get('view')||'cards';
  st.ogf=(h.get('ogf')||'').replace(/\D/g,''); st.ogMin=+h.get('ogn')||0; st.ogDist=h.get('ogd')==='1'; st.ogInst=h.get('ogi')==='1';
  st.saved=h.get('saved')==='1'; st.svSt=list('sst');
  const a=list('area').map(Number); st.bbox=a.length===4&&a.every(Number.isFinite)?a:null;
  return st;
}

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
    const lat=new Float32Array(n), lon=new Float32Array(n), mx=new Float64Array(n), my=new Float64Array(n);
    for(let k=0;k<n;k++){
      if(!la[k]){ lat[k]=NaN; lon[k]=NaN; mx[k]=NaN; my[k]=NaN; continue; }
      const a=la[k]/1e6+24, b=lo[k]/1e6-81.5, s=Math.sin(a*Math.PI/180);
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
  LMAP=L.map('map',{zoomControl:true,minZoom:8,maxZoom:19}).setView([25.70,-80.35],10);
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
  if(reset) fitResults(false);
  mapLayer.redraw();
}

/* ideas */
const BLANK=()=>({hideGov:true,sort:'lot_d',flags:{},owner:'all'});
const IDEAS=[
  ['🔥 Hottest leads', ()=>({...BLANK(), dsMin:50, sort:'ds_d'})],
  ['Pre-foreclosure & auctions', ()=>({...BLANK(), dsig:['LP','FC'], sort:'ds_d'})],
  ['Tax deeds & delinquent', ()=>({...BLANK(), dsig:['TD','TC'], dsMin:35, sort:'ds_d'})],
  ['Unsafe structures', ()=>({...BLANK(), dsig:['US'], sort:'ds_d'})],
  ['🏚 Likely vacant / neglected', ()=>({...BLANK(), vsMin:40, sort:'vs_d'})],
  ['🏘 Multi-property motivated owners', ()=>({...BLANK(), ogMin:2, ogDist:true, sort:'ogd_d'})],
  ['Owners with 5+ properties', ()=>({...BLANK(), ogMin:5, sort:'og_d'})],
  ['Vacant infill lots', ()=>({...BLANK(), types:['vacant'], lotMin:5000, lotMax:87120, sort:'lot_a'})],
  ['Houses on multifamily land', ()=>({...BLANK(), types:['sf'], zones:['mf'], sort:'lot_d'})],
  ['Teardowns', ()=>({...BLANK(), types:['sf','mf29'], lsMin:80, ybMax:1969, sort:'lp_d'})],
  ['Out-of-state owners, 15+ years', ()=>({...BLANK(), types:['sf','th','mf29','vacant'], hdMin:15, flags:{oos:'yes',homestead:'no'}, sort:'held_d'})],
  ['Estates and heirs', ()=>({...BLANK(), flags:{estate:'yes'}, sort:'held_d'})],
  ['Small multifamily (2–9 units)', ()=>({...BLANK(), types:['mf29'], flags:{homestead:'no'}, sort:'un_d'})],
  ['Big lots, 1 acre+', ()=>({...BLANK(), types:['sf','vacant'], lotMin:43560, sort:'lot_a'})],
  ['Tired landlords (absentee, 20+ yrs)', ()=>({...BLANK(), types:['sf','th','mf29'], hdMin:20, flags:{homestead:'no',absz:'yes'}, sort:'held_d'})],
  ['Lots owned from far away', ()=>({...BLANK(), types:['vacant'], lotMin:4000, flags:{absz:'yes'}, sort:'ppl_a'})],
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
  document.querySelectorAll(`[data-star="${folio}"]`).forEach(b=>{ const on=SV.has(folio); b.classList.toggle('on',on); b.setAttribute('aria-pressed',on); if(b.classList.contains('star')){ b.setAttribute('aria-label',on?'Remove from saved':'Save property'); b.title=on?'Saved · click to remove':'Save this property'; } });
  if(S.view==='cards'){ const el=document.querySelector(`#cards .card[data-folio="${folio}"]`); if(el){ const foc=document.activeElement&&el.contains(document.activeElement)&&document.activeElement.dataset.star; el.outerHTML=cardHTML(+el.dataset.id); if(foc){ const b=document.querySelector(`#cards .card[data-folio="${folio}"] [data-star]`); if(b) b.focus(); } } }
  if(S.view==='table'){ lastRange=''; renderTable(false); }
  const box=$('savedBox'); if(box && box.dataset.folio===folio && !(document.activeElement&&['svNote','svCond'].includes(document.activeElement.id))){ const foc=document.activeElement&&box.contains(document.activeElement)?document.activeElement.id||'star':''; box.innerHTML=savedBoxHTML(+box.dataset.id,folio); if(foc){ const t=foc==='star'?box.querySelector('[data-star]'):$(foc); if(t) t.focus(); } }
}
function download(name,blob){ const url=URL.createObjectURL(blob), a=document.createElement('a'); a.href=url; a.download=name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(url),60000); }
const stamp=()=>{ const d=new Date(); return d.getFullYear()+String(d.getMonth()+1).padStart(2,'0')+String(d.getDate()).padStart(2,'0'); };
function savedListCSV(){
  const ids=savedIdx(), head=['Folio','Address','City','ZIP','Status','Note','Marked Vacant/Damaged','Condition Note','Date Saved','Last Edited','Distress Score','Vacancy Hint','Market Value','Owner','Property Appraiser Link'];
  const rows=SV.list().map(x=>{ const id=ids.get(x.folio), p=id!=null?P(id):null, i=id!=null?I(id):0;
    return [x.folio,csvq(p?getStr(p,'addr',i):x.addr),csvq(p?D.city[p.c.city[i]]:x.city),p?D.zip[p.c.zip[i]]:x.zip,csvq(x.status),csvq(x.note),x.vacant?'Y':'',csvq(x.cond||''),x.savedAt,x.updatedAt,p?p.c.dscore[i]:'',p&&p.c.vscore?p.c.vscore[i]:'',p?p.c.mkt[i]:'',csvq(p?getStr(p,'owner',i):''),'https://apps.miamidadepa.gov/propertysearch/#/?folio='+x.folio].join(','); });
  return new Blob([head.join(',')+'\n'+rows.join('\n')+'\n'],{type:'text/csv'});
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
  $('svExportCsv').onclick=()=>{ download(`parcel-finder-saved-${stamp()}.csv`,savedListCSV()); toast(fmt.format(SV.count())+' saved properties exported'); };
  $('svImportLbl').addEventListener('keydown',e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); $('svImport').click(); } });
  $('svImport').addEventListener('change',async e=>{ const f=e.target.files&&e.target.files[0]; e.target.value=''; if(!f) return;
    try{ const r=SV.importJSON(JSON.parse(await f.text())); toast(`Imported: ${r.added} added, ${r.updated} updated, ${r.same} already up to date${r.bad?', '+r.bad+' skipped':''}`); await ensureSavedPacks(); run(); }
    catch(err){ toast('Import failed: '+(err.message||err)); } });
  // any search-filter interaction while the saved list is showing returns to the search
  const leave=e=>{ if(!S.saved) return; if(e.type==='click' && !e.target.closest('button,.chip,input[type=checkbox]')) return; S.saved=false; renderSavedUI(); };
  ['click','input','change'].forEach(t=>$('panel').addEventListener(t,leave,true));
  $('drawerHost').addEventListener('change',e=>{ if(e.target.id==='svVacant'){ const f=$('savedBox').dataset.folio; SV.update(f,{vacant:e.target.checked}); toast(e.target.checked?'Marked as looking vacant / damaged':'Vacant mark removed'); return; } if(e.target.id==='svStatusSel'){ const f=$('savedBox').dataset.folio; SV.update(f,{status:e.target.value}); toast('Status: '+e.target.value); } });
  let nt=null; $('drawerHost').addEventListener('input',e=>{ const id=e.target.id; if(id!=='svNote'&&id!=='svCond') return; const f=$('savedBox').dataset.folio, v=e.target.value; clearTimeout(nt); $('svNoteMsg').textContent='Saving…'; nt=setTimeout(()=>{ SV.update(f,id==='svNote'?{note:v}:{cond:v}); const m=$('svNoteMsg'); if(m) m.textContent=SV.error||'Saved in this browser.'; },400); });
}

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
async function ensureCondo(){ if(S.types.has('condo') && !PACKS[1]){ try{ await loadPack(1,'Loading condo units…'); }catch(e){ S.types.delete('condo'); toast(e.message); } } }
const clearIdea=()=>document.querySelectorAll('#ideas .chip').forEach(b=>b.classList.remove('on'));
function wire(){
  $('panel').addEventListener('input',e=>{ if(!e.target.closest('#ideas')) clearIdea(); });
  $('panel').addEventListener('click',e=>{ if(e.target.closest('.chip') && !e.target.closest('#ideas')) clearIdea(); });
  NUM_IDS.concat(['zips']).forEach(id=>$(id).addEventListener('input',()=>schedule()));
  ['mvMin','mvMax','city','cra','qScope','hideGov','noBldg','qualOnly'].forEach(id=>$(id).addEventListener('change',()=>{ clearIdea(); schedule(0); }));
  $('q').addEventListener('input',()=>schedule(250));
  $('types').addEventListener('click',async e=>{ const b=e.target.closest('.chip'); if(!b) return; const k=b.dataset.t; S.types.has(k)?S.types.delete(k):S.types.add(k); await ensureCondo(); run(); });
  $('dsigs').addEventListener('click',e=>{ const b=e.target.closest('.chip'); if(!b) return; const k=b.dataset.sig; S.dsig.has(k)?S.dsig.delete(k):S.dsig.add(k); run(); });
  $('dsMin').addEventListener('change',()=>{ clearIdea(); schedule(0); });
  $('clrDs').onclick=()=>{ S.dsig.clear(); $('dsMin').value='0'; clearIdea(); run(); };
  $('vsigs').addEventListener('click',e=>{ const b=e.target.closest('.chip'); if(!b) return; const k=b.dataset.vs; S.vsig.has(k)?S.vsig.delete(k):S.vsig.add(k); run(); });
  ['vsMin','vsMine'].forEach(id=>$(id).addEventListener('change',async()=>{ clearIdea(); if($('vsMine').checked) await ensureSavedPacks(); schedule(0); }));
  $('clrVs').onclick=()=>{ S.vsig.clear(); $('vsMin').value='0'; $('vsMine').checked=false; clearIdea(); run(); };
  $('mapColor').addEventListener('change',()=>{ MAP_COLOR=$('mapColor').value; try{ localStorage.setItem('mdpf.mapColor',MAP_COLOR); }catch(e){} legendSetup(); if(mapLayer) mapLayer.redraw(); });
  $('zones').addEventListener('click',e=>{ const b=e.target.closest('.chip'); if(!b) return; const k=b.dataset.z; S.zones.has(k)?S.zones.delete(k):S.zones.add(k); run(); });
  $('clrType').onclick=()=>{ S.types.clear(); S.exL.clear(); clearIdea(); run(); };
  $('ownerKind').addEventListener('click',e=>{ const b=e.target.closest('button[data-k]'); if(!b) return; S.owner=b.dataset.k; clearIdea(); run(); });
  $('mzq').addEventListener('input',()=>schedule(150));
  for(const h of ['mzMiami','mzCounty']) $(h).addEventListener('click',e=>{ const b=e.target.closest('.chip'); if(!b) return; const t=b.dataset.mz; let toks=mzTokens($('mzq').value); toks = toks.includes(t)? toks.filter(x=>x!==t) : toks.concat(t); $('mzq').value=toks.join(', '); run(); });
  $('clrMz').onclick=()=>{ $('mzq').value=''; clearIdea(); run(); };
  $('clrZone').onclick=()=>{ S.zones.clear(); S.exZ.clear(); clearIdea(); run(); };
  $('lotChips').innerHTML=LOT_CHIPS.map(([v,l])=>`<button type="button" class="chip" data-v="${v}">${l}</button>`).join('');
  $('lotChips').addEventListener('click',e=>{ const b=e.target.closest('.chip'); if(!b) return; const v=+b.dataset.v; $('lotMin').value=v||''; $('lotMax').value=''; run(); });
  ['zoning','landuse'].forEach(f=>{
    $(f+'Find').addEventListener('input',()=>renderFacet(f));
    $(f+'List').addEventListener('change',e=>{ const t=e.target; if(!t.dataset.f) return; const set=f==='zoning'?S.exZ:S.exL, i=+t.dataset.i; t.checked?set.add(i):set.delete(i); schedule(100); });
  });
  $('ideas').innerHTML=IDEAS.map(([l],i)=>`<button type="button" class="chip" data-i="${i}">${l}</button>`).join('');
  $('ideas').addEventListener('click',async e=>{ const b=e.target.closest('.chip'); if(!b) return; applyState({...IDEAS[+b.dataset.i][1](), view:S.view, bbox:S.bbox}); await ensureCondo(); await ensureOg(); run(); clearIdea(); b.classList.add('on'); });
  $('toResults').onclick=()=>{ const r=$('results'); const y=r.getBoundingClientRect().top+window.scrollY-($('stickybar').offsetHeight+16); window.scrollTo({top:y,behavior:'smooth'}); };
  $('resetBtn').onclick=()=>{ applyState({...BLANK(), view:S.view}); clearIdea(); run(); };
  $('sortSel').addEventListener('change',async()=>{ S.sort=$('sortSel').value; if(S.sort.startsWith('og')) await ensureOg(); doSort(); save(); renderResults(true); });
  $('vCards').onclick=()=>{ S.view='cards'; save(); renderResults(true); };
  $('vTable').onclick=()=>{ S.view='table'; save(); renderResults(true); };
  $('vMap').onclick=()=>{ S.view='map'; save(); renderResults(true); };
  $('clrArea').onclick=()=>{ S.bbox=null; $('areaRow').hidden=true; clearIdea(); run(); };
  $('mapArea').onclick=()=>{ if(!LMAP) return; const b=LMAP.getBounds(); S.bbox=[+b.getSouth().toFixed(6),+b.getWest().toFixed(6),+b.getNorth().toFixed(6),+b.getEast().toFixed(6)]; $('areaRow').hidden=false; clearIdea(); MAP_NOFIT=true; run(); };
  $('mapFit').onclick=()=>fitResults(true);
  window.addEventListener('hashchange',()=>{ const st=parseHash(); if(st){ applyState(st); ensureCondo().then(ensureOg).then(run); } });
  ['ogMin','ogDist','ogInst'].forEach(id=>$(id).addEventListener('change',async()=>{ clearIdea(); await ensureOg(); run(); }));
  $('clrOg').onclick=()=>{ S.ogf=''; S.og=0; renderOgRow(); clearIdea(); run(); };
  $('showMore').onclick=()=>renderResults(false);
  $('cards').addEventListener('click',e=>{ if(e.target.closest('[data-star]')) return; const c=e.target.closest('.card'); if(c) openDrawer(+c.dataset.id); });
  $('cards').addEventListener('keydown',e=>{ if((e.key==='Enter'||e.key===' ') && e.target.classList.contains('card')){ e.preventDefault(); openDrawer(+e.target.dataset.id); } });
  $('tbody').addEventListener('click',e=>{ if(e.target.closest('[data-star]')) return; const tr=e.target.closest('tr[data-id]'); if(tr) openDrawer(+tr.dataset.id); });
  wireSaved();
  $('thead').addEventListener('click',e=>{ const th=e.target.closest('th'); if(!th||!th.dataset.s) return; S.sort=th.dataset.s; $('sortSel').value=S.sort; doSort(); save(); renderResults(true); });
  let raf=0; $('scroller').addEventListener('scroll',()=>{ if(raf) return; raf=requestAnimationFrame(()=>{ raf=0; renderTable(false); }); });
  window.addEventListener('resize',()=>{ if(S.view==='table') renderTable(false); });
}

async function boot(){
  try{
    META=await (await fetch('data/meta.json')).json(); D=META.dicts;
    MZ=D.mzone||[null]; MZ_UP=MZ.map(e=>e?String(e[0]).toUpperCase():''); LU_T=D.landuse.map(luType); Z_G=D.zoning.map(zGroup);
    $('srcCount').textContent=fmt.format(META.total); $('srcDate').textContent=META.salesThrough||META.built;
    $('srcLine').title=`Downloaded from Miami-Dade County GIS on ${META.built}. Newest recorded sale on the roll: ${META.salesThrough}. ${META.rollYear} values.`;
    $('footData').textContent=`Pulled ${META.built}; ${fmt.format(META.stats.farmland_removed)} farm parcels and ${fmt.format(META.stats.reference_removed)} reference-only folios left out.`;
    D.city.filter(Boolean).forEach(v=>{ const o=document.createElement('option'); o.value=v; o.textContent=v; $('city').appendChild(o); });
    D.cra.filter(Boolean).forEach(v=>{ const o=document.createElement('option'); o.value=v; o.textContent=v; $('cra').appendChild(o); });
    $('mvMin').innerHTML=MONEY_STEPS.map(v=>`<option value="${v}">${v?money(v):'No min'}</option>`).join('');
    $('mvMax').innerHTML=MONEY_STEPS.map(v=>`<option value="${v}">${v?money(v):'No max'}</option>`).join('');
    $('vsMin').innerHTML=VS_STEPS.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
    $('dsMin').innerHTML=DS_STEPS.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
    try{ MAP_COLOR=localStorage.getItem('mdpf.mapColor')==='score'?'score':'type'; }catch(e){} $('mapColor').value=MAP_COLOR;
    if(META.distress){ const d=META.distress; $('dsSrc').textContent=`Built ${META.built}. ${fmt.format(d.parcels_with_signals||0)} parcels have at least one record.`; }
    if(META.vacancy){ const v=META.vacancy; $('vsSrc').textContent=`${fmt.format(v.ge40)} parcels score 40+ (likely), ${fmt.format(v.ge60)} score 60+. Built ${META.built}.`; }
    if(META.owners){ const o=META.owners; $('ogSrc').textContent=`${fmt.format(o.groups)} owners hold 2+ properties; ${fmt.format(o.groups_2plus_distressed_non_institutional)} (excluding banks, government and big institutions) have 2+ parcels with public-record distress signals.`; }
    $('sortSel').innerHTML=SORTS.map(([k,l])=>`<option value="${k}">Sort: ${l}</option>`).join('');
    $('ownerGrid').innerHTML=OWNER_ROWS.map(([k,l])=>`<label for="ow_${k}">${l}</label><select id="ow_${k}"><option value="any">Either</option><option value="yes">Only</option><option value="no">Hide</option></select>`).join('');
    OWNER_ROWS.forEach(([k])=>$('ow_'+k).addEventListener('change',e=>{ S.flags[k]=e.target.value; clearIdea(); schedule(0); }));
    wire();
    let st=parseHash(), fresh=false; if(!st){ try{ st=JSON.parse(localStorage.getItem('mdpf.v2')||'null'); }catch(e){} }
    if(!st){ st=IDEAS[0][1](); fresh=true; }
    applyState(st);
    const ownLoad=loadOwners().catch(()=>null);
    await loadPack(0,'Loading properties…');
    await ensureCondo(); if(S.saved||$('vsMine').checked) await ensureSavedPacks(); await ownLoad; await ensureOg();
    ['results','foot'].forEach(id=>$(id).hidden=false);
    run();
    if(fresh) document.querySelector('#ideas .chip').classList.add('on');
    IDB.prune(META.ver);
    setTimeout(()=>{ loadDetail(0).catch(()=>{}); },1500);
    setTimeout(()=>{ loadGeo(0).catch(()=>{}); },4000);
  }catch(e){ $('loadMsg').textContent='The property data did not load.'; $('loadSub').textContent=String(e.message||e)+'. Reload the page to try again.'; }
}
boot();
})();
