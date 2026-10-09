/* Lender tracking store: lender contacts + deals (a saved property pitched to a lender). Everything stays in this browser.
   Storage sits behind a tiny adapter so login / cloud sync (planned: Supabase) can be plugged in later without touching the UI:
     PFLenders.use({ load(): object|null, save(data): boolean })     // synchronous backend (default: localStorage)
   For an async/remote backend, fetch remote data and call PFLenders.importJSON(data) (newest updatedAt per id wins),
   and subscribe with PFLenders.onChange(fn) to push local edits upstream.
   Shapes (ISO timestamps, money in whole dollars):
     lender {id, name, company, phone, email, rate, terms, maxLoan, geography, status, notes, lastContacted 'YYYY-MM-DD', createdAt, updatedAt}
     deal   {id, folio, lenderId, requested, committed, stage, note, addr, city, createdAt, updatedAt} */
(function(){
  "use strict";
  const KEY = 'mdpf.lenders.v1';
  const STAGES = ['Prospect', 'Contacted', 'Interested', 'Term sheet', 'Funded'];
  const LSTATUS = ['Prospect', 'Active', 'Paused', 'Not a fit'];
  const localBackend = {
    load(){ try{ return JSON.parse(localStorage.getItem(KEY) || 'null'); }catch(e){ return null; } },
    save(data){ try{ localStorage.setItem(KEY, JSON.stringify(data)); return true; }catch(e){ return false; } }
  };
  let backend = localBackend, L = {}, Dl = {}, rev = 1, lastError = '';
  const subs = new Set();
  const now = () => new Date().toISOString();
  const uid = p => p + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  const str = (v, n) => String(v == null ? '' : v).slice(0, n).trim();
  const money = v => { const n = Math.round(Number(String(v == null ? '' : v).replace(/[^\d.]/g, '')) || 0); return n > 0 && n < 1e11 ? n : 0; };
  const iso = v => (typeof v === 'string' && v && !isNaN(Date.parse(v))) ? new Date(v).toISOString() : null;
  const day = v => { const s = str(v, 10); return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : ''; };
  const folioOf = f => { const s = String(f == null ? '' : f).replace(/\D/g, ''); return s ? s.padStart(13, '0').slice(-13) : ''; };
  function cleanLender(x){
    if(!x || typeof x !== 'object') return null;
    const name = str(x.name, 120), company = str(x.company, 120); if(!name && !company) return null;
    const c = iso(x.createdAt) || now();
    return { id: /^[\w-]{3,40}$/.test(x.id || '') ? x.id : uid('l_'), name, company, phone: str(x.phone, 40), email: str(x.email, 120),
      rate: str(x.rate, 120), terms: str(x.terms, 500), maxLoan: money(x.maxLoan), geography: str(x.geography, 200),
      status: LSTATUS.includes(x.status) ? x.status : 'Prospect', notes: str(x.notes, 5000), lastContacted: day(x.lastContacted),
      createdAt: c, updatedAt: iso(x.updatedAt) || c };
  }
  function cleanDeal(x){
    if(!x || typeof x !== 'object') return null;
    const folio = folioOf(x.folio); if(!/^\d{13}$/.test(folio) || /^0+$/.test(folio)) return null;
    const c = iso(x.createdAt) || now();
    return { id: /^[\w-]{3,40}$/.test(x.id || '') ? x.id : uid('d_'), folio, lenderId: str(x.lenderId, 40),
      requested: money(x.requested), committed: money(x.committed), stage: STAGES.includes(x.stage) ? x.stage : 'Prospect',
      note: str(x.note, 2000), addr: str(x.addr, 200), city: str(x.city, 80), createdAt: c, updatedAt: iso(x.updatedAt) || c };
  }
  function loadAll(){
    const raw = backend.load() || {}; L = {}; Dl = {};
    for(const x of Object.values(raw.lenders || {})){ const c = cleanLender(x); if(c) L[c.id] = c; }
    for(const x of Object.values(raw.deals || {})){ const c = cleanDeal(x); if(c) Dl[c.id] = c; }
  }
  loadAll();
  function emit(why, id){ rev++; subs.forEach(fn => { try{ fn(why, id); }catch(e){ console.warn(e); } }); }
  function persist(why, id){ lastError = backend.save({ version: 1, lenders: L, deals: Dl }) ? '' : 'Could not write to this browser\'s storage (full or blocked).'; emit(why, id); return !lastError; }
  window.addEventListener('storage', e => { if(e.key === KEY){ loadAll(); emit('external'); } });

  /* CSV helpers (RFC 4180-ish) */
  const csvq = v => { const s = String(v == null ? '' : v); return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  function parseCSV(text){
    const rows = []; let row = [], f = '', q = false;
    for(let i = 0; i < text.length; i++){ const ch = text[i];
      if(q){ if(ch === '"'){ if(text[i + 1] === '"'){ f += '"'; i++; } else q = false; } else f += ch; }
      else if(ch === '"') q = true; else if(ch === ','){ row.push(f); f = ''; }
      else if(ch === '\n' || ch === '\r'){ if(ch === '\r' && text[i + 1] === '\n') i++; row.push(f); f = ''; if(row.some(x => x !== '')) rows.push(row); row = []; }
      else f += ch; }
    row.push(f); if(row.some(x => x !== '')) rows.push(row);
    return rows;
  }
  const LCOLS = [['id', 'ID'], ['name', 'Name'], ['company', 'Company'], ['phone', 'Phone'], ['email', 'Email'], ['rate', 'Rate'], ['terms', 'Terms'], ['maxLoan', 'Max Loan'],
    ['geography', 'Geography'], ['status', 'Status'], ['lastContacted', 'Last Contacted'], ['notes', 'Notes'], ['createdAt', 'Created'], ['updatedAt', 'Updated']];
  const DCOLS = [['id', 'Deal ID'], ['folio', 'Folio'], ['addr', 'Address'], ['city', 'City'], ['lenderId', 'Lender ID'], ['lender', 'Lender'], ['stage', 'Stage'],
    ['requested', 'Amount Requested'], ['committed', 'Amount Committed'], ['note', 'Note'], ['createdAt', 'Created'], ['updatedAt', 'Updated']];
  const lenderLabel = l => l ? [l.name, l.company].filter(Boolean).join(' · ') : '';

  function mergeList(store, list, clean){
    let added = 0, updated = 0, same = 0, bad = 0;
    for(const raw of list){ const c = clean(raw); if(!c){ bad++; continue; } const cur = store[c.id];
      if(!cur){ store[c.id] = c; added++; } else if(c.updatedAt > cur.updatedAt){ store[c.id] = c; updated++; } else same++; }
    return { added, updated, same, bad };
  }
  const api = {
    KEY, STAGES, LSTATUS,
    get rev(){ return rev; }, get error(){ return lastError; },
    lenders: () => Object.values(L).sort((a, b) => (a.name || a.company).localeCompare(b.name || b.company)),
    lender: id => L[id] || null,
    deals: () => Object.values(Dl).sort((a, b) => b.updatedAt < a.updatedAt ? -1 : 1),
    deal: id => Dl[id] || null,
    dealsFor: folio => api.deals().filter(d => d.folio === folio),
    dealsOf: lenderId => api.deals().filter(d => d.lenderId === lenderId),
    lenderLabel,
    saveLender(x){ const cur = x && x.id && L[x.id]; const c = cleanLender({ ...(cur || {}), ...x, createdAt: cur ? cur.createdAt : now(), updatedAt: now() }); if(!c) throw new Error('A lender needs a name or a company'); L[c.id] = c; persist(cur ? 'lender-update' : 'lender-add', c.id); return c; },
    removeLender(id){ if(!L[id]) return; delete L[id]; for(const d of Object.values(Dl)) if(d.lenderId === id){ Dl[d.id] = { ...d, lenderId: '', updatedAt: now() }; } persist('lender-remove', id); },
    saveDeal(x){ const cur = x && x.id && Dl[x.id]; const c = cleanDeal({ ...(cur || {}), ...x, createdAt: cur ? cur.createdAt : now(), updatedAt: now() }); if(!c) throw new Error('A deal needs a property (folio)'); Dl[c.id] = c; persist(cur ? 'deal-update' : 'deal-add', c.id); return c; },
    removeDeal(id){ if(!Dl[id]) return; delete Dl[id]; persist('deal-remove', id); },
    /* dashboard numbers: "needed" counts each property once (its largest request); committed sums every lender's commitment */
    summary(){
      const deals = api.deals(), byP = new Map(), byL = new Map(), stages = Object.fromEntries(STAGES.map(s => [s, 0]));
      for(const d of deals){ stages[d.stage]++;
        const p = byP.get(d.folio) || { folio: d.folio, addr: d.addr, city: d.city, needed: 0, committed: 0, funded: 0, best: -1, lenders: new Set(), deals: 0 };
        p.needed = Math.max(p.needed, d.requested); p.committed += d.committed; if(d.stage === 'Funded') p.funded += d.committed;
        p.best = Math.max(p.best, STAGES.indexOf(d.stage)); if(d.lenderId) p.lenders.add(d.lenderId); p.deals++; byP.set(d.folio, p);
        const k = d.lenderId || ''; const l = byL.get(k) || { lenderId: k, deals: 0, requested: 0, committed: 0, funded: 0, open: 0 };
        l.deals++; l.requested += d.requested; l.committed += d.committed; if(d.stage === 'Funded') l.funded += d.committed; else l.open++; byL.set(k, l); }
      const props = [...byP.values()].map(p => ({ ...p, bestStage: STAGES[p.best] || '', lenders: [...p.lenders] }));
      const needed = props.reduce((a, p) => a + p.needed, 0), committed = props.reduce((a, p) => a + Math.min(p.committed, p.needed || p.committed), 0);
      return { needed, committed, committedRaw: deals.reduce((a, d) => a + d.committed, 0), funded: deals.filter(d => d.stage === 'Funded').reduce((a, d) => a + d.committed, 0),
        gap: Math.max(0, needed - committed), deals: deals.length, lenders: Object.keys(L).length, stages,
        byLender: [...byL.values()].sort((a, b) => b.committed - a.committed || b.requested - a.requested), byProperty: props.sort((a, b) => b.needed - a.needed) };
    },
    exportJSON: () => ({ app: 'miami-dade-parcel-finder', kind: 'lender-tracking', version: 1, exported: now(), lenders: api.lenders(), deals: api.deals() }),
    importJSON(data){
      if(!data || typeof data !== 'object' || (!Array.isArray(data.lenders) && !Array.isArray(data.deals))) throw new Error('Not a lender-tracking file');
      const a = mergeList(L, data.lenders || [], cleanLender), b = mergeList(Dl, data.deals || [], cleanDeal);
      if(a.added + a.updated + b.added + b.updated) persist('import');
      return { lenders: a, deals: b };
    },
    lendersCSV: () => [LCOLS.map(c => c[1]).join(',')].concat(api.lenders().map(l => LCOLS.map(([k]) => csvq(l[k])).join(','))).join('\n') + '\n',
    dealsCSV: () => [DCOLS.map(c => c[1]).join(',')].concat(api.deals().map(d => DCOLS.map(([k]) => csvq(k === 'lender' ? lenderLabel(L[d.lenderId]) : d[k])).join(','))).join('\n') + '\n',
    /* CSV import: recognizes the lenders or deals CSV made by the export (by header). Rows without an ID get a new one. */
    importCSV(text){
      const rows = parseCSV(String(text).replace(/^\uFEFF/, '')); if(rows.length < 1) throw new Error('Empty CSV');
      const head = rows[0].map(h => h.trim().toLowerCase());
      const isDeals = head.includes('folio'), cols = isDeals ? DCOLS : LCOLS;
      if(!isDeals && !head.includes('name') && !head.includes('company')) throw new Error('CSV needs a Name/Company column (lenders) or a Folio column (deals)');
      const idx = cols.map(([k, h]) => [k, head.indexOf(h.toLowerCase())]).filter(([, i]) => i >= 0);
      const byLabel = new Map(api.lenders().map(l => [lenderLabel(l).toLowerCase(), l.id]));
      const list = rows.slice(1).map(r => { const o = {}; for(const [k, i] of idx) o[k] = r[i] || ''; if(!o.id) delete o.id;
        if(isDeals && !L[o.lenderId] && o.lender) o.lenderId = byLabel.get(o.lender.toLowerCase()) || ''; if(!o.updatedAt) o.updatedAt = now(); return o; });
      const res = mergeList(isDeals ? Dl : L, list, isDeals ? cleanDeal : cleanLender);
      if(res.added + res.updated) persist('import');
      return { kind: isDeals ? 'deals' : 'lenders', ...res };
    },
    use(b){ if(!b || typeof b.load !== 'function' || typeof b.save !== 'function') throw new Error('backend needs load() and save()');
      const local = api.exportJSON(); backend = b; loadAll(); api.importJSON(local); emit('backend'); },
    onChange(fn){ subs.add(fn); return () => subs.delete(fn); }
  };
  window.PFLenders = api;
})();
