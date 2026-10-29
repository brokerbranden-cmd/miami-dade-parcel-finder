/* Team sync for the private site (https://app.prop-hunters.com, behind Cloudflare Access).
   Mirrors the per-county browser stores of saved properties (mdpf.saved.v1*: notes, statuses, outreach logs; mdpf.folders.v1*),
   Send-to tags / sent marks (pf.send.v1*) and skip trace results (pf.skip.v1*: phones / emails) plus call results (pf.phoneres.v1)
   and bad-email marks (pf.bademail.v1) to the parcel-sync Worker (D1) at /sync-api, one record per folio / folder / number.
   - local first: the app keeps reading and writing localStorage exactly as before; this file notices writes (Storage.setItem hook),
     stamps the changed records (time + who) and pushes them; remote changes are written back and the stores reload.
   - last edit wins per record (time on the server's clock); deletes travel as tombstones; first sync on a device pushes everything
     already saved there (older copies never overwrite newer ones on the server).
   - offline: changes wait in an outbox (pf.sync.out) and go up when the connection is back.
   - the public GitHub Pages copy never syncs (no sign-in there): it only shows "sign in at app.prop-hunters.com to sync".
   Personal data (phones / emails) only ever goes to the Access-protected same-origin Worker; nothing is logged. */
(function () {
  'use strict';
  const HOST = 'app.prop-hunters.com', APP_URL = 'https://' + HOST + '/';
  let ls = null; try { ls = window.localStorage; } catch (e) {}
  const lsGet = k => { try { return ls ? ls.getItem(k) : null; } catch (e) { return null; } };
  const TEST = lsGet('pf.sync.test') === '1';   // e2e tests on a local server only (the Worker still demands an Access login)
  const ON = !!ls && (location.hostname === HOST || TEST) && typeof fetch === 'function';
  const API = (TEST && lsGet('pf.sync.api')) || '/sync-api';
  const NS_RE = /^(?:(?:mdpf\.saved\.v1|mdpf\.folders\.v1|pf\.send\.v1|pf\.skip\.v1)(?:\.[a-z][a-z0-9-]{0,30})?|pf\.phoneres\.v1|pf\.bademail\.v1)$/;
  const K_RE = /^[\w.@+\/:-]{1,160}$/;
  const st = { on: ON, state: ON ? 'starting' : 'local', user: '', last: 0, pending: 0, error: '' };
  const subs = new Set();
  const api = window.PFSync = {
    get on() { return st.on; }, get user() { return st.user; }, get state() { return st.state; }, get pending() { return st.pending; }, get last() { return st.last; },
    APP_URL, who: e => String(e || '').split('@')[0], onChange(fn) { subs.add(fn); return () => subs.delete(fn); }, syncNow: () => syncNow(), status: () => ({ ...st })
  };
  const emitStatus = () => { subs.forEach(fn => { try { fn(st); } catch (e) {} }); paint(); };

  /* ---------- record views of each store ---------- */
  const base = ns => (ns.match(/^(?:mdpf\.saved|mdpf\.folders|pf\.send|pf\.skip|pf\.phoneres|pf\.bademail)\.v1/) || [''])[0];
  const parse = s => { try { return s ? JSON.parse(s) : null; } catch (e) { return null; } };
  function split(ns, o) {
    const b = base(ns), out = {};
    if (b === 'mdpf.folders.v1') { for (const x of Array.isArray(o) ? o : []) if (x && typeof x.id === 'string') out[x.id] = x; return out; }
    if (b === 'pf.send.v1') { if (o && typeof o === 'object') for (const t of ['tags', 'sent']) if (o[t] && typeof o[t] === 'object') for (const [f, v] of Object.entries(o[t])) out[t + '/' + f] = v; return out; }
    if (o && typeof o === 'object' && !Array.isArray(o)) for (const [k, v] of Object.entries(o)) out[k] = v;
    return out;
  }
  function join(ns, recs) {
    const b = base(ns);
    if (b === 'mdpf.folders.v1') return Object.keys(recs).sort((x, y) => x === 'default' ? -1 : y === 'default' ? 1 : x.length - y.length || (x < y ? -1 : 1)).map(k => recs[k]);
    if (b === 'pf.send.v1') { const o = { tags: {}, sent: {} }; for (const [k, v] of Object.entries(recs)) { const i = k.indexOf('/'); const t = k.slice(0, i); if (o[t]) o[t][k.slice(i + 1)] = v; } return o; }
    return recs;
  }
  const seedAt = (ns, v) => { const t = v && (Date.parse(v.updatedAt) || Date.parse(v.savedAt)); return t > 0 ? t : 1; };   // first sync: never newer than a real edit elsewhere
  function hash(s) { let h = 0x811c9dc5; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); } return (h >>> 0).toString(36) + '.' + s.length; }

  /* ---------- move data between sites by file (public github.io copy -> app.prop-hunters.com; their browser stores are separate) ---------- */
  function syncedKeys() { const a = []; try { for (let i = 0; i < ls.length; i++) { const k = ls.key(i); if (NS_RE.test(k)) a.push(k); } } catch (e) {} return a.sort(); }
  function backup() {
    const stores = {}; let n = 0;
    for (const k of syncedKeys()) { const v = parse(lsGet(k)); if (v == null) continue; const c = Object.keys(split(k, v)).length; if (!c) continue; stores[k] = v; n += c; }
    const blob = new Blob([JSON.stringify({ app: 'parcel-finder', kind: 'browser-backup', version: 1, exported: new Date().toISOString(), from: location.host, stores })], { type: 'application/json' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'parcel-finder-backup-' + new Date().toISOString().slice(0, 10) + '.json';
    document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
    return n;
  }
  // merge: anything missing here is added; a saved property already here keeps whichever copy was edited last; other records already here are kept
  function restore(data) {
    const src = data && data.kind === 'browser-backup' && data.stores && typeof data.stores === 'object' ? data.stores : null;
    if (!src) throw new Error('Not a Parcel Finder backup file');
    let added = 0, updated = 0; const touched = [];
    for (const [ns, v] of Object.entries(src)) {
      if (!NS_RE.test(ns)) continue;
      const inc = split(ns, v), cur = split(ns, parse(lsGet(ns))), saved = base(ns) === 'mdpf.saved.v1'; let ch = false;
      for (const [k, x] of Object.entries(inc)) {
        if (!K_RE.test(k) || x == null) continue;
        if (!(k in cur)) { cur[k] = x; added++; ch = true; }
        else if (saved && String(x.updatedAt || '') > String(cur[k].updatedAt || '')) { cur[k] = x; updated++; ch = true; }
      }
      if (ch) { ls.setItem(ns, JSON.stringify(join(ns, cur))); touched.push(ns); }
    }
    try { if (window.PFSaved && window.PFSaved.reload) window.PFSaved.reload(); } catch (e) {}
    try { const K = window.PFSkip && window.PFSkip.store; if (K && K.reload) K.reload(); } catch (e) {}
    try { window.dispatchEvent(new CustomEvent('pf-sync', { detail: { ns: touched } })); } catch (e) {}
    return { added, updated };
  }
  function pickRestore() {
    const i = document.createElement('input'); i.type = 'file'; i.accept = '.json,application/json'; i.style.display = 'none'; document.body.appendChild(i);
    i.addEventListener('change', () => { const f = i.files && i.files[0]; i.remove(); if (!f) return;
      f.text().then(t => { const r = restore(JSON.parse(t)); msg('Restored: ' + r.added + ' added, ' + r.updated + ' updated' + (ON ? ', syncing to your team.' : '.')); if (ON) syncSoon(300); })
        .catch(e => msg('Could not restore: ' + (e && e.message || e))); });
    i.click();
  }
  let lastMsg = '';
  function msg(t) { lastMsg = t; const n = document.getElementById('svSyncMsg'); if (n) n.textContent = t; try { if (typeof window.toast === 'function') window.toast(t); } catch (e) {} }
  api.backup = backup; api.restore = restore;
  document.addEventListener('click', e => { const b = e.target && e.target.closest && e.target.closest('[data-pfsync]'); if (!b) return; e.preventDefault();
    if (b.dataset.pfsync === 'backup') { const n = backup(); msg(n ? 'Backup downloaded (' + n + ' records). It holds phone numbers and emails: delete it once restored.' : 'Nothing saved in this browser yet.'); }
    else if (b.dataset.pfsync === 'restore') pickRestore(); });

  /* ---------- status in the page ---------- */
  function paint() {
    const n = document.getElementById('svSyncNote');
    if (n) n.innerHTML = !ON ? 'Your saved list and skip trace results live in this browser only. To have them on all your devices and shared with your team, sign in at <a href="' + APP_URL + '" target="_blank" rel="noopener">app.prop-hunters.com</a>. Moving to the app? <button type="button" class="lnk" data-pfsync="backup">Download a backup</button> of everything in this browser (saved list, folders, notes, outreach, Send-to tags, skip trace results, all counties), then use Restore backup on app.prop-hunters.com. <span id="svSyncMsg">' + esc(lastMsg) + '</span>'
      : 'Saved properties, folders, notes, outreach, Send-to tags and skip trace results sync with your team' + (st.user ? ' (signed in as ' + esc(st.user) + ')' : '') + ': ' + esc(label()) + '. Moving from the public site or another browser? <button type="button" class="lnk" data-pfsync="restore">Restore a backup file</button> (merges, nothing is overwritten by an older copy). <span id="svSyncMsg">' + esc(lastMsg) + '</span>';
    if (!ON) return;
    let p = document.getElementById('syncPill');
    if (!p) { const host = document.querySelector('.sb-act'); if (!host) return; p = document.createElement('button'); p.type = 'button'; p.id = 'syncPill'; p.className = 'btn syncpill'; p.addEventListener('click', () => { if (st.state === 'signin') location.reload(); else syncNow(); }); host.insertBefore(p, host.firstChild); }
    p.dataset.state = st.state; p.textContent = short(); p.title = label() + (st.user ? ' · ' + st.user : '') + '. Click to sync now.';
  }
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const tm = t => t ? new Date(t).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) : '';
  function label() { return { starting: 'connecting…', syncing: 'syncing…', ok: 'synced ' + tm(st.last), offline: 'offline, ' + st.pending + ' change' + (st.pending === 1 ? '' : 's') + ' waiting (kept on this device, sent when back online)', signin: 'sign-in expired: reload to sign in again (changes are kept on this device)', error: 'sync problem (' + st.error + '), retrying' }[st.state] || st.state; }
  function short() { return { starting: '⟳ Sync', syncing: '⟳ Syncing', ok: '✓ Synced', offline: '⚠ Offline' + (st.pending ? ' · ' + st.pending : ''), signin: '⚠ Sign in', error: '⚠ Sync' }[st.state] || 'Sync'; }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', paint); else paint();
  if (!ON) return;

  /* ---------- bookkeeping (this device) ---------- */
  const proto = Storage.prototype, oSet = proto.setItem, oRem = proto.removeItem;
  const rawSet = (k, v) => oSet.call(ls, k, v);
  const MK = ns => 'pf.sync.m:' + ns, OUT = 'pf.sync.out', CUR = 'pf.sync.cur', OFF = 'pf.sync.off';
  const metaCache = new Map();
  const meta = ns => { if (!metaCache.has(ns)) metaCache.set(ns, parse(lsGet(MK(ns)))); return metaCache.get(ns); };   // null = never synced on this device
  const saveMeta = (ns, m) => { metaCache.set(ns, m); try { rawSet(MK(ns), JSON.stringify(m)); } catch (e) { st.error = 'storage full'; } };
  let out = parse(lsGet(OUT)) || {};
  const saveOut = () => { try { rawSet(OUT, JSON.stringify(out)); } catch (e) {} st.pending = Object.values(out).reduce((a, o) => a + Object.keys(o).length, 0); };
  let cursor = +lsGet(CUR) || 0, offset = +lsGet(OFF) || 0;
  const srvNow = () => Date.now() + offset;
  saveOut();

  // every synced store: all counties (keys carry the county suffix) + any already in this browser
  function allNs() {
    const s = new Set(['pf.phoneres.v1', 'pf.bademail.v1']), sfx = [''];
    try { for (const c of (window.PFCounty && window.PFCounty.list) || []) if (c && typeof c.storeSuffix === 'string') sfx.push(c.storeSuffix); } catch (e) {}
    for (const b of ['mdpf.saved.v1', 'mdpf.folders.v1', 'pf.send.v1', 'pf.skip.v1']) for (const x of sfx) s.add(b + x);
    try { for (let i = 0; i < ls.length; i++) { const k = ls.key(i); if (NS_RE.test(k)) s.add(k); } } catch (e) {}
    return [...s].filter(k => NS_RE.test(k));
  }

  /* ---------- notice local edits ---------- */
  const dirty = new Map(); let applying = false, dt = null;   // store -> time of its latest write (the edit time, not the time it is sent)
  function mark(k) { if (applying || !NS_RE.test(k)) return; dirty.set(k, srvNow()); clearTimeout(dt); dt = setTimeout(() => { scanDirty(); syncSoon(400); }, 700); }
  proto.setItem = function (k, v) { const r = oSet.call(this, k, v); if (this === ls) mark(String(k)); return r; };
  proto.removeItem = function (k) { const r = oRem.call(this, k); if (this === ls) mark(String(k)); return r; };
  function scanDirty() { for (const k of [...dirty.keys()]) scan(k); }
  function scan(ns) {
    const t = dirty.has(ns) ? dirty.get(ns) : srvNow(); dirty.delete(ns);
    const recs = split(ns, parse(lsGet(ns))), m0 = meta(ns), seed = !m0, m = m0 || {}, o = out[ns] || {}; let ch = false;
    for (const [k, v] of Object.entries(recs)) {
      if (!K_RE.test(k) || v === undefined) continue;
      const h = hash(JSON.stringify(v)), e = m[k];
      if (!e || e[1] !== h) { m[k] = [seed ? seedAt(ns, v) : Math.max(t, e ? e[0] + 1 : 0), h]; o[k] = 1; ch = true; }
    }
    for (const k of Object.keys(m)) if (!(k in recs) && m[k][1] !== 0) { m[k] = [Math.max(t, m[k][0] + 1), 0]; o[k] = 1; ch = true; }
    if (ch || seed) saveMeta(ns, m);
    if (ch) { out[ns] = o; saveOut(); }
  }

  /* ---------- apply remote changes ---------- */
  function apply(list) {
    const by = new Map(); for (const c of list || []) { if (!c || !NS_RE.test(c.ns) || !K_RE.test(c.k)) continue; (by.get(c.ns) || by.set(c.ns, []).get(c.ns)).push(c); }
    const touched = [];
    for (const [ns, cs] of by) {
      scan(ns);   // fold in any unsent local edit first, so it is compared, not lost
      const m = meta(ns) || {}, o = out[ns] || {}, recs = split(ns, parse(lsGet(ns))); let ch = false;
      for (const c of cs) {
        const e = m[c.k], at = +c.at || 0; let v = null;
        if (c.v != null) { v = parse(c.v); if (v == null) continue; }
        const h = v == null ? 0 : hash(JSON.stringify(v));
        if (e && (at < e[0] || (at === e[0] && (e[1] === h || o[c.k])))) continue;   // ours is newer (or the same edit)
        if (v == null) delete recs[c.k]; else recs[c.k] = v;
        m[c.k] = [at, h]; delete o[c.k]; ch = true;
      }
      if (!ch) continue;
      applying = true; try { rawSet(ns, JSON.stringify(join(ns, recs))); } catch (e) { st.error = 'storage full'; } finally { applying = false; }
      saveMeta(ns, m); out[ns] = o; touched.push(ns);
    }
    if (!touched.length) return;
    saveOut();
    // reload the in-memory stores right away (before they write their stale copy back), then let the page redraw
    try { const S = window.PFSaved; if (S && S.reload && touched.some(ns => ns === S.KEY || ns === S.FKEY)) S.reload(); } catch (e) {}
    try { const K = window.PFSkip && window.PFSkip.store; if (K && touched.includes(K.key)) K.reload(); } catch (e) {}
    try { window.dispatchEvent(new CustomEvent('pf-sync', { detail: { ns: touched } })); } catch (e) {}
  }

  /* ---------- talk to the Worker ---------- */
  const MAXN = 300, MAXB = 900000;
  function collect() {
    const push = []; let bytes = 0;
    for (const ns of Object.keys(out)) {
      const o = out[ns], keys = Object.keys(o); if (!keys.length) { delete out[ns]; continue; }
      const recs = split(ns, parse(lsGet(ns))), m = meta(ns) || {};
      for (const k of keys) {
        const e = m[k]; if (!e) { delete o[k]; continue; }
        const v = e[1] === 0 || !(k in recs) ? null : JSON.stringify(recs[k]);
        if (v && v.length > 290000) { delete o[k]; continue; }   // a single record that big is not synced
        if (push.length >= MAXN || bytes + (v ? v.length : 0) + 200 > MAXB) return push;
        push.push({ ns, k, v, at: e[0] }); bytes += (v ? v.length : 0) + 200;
      }
    }
    return push;
  }
  async function call(path, body) {
    const t0 = Date.now();
    const r = await fetch(API + path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-PF-Sync': '1' }, body: JSON.stringify(body), credentials: 'same-origin', cache: 'no-store', redirect: 'manual' }
      : { credentials: 'same-origin', cache: 'no-store', redirect: 'manual' });
    if (r.type === 'opaqueredirect' || r.status === 401 || r.status === 403) { const e = new Error('signin'); e.signin = true; throw e; }
    if (!r.ok) { const e = new Error('http ' + r.status); e.http = r.status; throw e; }
    const j = await r.json();
    if (j && j.now) { offset = Math.round(j.now - (t0 + Date.now()) / 2); try { rawSet(OFF, String(offset)); } catch (e) {} }
    return j;
  }
  let busy = false, again = false, timer = null, fails = 0;
  function setState(s, err) { st.state = s; st.error = err || ''; emitStatus(); }
  async function syncNow() {
    if (busy) { again = true; return; }
    busy = true; clearTimeout(timer);
    try {
      if (!st.user) { const me = await call('/me'); st.user = me.email || ''; }
      setState('syncing');
      for (const ns of allNs()) scan(ns);
      for (let loop = 0; loop < 400; loop++) {
        const push = collect();
        const j = await call('/sync', { since: cursor, push });
        if (j.email) st.user = j.email;
        for (const x of push) { const m = meta(x.ns) || {}; if (out[x.ns] && m[x.k] && m[x.k][0] === x.at) delete out[x.ns][x.k]; }
        saveOut();
        apply(j.rejected); apply(j.changes);
        cursor = j.cursor || cursor; try { rawSet(CUR, String(cursor)); } catch (e) {}
        if (!j.more && !st.pending) break;
        if (!j.more && !push.length) break;
      }
      fails = 0; st.last = Date.now(); setState('ok');
    } catch (e) {
      fails++;
      setState(e && e.signin ? 'signin' : (e && e.http ? 'error' : 'offline'), e && e.http ? 'HTTP ' + e.http : '');
    } finally {
      busy = false;
      if (again) { again = false; syncSoon(300); } else syncSoon(st.state === 'signin' ? 300000 : fails ? Math.min(300000, 5000 * 2 ** Math.min(fails, 6)) : (document.hidden ? 120000 : 20000));
    }
  }
  function syncSoon(ms) { clearTimeout(timer); timer = setTimeout(syncNow, ms); }
  window.addEventListener('online', () => syncSoon(200));
  document.addEventListener('visibilitychange', () => { if (!document.hidden) syncSoon(300); else { scanDirty(); if (st.pending) syncSoon(50); } });
  window.addEventListener('pagehide', () => { clearTimeout(dt); scanDirty(); });
  window.addEventListener('storage', e => { if (e.key && NS_RE.test(e.key)) syncSoon(1500); });   // another tab wrote: it pushes too, this just catches up
  // first sync once the page's stores are up (they read localStorage synchronously while the scripts load)
  if (document.readyState === 'complete') syncSoon(300); else window.addEventListener('load', () => syncSoon(300));
})();
