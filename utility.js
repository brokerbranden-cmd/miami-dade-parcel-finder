/* 'Power / water cut' layer (every county; data/<county>/utility.json.gz from scripts/build_utility.py).
   Signals per parcel, most accurate first: 1 utility shutoff list (utility's own list, public-records request), 2 code case that says
   no water / water shut off / utilities off / no power, 4 permit in the last 24 months for a power reconnect / FPL release / meter
   release / water meter reconnect, 8 open unsafe-structure or vacant / boarded case (weaker).
   File: {counts, built, sources, notes, rows:{folio:[bits, best_bit, date, label, source]}} */
(function(){
  "use strict";
  const UT = { data: null, map: new Map(), p: null, err: '' };
  let H = null;
  UT.OPTS = [['', 'Any or none'], ['any', 'Any power / water signal'], ['list', 'Utility shutoff list'], ['case', 'No-water / utility code case'], ['rc', 'Recent reconnect permit'], ['uv', 'Unsafe / vacant case (weaker)']];
  UT.MASK = { any: 15, list: 1, case: 2, rc: 4, uv: 8 };
  UT.SRC = { 1: 'shutoff list', 2: 'code case', 4: 'permit', 8: 'open case' };
  UT.STRENGTH = { 1: 'Strongest', 2: 'Strong', 4: 'Medium', 8: 'Weak' };
  UT.load = function(h){ H = h || H; return UT.p || (UT.p = (async () => { const o = await H.fetchJSON('utility.json.gz');
    for(const [f, r] of Object.entries(o.rows || {})) UT.map.set(f, r);
    UT.data = o; H.packs.forEach(UT.index); return o; })().catch(e => { UT.p = null; UT.err = String(e && e.message || e); throw e; })); };
  UT.index = function(p){ if(!p || !UT.data || p.ut) return; const f = H.folioCol(p), g = new Uint8Array(p.n);
    for(let i = 0; i < p.n; i++){ const r = UT.map.get(f[i]); if(r) g[i] = r[0]; } p.ut = g; };
  UT.get = f => UT.map.get(f) || null;
  const ym = d => d ? String(d).slice(0, 7) : '';
  UT.text = r => r ? `${r[3].replace(/ \((open|open case)\)$/, '')} - ${UT.SRC[r[1]] || 'record'}${ym(r[2]) ? ' ' + ym(r[2]) : ''}` : '';
  UT.tag = f => { const r = UT.get(f); if(!r) return ''; return `<span class="tt ut ut${r[1]}" title="${UT.STRENGTH[r[1]]} signal. ${r[3]}, ${r[4]}${r[2] ? ', ' + r[2] : ''}. Public-record screening, not a utility confirmation.">${UT.text(r)}</span>`; };
  UT.detail = f => { const r = UT.get(f); if(!r) return ''; const other = [1, 2, 4, 8].filter(b => b !== r[1] && (r[0] & b)).map(b => ({1: 'shutoff list', 2: 'no-water / utility code case', 4: 'recent reconnect permit', 8: 'unsafe / vacant case'})[b]);
    return `<b>${UT.text(r)}</b><small>${UT.STRENGTH[r[1]]} signal · ${r[3]} · ${r[4]}${r[2] ? ' · ' + r[2] : ''}${other.length ? ' · also: ' + other.join(', ') : ''}</small>`; };
  UT.CSV_HEAD = ',Power / water cut';
  UT.csv = f => { const r = UT.get(f); if(!r) return ','; const v = `${UT.text(r)} (${UT.STRENGTH[r[1]].toLowerCase()}; ${r[4]})`; return ',' + (/[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v); };
  UT.cell = f => { const r = UT.get(f); return r ? UT.text(r) : ''; };
  UT.TIP = 'From public records: utility shutoff lists (when on file), code cases that say no water / no power / utilities off, recent reconnect / FPL release / meter permits, and open unsafe or vacant cases. Screening only.';
  window.PFUT = UT;
})();
