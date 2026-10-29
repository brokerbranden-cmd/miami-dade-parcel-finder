/* Smarter Contact export (mass texting at smartercontact.com): one CSV row per owner with that owner's skip traced phones, best first (grade, then mobile first),
   in Smarter Contact's own column names so its upload mapper lines them up by itself (First Name, Last Name, Phone 1-10, Email,
   Property / Mailing Address + City / State / Zip, APN, Parcel County, Parcel State) plus custom fields (Folio, Company, Owner Name,
   County, Properties, All Folios; Puerto Rico adds Barrio last). Sources: current results, the saved list / open folder, or the
   Skip traced view. Left out: rows with no usable phone, numbers flagged DNC / litigator by the provider, disconnected / Wrong number
   (grade F), and numbers already sent to Smarter Contact (unless "Include already sent" is ticked). After the download the orange bar
   offers "Mark as sent" to Smarter Contact: that stores the sent numbers (per property, in the Send-to store, so it syncs with the
   team on the private site) and logs a Text entry in each property's outreach history.
   Nothing is uploaded anywhere: the CSV is built in this browser. Pure logic in PFSC.build (unit tested: tests/unit_smartercontact.js). */
(function (root) {
  'use strict';
  const MAXPH = 10;   // Smarter Contact maps up to 10 phone numbers per upload row (each becomes its own contact record)
  const HEAD = ['First Name', 'Last Name', ...Array.from({ length: MAXPH }, (_, k) => 'Phone ' + (k + 1)), 'Email',
    'Property Address', 'Property City', 'Property State', 'Property Zip', 'Mailing Address', 'Mailing City', 'Mailing State', 'Mailing Zip',
    'APN', 'Parcel County', 'Parcel State', 'Folio', 'Company', 'Owner Name', 'County', 'Properties', 'All Folios'];
  const PR_HEAD = ['Barrio'];   // Puerto Rico only, after every shared column
  const GRADE_ORDER = { 'A+': 0, A: 1, B: 2, C: 3, F: 4 };

  // 10-digit US / PR number or ''
  function norm10(v) { let d = String(v == null ? '' : v).replace(/\D/g, ''); if (d.length === 11 && d[0] === '1') d = d.slice(1); return d.length === 10 && !/^[01]/.test(d) ? d : ''; }

  // owner -> {first, last, company}. Individuals: their first / last. LLC / trust / government: the entity goes in Last Name and Company,
  // First Name is "Owner" (or blank, opts.entityFirst = ''), unless the skip trace provider returned the person behind the number.
  function names(SK, owner, provName, opts) {
    const T = s => SK.title(s); const o = SK.parseOwner(owner, { order: opts.order, gov: !!opts.gov });
    if (!o.isCompany && (o.first || o.last)) return { first: T(o.first), last: T(o.last), company: '' };
    const co = o.isCompany ? T(o.company) : '';
    const [a, b] = SK.splitName(String(provName || '').replace(/[^A-Za-z\u00C0-\u024F' .-]+/g, ' ').trim(), 'first-last');
    if (a && b && !/\b(LLC|INC|CORP|TRUST|BANK|LTD)\b/i.test(provName)) return { first: T(a), last: T(b), company: co };
    const ef = opts.entityFirst == null ? 'Owner' : opts.entityFirst;
    if (co) return { first: ef, last: co, company: co };
    return { first: ef, last: T(String(owner || '').split(/\s*\|\s*/)[0]), company: '' };
  }

  /* items: [{id, x:{folio, addr, city, zip, owner, mail, gov}}]
     env: {SK, rec(folio) -> skip record, res(num) -> 'reached'|'wrong'|'', sentPh: Set of numbers already sent to Smarter Contact,
           sentAll: Set of folios marked sent with no number list (whole property counts as sent), badEmail(e), folioOut(f),
           county, state, order, muni (PR municipio)}
     opts: {includeSent, noLandline, entityFirst, pr}
     -> {head, rows: [{vals, folios, phones}], folios: [...], idmap: Map(folio -> id), phByFolio: {folio: [nums]}, n: counts} */
  function build(items, env, opts) {
    const SK = env.SK; opts = opts || {};
    const n = { items: items.length, noTrace: 0, noPhone: 0, dnc: 0, bad: 0, land: 0, sent: 0, dupe: 0, owners: 0, rows: 0, phones: 0 };
    const groups = new Map(), order = [];
    for (const it of items) {
      const x = it.x, r = env.rec(x.folio); if (!r) { n.noTrace++; continue; } if (!r.p || !r.p.length) { n.noPhone++; continue; }
      const k = SK.ownerGroupKey(x.owner || r.n || x.folio, x.mail, x.addr, { order: env.order, gov: x.gov });
      let g = groups.get(k); if (!g) { groups.set(k, g = { x, r, items: [] }); order.push(g); } g.items.push(it);
    }
    n.owners = order.length;
    const used = new Set(), rows = [], folios = new Set(), idmap = new Map(), phByFolio = {};
    for (const g of order) {
      const cand = [];
      for (let gi = 0; gi < g.items.length; gi++) {
        const it = g.items[gi], f = it.x.folio, r = env.rec(f);
        const G = r.p.map((q, i) => ({ q, i, g: SK.gradeOf(q, i, env.res(q[0]) || '') })).sort((a, b) => GRADE_ORDER[a.g] - GRADE_ORDER[b.g] || a.i - b.i);
        for (const c of G) { const num = norm10(c.q[0]); if (!num) continue; cand.push({ num, t: c.q[1] || '', fl: c.q[2] | 0, g: c.g, gi, i: c.i, f, sentHere: env.sentAll.has(f) }); }
      }
      const TR = t => (t === 'm' ? 0 : t === 'l' ? 2 : 1);   // texting: mobile before unknown / VoIP before landline inside a grade
      cand.sort((a, b) => GRADE_ORDER[a.g] - GRADE_ORDER[b.g] || TR(a.t) - TR(b.t) || a.gi - b.gi || a.i - b.i);
      const ph = [], seen = new Set();
      for (const c of cand) {
        if (seen.has(c.num)) continue; seen.add(c.num);
        if (c.g === 'F') { n.bad++; continue; }                     // disconnected / marked Wrong number
        if (c.fl & 3) { n.dnc++; continue; }                       // provider: DNC / litigator
        if (opts.noLandline && c.t === 'l') { n.land++; continue; }
        if (!opts.includeSent && (env.sentPh.has(c.num) || c.sentHere)) { n.sent++; continue; }
        if (used.has(c.num)) { n.dupe++; continue; }                // same number already on another row of this file
        if (ph.length < MAXPH) ph.push(c);
      }
      if (!ph.length) continue;
      ph.forEach(c => used.add(c.num));
      const x = g.x, r = g.r, nm = names(SK, x.owner, r.n, { order: env.order, gov: x.gov, entityFirst: opts.entityFirst });
      const m = SK.parseMailing(x.mail); const fs = g.items.map(it => it.x.folio), fo = fs.map(f => env.folioOut(f));
      let email = ''; for (const it of g.items) { const rr = env.rec(it.x.folio); for (const e of (rr && rr.e) || []) if (!email && !env.badEmail(e)) email = e; }
      const city = opts.pr ? (env.muni || x.city || '') : (/unincorporated/i.test(x.city || '') ? '' : (x.city || ''));
      const vals = [nm.first, nm.last, ...Array.from({ length: MAXPH }, (_, k) => ph[k] ? ph[k].num : ''), email,
        x.addr || '', city, env.state, SK.zip5(x.zip) || x.zip || '', m.street, m.city, m.state, m.zip,
        fo[0], env.county, env.state, fo[0], nm.company, String(x.owner || '').split(' | ').filter(Boolean).join('; '), env.county, fs.length, fo.join(';')];
      if (opts.pr) vals.push(x.city && x.city !== env.muni ? x.city : '');
      rows.push({ vals, folios: fs, phones: ph.map(c => c.num) });
      for (const it of g.items) { folios.add(it.x.folio); if (it.id != null) idmap.set(it.x.folio, it.id); phByFolio[it.x.folio] = ph.map(c => c.num); }
      n.phones += ph.length;
    }
    n.rows = rows.length;
    return { head: opts.pr ? HEAD.concat(PR_HEAD) : HEAD.slice(), rows, folios: [...folios], idmap, phByFolio, n };
  }

  // numbers already sent to Smarter Contact, from the Send-to store's sent records: {folio: {sc: {d, t, list, ph: [...]}}}
  function sentSets(sent) {
    const ph = new Set(), all = new Set();
    for (const f in sent || {}) { const s = sent[f] && sent[f].sc; if (!s) continue; if (Array.isArray(s.ph) && s.ph.length) s.ph.forEach(p => ph.add(p)); else all.add(f); }
    return { ph, all };
  }

  root.PFSC = { HEAD, PR_HEAD, MAXPH, norm10, names, build, sentSets, KEY: 'sc', LABEL: 'Smarter Contact' };
  if (typeof module !== 'undefined' && module.exports) { module.exports = root.PFSC; return; }

  /* ---------- page UI ---------- */
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = new Intl.NumberFormat('en-US');
  let modalEl = null;
  function closeModal() { if (modalEl) { modalEl.remove(); modalEl = null; document.removeEventListener('keydown', onKey, true); } }
  function onKey(e) { if (e.key === 'Escape') closeModal(); }
  function openModal(title, html) {
    if (window.PFSkipUI && PFSkipUI.closeModal) PFSkipUI.closeModal(); closeModal();
    const m = document.createElement('div'); m.className = 'stmodal'; m.id = 'scModal';
    m.innerHTML = `<div class="stbox" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="sth"><h2>${esc(title)}</h2><button type="button" class="btn" data-scclose>Close</button></div><div class="stbody">${html}</div></div>`;
    m.addEventListener('click', e => { if (e.target === m || e.target.closest('[data-scclose]')) closeModal(); });
    document.body.appendChild(m); modalEl = m; document.addEventListener('keydown', onKey, true); return m.querySelector('.stbody');
  }
  const csvq = s => { s = s == null ? '' : String(s); return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  const toCSV = rows => rows.map(r => r.map(csvq).join(',')).join('\r\n') + '\r\n';

  async function open(B, src) {
    const PFC = window.PFCounty, SK = window.PFSkip, ST = SK.store, pr = PFC.id === 'pr';
    const srcs = B.scSources();
    if (!src || !srcs.some(s => s.k === src)) src = srcs[0].k;
    const body = openModal('Smarter Contact export', `
      <p class="note">One row per owner with up to ${MAXPH} skip traced phones (best first), in <b>Smarter Contact's column names</b> (First Name, Last Name, Phone 1-${MAXPH}, Property / Mailing Address…) so its upload mapper matches them by itself. Folio, owner name and county ride along as custom fields. ${esc(PFC.cfg.name)} only: counties are never mixed.</p>
      <div class="stopts">
        <label class="stmax">Export <select id="scSrc" aria-label="Which properties">${srcs.map(s => `<option value="${s.k}" ${s.k === src ? 'selected' : ''}>${esc(s.label)}</option>`).join('')}</select></label>
        <label class="check"><input type="checkbox" id="scSent"> Include already sent (numbers sent to Smarter Contact before)</label>
        <label class="check"><input type="checkbox" id="scLand"> Leave out landlines (Smarter Contact puts landlines in a separate “_landline” group for its dialer)</label>
        <label class="stmax">LLC / trust owners: First Name <select id="scEnt" aria-label="First Name for company owners"><option value="Owner">“Owner”</option><option value="">blank</option></select></label>
      </div>
      <div class="stwarn" role="note"><b>DNC / litigator numbers and wrong / disconnected numbers are always left out.</b> Smarter Contact also scrubs opt-outs, litigators and the National DNC list during its phone verification; keep those filters on. Texting rules (TCPA, Florida's telephone solicitation law) are your responsibility. Reminder only, not legal advice.</div>
      <div class="stcounts" id="scCounts" aria-live="polite">Preparing…</div>
      <div class="stact"><button type="button" class="btn primary" id="scGo" disabled>Download Smarter Contact CSV</button><button type="button" class="btn" data-scclose>Cancel</button></div>`);
    const q = id => body.querySelector('#' + id); let plan = null, token = 0;
    async function compute() {
      const my = ++token; plan = null; q('scGo').disabled = true; q('scCounts').textContent = 'Preparing…';
      let items; try { items = await B.scItems(q('scSrc').value); } catch (e) { q('scCounts').textContent = 'The property details did not load. Close and try again.'; return; }
      if (my !== token) return;
      const ss = sentSets(B.sentAll()), res = SK.callResult;
      const env = { SK, rec: f => ST.get(f), res: num => res(num), sentPh: ss.ph, sentAll: ss.all, badEmail: e => !!(window.PFSkipUI && PFSkipUI.isBad && PFSkipUI.isBad(e)),
        folioOut: B.folioOut, county: PFC.cfg.name, state: PFC.cfg.state || 'FL', order: B.order, muni: (window.PF && PF.META && PF.META.municipio) || '' };
      plan = build(items, env, { includeSent: q('scSent').checked, noLandline: q('scLand').checked, entityFirst: q('scEnt').value, pr });
      const n = plan.n, props = plan.folios.length;
      const noPh = (items.total || n.items) - n.items + n.noTrace + n.noPhone; const out = [noPh ? fmt.format(noPh) + (noPh === 1 ? ' property' : ' properties') + ' with no phone from skip tracing' : '', n.dnc ? fmt.format(n.dnc) + ' DNC / litigator ' + (n.dnc === 1 ? 'number' : 'numbers') : '', n.bad ? fmt.format(n.bad) + ' wrong / disconnected' : '',
        n.land ? fmt.format(n.land) + ' landlines' : '', n.sent ? fmt.format(n.sent) + ' already sent to Smarter Contact' : '', n.dupe ? fmt.format(n.dupe) + ' repeat numbers' : ''].filter(Boolean);
      q('scCounts').innerHTML = `<b>${fmt.format(n.rows)} ${n.rows === 1 ? 'owner' : 'owners'}</b> with ${fmt.format(n.phones)} ${n.phones === 1 ? 'number' : 'numbers'} for ${fmt.format(props)} ${props === 1 ? 'property' : 'properties'} (of ${fmt.format(items.total || n.items)} in this list).` +
        (out.length ? `<br><span class="note">Left out: ${out.join(', ')}.</span>` : '') + (n.rows ? '' : '<br>Nothing to export with these options.');
      q('scGo').disabled = !n.rows;
    }
    body.addEventListener('change', e => { if (e.target.closest('.stopts')) compute(); });
    q('scGo').onclick = () => {
      if (!plan || !plan.rows.length) return; const day = B.dayStr(new Date()), p = plan;
      B.download(`smarter-contact-${PFC.id}${pr && PFC.cfg.muni ? '-' + PFC.cfg.muni : ''}-${p.rows.length}-${day.replace(/-/g, '')}.csv`, new Blob([toCSV([p.head, ...p.rows.map(r => r.vals)])], { type: 'text/csv' }));
      B.setPending({ folios: p.folios, ids: p.idmap, day, team: 'sc', list: 'Smarter Contact ' + day, ph: p.phByFolio, what: `${fmt.format(p.rows.length)} owners (${fmt.format(p.n.phones)} numbers, ${fmt.format(p.folios.length)} properties) for Smarter Contact` });
      B.toast(`${fmt.format(p.rows.length)} owners exported for Smarter Contact`); closeModal();
    };
    compute();
  }
  function wire(B) {
    if (!B || !B.scItems) return;
    document.addEventListener('click', e => { const b = e.target.closest('[data-scexport]'); if (!b) return; e.preventDefault(); open(B, b.dataset.scexport).catch(err => { console.error(err); B.toast('Smarter Contact export: ' + (err && err.message || err)); }); });
    root.PFSC.open = src => open(B, src); root.PFSC.close = closeModal;
  }
  const start = () => wire(window.PF && window.PF.skBridge);
  if (window.PF_READY && window.PF) start(); else document.addEventListener('pf:ready', start, { once: true });
})(typeof window !== 'undefined' ? window : globalThis);
