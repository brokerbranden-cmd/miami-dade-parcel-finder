/* Saved properties store (favorites), keyed by 13-digit folio.
   Storage sits behind a tiny backend interface so cloud sync can be plugged in later:
     PFSaved.use({ load(): object|null, save(items): boolean })      // synchronous backend (default: localStorage)
   For an async/remote backend, fetch remote data and call PFSaved.importJSON(data) (newest edit per folio wins),
   and subscribe with PFSaved.onChange(fn) to push local edits upstream.
   Item shape: {folio, savedAt, updatedAt, status, note, vacant, cond, addr, city, zip, pack, stage, next, acts}
   Outreach: stage (STAGES), next = next follow-up 'YYYY-MM-DD' or '', acts = [{id, d:'YYYY-MM-DD', type, outcome, note, at}] newest first.
   (ISO timestamps; vacant = your own 'looks vacant / damaged' mark, cond = condition note; pack = 'main' | 'condo'). */
(function(){
  "use strict";
  const KEY = 'mdpf.saved.v1';
  const STATUSES = ['New','Researching','Mailed','Called','Offer sent','Under contract','Pass'];
  const STAGES = ['New','Contacted','Follow-up','Offer','Under contract','Closed','Dead'];
  const ACT_TYPES = [['call','Call'],['text','Text'],['mailer','Mailer'],['door','Door knock'],['email','Email'],['note','Note']];
  const OUTCOMES = ['','No answer','Left voicemail','Talked','Interested','Not interested','Call back later','Wrong number','Do not contact','Offer made','Sent to list'];
  const isDay = v => typeof v === 'string' && /^\d{4}-\d\d-\d\d$/.test(v) && !isNaN(Date.parse(v));
  const cleanAct = a => (a && typeof a === 'object' && ACT_TYPES.some(t => t[0] === a.type) && isDay(a.d)) ? { id: String(a.id || ('a' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7))).slice(0, 40), d: a.d, type: a.type,
      outcome: OUTCOMES.includes(a.outcome) ? a.outcome : '', note: typeof a.note === 'string' ? a.note.slice(0, 2000) : '', at: (typeof a.at === 'string' && !isNaN(Date.parse(a.at))) ? a.at : new Date().toISOString() } : null;
  const sortActs = l => l.sort((x, y) => (y.d + y.at) < (x.d + x.at) ? -1 : 1);
  const localBackend = {
    load(){ try{ return JSON.parse(localStorage.getItem(KEY) || '{}'); }catch(e){ return {}; } },
    save(items){ try{ localStorage.setItem(KEY, JSON.stringify(items)); return true; }catch(e){ return false; } }
  };
  let backend = localBackend, items = {}, rev = 1, lastError = '';
  const subs = new Set();
  const now = () => new Date().toISOString();
  const normFolio = f => String(f == null ? '' : f).replace(/\D/g, '').padStart(13, '0').slice(-13);
  function cleanItem(x, f){
    if(!x || typeof x !== 'object') return null;
    const folio = normFolio(x.folio || f); if(!/^\d{13}$/.test(folio) || /^0+$/.test(folio)) return null;
    const t = v => (typeof v === 'string' && !isNaN(Date.parse(v))) ? new Date(v).toISOString() : null;
    const savedAt = t(x.savedAt) || now();
    return { folio, savedAt, updatedAt: t(x.updatedAt) || savedAt,
      status: STATUSES.includes(x.status) ? x.status : 'New', note: typeof x.note === 'string' ? x.note.slice(0, 5000) : '',
      vacant: x.vacant === true, cond: typeof x.cond === 'string' ? x.cond.slice(0, 2000) : '',
      addr: String(x.addr || '').slice(0, 200), city: String(x.city || '').slice(0, 80), zip: String(x.zip || '').slice(0, 10),
      pack: x.pack === 'condo' ? 'condo' : 'main',
      stage: STAGES.includes(x.stage) ? x.stage : 'New', next: isDay(x.next) ? x.next : '',
      acts: sortActs((Array.isArray(x.acts) ? x.acts : []).map(cleanAct).filter(Boolean)).slice(0, 500) };
  }
  function clean(obj){ const out = {}; if(obj && typeof obj === 'object') for(const [f, x] of Object.entries(obj)){ const c = cleanItem(x, f); if(c) out[c.folio] = c; } return out; }
  items = clean(backend.load());
  function emit(why, folio){ rev++; subs.forEach(fn => { try{ fn(why, folio); }catch(e){ console.warn(e); } }); }
  let batching = 0, dirty = false;
  function persist(why, folio){ if(batching){ dirty = true; return true; } lastError = backend.save(items) ? '' : 'Could not write to this browser\'s storage (full or blocked).'; emit(why, folio); return !lastError; }
  window.addEventListener('storage', e => { if(e.key === KEY){ items = clean(backend.load()); emit('external'); } });   // another tab changed the list

  const api = {
    STATUSES, STAGES, ACT_TYPES, OUTCOMES, KEY,
    get rev(){ return rev; }, get error(){ return lastError; },
    /* run many add/update/logActivity calls with one storage write + one change event (bulk Mark as sent) */
    batch(fn){ batching++; try{ fn(); } finally { batching--; if(!batching && dirty){ dirty = false; persist('batch'); } } },
    has: f => !!items[f], get: f => items[f] || null, count: () => Object.keys(items).length,
    list: () => Object.values(items).sort((a, b) => b.savedAt < a.savedAt ? -1 : 1),
    add(f, info){ if(items[f]) return items[f]; const t = now(); items[f] = cleanItem({ ...info, folio: f, savedAt: t, updatedAt: t, status: 'New', note: '', vacant: false, cond: '' }); persist('add', f); return items[f]; },
    update(f, patch){ if(!items[f]) return null; const c = cleanItem({ ...items[f], ...patch, folio: f, savedAt: items[f].savedAt, updatedAt: now() }); if(c){ items[f] = c; persist('update', f); } return items[f]; },
    remove(f){ if(!items[f]) return; delete items[f]; persist('remove', f); },
    /* outreach: logging on an unsaved property saves it first; the first contact moves a New lead to Contacted */
    logActivity(f, act, info){ const a = cleanAct(act); if(!a) return null; if(!items[f]) api.add(f, info || {}); const cur = items[f];
      const acts = sortActs([a, ...cur.acts.filter(x => x.id !== a.id)]).slice(0, 500), patch = { acts };
      if(cur.stage === 'New' && a.type !== 'note' && a.outcome !== 'Sent to list') patch.stage = 'Contacted'; if(a.outcome === 'Offer made' && ['New','Contacted','Follow-up'].includes(cur.stage)) patch.stage = 'Offer';
      api.update(f, patch); return a; },
    removeActivity(f, id){ if(!items[f]) return; api.update(f, { acts: items[f].acts.filter(x => x.id !== id) }); },
    lastTouch: f => { const x = items[f]; return x && x.acts.find(a => a.type !== 'note' && a.outcome !== 'Sent to list') || null; },
    /* due: next follow-up today or earlier on a lead that is still open */
    dueState(f, today){ const x = items[f]; if(!x || !x.next || x.stage === 'Closed' || x.stage === 'Dead') return null; const t = today || new Date().toLocaleDateString('en-CA');
      const days = Math.round((Date.parse(t) - Date.parse(x.next)) / 864e5); return days < 0 ? null : { days, overdue: days > 0 }; },
    toggle(f, info){ if(items[f]){ api.remove(f); return false; } api.add(f, info); return true; },
    exportJSON: () => ({ app: 'miami-dade-parcel-finder', kind: 'saved-properties', version: 2, exported: now(), count: api.count(), items: api.list() }),
    /* merge: new folios are added; for folios already saved the copy with the newer updatedAt wins */
    importJSON(data){
      const src = Array.isArray(data) ? data : Array.isArray(data && data.items) ? data.items : (data && typeof data === 'object' ? Object.values(data) : null);
      if(!src) throw new Error('Not a saved-properties file');
      let added = 0, updated = 0, same = 0, bad = 0;
      for(const raw of src){ const c = cleanItem(raw); if(!c){ bad++; continue; }
        const cur = items[c.folio];
        if(!cur){ items[c.folio] = c; added++; }
        else { const ids = new Set(cur.acts.map(a => a.id)), extra = c.acts.filter(a => !ids.has(a.id));   // activity logs merge by id from both sides
          if(c.updatedAt > cur.updatedAt){ const mine = new Set(c.acts.map(a => a.id)); items[c.folio] = { ...c, savedAt: c.savedAt < cur.savedAt ? c.savedAt : cur.savedAt, acts: sortActs([...c.acts, ...cur.acts.filter(a => !mine.has(a.id))]).slice(0, 500) }; updated++; }
          else if(extra.length){ items[c.folio] = { ...cur, acts: sortActs([...cur.acts, ...extra]).slice(0, 500) }; updated++; }
          else same++; } }
      if(added || updated) persist('import');
      return { added, updated, same, bad };
    },
    use(b){ if(!b || typeof b.load !== 'function' || typeof b.save !== 'function') throw new Error('backend needs load() and save()');
      const local = items; backend = b; items = clean(b.load()); api.importJSON(Object.values(local)); emit('backend'); },
    onChange(fn){ subs.add(fn); return () => subs.delete(fn); }
  };
  window.PFSaved = api;
})();
