/* Drive for dollars: phone-first full-screen map around your GPS position.
   Uses the main pack + geo pack already loaded by app.js (window.PF); saved items go through PFSaved (saved.js).
   Location stays on the device: it is only used to center the map and find the nearest parcel. */
(function(){
  "use strict";
  const $ = id => document.getElementById(id);
  const PREF = 'mdpf.drive', HASH0 = location.hash;   // the app rewrites the hash once it runs; decide on the URL as opened                 // 'off' after you leave drive mode, 'on' after you pick it
  let PF = null, M = null, layer = null, me = null, acc = null, follow = true, watchId = null, last = null, sel = -1, open = false, grid = null, booting = null;
  const want = () => { const q = new URLSearchParams(location.search).get('drive'); if(q === '1') return true; if(q === '0') return false;
    let pref = null, sess = null; try{ pref = localStorage.getItem(PREF); sess = sessionStorage.getItem(PREF); }catch(e){}
    if(sess === 'open') return true;     // reload while driving stays in drive mode
    return pref === 'on' || (pref !== 'off' && !HASH0 && matchMedia('(max-width: 600px)').matches); };

  /* spatial grid over the main pack (cell ~ 0.002 deg = ~200 m) for fast "what's near here" */
  const G0LA = 24.4, G0LO = -81.0, CELL = 0.002, GW = 900, GH = 900;
  function buildGrid(p){
    const g = p.geo, n = p.n, cell = new Int32Array(n), cnt = new Uint32Array(GW * GH + 1);
    for(let i = 0; i < n; i++){ const la = g.lat[i], lo = g.lon[i]; if(!(la > 20)){ cell[i] = -1; continue; }
      const cx = Math.floor((lo - G0LO) / CELL), cy = Math.floor((la - G0LA) / CELL);
      if(cx < 0 || cy < 0 || cx >= GW || cy >= GH){ cell[i] = -1; continue; } cell[i] = cy * GW + cx; cnt[cell[i] + 1]++; }
    for(let k = 1; k <= GW * GH; k++) cnt[k] += cnt[k - 1];
    const start = cnt.slice(), items = new Uint32Array(n), pos = cnt.slice(0, GW * GH);
    for(let i = 0; i < n; i++) if(cell[i] >= 0) items[pos[cell[i]]++] = i;
    return { start, items };
  }
  function each(la0, lo0, la1, lo1, fn){
    const x0 = Math.max(0, Math.floor((lo0 - G0LO) / CELL)), x1 = Math.min(GW - 1, Math.floor((lo1 - G0LO) / CELL));
    const y0 = Math.max(0, Math.floor((la0 - G0LA) / CELL)), y1 = Math.min(GH - 1, Math.floor((la1 - G0LA) / CELL));
    for(let y = y0; y <= y1; y++) for(let x = x0; x <= x1; x++){ const k = y * GW + x; for(let j = grid.start[k]; j < grid.start[k + 1]; j++) fn(grid.items[j]); }
  }
  const metres = (la1, lo1, la2, lo2) => { const r = Math.PI / 180, x = (lo2 - lo1) * r * Math.cos((la1 + la2) * r / 2), y = (la2 - la1) * r; return Math.sqrt(x * x + y * y) * 6371000; };
  function nearestTo(la, lo, maxM){
    const g = PF.PACKS[0].geo, d = maxM / 111000 * 1.3; let best = -1, bd = maxM;
    each(la - d, lo - d, la + d, lo + d, i => { const m = metres(la, lo, g.lat[i], g.lon[i]); if(m < bd){ bd = m; best = i; } });
    return [best, bd];
  }
  const tone = v => v >= 50 ? '--s4' : v >= 35 ? '--s3' : v >= 20 ? '--s2' : v > 0 ? '--s1' : '--s0';

  /* canvas dots for parcels in view (zoom 15+) */
  function makeLayer(){
    return L.Layer.extend({
      onAdd(map){ this._map = map; this._c = L.DomUtil.create('canvas', 'dotlayer'); map.getPanes().overlayPane.appendChild(this._c); map.on('moveend resize zoomend', this.redraw, this); this.redraw(); },
      onRemove(map){ L.DomUtil.remove(this._c); map.off('moveend resize zoomend', this.redraw, this); },
      redraw(){ if(this._map) draw(this); return this; }
    });
  }
  let shown = 0;
  function draw(ly){
    const map = ly._map, c = ly._c, size = map.getSize(), dpr = Math.min(2, devicePixelRatio || 1);
    L.DomUtil.setPosition(c, map.containerPointToLayerPoint([0, 0]));
    c.width = Math.round(size.x * dpr); c.height = Math.round(size.y * dpr); c.style.width = size.x + 'px'; c.style.height = size.y + 'px';
    const ctx = c.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, size.x, size.y);
    const z = map.getZoom(); shown = 0;
    if(z < 15 || !grid){ $('dHint').textContent = grid ? 'Zoom in to see parcels' : 'Loading parcels…'; $('dHint').hidden = false; return; }
    const b = map.getBounds(), p = PF.PACKS[0], g = p.geo, cs = getComputedStyle(document.documentElement), col = {}, r = z >= 18 ? 9 : z >= 17 ? 7 : z >= 16 ? 6 : 4.5;
    for(const t of ['--s0', '--s1', '--s2', '--s3', '--s4']) col[t] = cs.getPropertyValue(t).trim();
    const brand = cs.getPropertyValue('--brand').trim() || '#FC4C02', surf = cs.getPropertyValue('--surface').trim() || '#fff', saved = [];
    ctx.lineWidth = 1.2; ctx.strokeStyle = surf;
    each(b.getSouth(), b.getWest(), b.getNorth(), b.getEast(), i => {
      const pt = map.latLngToContainerPoint([g.lat[i], g.lon[i]]); shown++;
      ctx.beginPath(); ctx.arc(pt.x, pt.y, r, 0, 6.2832); ctx.fillStyle = col[tone(p.c.dscore[i])]; ctx.fill(); ctx.stroke();
      if(PF.SV.has(PF.getStr(p, 'folio', i))) saved.push(pt);
    });
    ctx.lineWidth = 3; ctx.strokeStyle = brand; for(const pt of saved){ ctx.beginPath(); ctx.arc(pt.x, pt.y, r + 4, 0, 6.2832); ctx.stroke(); }
    if(sel >= 0){ const pt = map.latLngToContainerPoint([g.lat[sel], g.lon[sel]]); ctx.lineWidth = 4; ctx.strokeStyle = cs.getPropertyValue('--brand-2').trim() || '#00B2BD'; ctx.beginPath(); ctx.arc(pt.x, pt.y, r + 8, 0, 6.2832); ctx.stroke(); }
    $('dHint').hidden = shown > 0; if(!shown) $('dHint').textContent = 'No parcels here';
  }
  const redraw = () => { if(layer) layer.redraw(); };

  /* bottom sheet */
  function sheet(i, extra){
    const p = PF.PACKS[0], c = p.c, id = i, folio = PF.getStr(p, 'folio', i), sv = PF.SV.get(folio), esc = PF.esc;
    const addr = PF.getStr(p, 'addr', i) || 'No street address', owner = PF.getStr(p, 'owner', i).split(' | ')[0];
    const t = PF.TYPE_LABEL[PF.LU_T[c.landuse[i]]], mv = c.mkt[i], yb = c.yb[i], g = p.geo;
    const held = c.sd1[i] ? Math.max(0, Math.floor((PF.today - c.sd1[i]) / 365.25)) + ' yrs' : 'no sale on record';
    sel = i; redraw();
    $('dSheet').innerHTML = `<div class="dgrab" aria-hidden="true"></div>
      <div class="dsh-top"><div class="dsh-addr"><h2>${esc(addr)}</h2><div class="dsh-sub">${esc(PF.D.city[c.city[i]])} · ${t}${yb ? ' · built ' + yb : ''} · ${mv ? PF.money(mv) : '–'}</div></div>
        <button type="button" class="dbtn dclose" id="dSheetClose" aria-label="Close">✕</button></div>
      ${extra ? `<div class="dsh-note">${esc(extra)}</div>` : ''}
      <div class="dsh-owner"><span>Owner</span><b>${esc(owner || '–')}</b><small>owned ${held}</small></div>
      <div class="dsh-score">${c.dscore[i] ? PF.scoreBadge(c.dscore[i], true) + '<span>distress score</span>' : '<span class="muted">No distress records</span>'}</div>
      <div class="ob dsh-sigs">${PF.vacBadge(c, i)}${PF.sigBadges(c.dsig[i])}</div>
      <button type="button" class="dbtn dsave ${sv ? 'on' : ''}" id="dSave" data-folio="${folio}" aria-pressed="${!!sv}">${sv ? '★ Saved' : '☆ Save'}</button>
      ${sv ? `<div class="dsh-form">
        <label for="dStatus">Status</label><select id="dStatus">${PF.SV.STATUSES.map(s => `<option ${s === sv.status ? 'selected' : ''}>${s}</option>`).join('')}</select>
        <label class="dchk"><input type="checkbox" id="dVacant" ${sv.vacant ? 'checked' : ''}> Looks vacant / damaged</label>
        <label for="dNote">Quick note</label><textarea id="dNote" rows="2" placeholder="Tall grass, boarded window, for-rent sign…" maxlength="5000">${esc(sv.note)}</textarea>
        <span class="dsh-msg" id="dMsg">Saves on this phone automatically.</span></div>` : ''}
      <div class="dsh-links"><button type="button" class="dbtn" id="dDetails">Full details</button>
        <a class="dbtn" href="https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${g.lat[i].toFixed(6)},${g.lon[i].toFixed(6)}" target="_blank" rel="noopener">Street View ↗</a></div>`;
    $('dSheet').hidden = false; $('dSheet').dataset.i = i; $('drive').classList.add('has-sheet');
  }
  function closeSheet(){ $('dSheet').hidden = true; $('dSheet').innerHTML = ''; sel = -1; $('drive').classList.remove('has-sheet'); redraw(); }

  /* GPS */
  function gpsStatus(t, bad){ const el = $('dGps'); el.textContent = t; el.classList.toggle('bad', !!bad); }
  function startGps(){
    if(!navigator.geolocation){ gpsStatus('No GPS on this device', true); return; }
    if(watchId != null) return;
    gpsStatus('Finding you…');
    watchId = navigator.geolocation.watchPosition(pos => {
      const { latitude: la, longitude: lo, accuracy: a } = pos.coords; const first = !last; last = { la, lo, a: a || 0, t: Date.now() };
      if(!me){ me = L.circleMarker([la, lo], { radius: 9, color: '#fff', weight: 3, fillColor: '#1A73E8', fillOpacity: 1, interactive: false }).addTo(M); acc = L.circle([la, lo], { radius: a || 0, color: '#1A73E8', weight: 1, fillOpacity: .08, interactive: false }).addTo(M); }
      else { me.setLatLng([la, lo]); acc.setLatLng([la, lo]).setRadius(a || 0); }
      gpsStatus('GPS ±' + Math.round(a || 0) + ' m');
      if(follow) M.setView([la, lo], first ? 18 : M.getZoom(), { animate: !first });
    }, err => { gpsStatus(err.code === 1 ? 'Location blocked: allow it in settings' : 'No GPS fix yet', true); if(err.code === 1){ navigator.geolocation.clearWatch(watchId); watchId = null; } },
    { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 });
  }
  function stopGps(){ if(watchId != null){ navigator.geolocation.clearWatch(watchId); watchId = null; } }

  function saveHere(){
    if(!last){ PF.toast('Waiting for GPS… (allow location)'); startGps(); return; }
    const [i, m] = nearestTo(last.la, last.lo, 120);
    if(i < 0){ PF.toast('No parcel within 120 m of you'); return; }
    const p = PF.PACKS[0], folio = PF.getStr(p, 'folio', i);
    if(!PF.SV.has(folio)) PF.SV.add(folio, PF.savedInfo(i));
    follow = false; M.setView([p.geo.lat[i], p.geo.lon[i]], Math.max(M.getZoom(), 18));
    sheet(i, `Saved the parcel nearest to you (~${Math.round(m)} m, GPS ±${Math.round(last.a)} m). Check it's the right one.`);
    PF.toast(PF.SV.error || 'Saved ' + (PF.getStr(p, 'addr', i) || 'parcel'));
    const n = $('dNote'); if(n) n.focus({ preventScroll: true });
  }

  async function init(){
    if(booting) return booting;
    booting = (async () => {
      await PF.loadLeaflet(); await PF.loadGeo(0);
      M = L.map('dmap', { zoomControl: false, minZoom: 10, maxZoom: 20, tap: true }).setView([25.774, -80.194], 17);
      const esri = (svc, o = {}) => L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/${svc}/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 20, maxNativeZoom: svc.includes('Imagery') ? 19 : 16, crossOrigin: true, attribution: 'Esri, HERE, Garmin, © OpenStreetMap', ...o });
      const streets = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 20, maxNativeZoom: 19, crossOrigin: true, attribution: '© OpenStreetMap contributors' });
      const sat = L.layerGroup([esri('World_Imagery'), esri('Reference/World_Transportation', { opacity: .7 })]);
      streets.addTo(M); L.control.layers({ 'Streets': streets, 'Satellite': sat }, null, { position: 'topright' }).addTo(M);
      L.control.zoom({ position: 'bottomright' }).addTo(M);
      grid = buildGrid(PF.PACKS[0]);
      const Ly = makeLayer(); layer = new Ly(); layer.addTo(M);
      M.on('dragstart', () => { follow = false; $('dLocate').classList.remove('on'); });
      M.on('click', e => { const p = PF.PACKS[0], g = p.geo, z = M.getZoom(); if(z < 15) return;
        const ll = e.latlng, px = z >= 18 ? 30 : 24, mpp = 156543 * Math.cos(ll.lat * Math.PI / 180) / Math.pow(2, z);
        const [i] = nearestTo(ll.lat, ll.lng, px * mpp); if(i >= 0) sheet(i); else closeSheet(); });
    })();
    return booting;
  }
  async function enter(byUser){
    if(open) return; open = true;
    try{ if(byUser) localStorage.setItem(PREF, 'on'); sessionStorage.setItem(PREF, 'open'); }catch(e){}
    document.body.classList.add('driving'); $('drive').hidden = false; $('driveBtn').setAttribute('aria-pressed', 'true');
    try{ await init(); }catch(e){ PF.toast('Map did not load: ' + (e.message || e)); }
    M.invalidateSize(); follow = true; $('dLocate').classList.add('on'); startGps(); redraw();
  }
  function exit(){
    open = false; stopGps(); closeSheet(); try{ localStorage.setItem(PREF, 'off'); sessionStorage.removeItem(PREF); }catch(e){}
    document.body.classList.remove('driving'); $('drive').hidden = true; $('driveBtn').setAttribute('aria-pressed', 'false');
    if(new URLSearchParams(location.search).has('drive')) history.replaceState(null, '', location.pathname + location.hash);
  }

  function wire(){
    $('driveBtn').onclick = () => open ? exit() : enter(true);
    $('dExit').onclick = exit;
    $('dLocate').onclick = () => { follow = true; $('dLocate').classList.add('on'); if(last) M.setView([last.la, last.lo], Math.max(M.getZoom(), 17)); else startGps(); };
    $('dHere').onclick = saveHere;
    const sh = $('dSheet');
    sh.addEventListener('click', e => {
      const t = e.target.closest('button'); if(!t) return; const i = +sh.dataset.i, p = PF.PACKS[0];
      if(t.id === 'dSheetClose') closeSheet();
      else if(t.id === 'dSave'){ const f = t.dataset.folio, on = PF.SV.toggle(f, PF.savedInfo(i)); PF.toast(PF.SV.error || (on ? 'Saved' : 'Removed from saved')); sheet(i); if(on){ const n = $('dNote'); if(n) n.focus({ preventScroll: true }); } }
      else if(t.id === 'dDetails') PF.openDrawer(i);
    });
    sh.addEventListener('change', e => { const f = $('dSave') && $('dSave').dataset.folio; if(!f) return;
      if(e.target.id === 'dStatus'){ PF.SV.update(f, { status: e.target.value }); PF.toast('Status: ' + e.target.value); }
      if(e.target.id === 'dVacant'){ PF.SV.update(f, { vacant: e.target.checked }); PF.toast(e.target.checked ? 'Marked: looks vacant / damaged' : 'Vacant mark removed'); } });
    let nt = null; sh.addEventListener('input', e => { if(e.target.id !== 'dNote') return; const f = $('dSave').dataset.folio, v = e.target.value; clearTimeout(nt); $('dMsg').textContent = 'Saving…';
      nt = setTimeout(() => { PF.SV.update(f, { note: v }); const m = $('dMsg'); if(m) m.textContent = PF.SV.error || 'Saved on this phone.'; }, 400); });
    PF.SV.onChange(() => redraw());
    document.addEventListener('visibilitychange', () => { if(!open) return; document.hidden ? stopGps() : startGps(); });
  }
  function ready(){ PF = window.PF; wire(); if(want()) enter(false); }
  if(window.PF_READY) ready(); else document.addEventListener('pf:ready', ready, { once: true });
  /* test hook: screen point of the parcel nearest the map center */
  function nearestPoint(){ const c = M.getCenter(), [i] = nearestTo(c.lat, c.lng, 200); if(i < 0) return null; const g = PF.PACKS[0].geo, pt = M.latLngToContainerPoint([g.lat[i], g.lon[i]]), r = $('dmap').getBoundingClientRect(); return { x: pt.x + r.left, y: pt.y + r.top, i }; }
  window.PFDrive = { enter: () => enter(true), exit, saveHere, nearestPoint, get open(){ return open; } };
})();
