// JS side of tests/unit_orgname.py: runs the app's orgGiven() + orgName() (the code reclassOwners() runs on every pack load) on every pack
// of every county in counties.js, and on a list of test names.   node tests/unit_orgname.js <names.json>  -> JSON on stdout
const fs=require('fs'), zlib=require('zlib'), path=require('path'), vm=require('vm');
const R=path.join(__dirname,'..');
function counties(){   // evaluate counties.js with a stub browser, so every entry (whatever its formatting) is listed
  const ctx={window:{}, location:{search:'',href:'http://x/',pathname:'/'}, localStorage:{getItem:()=>null,setItem:()=>{}}, URLSearchParams,
    document:{readyState:'loading',title:'',addEventListener:()=>{},querySelector:()=>null,getElementById:()=>null,querySelectorAll:()=>[],documentElement:{classList:{add(){},toggle(){}},dataset:{}},body:null},
    console, fetch:()=>Promise.reject(new Error('no fetch'))};
  ctx.window=ctx; vm.createContext(ctx); vm.runInContext(fs.readFileSync(path.join(R,'counties.js'),'utf8'),ctx);
  return ctx.PFCounty.list.map(c=>({id:c.id,dir:c.dataDir})); }
function parse(file){ const u8=zlib.gunzipSync(fs.readFileSync(file)); const hl=u8.readUInt32LE(0), hdr=JSON.parse(u8.subarray(4,4+hl).toString()), st=4+hl, out={n:hdr.n,owner:null,flags:null};
  for(const c of hdr.cols){ const b=u8.subarray(st+c.offset,st+c.offset+c.bytes);
    if(c.name==='owner') out.owner=b.toString().split('\n');
    if(c.name==='flags'){ const T={uint8:Uint8Array,uint16:Uint16Array,uint32:Uint32Array}[c.type]; out.flags=new T(b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength)); } }
  return out; }
const src=fs.readFileSync(path.join(R,'app.js'),'utf8'), a=src.indexOf('const ORG_CAREOF'), b=src.indexOf('function reclassOwners');
if(a<0||b<0) throw new Error('orgName block not found in app.js');
const F=new Function(src.slice(a,b)+'; return {orgName, orgGiven: typeof orgGiven==="function"?orgGiven:()=>new Set()};')();
const names=process.argv[2]?JSON.parse(fs.readFileSync(process.argv[2],'utf8')):[];
const out={};
for(const c of counties()){ const meta=JSON.parse(fs.readFileSync(path.join(R,c.dir,'meta.json'),'utf8')); const packs=[];
  for(const p of meta.packs||[]){ const d=parse(path.join(R,c.dir,p.files[0])); const r={name:p.name,n:d.n,hasOwner:!!d.owner&&d.owner.some(x=>x&&x.trim())};
    if(d.owner&&d.flags){ let g=F.orgGiven(d.owner,d.flags); const fixed=[];
      if(packs.length&&packs[0].givenSet) g=new Set([...packs[0].givenSet,...g]);   // as reclassOwners: the condo pack (loaded after main) adds main's given names
      for(let i=0;i<d.n;i++) if(!(d.flags[i]&(8|16|32)) && F.orgName(d.owner[i],g)) fixed.push(i);
      r.given=[...g].sort(); r.fixed=fixed; r.names=Object.fromEntries(names.map(x=>[x,F.orgName(x,g)])); }
    packs.push(r); if(packs.length===1&&r.given) Object.defineProperty(r,'givenSet',{value:new Set(r.given),enumerable:false}); }
  out[c.id]={dir:c.dir,packs}; }
process.stdout.write(JSON.stringify(out));
