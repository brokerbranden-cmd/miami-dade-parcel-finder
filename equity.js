/* Estimated owner equity (Miami-Dade only; data/equity.json.gz from scripts/build_equity.py).
   Recorded mortgages (Clerk Official Records, current owner since acquisition) with no recorded satisfaction / release,
   balances amortized as 30-yr fixed at the Freddie Mac average rate of the origination year (private / subordinate notes at
   full amount), equity = PA just value - estimated balances. An ESTIMATE: shown with "est." everywhere.
   Row: [folio, estBal, nOpen, lender, value, estEq, eqPct, flags, checked, loans[[recDate, amount, lender, kind, estBal, cfn]]]
   flags: c = owner search capped (coverage incomplete), m = loan linked by owner name only, u = a loan amount unreadable,
          r = older loan(s) assumed refinanced. "Free & clear" = checked, no open mortgage found and not capped. */
(function(){
  "use strict";
  const EQ = { data: null, map: new Map(), p: null };
  /* app.js passes its helpers (it runs in its own scope): fetchJSON(name) -> parsed gz JSON, folioCol(pack) -> folio strings, packs */
  let H = null;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const HAS = l => !!(window.PFCounty && window.PFCounty.has(l));
  EQ.load = function(h){ H = h || H; return EQ.p || (EQ.p = (async () => { const o = await H.fetchJSON('equity.json.gz');
    o.rows.forEach(r => EQ.map.set(r[0], r)); EQ.data = o; H.packs.forEach(EQ.index); return o; })().catch(e => { EQ.p = null; throw e; })); };
  EQ.get = f => EQ.map.get(f);
  EQ.fc = r => !!r && r[2] === 0 && r[7].indexOf('c') < 0;
  /* per-pack column: 0 = not checked, 1..201 = equity % + 101 (clamped -100..100), 255 = free & clear */
  EQ.index = function(p){ if(!p || !EQ.data || p.eq) return; const f = H.folioCol(p), g = new Uint8Array(p.n);
    for(let i = 0; i < p.n; i++){ const r = EQ.map.get(f[i]); if(!r) continue; g[i] = EQ.fc(r) ? 255 : r[6] == null ? 0 : Math.max(-100, Math.min(100, r[6])) + 101; } p.eq = g; };
  /* filter: min equity % (0 = off), fc = free & clear only */
  EQ.pass = (v, min, fc) => { if(fc) return v === 255; if(min) return v === 255 || (v > 0 && v - 101 >= min); return true; };
  const usd = v => v == null ? '–' : (v < 0 ? '-$' : '$') + Math.abs(Math.round(v)).toLocaleString('en-US');
  const ymd = n => String(n).replace(/^(\d{4})(\d\d)(\d\d)$/, '$2/$3/$1');
  const KIND = { first: 'amortized 30-yr', private: 'private note, full amount', subordinate: 'subordinate / partial claim, full amount', heloc: 'HELOC-type, full amount' };
  function tip(r){ const m = EQ.data.meta; return `ESTIMATE, not a payoff. ${r[2] ? r[2] + ' recorded mortgage' + (r[2] > 1 ? 's' : '') + ' with no recorded satisfaction found' : 'No open recorded mortgage found'} in Clerk Official Records for the current owner (checked ${r[8]}). Balances amortized as 30-yr fixed at the Freddie Mac average rate of the origination year; private and subordinate notes at full amount. Equity = Property Appraiser just value ${usd(r[4])} minus estimated balances.`
    + (r[7].includes('c') ? ' Owner name search hit the 500-row cap: coverage incomplete.' : '') + (r[7].includes('m') ? ' A loan was linked by owner name only (no folio on the record).' : '')
    + (r[7].includes('u') ? ' A loan amount could not be read and is not in the balance.' : '') + (r[7].includes('r') ? ' Older loans assumed refinanced.' : ''); }
  EQ.badge = function(f){ const r = EQ.data && EQ.map.get(f); if(!r) return ''; if(EQ.fc(r)) return `<span class="eqfc" title="${esc(tip(r))}">Free &amp; clear (est.)</span>`;
    return r[6] != null && r[6] >= 50 ? `<span class="eqhi" title="${esc(tip(r))}">High equity ${r[6]}% (est.)</span>` : ''; };
  EQ.line = function(f){ const r = EQ.data && EQ.map.get(f); if(!r) return '';
    const v = EQ.fc(r) ? `<b>Free &amp; clear</b> · est. equity <b>${usd(r[5])}</b> (100%)` : r[2] ? `est. equity <b>${usd(r[5])}</b>${r[6] != null ? ' (' + r[6] + '%)' : ''} · est. loans ${usd(r[1])} · ${r[2]} open · ${esc(r[3])}` : `no open mortgage found (search incomplete) · est. equity ${usd(r[5])}`;
    return `<div class="line eqline"><span class="k" title="Estimate from recorded mortgages">Equity</span><span class="v" title="${esc(tip(r))}">${v}</span></div>`; };
  EQ.html = function(f){ const r = EQ.data && EQ.map.get(f); if(!r) return HAS('equity') && EQ.data ? '<div class="note eqnote">Equity estimate: this property\'s owner has not been checked against Clerk mortgage records yet.</div>' : '';
    const li = r[9].map(l => `<li><span class="dtag ${l[3] === 'first' ? 'warm' : 'hot'}">Mortgage</span> <b>${esc(l[2])}</b> · recorded ${ymd(l[0])} · original ${l[1] ? usd(l[1]) : 'amount n/a'} · est. balance <b>${l[4] == null ? 'n/a' : usd(l[4])}</b><br><span class="mono">${esc(l[5])}</span><small>${esc(KIND[l[3]] || '')}</small></li>`).join('');
    return `<h3 class="eqh">Estimated equity (est.)</h3><div class="eqsum">${EQ.fc(r) ? '<span class="eqfc">Free &amp; clear (est.)</span> ' : ''}Value ${usd(r[4])} · est. open loans ${usd(r[1])} (${r[2]}) · <b>est. equity ${usd(r[5])}${r[6] != null ? ' (' + r[6] + '%)' : ''}</b></div>${li ? `<ul class="dlist">${li}</ul>` : ''}<div class="note">${esc(tip(r))} Verify with a title search before acting.</div>`; };
  EQ.cells = function(f){ const r = EQ.data && EQ.map.get(f); if(!r) return ['–', '–'];
    return [EQ.fc(r) ? 'Free & clear' : r[6] != null ? r[6] + '%' : '–', r[2] ? usd(r[1]) + ' (' + r[2] + ')' : EQ.fc(r) ? '$0' : '–']; };
  EQ.CSV_HEAD = ',Est Equity $,Est Equity %,Est Loan Balance,Open Mortgages,Lender,Free & Clear,Equity Checked';
  EQ.csv = function(f){ const r = EQ.data && EQ.map.get(f); if(!r) return ',,,,,,,';
    const q = s => /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    return ',' + [r[5] == null ? '' : r[5], r[6] == null ? '' : r[6], r[1], r[2], q(r[3] || ''), EQ.fc(r) ? 'Y' : '', r[8]].join(','); };
  window.PFEQ = EQ;
})();
