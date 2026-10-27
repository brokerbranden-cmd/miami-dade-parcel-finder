/* Parcel Finder skip trace proxy (Cloudflare Worker, ES module, no dependencies).
   The public site (GitHub Pages) cannot hold a BatchData API key, so the browser sends owner/property rows here with an access code,
   and this Worker calls BatchData's Property Skip Trace (V3) with the key stored as a Worker secret.
   Secrets (set in Cloudflare, never in this repo):  ACCESS_CODE, and BATCHDATA_API_KEY (the BatchData key can instead live in the KV namespace bound as SK_KV, key 'batchdata_key'; KV wins when present)
   Plain variables:  ALLOWED_ORIGIN (default https://brokerbranden-cmd.github.io), MAX_PER_REQUEST (default 50), DAILY_CAP (default 500 records/day, New York day)
   Routes:  GET /health (public, no secrets)   GET /status (access code)   POST /skiptrace (access code)
   Nothing personal is logged or stored: the Durable Object only keeps counters (per day, per IP request times and failed-code times). */

const BD_URL = 'https://api.batchdata.com/api/v3/property/skip-trace';
const DEFAULT_ORIGIN = 'https://brokerbranden-cmd.github.io';
const MAX_BODY = 96 * 1024;
const RATE_PER_MIN = 20, RATE_PER_HOUR = 200;      // requests per IP (each request is up to MAX_PER_REQUEST records)
const FAIL_LIMIT = 8, FAIL_WINDOW = 15 * 60e3;     // wrong access codes per IP before a 15 minute lockout
const UPSTREAM_TIMEOUT = 50e3;

const cfgInt = (v, d, lo, hi) => { const n = parseInt(v, 10); return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : d; };
const conf = env => ({
  origin: String(env.ALLOWED_ORIGIN || DEFAULT_ORIGIN).replace(/\/+$/, ''),
  maxPer: cfgInt(env.MAX_PER_REQUEST, 50, 1, 100),
  cap: cfgInt(env.DAILY_CAP, 500, 0, 1e6)
});
// BatchData key: prefer the value stored in Workers KV (binding SK_KV, key 'batchdata_key'), fall back to the BATCHDATA_API_KEY secret
async function bdKey(env) {
  try { if (env.SK_KV) { const v = await env.SK_KV.get('batchdata_key'); if (v && v.trim()) return v.trim(); } } catch (e) { /* fall back to the secret */ }
  return env.BATCHDATA_API_KEY || '';
}
const nyDay = (d = new Date()) => d.toLocaleDateString('en-CA', { timeZone: 'America/New_York' });

/* ---------- helpers ---------- */
function corsHeaders(req, c) {
  const o = req.headers.get('Origin');
  const h = { 'Vary': 'Origin', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' };
  if (o && o === c.origin) {
    h['Access-Control-Allow-Origin'] = o; h['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS';
    h['Access-Control-Allow-Headers'] = 'Content-Type, X-Access-Code'; h['Access-Control-Max-Age'] = '600';
  }
  return h;
}
const json = (obj, status, h, extra) => new Response(JSON.stringify(obj), { status: status || 200, headers: { 'Content-Type': 'application/json; charset=utf-8', ...h, ...(extra || {}) } });

async function sha256(s) { return new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(String(s)))); }
// constant-time: compare SHA-256 digests (equal length) without early exit
async function codeOk(given, expected) {
  if (!expected) return false;
  const a = await sha256(given || ''), b = await sha256(expected); let d = 0;
  for (let i = 0; i < a.length; i++) d |= a[i] ^ b[i];
  return d === 0;
}
async function limiter(env, op) {
  const stub = env.LIMITER.get(env.LIMITER.idFromName('global'));
  const r = await stub.fetch('https://limiter/op', { method: 'POST', body: JSON.stringify(op) });
  return r.json();
}

/* ---------- input validation / mapping ---------- */
const S = (v, n) => String(v == null ? '' : v).replace(/[\u0000-\u001f]/g, ' ').trim().slice(0, n || 120);
const ST = v => { const s = S(v, 2).toUpperCase(); return /^[A-Z]{2}$/.test(s) ? s : ''; };
const Z5 = v => { const m = String(v == null ? '' : v).match(/\b(\d{5})(?:-\d{4})?\b/); return m ? m[1] : ''; };
function cleanItem(it) {
  if (!it || typeof it !== 'object') return null;
  const id = S(it.id, 40); if (!id) return null;
  const o = { id, first: S(it.first, 60), last: S(it.last, 60), company: S(it.company, 120), street: S(it.street, 120), city: S(it.city, 60), state: ST(it.state) || 'FL', zip: Z5(it.zip),
    mailStreet: S(it.mailStreet, 120), mailCity: S(it.mailCity, 60), mailState: ST(it.mailState), mailZip: Z5(it.mailZip) };
  // BatchData accepts street+city+state, street+zip, or street+city+state+zip
  o.ok = !!o.street && /\d/.test(o.street) && (!!o.zip || !!o.city);
  return o;
}
function toRequest(o, idx) {
  const r = { requestId: String(idx), propertyAddress: { street: o.street, state: o.state } };
  if (o.city) r.propertyAddress.city = o.city; if (o.zip) r.propertyAddress.zip = o.zip;
  if (o.first && o.last && !o.company) r.name = { first: o.first, last: o.last };
  if (o.mailStreet && (o.mailZip || o.mailCity) && o.mailState) { r.mailingAddress = { street: o.mailStreet, state: o.mailState }; if (o.mailCity) r.mailingAddress.city = o.mailCity; if (o.mailZip) r.mailingAddress.zip = o.mailZip; }
  return r;
}
function phoneType(v) { const s = String(v || '').toLowerCase(); if (/mobile|wireless|cell/.test(s)) return 'm'; if (/land|wireline|fixed|residential/.test(s)) return 'l'; if (/voip|internet|virtual/.test(s)) return 'v'; return ''; }
const normPhone = v => { let d = String(v == null ? '' : v).replace(/\D/g, ''); if (d.length === 11 && d[0] === '1') d = d.slice(1); return d.length === 10 && !/^[01]/.test(d) ? d : ''; };
const normEmail = v => { const s = String(v == null ? '' : v).trim().toLowerCase(); return /^[^\s@,;]+@[^\s@,;]+\.[a-z]{2,}$/.test(s) ? s : ''; };
// store shape: phones [[10 digits, 'm'|'l'|'v'|'', flags (1 = DNC, 2 = litigator / TCPA)]], emails [..], name
function mapEntry(d) {
  const persons = (Array.isArray(d && d.persons) ? d.persons : []).filter(p => p && typeof p === 'object' && !p.deceased);
  const owners = persons.filter(p => p.propertyOwner); const use = (owners.length ? owners : persons).slice(0, 3);
  const phones = [], emails = []; let name = '';
  for (const p of use) {
    if (!name && p.name) name = S(p.name.full || [p.name.first, p.name.last].filter(Boolean).join(' '), 80);
    const lit = p.litigator === true;
    const list = (Array.isArray(p.phones) ? p.phones : []).slice().sort((a, b) => (a.rank || 99) - (b.rank || 99));
    // 16 = last reported within 2 years, 32 = older (feeds phone grades in skiptrace.js)
    const recency = d => { const t = Date.parse(d || ''); if (!t) return 0; return Date.now() - t < 730 * 864e5 ? 16 : 32; };
    for (const ph of list) { const n = normPhone(ph.number); if (!n || phones.some(x => x[0] === n)) continue; phones.push([n, phoneType(ph.type), (ph.dnc === true ? 1 : 0) | (lit || ph.tcpa === true ? 2 : 0) | (ph.reachable === true ? 4 : 0) | (ph.reachable === false ? 8 : 0) | recency(ph.lastReportedDate)]); }
    for (const e of Array.isArray(p.emails) ? p.emails : []) { const m = normEmail(e && (e.email || e)); if (m && !emails.includes(m)) emails.push(m); }
  }
  return { phones: phones.slice(0, 8), emails: emails.slice(0, 5), name, hasPerson: persons.length > 0 };
}
// parse BatchData's response into one result per sent request (index = request position)
function parseUpstream(body, sent) {
  const out = new Array(sent.length).fill(null);
  const data = body && body.result && Array.isArray(body.result.data) ? body.result.data : [];
  data.forEach((d, k) => {
    let idx = -1; const rid = d && d.input && d.input.requestId; if (rid != null && /^\d+$/.test(String(rid))) idx = +rid; else if (data.length === sent.length) idx = k;
    if (idx < 0 || idx >= sent.length || out[idx]) return;
    const meta = d.meta || {};
    if (meta.error === true) { out[idx] = { status: 'error', error: 'provider_error' }; return; }
    const m = mapEntry(d);
    if (meta.matched === false || !m.hasPerson) out[idx] = { status: 'nomatch' };
    else if (!m.phones.length && !m.emails.length) out[idx] = { status: 'nocontact', name: m.name };
    else out[idx] = { status: 'match', name: m.name, phones: m.phones, emails: m.emails };
  });
  return out;
}

/* ---------- routes ---------- */
async function handle(req, env, ctx, fetchImpl) {
  const c = conf(env), cors = corsHeaders(req, c), url = new URL(req.url), path = url.pathname.replace(/\/+$/, '') || '/';
  const origin = req.headers.get('Origin');
  if (req.method === 'OPTIONS') return origin === c.origin ? new Response(null, { status: 204, headers: cors }) : new Response(null, { status: 403, headers: cors });
  if (path === '/health' && req.method === 'GET') return json({ ok: true, service: 'parcel-skiptrace', configured: !!((await bdKey(env)) && env.ACCESS_CODE && env.LIMITER) }, 200, cors);
  if (path !== '/skiptrace' && path !== '/status') return json({ error: 'not_found' }, 404, cors);
  if ((path === '/skiptrace' && req.method !== 'POST') || (path === '/status' && req.method !== 'GET')) return json({ error: 'method_not_allowed' }, 405, cors, { Allow: path === '/status' ? 'GET' : 'POST' });
  if (origin && origin !== c.origin) return json({ error: 'forbidden_origin' }, 403, cors);   // browsers from other sites; curl has no Origin
  const apiKey = await bdKey(env);
  if (!env.ACCESS_CODE || !apiKey || !env.LIMITER) return json({ error: 'not_configured' }, 503, cors);

  const ip = req.headers.get('CF-Connecting-IP') || 'unknown', now = Date.now(), day = nyDay();
  const pre = await limiter(env, { op: 'precheck', ip, now });
  if (!pre.ok) return json({ error: pre.reason, retryAfter: pre.retryAfter }, 429, cors, { 'Retry-After': String(pre.retryAfter || 60) });
  if (!(await codeOk(req.headers.get('X-Access-Code'), env.ACCESS_CODE))) {
    await limiter(env, { op: 'fail', ip, now });
    return json({ error: 'bad_access_code' }, 401, cors);
  }
  const usage = async () => { const u = await limiter(env, { op: 'usage', day }); return { dailyCap: c.cap, usedToday: u.used, remainingToday: Math.max(0, c.cap - u.used), maxPerRequest: c.maxPer }; };
  if (path === '/status') return json({ ok: true, ...(await usage()) }, 200, cors);

  const rl = await limiter(env, { op: 'rate', ip, now, perMin: RATE_PER_MIN, perHour: RATE_PER_HOUR });
  if (!rl.ok) return json({ error: 'rate_limited', retryAfter: rl.retryAfter }, 429, cors, { 'Retry-After': String(rl.retryAfter || 60) });

  const len = +req.headers.get('Content-Length') || 0; if (len > MAX_BODY) return json({ error: 'body_too_large' }, 413, cors);
  let body; try { const t = await req.text(); if (t.length > MAX_BODY) return json({ error: 'body_too_large' }, 413, cors); body = JSON.parse(t); } catch (e) { return json({ error: 'bad_json' }, 400, cors); }
  const raw = Array.isArray(body && body.items) ? body.items : null;
  if (!raw || !raw.length) return json({ error: 'no_items' }, 400, cors);
  if (raw.length > c.maxPer) return json({ error: 'too_many_items', maxPerRequest: c.maxPer }, 413, cors);
  const items = raw.map(cleanItem); if (items.some(x => !x)) return json({ error: 'bad_item' }, 400, cors);
  if (new Set(items.map(x => x.id)).size !== items.length) return json({ error: 'duplicate_ids' }, 400, cors);

  const results = items.map(x => ({ id: x.id })); const sendIdx = [];
  items.forEach((x, i) => { if (x.ok) sendIdx.push(i); else Object.assign(results[i], { status: 'error', error: 'bad_address' }); });
  const meta = { requested: items.length, sent: sendIdx.length, matched: 0, withContact: 0, nomatch: 0, errors: 0 };
  if (sendIdx.length) {
    const rsv = await limiter(env, { op: 'reserve', day, n: sendIdx.length, cap: c.cap });
    if (!rsv.ok) return json({ error: 'daily_cap', dailyCap: c.cap, remainingToday: rsv.remaining }, 429, cors);
    let up = null, failure = '', upStatus = 0, upMsg = '';
    const ac = new AbortController(), timer = setTimeout(() => ac.abort(), UPSTREAM_TIMEOUT);
    try {
      const r = await fetchImpl(BD_URL, { method: 'POST', signal: ac.signal, headers: { 'Authorization': 'Bearer ' + apiKey, 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ requests: sendIdx.map((i, k) => toRequest(items[i], k)), options: { includeTCPABlacklistedPhones: true, prioritizeMobilePhones: true } }) });
      upStatus = r.status;
      if (!r.ok) { try { const eb = await r.json(); upMsg = S(eb && eb.status && eb.status.message, 120); } catch (e) { /* not JSON */ } }
      if (upMsg && apiKey && upMsg.includes(apiKey)) upMsg = '';
      if (r.status === 401 || r.status === 403) failure = 'provider_auth'; else if (r.status === 429) failure = 'provider_rate_limited'; else if (r.status === 402) failure = 'provider_payment'; else if (!r.ok) failure = 'provider_error';
      else { try { up = await r.json(); } catch (e) { failure = 'provider_bad_response'; } }
    } catch (e) { failure = e && e.name === 'AbortError' ? 'provider_timeout' : 'provider_unreachable'; }
    clearTimeout(timer);
    if (failure) { await limiter(env, { op: 'refund', day, n: sendIdx.length }); return json({ error: failure, ...(upStatus ? { upstreamStatus: upStatus } : {}), ...(upMsg ? { upstreamMessage: upMsg } : {}), ...(await usage()) }, failure === 'provider_rate_limited' ? 429 : 502, cors); }
    const parsed = parseUpstream(up, sendIdx);
    sendIdx.forEach((i, k) => { Object.assign(results[i], parsed[k] || { status: 'error', error: 'no_result' }); });
    // billed by BatchData = matched properties with a person; keep the daily cap close to that: refund everything else
    const billed = results.filter(r => r.status === 'match' || r.status === 'nocontact').length;
    if (billed < sendIdx.length) await limiter(env, { op: 'refund', day, n: sendIdx.length - billed });
  }
  for (const r of results) { if (r.status === 'match') { meta.matched++; meta.withContact++; } else if (r.status === 'nocontact') meta.matched++; else if (r.status === 'nomatch') meta.nomatch++; else meta.errors++; }
  meta.billable = meta.matched;
  return json({ ok: true, results, meta, ...(await usage()) }, 200, cors);
}

/* ---------- Durable Object: counters only (SQLite-backed, atomic) ---------- */
export class Limiter {
  constructor(state) { this.s = state.storage; }
  async fetch(req) {
    const o = await req.json(); const s = this.s; let out = { ok: true };
    const prune = (a, win, now) => (Array.isArray(a) ? a : []).filter(t => now - t < win);
    if (o.op === 'precheck') {
      const f = prune(await s.get('f:' + o.ip), FAIL_WINDOW, o.now);
      if (f.length >= FAIL_LIMIT) out = { ok: false, reason: 'locked_out', retryAfter: Math.ceil((FAIL_WINDOW - (o.now - f[0])) / 1000) };
    } else if (o.op === 'fail') {
      const f = prune(await s.get('f:' + o.ip), FAIL_WINDOW, o.now); f.push(o.now); await s.put('f:' + o.ip, f);
    } else if (o.op === 'rate') {
      const r = prune(await s.get('r:' + o.ip), 3600e3, o.now); const m = r.filter(t => o.now - t < 60e3);
      if (m.length >= o.perMin) out = { ok: false, retryAfter: Math.ceil((60e3 - (o.now - m[0])) / 1000) };
      else if (r.length >= o.perHour) out = { ok: false, retryAfter: Math.ceil((3600e3 - (o.now - r[0])) / 1000) };
      else { r.push(o.now); await s.put('r:' + o.ip, r); }
    } else if (o.op === 'usage') {
      out = { ok: true, used: (await s.get('d:' + o.day)) || 0 };
    } else if (o.op === 'reserve') {
      const used = (await s.get('d:' + o.day)) || 0;
      if (used + o.n > o.cap) out = { ok: false, remaining: Math.max(0, o.cap - used) };
      else { await s.put('d:' + o.day, used + o.n); const old = await s.list({ prefix: 'd:' }); for (const k of old.keys()) if (k !== 'd:' + o.day) await s.delete(k); }
    } else if (o.op === 'refund') {
      const used = (await s.get('d:' + o.day)) || 0; await s.put('d:' + o.day, Math.max(0, used - (o.n | 0)));
    }
    return new Response(JSON.stringify(out), { headers: { 'Content-Type': 'application/json' } });
  }
}

export default {
  async fetch(req, env, ctx) {
    try { return await handle(req, env, ctx, fetch); }
    catch (e) { return new Response(JSON.stringify({ error: 'internal_error' }), { status: 500, headers: { 'Content-Type': 'application/json', ...corsHeaders(req, conf(env)) } }); }   // never echo the exception
  }
};
export const _test = { handle, parseUpstream, mapEntry, cleanItem, toRequest, codeOk, conf, Limiter };
