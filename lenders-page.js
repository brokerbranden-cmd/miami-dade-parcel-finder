/* Lenders page: dashboard, lender contacts, deals (saved property x lender). UI only; data lives in lenders.js (window.PFLenders).
   Nothing leaves the browser. */
(function(){
  "use strict";
  const $ = id => document.getElementById(id);
  const LS = window.PFLenders;
  let PF = null, tab = 'dash', lfStatus = '', dfStage = '', lq = '';
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  const usd = v => '$' + new Intl.NumberFormat('en-US').format(Math.round(v || 0));
  const short = v => v >= 1e6 ? '$' + (v / 1e6).toFixed(v >= 1e7 ? 1 : 2).replace(/\.?0+$/, '') + 'M' : v >= 1e3 ? '$' + Math.round(v / 1e3) + 'K' : usd(v);
  const stKey = s => String(s).toLowerCase().replace(/[^a-z]+/g, '-');
  const todayStr = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  const ago = s => { if(!s) return 'never'; const d = Math.round((Date.parse(todayStr()) - Date.parse(s)) / 864e5); return d <= 0 ? 'today' : d === 1 ? 'yesterday' : d + ' days ago'; };
  const fmtDay = s => { if(!s) return ''; const [y, m, d] = s.split('-'); return `${+m}/${+d}/${y}`; };
  const prop = folio => { const ids = PF.savedIdx(), id = ids.get(folio), sv = PF.SV.get(folio);
    if(id != null){ const p = PF.P(id), i = PF.I(id); return { id, addr: PF.getStr(p, 'addr', i) || 'No street address', city: PF.D.city[p.c.city[i]], saved: !!sv, mkt: p.c.mkt[i] }; }
    return { id: null, addr: (sv && sv.addr) || '', city: (sv && sv.city) || '', saved: !!sv, mkt: 0 }; };
  const propLabel = (folio, d) => { const p = prop(folio); return (p.addr || (d && d.addr) || PF.folioFmt(folio)) + (p.city || (d && d.city) ? ', ' + (p.city || d.city) : ''); };
  const lenderName = id => { const l = LS.lender(id); return l ? LS.lenderLabel(l) : 'No lender yet'; };

  /* ---------- render ---------- */
  function render(){
    if($('lendersPage').hidden) return;
    const s = LS.summary();
    $('lpTabs').innerHTML = [['dash', 'Dashboard'], ['lenders', `Lenders <span class="n">${s.lenders}</span>`], ['deals', `Deals <span class="n">${s.deals}</span>`]]
      .map(([k, l]) => `<button type="button" role="tab" class="lptab ${tab === k ? 'on' : ''}" data-tab="${k}" aria-selected="${tab === k}">${l}</button>`).join('');
    $('lpBody').innerHTML = tab === 'dash' ? dash(s) : tab === 'lenders' ? lenders() : deals();
    $('lendersCount').textContent = s.lenders;
  }
  function dash(s){
    const pct = s.needed ? Math.min(100, Math.round(s.committed / s.needed * 100)) : 0, maxSt = Math.max(1, ...Object.values(s.stages));
    if(!s.deals && !s.lenders) return `<div class="lpempty"><h2>Track who's funding your deals</h2><p>Add the private lenders, hard-money lenders and partners you work with, then link your saved properties to them with the amount you asked for and what they committed.</p>
      <div class="lpacts"><button type="button" class="btn primary" data-act="add-lender">+ Add a lender</button><button type="button" class="btn" data-act="add-deal">+ Add a deal</button></div></div>`;
    const lrow = r => { const l = LS.lender(r.lenderId); return `<tr><td>${l ? `<button type="button" class="lnk" data-act="edit-lender" data-id="${l.id}">${esc(LS.lenderLabel(l))}</button>` : '<span class="muted">No lender yet</span>'}</td><td>${l ? `<span class="lpill ls-${stKey(l.status)}">${esc(l.status)}</span>` : ''}</td>
      <td class="num">${r.deals}</td><td class="num">${usd(r.requested)}</td><td class="num"><b>${usd(r.committed)}</b></td><td class="num">${usd(r.funded)}</td><td class="num">${l && l.maxLoan ? usd(l.maxLoan) : '–'}</td><td>${l ? esc(ago(l.lastContacted)) : ''}</td></tr>`; };
    const prow = p => { const pc = p.needed ? Math.min(100, Math.round(Math.min(p.committed, p.needed) / p.needed * 100)) : 0;
      return `<tr><td>${prop(p.folio).id != null ? `<button type="button" class="lnk" data-act="open-prop" data-folio="${p.folio}">${esc(propLabel(p.folio, p))}</button>` : esc(propLabel(p.folio, p))}</td>
      <td class="num">${usd(p.needed)}</td><td class="num">${usd(p.committed)}</td><td><div class="lpbar sm" title="${pc}% covered"><i style="width:${pc}%"></i></div></td><td><span class="spill st-${stKey(p.bestStage)}">${esc(p.bestStage)}</span></td><td class="num">${p.lenders.length}</td></tr>`; };
    return `<div class="lpkpis">
        <div class="kpi"><span>Needed</span><b>${short(s.needed)}</b><small>${s.byProperty.length} propert${s.byProperty.length === 1 ? 'y' : 'ies'} (largest request each)</small></div>
        <div class="kpi hl"><span>Committed</span><b>${short(s.committed)}</b><small>${pct}% of needed${s.committedRaw > s.committed ? ' · ' + short(s.committedRaw) + ' offered in total' : ''}</small></div>
        <div class="kpi"><span>Still to raise</span><b>${short(s.gap)}</b><small>needed − committed</small></div>
        <div class="kpi"><span>Funded</span><b>${short(s.funded)}</b><small>${s.stages.Funded} deal${s.stages.Funded === 1 ? '' : 's'} at Funded</small></div></div>
      <div class="lpbar big" role="img" aria-label="Committed ${pct}% of needed"><i style="width:${pct}%"></i><span>${short(s.committed)} committed of ${short(s.needed)} needed</span></div>
      <h3>Pipeline</h3><div class="lppipe">${LS.STAGES.map(st => `<button type="button" class="pst st-${stKey(st)}" data-act="stage" data-stage="${st}"><span>${st}</span><b>${s.stages[st]}</b><i style="width:${Math.round(s.stages[st] / maxSt * 100)}%"></i></button>`).join('')}</div>
      <h3>By lender</h3>${s.byLender.length ? `<div class="lptable"><table><thead><tr><th>Lender</th><th>Status</th><th class="num">Deals</th><th class="num">Requested</th><th class="num">Committed</th><th class="num">Funded</th><th class="num">Max loan</th><th>Last contact</th></tr></thead><tbody>${s.byLender.map(lrow).join('')}</tbody></table></div>` : '<div class="note">No deals yet.</div>'}
      <h3>By property</h3>${s.byProperty.length ? `<div class="lptable"><table><thead><tr><th>Property</th><th class="num">Needed</th><th class="num">Committed</th><th>Covered</th><th>Furthest stage</th><th class="num">Lenders</th></tr></thead><tbody>${s.byProperty.map(prow).join('')}</tbody></table></div>` : '<div class="note">No deals yet.</div>'}`;
  }
  function lenders(){
    const all = LS.lenders(), q = lq.toLowerCase();
    const list = all.filter(l => (!lfStatus || l.status === lfStatus) && (!q || [l.name, l.company, l.geography, l.notes, l.email, l.terms, l.rate].join(' ').toLowerCase().includes(q)));
    const cnt = st => all.filter(l => l.status === st).length;
    const card = l => { const ds = LS.dealsOf(l.id), com = ds.reduce((a, d) => a + d.committed, 0);
      return `<article class="lcard" data-id="${l.id}"><div class="lc-h"><div><h3>${esc(l.name || l.company)}</h3>${l.name && l.company ? `<div class="sub">${esc(l.company)}</div>` : ''}</div><span class="lpill ls-${stKey(l.status)}">${esc(l.status)}</span></div>
        <div class="lc-contact">${l.phone ? `<a href="tel:${esc(l.phone.replace(/[^\d+]/g, ''))}">📞 ${esc(l.phone)}</a>` : ''}${l.email ? `<a href="mailto:${esc(l.email)}">✉ ${esc(l.email)}</a>` : ''}</div>
        <dl>${l.rate ? `<dt>Rate</dt><dd>${esc(l.rate)}</dd>` : ''}${l.terms ? `<dt>Terms</dt><dd>${esc(l.terms)}</dd>` : ''}${l.maxLoan ? `<dt>Max loan</dt><dd>${usd(l.maxLoan)}</dd>` : ''}${l.geography ? `<dt>Lends in</dt><dd>${esc(l.geography)}</dd>` : ''}
          <dt>Last contact</dt><dd>${l.lastContacted ? fmtDay(l.lastContacted) + ' · ' + ago(l.lastContacted) : 'never'}</dd><dt>Deals</dt><dd>${ds.length}${com ? ' · ' + usd(com) + ' committed' : ''}</dd></dl>
        ${l.notes ? `<p class="lc-notes">${esc(l.notes)}</p>` : ''}
        <div class="lc-acts"><button type="button" class="btn" data-act="edit-lender" data-id="${l.id}">Edit</button><button type="button" class="btn" data-act="contacted" data-id="${l.id}">Contacted today</button><button type="button" class="btn" data-act="add-deal" data-lender="${l.id}">+ Deal</button></div></article>`; };
    return `<div class="lptools"><input type="search" id="lpSearch" placeholder="Search name, company, area, notes…" value="${esc(lq)}" aria-label="Search lenders">
      <div class="chips">${['', ...LS.LSTATUS].map(st => `<button type="button" class="chip ${lfStatus === st ? 'on' : ''}" data-act="lstatus" data-st="${st}" aria-pressed="${lfStatus === st}">${st || 'All'}<span class="n">${st ? cnt(st) : all.length}</span></button>`).join('')}</div>
      <button type="button" class="btn primary" data-act="add-lender">+ Add lender</button></div>
      ${list.length ? `<div class="lcards">${list.map(card).join('')}</div>` : `<div class="note">${all.length ? 'No lenders match.' : 'No lenders yet. Add the first one.'}</div>`}`;
  }
  function deals(){
    const all = LS.deals(), list = all.filter(d => !dfStage || d.stage === dfStage), cnt = st => all.filter(d => d.stage === st).length;
    const row = d => `<tr data-id="${d.id}"><td>${prop(d.folio).id != null ? `<button type="button" class="lnk" data-act="open-prop" data-folio="${d.folio}">${esc(propLabel(d.folio, d))}</button>` : esc(propLabel(d.folio, d))}${prop(d.folio).saved ? '' : '<small class="muted"> (not on saved list)</small>'}</td>
      <td>${d.lenderId ? `<button type="button" class="lnk" data-act="edit-lender" data-id="${d.lenderId}">${esc(lenderName(d.lenderId))}</button>` : '<span class="muted">No lender yet</span>'}</td>
      <td><select class="dstage" data-id="${d.id}" aria-label="Stage">${LS.STAGES.map(s => `<option ${s === d.stage ? 'selected' : ''}>${s}</option>`).join('')}</select></td>
      <td class="num">${usd(d.requested)}</td><td class="num"><b>${usd(d.committed)}</b></td><td>${esc(d.note)}</td><td><button type="button" class="btn sm" data-act="edit-deal" data-id="${d.id}">Edit</button></td></tr>`;
    return `<div class="lptools"><div class="chips">${['', ...LS.STAGES].map(st => `<button type="button" class="chip ${dfStage === st ? 'on' : ''}" data-act="dstage" data-st="${st}" aria-pressed="${dfStage === st}">${st || 'All'}<span class="n">${st ? cnt(st) : all.length}</span></button>`).join('')}</div>
      <button type="button" class="btn primary" data-act="add-deal">+ Add deal</button></div>
      ${list.length ? `<div class="lptable"><table><thead><tr><th>Property</th><th>Lender</th><th>Stage</th><th class="num">Requested</th><th class="num">Committed</th><th>Note</th><th></th></tr></thead><tbody>${list.map(row).join('')}</tbody></table></div>`
        : `<div class="note">${all.length ? 'No deals at this stage.' : 'No deals yet. Save a property (☆), then add a deal here or from its detail drawer.'}</div>`}`;
  }

  /* ---------- forms (native <dialog>) ---------- */
  const field = (id, label, input) => `<label class="lf"><span>${label}</span>${input}</label>`;
  function lenderForm(id){
    const l = id ? LS.lender(id) : {}, v = k => esc(l[k] || '');
    $('lpDialog').innerHTML = `<form method="dialog" id="lfForm" class="lform"><h2>${id ? 'Edit lender' : 'Add lender'}</h2>
      <div class="lgrid">${field('lfName', 'Name', `<input id="lfName" name="name" value="${v('name')}" autocomplete="off">`)}${field('lfCompany', 'Company', `<input id="lfCompany" name="company" value="${v('company')}" autocomplete="off">`)}
      ${field('lfPhone', 'Phone', `<input id="lfPhone" name="phone" type="tel" value="${v('phone')}">`)}${field('lfEmail', 'Email', `<input id="lfEmail" name="email" type="email" value="${v('email')}">`)}
      ${field('lfRate', 'Rate / points', `<input id="lfRate" name="rate" value="${v('rate')}" placeholder="11%, 2 pts">`)}${field('lfMax', 'Max loan size ($)', `<input id="lfMax" name="maxLoan" inputmode="numeric" value="${l.maxLoan || ''}" placeholder="750000">`)}
      ${field('lfGeo', 'Geography', `<input id="lfGeo" name="geography" value="${v('geography')}" placeholder="Miami-Dade, Broward">`)}${field('lfStatus', 'Status', `<select id="lfStatus" name="status">${LS.LSTATUS.map(s => `<option ${s === (l.status || 'Prospect') ? 'selected' : ''}>${s}</option>`).join('')}</select>`)}
      ${field('lfLast', 'Last contacted', `<input id="lfLast" name="lastContacted" type="date" value="${v('lastContacted')}">`)}</div>
      ${field('lfTerms', 'Terms', `<textarea id="lfTerms" name="terms" rows="2" placeholder="12-month interest-only, 75% LTV, 65% ARV…">${v('terms')}</textarea>`)}
      ${field('lfNotes', 'Notes', `<textarea id="lfNotes" name="notes" rows="3">${v('notes')}</textarea>`)}
      <p class="lferr" id="lfErr" role="alert"></p>
      <div class="lfacts">${id ? `<button type="button" class="btn danger" data-act="del-lender" data-id="${id}">Delete</button>` : ''}<span></span><button type="button" class="btn" data-act="cancel">Cancel</button><button type="submit" class="btn primary" value="save">Save lender</button></div></form>`;
    $('lpDialog').dataset.kind = 'lender'; $('lpDialog').dataset.id = id || ''; open();
  }
  function dealForm(id, pre){
    const d = id ? LS.deal(id) : { stage: 'Prospect', ...(pre || {}) };
    const saved = PF.SV.list(), opts = saved.map(x => `<option value="${x.folio}" ${x.folio === d.folio ? 'selected' : ''}>${esc(propLabel(x.folio, x))} · ${esc(x.status)}</option>`);
    if(d.folio && !PF.SV.has(d.folio)) opts.unshift(`<option value="${d.folio}" selected>${esc(propLabel(d.folio, d))} (not saved)</option>`);
    $('lpDialog').innerHTML = `<form method="dialog" id="dfForm" class="lform"><h2>${id ? 'Edit deal' : 'Add deal'}</h2>
      ${opts.length ? field('dfProp', 'Property (from your saved list)', `<select id="dfProp" name="folio">${opts.join('')}</select>`) : '<p class="note">Save a property first (☆ on any card, or "Save where I am" in Drive mode).</p>'}
      <div class="lgrid">${field('dfLender', 'Lender', `<select id="dfLender" name="lenderId"><option value="">No lender yet</option>${LS.lenders().map(l => `<option value="${l.id}" ${l.id === d.lenderId ? 'selected' : ''}>${esc(LS.lenderLabel(l))}</option>`).join('')}</select>`)}
      ${field('dfStage', 'Pipeline stage', `<select id="dfStage" name="stage">${LS.STAGES.map(s => `<option ${s === d.stage ? 'selected' : ''}>${s}</option>`).join('')}</select>`)}
      ${field('dfReq', 'Amount requested ($)', `<input id="dfReq" name="requested" inputmode="numeric" value="${d.requested || ''}" placeholder="250000">`)}
      ${field('dfCom', 'Amount committed ($)', `<input id="dfCom" name="committed" inputmode="numeric" value="${d.committed || ''}" placeholder="0">`)}</div>
      ${field('dfNote', 'Note', `<textarea id="dfNote" name="note" rows="2" placeholder="Wants appraisal first; 2 pts">${esc(d.note || '')}</textarea>`)}
      <p class="lferr" id="lfErr" role="alert"></p>
      <div class="lfacts">${id ? `<button type="button" class="btn danger" data-act="del-deal" data-id="${id}">Delete</button>` : ''}<span></span><button type="button" class="btn" data-act="cancel">Cancel</button>${opts.length ? '<button type="submit" class="btn primary" value="save">Save deal</button>' : ''}</div></form>`;
    $('lpDialog').dataset.kind = 'deal'; $('lpDialog').dataset.id = id || ''; open();
  }
  function open(){ const dl = $('lpDialog'); if(dl.showModal) dl.showModal(); else dl.setAttribute('open', ''); const f = dl.querySelector('input,select'); if(f) f.focus(); }
  function close(){ const dl = $('lpDialog'); if(dl.open) dl.close(); }
  function submit(e){
    e.preventDefault(); const dl = $('lpDialog'), form = e.target, data = Object.fromEntries(new FormData(form).entries()), id = dl.dataset.id || undefined;
    try{
      if(dl.dataset.kind === 'lender'){ const l = LS.saveLender({ ...data, id }); PF.toast(LS.error || (id ? 'Lender updated' : 'Lender added: ' + LS.lenderLabel(l))); }
      else { const sv = PF.SV.get(data.folio), p = prop(data.folio); LS.saveDeal({ ...data, id, addr: p.addr || (sv && sv.addr) || '', city: p.city || (sv && sv.city) || '' }); PF.toast(LS.error || (id ? 'Deal updated' : 'Deal added')); }
      close(); render();
    }catch(err){ $('lfErr').textContent = err.message || String(err); }
  }

  /* ---------- page ---------- */
  function show(t){ if(t) tab = t; $('lendersPage').hidden = false; document.body.classList.add('lending'); $('lendersBtn').setAttribute('aria-pressed', 'true'); render(); $('lpClose').focus(); }
  function hide(){ $('lendersPage').hidden = true; document.body.classList.remove('lending'); $('lendersBtn').setAttribute('aria-pressed', 'false'); }
  function dl(name, text, type){ PF.download(name, new Blob([text], { type })); }
  function wire(){
    $('lendersBtn').onclick = () => $('lendersPage').hidden ? show() : hide();
    $('lpClose').onclick = hide;
    $('lpTabs').addEventListener('click', e => { const b = e.target.closest('[data-tab]'); if(b){ tab = b.dataset.tab; render(); } });
    $('lendersPage').addEventListener('click', e => {
      const b = e.target.closest('[data-act]'); if(!b) return; const a = b.dataset.act;
      if(a === 'add-lender') lenderForm();
      else if(a === 'edit-lender') lenderForm(b.dataset.id);
      else if(a === 'add-deal') dealForm(null, { lenderId: b.dataset.lender || '', folio: b.dataset.folio || '' });
      else if(a === 'edit-deal') dealForm(b.dataset.id);
      else if(a === 'contacted'){ const l = LS.lender(b.dataset.id); LS.saveLender({ ...l, lastContacted: todayStr() }); PF.toast('Logged contact with ' + (l.name || l.company)); render(); }
      else if(a === 'lstatus'){ lfStatus = b.dataset.st; render(); }
      else if(a === 'dstage'){ dfStage = b.dataset.st; render(); }
      else if(a === 'stage'){ tab = 'deals'; dfStage = b.dataset.stage; render(); }
      else if(a === 'open-prop'){ const id = PF.savedIdx().get(b.dataset.folio); if(id != null) PF.openDrawer(id); }
    });
    $('lendersPage').addEventListener('change', e => { const s = e.target.closest('.dstage'); if(s){ const d = LS.deal(s.dataset.id); LS.saveDeal({ ...d, stage: s.value }); PF.toast('Stage: ' + s.value); render(); } });
    $('lendersPage').addEventListener('input', e => { if(e.target.id === 'lpSearch'){ lq = e.target.value; const pos = e.target.selectionStart; render(); const s = $('lpSearch'); s.focus(); s.setSelectionRange(pos, pos); } });
    $('lpDialog').addEventListener('submit', submit);
    $('lpDialog').addEventListener('click', e => { const b = e.target.closest('[data-act]'); if(!b) return; const a = b.dataset.act;
      if(a === 'cancel') close();
      else if(a === 'del-lender'){ if(confirm('Delete this lender? Their deals stay, marked "No lender yet".')){ LS.removeLender(b.dataset.id); close(); render(); PF.toast('Lender deleted'); } }
      else if(a === 'del-deal'){ if(confirm('Delete this deal?')){ LS.removeDeal(b.dataset.id); close(); render(); PF.toast('Deal deleted'); } } });
    $('lpExportJson').onclick = () => { dl(`parcel-finder-lenders-${PF.stamp()}.json`, JSON.stringify(LS.exportJSON(), null, 1), 'application/json'); PF.toast('Lenders + deals exported (JSON)'); };
    $('lpExportLCsv').onclick = () => { dl(`parcel-finder-lenders-${PF.stamp()}.csv`, LS.lendersCSV(), 'text/csv'); PF.toast('Lenders exported (CSV)'); };
    $('lpExportDCsv').onclick = () => { dl(`parcel-finder-deals-${PF.stamp()}.csv`, LS.dealsCSV(), 'text/csv'); PF.toast('Deals exported (CSV)'); };
    $('lpImportLbl').addEventListener('keydown', e => { if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); $('lpImport').click(); } });
    $('lpImport').addEventListener('change', async e => { const f = e.target.files && e.target.files[0]; e.target.value = ''; if(!f) return;
      try{ const text = await f.text();
        if(/^\s*[\[{]/.test(text)){ const r = LS.importJSON(JSON.parse(text)); PF.toast(`Imported: ${r.lenders.added} lenders added, ${r.lenders.updated} updated; ${r.deals.added} deals added, ${r.deals.updated} updated`); }
        else { const r = LS.importCSV(text); PF.toast(`Imported ${r.kind}: ${r.added} added, ${r.updated} updated${r.bad ? ', ' + r.bad + ' skipped' : ''}`); }
        render(); }catch(err){ PF.toast('Import failed: ' + (err.message || err)); } });
    document.addEventListener('keydown', e => { if(e.key === 'Escape' && !$('lendersPage').hidden && !$('lpDialog').open && !$('drawerHost').innerHTML) hide(); });
    LS.onChange(() => { render(); $('lendersCount').textContent = LS.lenders().length; });
    PF.SV.onChange(() => render());
    $('lendersCount').textContent = LS.lenders().length;
    if(new URLSearchParams(location.search).get('page') === 'lenders') show();
  }
  function ready(){ PF = window.PF; wire(); }
  if(window.PF_READY) ready(); else document.addEventListener('pf:ready', ready, { once: true });
  window.PFLendersUI = { show, hide, addDeal: folio => { show('deals'); dealForm(null, { folio }); }, editDeal: id => { show('deals'); dealForm(id); } };
})();
