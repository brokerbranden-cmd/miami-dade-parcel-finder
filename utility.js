/* 'Power / water cut' layer (every county; data/<county>/utility.json.gz from scripts/build_utility.py).
   Signals per parcel, most accurate first: 1 utility shutoff list (utility's own list, public-records request), 2 code case that says
   no water / water shut off / utilities off / no power, 4 permit in the last 24 months for a power reconnect / FPL release / meter
   release / water meter reconnect, 8 open unsafe-structure or vacant / boarded case (weaker).
   File: {counts, built, sources, notes, lists, short:{source: place}, rows:{folio:[bits, best_bit, date, label, source, status?]}}
   Signal 1 rows (shutoff lists) come from per-city parsers (scripts/utility_lists.py -> build_utility.py); the card badge reads
   'Water shut off <date> (<place> cut list)', the 'Shut off within' filter and the map ring layer use the list date. */
(function(){
  "use strict";
  const UT = { data: null, map: new Map(), p: null, err: '' };
  let H = null;
  UT.OPTS = [['', 'Any or none'], ['any', 'Any power / water signal'], ['list', 'Utility shutoff list / lien'], ['case', 'No-water / utility code case'], ['rc', 'Recent reconnect permit'], ['uv', 'Unsafe / vacant case (weaker)']];
  UT.MASK = { any: 15, list: 1, case: 2, rc: 4, uv: 8 };
  UT.SRC = { 1: 'shutoff list', 2: 'code case', 4: 'permit', 8: 'open case' };
  UT.STRENGTH = { 1: 'Strongest', 2: 'Strong', 4: 'Medium', 8: 'Weak' };
  UT.load = function(h){ H = h || H; return UT.p || (UT.p = (async () => { const o = await H.fetchJSON('utility.json.gz');
    for(const [f, r] of Object.entries(o.rows || {})) UT.map.set(f, r);
    UT.data = o; H.packs.forEach(UT.index); return o; })().catch(e => { UT.p = null; UT.err = String(e && e.message || e); throw e; })); };
  UT.index = function(p){ if(!p || !UT.data || p.ut) return; const f = H.folioCol(p), g = new Uint8Array(p.n);
    const dd = new Uint16Array(p.n);   // shutoff-list (signal 1, not a lien) date as days since 2000-01-01; 1 = listed without a date, 0 = not listed
    for(let i = 0; i < p.n; i++){ const r = UT.map.get(f[i]); if(r){ g[i] = r[0]; if(r[1] === 1 && !/^Utility lien/.test(r[3])) dd[i] = r[2] ? UT.dnum(r[2]) : 1; } } p.ut = g; p.utd = dd; };
  UT.dnum = d => { const t = Date.parse(String(d).slice(0, 10) + 'T00:00:00Z'); return isFinite(t) ? Math.max(1, Math.round(t / 864e5) - 10957) : 0; };
  UT.today = () => { const t = new Date(); return Math.round(Date.UTC(t.getFullYear(), t.getMonth(), t.getDate()) / 864e5) - 10957; };
  UT.DAYS = [[0, 'Any date'], [30, 'Last 30 days'], [60, 'Last 60 days'], [90, 'Last 90 days'], [180, 'Last 180 days'], [365, 'Last 12 months']];
  UT.hasList = () => !!(UT.data && (UT.data.counts || {}).list);
  UT.NOLIST = 'No utility shutoff data yet for this county';
  UT.get = f => UT.map.get(f) || null;
  const ym = d => d ? String(d).slice(0, 7) : '';
  const srcw = r => r[1] === 1 && /^Utility lien/.test(r[3]) ? 'utility lien' : UT.SRC[r[1]] || 'record';
  UT.place = src => ((UT.data && UT.data.short) || {})[src] || String(src || '').replace(/^Utility shutoff list:\s*/, '').split(/ (?:water|power|open|utility)\b/i)[0];
  const listText = r => `${r[3].replace(/ \((open|open case)\)$/, '')} ${r[2] || ''} (${UT.place(r[4])})`.replace('  ', ' ');
  UT.text = r => r ? (r[1] === 1 ? listText(r) : `${r[3].replace(/ \((open|open case)\)$/, '')} - ${srcw(r)}${ym(r[2]) ? ' ' + ym(r[2]) : ''}`) : '';
  const tip = r => `${UT.STRENGTH[r[1]]} signal. ${r[3]}, ${r[4]}${r[2] ? ', ' + r[2] : ''}${r[5] ? ' (' + r[5] + ')' : ''}. Public-record screening, not a utility confirmation.`.replace(/"/g, '&quot;');
  UT.tag = f => { const r = UT.get(f); if(!r) return ''; return `<span class="tt ut ut${r[1]}" title="${tip(r)}">${UT.text(r)}</span>`; };
  UT.detail = f => { const r = UT.get(f); if(!r) return ''; const other = [1, 2, 4, 8].filter(b => b !== r[1] && (r[0] & b)).map(b => ({1: 'shutoff list / utility lien', 2: 'no-water / utility code case', 4: 'recent reconnect permit', 8: 'unsafe / vacant case'})[b]);
    return `<b>${UT.text(r)}</b><small>${UT.STRENGTH[r[1]]} signal · ${r[3]} · ${r[4]}${r[2] ? ' · ' + r[2] : ''}${r[5] ? ' · ' + r[5] : ''}${other.length ? ' · also: ' + other.join(', ') : ''}</small>`; };
  // export: 'Power / water cut' (best signal), then the shutoff-list date + source (blank when the parcel is on no list), always last
  UT.CSV_HEAD = ',Power / water cut,Utility shut off date,Utility shut off source';
  const q = v => /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  UT.csv = f => { const r = UT.get(f); if(!r) return ',,,'; const v = `${UT.text(r)} (${UT.STRENGTH[r[1]].toLowerCase()}; ${r[4]})`, L = r[1] === 1;
    return ',' + q(v) + ',' + (L ? r[2] || '' : '') + ',' + (L ? q(r[4] + (r[5] ? '; ' + r[5] : '')) : ''); };
  UT.cell = f => { const r = UT.get(f); return r ? UT.text(r) : ''; };
  UT.TIP = 'From public records: utility shutoff lists and open utility liens (when on file), code cases that say no water / no power / utilities off, recent reconnect / FPL release / meter permits, and open unsafe or vacant cases. Screening only.';
  window.PFUT = UT;
})();
