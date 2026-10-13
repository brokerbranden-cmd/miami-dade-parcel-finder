/* Simplified layout (2026-10-12): results-first layout with a filter sidebar (desktop) / bottom sheet (phone), collapsible
   filter groups with active-filter badges, 8 presets + "More ideas", compact cards (3 badges + "+N", team buttons behind ⋯),
   drawer with collapsible sections. Pure presentation: every control is the same element app.js wires up.
   Prefs in localStorage 'pf.ui.v1': {open:{group:bool}, more:bool, dsec:{section:bool}, detail:bool, legacy:bool}.
   legacy:true (used by the older e2e suites) opens every group / section and keeps the phone filters inline. */
(function(){
  const KEY='pf.ui.v1', $=id=>document.getElementById(id);
  let P={}; try{ P=JSON.parse(localStorage.getItem(KEY)||'{}')||{}; }catch(e){}
  P.open=P.open||{}; P.dsec=P.dsec||{};
  const saveP=()=>{ try{ localStorage.setItem(KEY,JSON.stringify(P)); }catch(e){} };
  const B=document.body; B.classList.add('simple'); if(P.legacy) B.classList.add('legacy'); if(P.detail) B.classList.add('detail');
  const phone=()=>matchMedia('(max-width:899px)').matches;
  const DEFAULT_OPEN=new Set(['search','start with an idea','distress signals',"what's on the property",'market value','lot size']);

  /* ---- filter groups ---- */
  const gkey=g=>{ const h=g.querySelector(':scope>.grp-h h2'); return h?h.textContent.trim().toLowerCase():''; };
  function activeIn(g){ const skip=x=>x.closest('#tdRules,#moreIdeas,#ideasMore,.sendgrp-x');
    let n=[...g.querySelectorAll('.chip.on:not([data-i]):not([data-v="0"]),.seg button.on:not([data-k="all"]):not([data-tier="any"])')].filter(x=>!skip(x)).length;
    g.querySelectorAll('input[type=checkbox]').forEach(x=>{ if(skip(x)) return; if(x.id==='hideGov' ? !x.checked : x.checked) n++; });
    g.querySelectorAll('input[type=text],input[type=search],input:not([type])').forEach(x=>{ if(!skip(x) && x.value.trim() && !/^listName/.test(x.id)) n++; });
    g.querySelectorAll('select').forEach(x=>{ if(!skip(x) && x.selectedIndex>0) n++; });
    if(g.id==='tdGrp' && location.hash.includes('tdr=')) n++;
    return n; }
  let groups=[];
  function setupGroups(){
    const panel=$('panel'); if(!panel) return;
    const sr=panel.querySelector('.searchrow'); if(sr && !sr.closest('.grp')){ const w=document.createElement('div'); w.className='grp searchgrp'; w.innerHTML='<div class="grp-h"><h2>Search</h2></div>'; sr.before(w); w.appendChild(sr); const ar=$('areaRow'); if(ar) w.appendChild(ar); }
    groups=[...panel.querySelectorAll('.grp')].filter(g=>g.querySelector(':scope>.grp-h h2') && !g.closest('#moreBox'));
    groups.forEach(g=>{ const k=gkey(g), h=g.querySelector(':scope>.grp-h'), h2=h.querySelector('h2');
      g.classList.add('cgrp'); g.dataset.g=k;
      const t=document.createElement('button'); t.type='button'; t.className='gtog'; t.setAttribute('aria-expanded','true');
      t.innerHTML=`<span class="gname"></span><span class="gact" hidden></span><span class="gchev" aria-hidden="true"></span>`; t.querySelector('.gname').textContent=h2.textContent;
      h2.textContent=''; h2.appendChild(t);
      const open=P.legacy || (k in P.open ? P.open[k] : DEFAULT_OPEN.has(k)); setOpen(g,open);
      t.addEventListener('click',()=>{ const o=g.classList.contains('closed'); setOpen(g,o); P.open[k]=o; saveP(); }); });
    const mb=$('moreBox'); if(mb && P.legacy) mb.open=true;
  }
  function setOpen(g,o){ g.classList.toggle('closed',!o); const t=g.querySelector('.gtog'); if(t) t.setAttribute('aria-expanded',String(o)); }
  let first=true;
  function refreshBadges(){ let tot=0; groups.forEach(g=>{ const n=activeIn(g), b=g.querySelector('.gact'); tot+=n; if(!b) return; b.hidden=!n; b.textContent=n; if(n && first && g.classList.contains('closed')) setOpen(g,true); });
    first=false; const fb=$('filtersBtn'); if(fb){ const on=$('onCount'); const m=on&&!on.hidden?parseInt(on.textContent,10)||0:0; fb.querySelector('.n').textContent=m?String(m):''; fb.querySelector('.n').hidden=!m; } }
  let rt=0; const sched=()=>{ clearTimeout(rt); rt=setTimeout(refreshBadges,120); };

  /* ---- presets: 8 + More ideas (grouped) ---- */
  const TOP=[/hottest/i,/pre-foreclosure/i,/tax deeds/i,/likely vacant/i,/strong teardowns/i,/^🧩 assemblages$/i,/vacant infill/i,/estates and heirs/i];
  const CATS=[['Distress',/unsafe|motivated|foreclos|tax|hottest|vacant \/ neglected/i],['Land, teardown & zoning',/teardown|lot|multifamily land|split|assemblage|zone minimum|small multifamily|infill/i],['Owners',/owner|landlord|estate|far away/i]];
  function setupIdeas(){
    const ideas=$('ideas'); if(!ideas || ideas.dataset.simple) return; const chips=[...ideas.querySelectorAll('.chip[data-i]')]; if(!chips.length) return; ideas.dataset.simple='1';
    const top=[], rest=[]; chips.forEach(c=>{ const t=c.textContent.trim(); (TOP.some(r=>r.test(t))&&top.length<8?top:rest).push(c); });
    const more=document.createElement('div'); more.className='ideas-more'; more.id='ideasMore';
    const cats=CATS.map(([l])=>{ const d=document.createElement('div'); d.className='icat'; d.innerHTML=`<div class="icat-h"></div><div class="chips"></div>`; d.querySelector('.icat-h').textContent=l; return d; });
    rest.forEach(c=>{ const t=c.textContent.trim(); let j=CATS.findIndex(([,r])=>r.test(t)); if(j<0) j=0; cats[j].querySelector('.chips').appendChild(c); });
    cats.forEach(d=>{ if(d.querySelector('.chip')) more.appendChild(d); });
    top.forEach(c=>ideas.appendChild(c));
    const b=document.createElement('button'); b.type='button'; b.className='chip morechip'; b.id='moreIdeas'; ideas.appendChild(b); ideas.appendChild(more);
    const upd=()=>{ const o=!!P.more||!!P.legacy; more.hidden=!o; b.setAttribute('aria-expanded',String(o)); b.textContent=o?'Fewer ideas ▴':`More ideas (${rest.length}) ▾`; };
    b.addEventListener('click',e=>{ e.stopPropagation(); P.more=!P.more; saveP(); upd(); }); upd();
  }

  /* ---- phone: filters in a bottom sheet ---- */
  function setupSheet(){
    const act=document.querySelector('#stickybar .sb-act'); if(!act || $('filtersBtn')) return;
    const fb=document.createElement('button'); fb.type='button'; fb.className='btn filtersbtn'; fb.id='filtersBtn'; fb.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4"/></svg>Filters <span class="n" hidden></span>';
    act.insertBefore(fb,$('toResults'));
    fb.addEventListener('click',()=>B.classList.add('sheet-open'));
    const done=document.createElement('div'); done.className='sheetbar'; done.innerHTML='<button type="button" class="btn" id="sheetClose">Close</button><button type="button" class="btn primary" id="sheetDone">Show results</button>';
    $('panel').prepend(done);
    const close=()=>{ B.classList.remove('sheet-open'); };
    $('sheetClose').onclick=close; $('sheetDone').onclick=()=>{ close(); const r=$('results'); if(r) window.scrollTo({top:r.getBoundingClientRect().top+scrollY-($('stickybar').offsetHeight+8)}); };
    const upd=()=>{ $('sheetDone').textContent='Show '+($('liveCount').textContent||'')+' results'; }; new MutationObserver(upd).observe($('liveCount'),{childList:true,characterData:true,subtree:true}); upd();
    // picking a preset on the phone closes the sheet so the results show
    $('ideas').addEventListener('click',e=>{ if(phone() && e.target.closest('.chip[data-i]') && !P.legacy) setTimeout(close,250); });
    document.addEventListener('keydown',e=>{ if(e.key==='Escape') close(); });
  }

  /* ---- compact cards ---- */
  function compactCards(root){
    root.querySelectorAll('.card:not([data-cx])').forEach(c=>{ c.dataset.cx='1';
      const ob=c.querySelector('.ob'); if(ob){ const k=ob.children.length; if(k>3){ const b=document.createElement('button'); b.type='button'; b.className='obmore'; b.textContent='+'+(k-3); b.title='Show all '+k+' labels'; ob.appendChild(b); } }
      const tr=c.querySelector('.tags .tr'); if(tr){ const m=document.createElement('button'); m.type='button'; m.className='cmore'; m.title='More actions: Call center, Door knock'; m.setAttribute('aria-label','More actions'); m.textContent='⋯'; tr.appendChild(m); }
    }); }
  document.addEventListener('click',e=>{ const ob=e.target.closest('.obmore'); if(ob){ e.stopPropagation(); e.preventDefault(); const c=ob.closest('.card'); c.classList.add('ob-all'); ob.remove(); return; }
    const m=e.target.closest('.cmore'); if(m){ e.stopPropagation(); e.preventDefault(); const c=m.closest('.card'); const o=!c.classList.contains('menu-open'); document.querySelectorAll('.card.menu-open').forEach(x=>x.classList.remove('menu-open')); c.classList.toggle('menu-open',o); return; }
    if(!e.target.closest('.sendline')) document.querySelectorAll('.card.menu-open').forEach(x=>x.classList.remove('menu-open')); },true);

  /* ---- drawer: overview first, other sections collapsible ---- */
  const DOPEN=new Set(['the property']);
  function sectionDrawer(d){
    if(d.dataset.sx) return; d.dataset.sx='1';
    const kids=[...d.children]; let sec=null, secs=[];
    kids.forEach(el=>{ if(el.tagName==='H3'){ sec=document.createElement('section'); sec.className='dsec'; el.before(sec); secs.push(sec); sec.appendChild(el); return; } if(sec && !el.matches('#closeD,.back')) sec.appendChild(el); });
    const key=s=>s.querySelector('h3').textContent.replace(/\d+\s*$/,'').trim().toLowerCase().replace(/^\d{4} /,'');
    // core facts right under the overview
    const firstSec=secs[0]; secs.filter(s=>/^(the property|\d{4} values|values)$/.test(key(s))).forEach(s=>{ if(firstSec && s!==firstSec) firstSec.before(s); });
    secs.forEach(s=>{ const k=key(s), h=s.querySelector('h3'); const t=document.createElement('button'); t.type='button'; t.className='dtog'; t.innerHTML=h.innerHTML; h.innerHTML=''; h.appendChild(t);
      const open=P.legacy||P.detail||(k in P.dsec?P.dsec[k]:DOPEN.has(k)||/values$/.test(k)); s.classList.toggle('closed',!open); t.setAttribute('aria-expanded',String(open));
      t.addEventListener('click',()=>{ const o=s.classList.contains('closed'); s.classList.toggle('closed',!o); t.setAttribute('aria-expanded',String(o)); P.dsec[k]=o; saveP(); }); });
  }

  /* ---- detail toggle in the results bar ---- */
  function setupDetail(){
    const bar=$('vMap'); if(!bar || $('detailBtn')) return; const seg=bar.closest('.seg');
    const b=document.createElement('button'); b.type='button'; b.className='btn'; b.id='detailBtn';
    const upd=()=>{ b.textContent=B.classList.contains('detail')?'Compact cards':'Detailed cards'; b.setAttribute('aria-pressed',String(B.classList.contains('detail'))); };
    b.onclick=()=>{ B.classList.toggle('detail'); P.detail=B.classList.contains('detail'); saveP(); upd(); }; upd(); seg.after(b);
  }

  function init(){
    setupGroups(); setupIdeas(); setupSheet(); setupDetail(); refreshBadges();
    const panel=$('panel'); panel.addEventListener('input',sched); panel.addEventListener('change',sched); panel.addEventListener('click',()=>setTimeout(sched,50));
    new MutationObserver(sched).observe(panel,{subtree:true,attributes:true,attributeFilter:['class']});
    window.addEventListener('hashchange',()=>{ first=true; sched(); });
    $('resetBtn').addEventListener('click',()=>setTimeout(sched,200));
    const cards=$('cards'); compactCards(cards); new MutationObserver(()=>compactCards(cards)).observe(cards,{childList:true});
    const dh=$('drawerHost'); new MutationObserver(()=>{ const d=dh.querySelector('aside.drawer'); if(d) sectionDrawer(d); }).observe(dh,{childList:true});
    window.PFUI={prefs:P, setOpen:(k,o)=>{ const g=groups.find(x=>x.dataset.g===k.toLowerCase()); if(g) setOpen(g,o); }, refresh:refreshBadges};
  }
  if(window.PF_READY) init(); else document.addEventListener('pf:ready',init,{once:true});
})();
