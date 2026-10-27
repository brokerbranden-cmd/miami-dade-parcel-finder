/* County registry + the active county (loaded before every other script).
   Each county ships its own data pack folder (dataDir) and gets its own browser storage namespace, so saved properties,
   outreach, send tags and the last search never mix between counties. Miami-Dade keeps the original paths and keys
   (data/, mdpf.*) so existing builds, links and saved lists keep working.
   Active county: ?county=<id> in the URL, else the last one picked (localStorage pf.county), else miami-dade.
   To add a county: add an entry here, build its packs into data/<id>/ (scripts/counties/<id>/), list its layers. */
(function(){
  "use strict";
  // layers: which data the county has. The UI hides filter groups / ideas that need a missing layer.
  const ALL = ['distress','signals','permits','vacancy','zoning','asm','teardown','commercial','comps','owners','construction','cra','flood','mzoning','equity'];
  const COUNTIES = {
    'miami-dade': { id:'miami-dade', name:'Miami-Dade', state:'FL', dataDir:'data/', storeSuffix:'',
      nameOrder:'first-last',   // owner names on the roll read FIRST MIDDLE LAST (used by the skip trace export / import)
      center:[25.76,-80.30], bounds:[[25.13,-80.88],[25.98,-80.11]],
      layers: ALL.filter(l=>l!=='flood'),
      source:'Miami-Dade County GIS', roll:'Miami-Dade Property Appraiser roll',
      paUrl:f=>`https://apps.miamidadepa.gov/propertysearch/#/?folio=${f}`, auctionHost:'https://www.miamidade.realforeclose.com',
      searchHint:'Search an address, owner name or folio number' },
    'monroe': { id:'monroe', name:'Monroe', state:'FL', dataDir:'data/monroe/', storeSuffix:'.monroe',
      nameOrder:'last-first',   // Monroe roll names read LAST FIRST MIDDLE
      center:[24.75,-81.20], bounds:[[24.45,-82.20],[25.40,-80.25]],
      layers: ['owners','teardown','comps','flood','mzoning','monroe','mscreen','rogo','mtax'],
      area:'the Keys',   // wording for the absentee rule: owner mails from outside this area
      planning:{ who:'Monroe County Planning & Environmental Resources (305-453-8739) or the city planning department', rateY:'Allocation, habitat or flood issues to clear', rateR:'Conservation, wetland, Tier I or public land' },
      source:'Florida statewide cadastral (FDOR roll, Monroe County), county / city zoning + ROGO / Tier, FNAI / NWI / FEMA layers', roll:'Monroe County Property Appraiser roll (via Florida DOR)',
      // qPublic key = the RE number (last 14 digits of the 20-digit roll id, 8-6 with a dash), e.g. 00065780-000206
      paUrl:f=>{ const d=String(f).replace(/\D/g,'').slice(-14); const re=d.length===14?d.slice(0,8)+'-'+d.slice(8):String(f); return `https://qpublic.schneidercorp.com/Application.aspx?AppID=605&LayerID=9946&PageTypeID=4&PageID=7635&KeyValue=${encodeURIComponent(re)}`; },
      auctionHost:'https://monroe.realforeclose.com', searchHint:'Search an address, owner name or RE number' }
    ,'broward': { id:'broward', name:'Broward', state:'FL', dataDir:'data/broward/', storeSuffix:'.broward',
      nameOrder:'last-first',   // Broward roll names read LAST,FIRST & SECOND (comma after the surname; the pack stores them with a space)
      center:[26.15,-80.32], bounds:[[25.95,-80.92],[26.40,-79.98]],
      layers: ['owners','teardown','comps','flood','mzoning','mscreen','broward','mtax','mtdeed'],
      area:'Broward',
      planning:{ who:'the city planning / zoning department (Broward County Planning for unincorporated areas)', rateY:'Flood, small lot or unmapped zoning to clear', rateR:'Public / conservation land, VE flood or non-residential zoning' },
      source:'FDOR roll (Broward County Property Appraiser), BCPA parcels, county Land Use Plan, city zoning layers, FEMA flood', roll:'Broward County Property Appraiser roll (via Florida DOR NAL)',
      // BCPA record page keyed by the 12-digit folio
      paUrl:f=>`https://bcpa.net/RecInfo.asp?URL_Folio=${String(f).replace(/[^0-9A-Za-z]/g,'').toUpperCase()}`,
      auctionHost:'https://www.broward.realforeclose.com', searchHint:'Search an address, owner name or folio number' }
    // Puerto Rico: one data folder per municipio (data/pr/<slug>/, list in data/pr/index.json) so a page load is ~5k-100k parcels, not the island's 1.44M.
    // Public PR data has parcels + zoning only (no owner / value / address: CRIM keeps those behind a token), so most Florida layers are listed as not public (PR_GAPS).
    ,'pr': { id:'pr', name:'Puerto Rico', label:'Puerto Rico', state:'PR', dataDir:'data/pr/san-juan/', storeSuffix:'.pr.san-juan', muni:'san-juan',
      nameOrder:'first-last',
      center:[18.22,-66.45], bounds:[[17.85,-67.95],[18.55,-65.20]],
      layers: ['mzoning','mscreen','pr'],
      area:'Puerto Rico',
      planning:{ who:'the Junta de Planificacion (787-723-6200) or OGPe permits office', rateY:'Overlay (coast, hazard, historic) to clear', rateR:'Conservation / preservation or public land' },
      source:'CRIM parcelario (feb 2025) via Junta de Planificacion GIS, Junta de Planificacion calificacion vigente', roll:'CRIM parcel map (owner and value data are not public)',
      paUrl:f=>`https://catastro.crimpr.net/cdprpc/`, auctionHost:'', searchHint:'Search a catastro number (e.g. 060-000-001-01)' }
    // 'palm-beach': {...}   (add when its packs exist)
  };
  const DEF = 'miami-dade';
  let id = null;
  try{ const q = new URLSearchParams(location.search).get('county'); if(q && COUNTIES[q]) id = q; }catch(e){}
  if(!id){ try{ const s = localStorage.getItem('pf.county'); if(s && COUNTIES[s]) id = s; }catch(e){} }
  if(!id) id = DEF;
  try{ localStorage.setItem('pf.county', id); }catch(e){}
  const cfg = COUNTIES[id];
  // Puerto Rico municipio: ?muni=<slug>, else the last one picked (localStorage pf.pr.muni), else San Juan. Each municipio is its own data folder + storage namespace.
  if(id === 'pr'){ let m = null; try{ m = new URLSearchParams(location.search).get('muni') || localStorage.getItem('pf.pr.muni'); }catch(e){}
    m = /^[a-z0-9-]{2,40}$/.test(m||'') ? m : 'san-juan'; try{ localStorage.setItem('pf.pr.muni', m); }catch(e){}
    cfg.muni = m; cfg.dataDir = 'data/pr/' + m + '/'; cfg.storeSuffix = '.pr.' + m; }
  const has = l => cfg.layers.includes(l);
  // per-county storage key: Miami-Dade keeps the original key names
  const key = k => k + cfg.storeSuffix;
  // the URL for a county: keeps ?county= in the address bar (so copied links carry it), drops the hash (filters are county-specific)
  const urlFor = c => { const u = new URL(location.href); u.hash = ''; u.searchParams.set('county', c); u.searchParams.delete('folio'); if(c !== 'pr') u.searchParams.delete('muni'); else if(c === id) u.searchParams.set('muni', cfg.muni); return u.toString(); };
  function sw(c){ if(!COUNTIES[c] || c === id) return; try{ localStorage.setItem('pf.county', c); }catch(e){} location.assign(urlFor(c)); }
  // make sure the current URL names the county, so "Copy link" / shared links reopen in it
  try{ const u = new URL(location.href); const wantM = id === 'pr' ? cfg.muni : null; if(u.searchParams.get('county') !== id || (wantM && u.searchParams.get('muni') !== wantM)){ u.searchParams.set('county', id); if(wantM) u.searchParams.set('muni', wantM); history.replaceState(history.state, '', u.toString()); } }catch(e){}
  // hide UI that needs a layer this county lacks (runs on DOMContentLoaded and again by app.js after it builds dynamic UI)
  const NEED = { '.grp.distress':'distress', '.grp.permits':'permits', '.grp.vacancy':'vacancy', '#asmGrp':'asm', '#tdGrp':'teardown',
    '[data-need]':null };
  function applyLayers(root){
    root = root || document;
    for(const [sel, l] of Object.entries(NEED)){
      root.querySelectorAll(sel).forEach(n => { const need = l || n.dataset.need; if(!need) return;
        const ok = need.split(/\s+/).every(has); n.hidden = !ok; if(!ok) n.setAttribute('data-county-hidden',''); });
    }
    document.documentElement.dataset.county = id;
  }
  function header(){
    const h1 = document.querySelector('header.top h1'); if(h1 && !document.getElementById('countySel')){
      h1.firstChild.nodeValue = cfg.name + ' ';
      const s = document.createElement('select'); s.id = 'countySel'; s.className = 'countysel'; s.setAttribute('aria-label', 'County');
      s.innerHTML = Object.values(COUNTIES).map(c => `<option value="${c.id}" ${c.id===id?'selected':''}>${c.label || c.name + ' County'}</option>`).join('');
      s.addEventListener('change', () => sw(s.value));
      h1.parentNode.insertBefore(s, h1.nextSibling);
      if(id === 'pr') muniPicker(s);
    }
    const q = document.getElementById('q'); if(q) q.placeholder = cfg.searchHint;
    document.title = document.title.replace(/Miami-Dade/, cfg.name);
    applyLayers();
  }
  // municipio picker (Puerto Rico only), filled from data/pr/index.json
  function muniPicker(after){
    const m = document.createElement('select'); m.id = 'muniSel'; m.className = 'countysel'; m.setAttribute('aria-label', 'Municipio');
    m.innerHTML = `<option value="${cfg.muni}" selected>${cfg.muni}</option>`; after.parentNode.insertBefore(m, after.nextSibling);
    m.addEventListener('change', () => { if(m.value === cfg.muni) return; try{ localStorage.setItem('pf.pr.muni', m.value); }catch(e){}
      const u = new URL(location.href); u.hash = ''; u.searchParams.set('county', 'pr'); u.searchParams.set('muni', m.value); u.searchParams.delete('folio'); location.assign(u.toString()); });
    fetch('data/pr/index.json').then(r => r.json()).then(ix => { window.PFPRIndex = ix;
      m.innerHTML = ix.municipios.map(r => `<option value="${r.slug}" ${r.slug===cfg.muni?'selected':''}>${r.name} (${r.n.toLocaleString()})</option>`).join(''); }).catch(() => {});
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', header); else header();
  window.PFCounty = { id, cfg, list: Object.values(COUNTIES), has, key, dp: cfg.dataDir, switchTo: sw, urlFor, applyLayers, DEFAULT: DEF };
})();
