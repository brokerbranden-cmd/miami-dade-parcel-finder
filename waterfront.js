/* Waterfront / oceanfront layer (every county; data/<county>/water.json.gz from scripts/build_waterfront.py).
   Parcel polygon vs mapped water (OpenStreetMap coastline + lakes / canals / rivers). Bits per parcel: 1 oceanfront / open water
   (Atlantic, Gulf, Florida Bay, Biscayne Bay, wide sounds), 2 bay (Intracoastal, harbours, basins, smaller bays), 4 canal,
   8 lake / other water. Screening data, not a survey. File: {counts, built, sources, method, groups:{"<bits>":"folio,folio,..."}} */
(function(){
  "use strict";
  const WF = { data: null, map: new Map(), p: null, err: '' };
  let H = null;
  WF.OPTS = [['', 'Any or none'], ['any', 'Any waterfront'], ['o', 'Oceanfront / open water'], ['b', 'Bay / Intracoastal'], ['c', 'Canal'], ['l', 'Lake or other water']];
  WF.MASK = { any: 15, o: 1, b: 2, c: 4, l: 8 };
  WF.KEY = { o: 'ocean', b: 'bay', c: 'canal', l: 'lake', any: 'any' };
  const NAME = [[1, 'Oceanfront'], [2, 'Bay'], [4, 'Canal'], [8, 'Lake / other']];
  WF.load = function(h){ H = h || H; return WF.p || (WF.p = (async () => { const o = await H.fetchJSON('water.json.gz');
    for(const [k, v] of Object.entries(o.groups || {})){ const b = +k; if(v) for(const f of v.split(',')) WF.map.set(f, b); }
    WF.data = o; H.packs.forEach(WF.index); return o; })().catch(e => { WF.p = null; WF.err = String(e && e.message || e); throw e; })); };
  WF.index = function(p){ if(!p || !WF.data || p.wf) return; const f = H.folioCol(p), g = new Uint8Array(p.n);
    for(let i = 0; i < p.n; i++){ const b = WF.map.get(f[i]); if(b) g[i] = b; } p.wf = g; };
  WF.get = f => WF.map.get(f) || 0;
  WF.best = b => b & 1 ? 1 : b & 2 ? 2 : b & 4 ? 4 : b & 8 ? 8 : 0;
  WF.label = b => { const n = NAME.filter(([m]) => b & m).map(x => x[1]); return n.join(' · '); };
  WF.short = b => { const x = WF.best(b); return x === 1 ? 'Oceanfront' : x === 2 ? 'Bayfront' : x === 4 ? 'Canalfront' : x === 8 ? 'Lakefront' : ''; };
  const TIP = 'Mapped from the parcel boundary and OpenStreetMap water (coastline, lakes, canals). Screening only: confirm water frontage on the Property Appraiser record or an aerial.';
  WF.tag = b => b ? `<span class="tt wf wf${WF.best(b)}" title="${WF.label(b)}. ${TIP}">${WF.short(b)}</span>` : '';
  WF.CSV_HEAD = ',Waterfront';
  WF.csv = f => ',' + WF.label(WF.get(f)).replace(/ · /g, '; ');
  WF.TIP = TIP;
  window.PFWF = WF;
})();
