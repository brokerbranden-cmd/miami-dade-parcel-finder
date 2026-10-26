/* One-click skip tracing through BatchData, via the Parcel Finder Cloudflare Worker (see worker/README.md).
   The BatchData API key lives ONLY in the Worker (a Cloudflare secret). This file holds the per-device access code (localStorage) and talks to the Worker.
   Results are written into the same per-county skip store as the CSV import (PFSkip.store): phones [number, type, flags(1 DNC, 2 litigator/TCPA)], emails, name.
   Pure helpers are exported for node tests (tests/unit_skiptrace_api.js). Not legal advice: DNC / TCPA flags are whatever BatchData returned. */
(function (root) {
  'use strict';
  const SK = root.PFSkip || (typeof require !== 'undefined' ? require('./skiptrace.js') : null);
  const WORKER_URL = 'https://parcel-skiptrace.brokerbranden.workers.dev';
  const CODE_KEY = 'pf.skapi.code.v1', SRC = 'BatchData API';
  const ls = () => { try { return root.localStorage; } catch (e) { return null; } };
  const getCode = () => { try { return (ls().getItem(CODE_KEY) || '').trim(); } catch (e) { return ''; } };
  const persist = () => { try { const st = root.navigator && root.navigator.storage; if (st && st.persist) st.persist().catch(() => {}); } catch (e) {} };
  const setCode = c => { try { ls().setItem(CODE_KEY, String(c || '').trim()); persist(); return true; } catch (e) { return false; } };
  const clearCode = () => { try { ls().removeItem(CODE_KEY); } catch (e) {} };

  class ApiError extends Error { constructor(code, status, data) { super(code); this.code = code; this.status = status || 0; this.data = data || {}; } }
  const MESSAGES = {
    bad_access_code: 'That access code was not accepted.', locked_out: 'Too many wrong codes. Try again in a few minutes.', rate_limited: 'Slow down: too many requests. Try again in a minute.',
    daily_cap: 'Daily skip trace limit reached. It resets at midnight Eastern.', too_many_items: 'That batch was too large.', provider_auth: 'BatchData rejected the Worker\'s API key. Check the key in Cloudflare.',
    provider_rate_limited: 'BatchData is rate limiting requests. Wait a minute and try again.', provider_payment: 'BatchData says the account needs credits or a plan.', provider_error: 'BatchData had an error. Try again shortly.',
    provider_timeout: 'BatchData took too long. Try again.', provider_unreachable: 'Could not reach BatchData. Try again.', provider_bad_response: 'BatchData sent an unreadable response.', not_configured: 'The skip trace Worker is not fully set up.',
    network: 'Could not reach the skip trace service. Check your connection.', forbidden_origin: 'This site is not allowed to use the skip trace service.', body_too_large: 'That batch was too large.', internal_error: 'The skip trace service had an error.'
  };
  const messageFor = e => (e && e.code && MESSAGES[e.code]) || (e && e.message) || 'Skip trace failed.';

  async function call(path, opts) {
    opts = opts || {}; const code = opts.code != null ? opts.code : getCode(); let res;
    try {
      res = await fetch(WORKER_URL + path, { method: opts.body ? 'POST' : 'GET', headers: { 'X-Access-Code': code, ...(opts.body ? { 'Content-Type': 'application/json' } : {}) }, body: opts.body ? JSON.stringify(opts.body) : undefined, signal: opts.signal, cache: 'no-store', credentials: 'omit', referrerPolicy: 'no-referrer' });
    } catch (e) { if (e && e.name === 'AbortError') throw e; throw new ApiError('network', 0); }
    let data = null; try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok || !data || data.ok === false) throw new ApiError((data && data.error) || (res.status === 401 ? 'bad_access_code' : 'internal_error'), res.status, data || {});
    return data;
  }
  const status = (code, signal) => call('/status', { code, signal });

  /* ---------- building requests ---------- */
  // info: {folio, addr, city, zip, owner, mail, gov} (PF.skBridge.info); opts: {order}
  function buildItem(info, opts) {
    opts = opts || {}; const o = SK.parseOwner(info.owner, { order: opts.order, gov: !!info.gov }), m = SK.parseMailing(info.mail);
    const nm = s => SK.title(s);
    return { id: String(info.folio), first: o.isCompany ? '' : nm(o.first), last: o.isCompany ? '' : nm(o.last), company: o.isCompany ? SK.title(o.company) : '',
      street: String(info.addr || '').trim(), city: /unincorporated/i.test(info.city || '') ? '' : String(info.city || ''), state: 'FL', zip: SK.zip5(info.zip) || '',
      mailStreet: m.street || '', mailCity: m.city || '', mailState: m.state || '', mailZip: SK.zip5(m.zip) || '' };
  }
  const hasAddress = it => !!it.street && /\d/.test(it.street) && !!(it.zip || it.city);

  /* ---------- writing results ---------- */
  // group: {id, folios:[...]}; result: one entry of the Worker's results[]
  function applyResult(store, group, r, day) {
    if (!r || (r.status !== 'match' && r.status !== 'nocontact' && r.status !== 'nomatch')) return false;   // errors are not stored, so they can be retried
    const rec = { n: r.name || '', p: r.status === 'match' ? (r.phones || []).map(q => [q[0], q[1] || '', q[2] | 0]) : [], e: r.status === 'match' ? (r.emails || []).slice() : [] };
    for (const f of group.folios) store.merge(f, rec, SRC, day);
    return true;
  }
  const newSummary = () => ({ requested: 0, sent: 0, matched: 0, withContact: 0, nomatch: 0, errors: 0, props: 0, phones: new Set(), emails: new Set(), dnc: new Set(), mobile: 0, noAddress: 0, errorCodes: {}, remaining: null, cancelled: false, stopped: '' });
  function tally(sum, group, r) {
    if (r.status === 'match') { sum.matched++; sum.withContact++; for (const q of r.phones || []) { sum.phones.add(q[0]); if (q[1] === 'm') sum.mobile++; if (q[2] & 3) sum.dnc.add(q[0]); } for (const e of r.emails || []) sum.emails.add(e); sum.props += group.folios.length; }
    else if (r.status === 'nocontact') { sum.matched++; sum.props += group.folios.length; }
    else if (r.status === 'nomatch') { sum.nomatch++; sum.props += group.folios.length; }
    else { sum.errors++; sum.errorCodes[r.error || 'error'] = (sum.errorCodes[r.error || 'error'] || 0) + 1; }
  }
  const sleep = (ms, signal) => new Promise((res, rej) => { const t = setTimeout(res, ms); if (signal) signal.addEventListener('abort', () => { clearTimeout(t); rej(new DOMException('Aborted', 'AbortError')); }, { once: true }); });

  /* run groups ({id, folios, item}) in chunks; every finished chunk is written to the store at once (cancel keeps what is done).
     opts: {store, code, signal, chunk, day, onProgress(doneGroups, totalGroups, sum)} -> summary */
  async function run(groups, opts) {
    const st = opts.store, chunk = Math.max(1, opts.chunk || 50), sum = newSummary(), day = opts.day || new Date().toLocaleDateString('en-CA'); sum.requested = groups.length;
    let done = 0; const byId = new Map(groups.map(g => [g.id, g]));
    for (let i = 0; i < groups.length; i += chunk) {
      if (opts.signal && opts.signal.aborted) { sum.cancelled = true; break; }
      const part = groups.slice(i, i + chunk); let data = null, tries = 0;
      for (;;) {
        try { data = await call('/skiptrace', { code: opts.code, signal: opts.signal, body: { items: part.map(g => g.item) } }); break; }
        catch (e) {
          if (e && e.name === 'AbortError') { sum.cancelled = true; break; }
          if (e instanceof ApiError && e.code === 'rate_limited' && tries++ < 2 && (e.data.retryAfter || 60) <= 30) { try { await sleep((e.data.retryAfter || 5) * 1000 + 250, opts.signal); continue; } catch (e2) { sum.cancelled = true; break; } }
          sum.stopped = e instanceof ApiError ? e.code : 'network'; if (e instanceof ApiError && e.data && e.data.remainingToday != null) sum.remaining = e.data.remainingToday; break;
        }
      }
      if (!data) break;
      sum.sent += data.meta ? data.meta.sent : part.length;
      for (const r of data.results || []) { const g = byId.get(r.id); if (!g) continue; applyResult(st, g, r, day); tally(sum, g, r); }
      st.commit(); done += part.length; if (data.remainingToday != null) sum.remaining = data.remainingToday;
      if (opts.onProgress) opts.onProgress(done, groups.length, sum);
    }
    return sum;
  }
  const api = { WORKER_URL, ApiError, getCode, setCode, clearCode, call, status, buildItem, hasAddress, applyResult, newSummary, tally, run, messageFor, SRC };
  root.PFSkipApi = api; if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
