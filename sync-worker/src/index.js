/* Parcel Finder team sync Worker (Cloudflare Worker + D1).
   Keeps the team's saved properties (folders, notes, statuses, outreach logs, Send-to tags) and skip trace results
   (phones / emails / call results) in one shared store so every device and teammate sees the same lists.
   ONLY reachable behind Cloudflare Access: routed at app.prop-hunters.com/sync-api/* (workers_dev is off) and every request must carry a
   valid Access JWT (Cf-Access-Jwt-Assertion header or CF_Authorization cookie, RS256 against https://<team>/cdn-cgi/access/certs, issuer,
   application AUD, expiry) for a user email. Nothing is ever served without it. No personal data is logged (no console.*).
   Settings (wrangler.toml [vars], public identifiers): ACCESS_TEAM_DOMAIN, ACCESS_AUD, ALLOWED_ORIGIN (comma list). D1 binding: DB.
   Data model: one row per (ns, k): ns = the browser storage key it mirrors (county suffix included, so counties never mix), k = record id
   (folio, folder id, 'tags/<folio>', phone number ...), v = the record as JSON text (NULL = deleted), at = edit time (ms, client clock
   corrected to server time), by = email of whoever made that edit (from the Access token), seq = server change counter.
   Merge: last edit wins per record (higher at; ties keep the stored copy).
   API (same origin only):
     GET  /sync-api/me                -> {ok, email, now}
     POST /sync-api/sync  {since, push:[{ns,k,v,at}]}  (header X-PF-Sync: 1)
                                      -> {ok, email, now, cursor, more, changes:[{ns,k,v,at,by,seq}], accepted, rejected} */
const NS_RE = /^(?:(?:mdpf\.saved\.v1|mdpf\.folders\.v1|pf\.send\.v1|pf\.skip\.v1)(?:\.[a-z][a-z0-9-]{0,30})?|pf\.phoneres\.v1|pf\.bademail\.v1)$/;
const K_RE = /^[\w.@+\/:-]{1,160}$/;
const MAX_BODY = 1500000, MAX_PUSH = 400, MAX_V = 300000, PAGE = 1500;

const b64u = s => { s = String(s).replace(/-/g, '+').replace(/_/g, '/'); while (s.length % 4) s += '='; const b = atob(s), u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; };
let certCache = { url: '', at: 0, keys: [] };
async function accessKeys(url, fetchImpl, force) {
  if (!force && certCache.url === url && Date.now() - certCache.at < 3600e3 && certCache.keys.length) return certCache.keys;
  const r = await fetchImpl(url, { headers: { Accept: 'application/json' } });
  if (!r.ok) return certCache.url === url ? certCache.keys : [];
  const j = await r.json(); certCache = { url, at: Date.now(), keys: Array.isArray(j && j.keys) ? j.keys : [] };
  return certCache.keys;
}
function accessToken(req) {
  const h = req.headers.get('Cf-Access-Jwt-Assertion'); if (h) return h.trim();
  const m = (req.headers.get('Cookie') || '').match(/(?:^|;\s*)CF_Authorization=([^;]+)/); return m ? m[1].trim() : '';
}
// -> lower-case email of a valid Access login for this application, else ''
async function accessEmail(req, env, fetchImpl) {
  const team = String(env.ACCESS_TEAM_DOMAIN || '').trim().replace(/^https?:\/\//, '').replace(/\/+$/, ''), aud = String(env.ACCESS_AUD || '').trim();
  if (!team || !aud) return '';
  const tok = accessToken(req); const parts = tok.split('.'); if (parts.length !== 3 || tok.length > 8192) return '';
  let hdr, pl; try { hdr = JSON.parse(new TextDecoder().decode(b64u(parts[0]))); pl = JSON.parse(new TextDecoder().decode(b64u(parts[1]))); } catch (e) { return ''; }
  if (!hdr || hdr.alg !== 'RS256' || !pl) return '';
  const now = Math.floor(Date.now() / 1000);
  if (!(typeof pl.exp === 'number' && pl.exp > now - 30) || (typeof pl.nbf === 'number' && pl.nbf > now + 30)) return '';
  if (pl.iss !== 'https://' + team) return '';
  const auds = Array.isArray(pl.aud) ? pl.aud : [pl.aud]; if (!auds.includes(aud)) return '';
  const email = typeof pl.email === 'string' ? pl.email.trim().toLowerCase() : '';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 200) return '';   // people only (service tokens carry no email)
  const certs = String(env.ACCESS_CERTS_URL || '') || 'https://' + team + '/cdn-cgi/access/certs';
  for (const force of [false, true]) {
    let keys; try { keys = await accessKeys(certs, fetchImpl, force); } catch (e) { return ''; }
    const jwk = keys.find(k => k && k.kid === hdr.kid && k.kty === 'RSA');
    if (!jwk) continue;
    try {
      const key = await crypto.subtle.importKey('jwk', { kty: 'RSA', n: jwk.n, e: jwk.e, alg: 'RS256', ext: true }, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
      const ok = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, b64u(parts[2]), new TextEncoder().encode(parts[0] + '.' + parts[1]));
      if (!ok) return '';
      // Access also sends the email in a header; if present it must agree with the signed token
      const hEmail = (req.headers.get('Cf-Access-Authenticated-User-Email') || '').trim().toLowerCase();
      return hEmail && hEmail !== email ? '' : email;
    } catch (e) { return ''; }
  }
  return '';
}

const HDR = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'X-Robots-Tag': 'noindex' };
const json = (obj, status) => new Response(JSON.stringify(obj), { status: status || 200, headers: HDR });

export const SCHEMA = [
  'CREATE TABLE IF NOT EXISTS rec (ns TEXT NOT NULL, k TEXT NOT NULL, v TEXT, at INTEGER NOT NULL, by TEXT NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY (ns, k))',
  'CREATE INDEX IF NOT EXISTS rec_seq ON rec (seq)',
  'CREATE TABLE IF NOT EXISTS ctr (id INTEGER PRIMARY KEY, seq INTEGER NOT NULL)',
  'INSERT OR IGNORE INTO ctr (id, seq) VALUES (1, 0)'
];
let schemaOk = false;
async function ensureSchema(db) { if (schemaOk) return; await db.batch(SCHEMA.map(s => db.prepare(s))); schemaOk = true; }

function cleanPush(list) {
  const out = new Map();
  for (const x of Array.isArray(list) ? list : []) {
    if (!x || typeof x !== 'object' || typeof x.ns !== 'string' || typeof x.k !== 'string' || !NS_RE.test(x.ns) || !K_RE.test(x.k)) continue;
    const at = Math.floor(Number(x.at)); if (!(at >= 1 && at < 8.64e15)) continue;
    let v = null; if (x.v != null) { if (typeof x.v !== 'string' || x.v.length > MAX_V) continue; try { JSON.parse(x.v); } catch (e) { continue; } v = x.v; }
    const key = x.ns + '\u0001' + x.k, cur = out.get(key); if (!cur || at >= cur.at) out.set(key, { ns: x.ns, k: x.k, v, at });
  }
  return [...out.values()];
}

async function sync(req, env, email) {
  const len = +(req.headers.get('Content-Length') || 0); if (len > MAX_BODY) return json({ error: 'body_too_large' }, 413);
  const text = await req.text(); if (text.length > MAX_BODY) return json({ error: 'body_too_large' }, 413);
  let body; try { body = JSON.parse(text || '{}'); } catch (e) { return json({ error: 'bad_json' }, 400); }
  const since = Math.max(0, Math.floor(Number(body && body.since) || 0));
  const push = cleanPush(body && body.push); if (push.length > MAX_PUSH) return json({ error: 'too_many_items', max: MAX_PUSH }, 413);
  const db = env.DB; await ensureSchema(db);
  let accepted = 0, rejected = [];
  if (push.length) {
    const arr = JSON.stringify(push);
    const res = await db.batch([
      // one statement for the whole push: each record gets its own seq (ctr + position); the stored copy is replaced only by a newer edit
      db.prepare(`INSERT INTO rec (ns, k, v, at, by, seq)
        SELECT json_extract(j.value, '$.ns'), json_extract(j.value, '$.k'), json_extract(j.value, '$.v'), json_extract(j.value, '$.at'), ?2,
               (SELECT seq FROM ctr WHERE id = 1) + j.key + 1
        FROM json_each(?1) AS j WHERE 1
        ON CONFLICT (ns, k) DO UPDATE SET v = excluded.v, at = excluded.at, by = excluded.by, seq = excluded.seq WHERE excluded.at > rec.at`).bind(arr, email),
      db.prepare('UPDATE ctr SET seq = seq + ?1 WHERE id = 1').bind(push.length),
      // pushed records that lost (the stored copy is newer): sent back so the device takes the newer copy
      db.prepare(`SELECT r.ns, r.k, r.v, r.at, r.by, r.seq FROM rec AS r JOIN json_each(?1) AS j
        ON r.ns = json_extract(j.value, '$.ns') AND r.k = json_extract(j.value, '$.k') WHERE r.at > json_extract(j.value, '$.at')`).bind(arr)
    ]);
    accepted = (res[0].meta && res[0].meta.changes) || 0; rejected = res[2].results || [];
  }
  const ch = await db.prepare('SELECT ns, k, v, at, by, seq FROM rec WHERE seq > ?1 ORDER BY seq LIMIT ?2').bind(since, PAGE + 1).all();
  let changes = ch.results || []; const more = changes.length > PAGE; if (more) changes = changes.slice(0, PAGE);
  const cursor = changes.length ? changes[changes.length - 1].seq : since;
  return json({ ok: true, email, now: Date.now(), cursor, more, changes, accepted, rejected });
}

export async function handle(req, env, fetchImpl) {
  fetchImpl = fetchImpl || fetch;
  const url = new URL(req.url), path = url.pathname.replace(/^\/sync-api(?=\/)/, '');
  // same-origin app only: cross-site browser requests are refused (no CORS headers are ever sent)
  const origin = req.headers.get('Origin'), allowed = String(env.ALLOWED_ORIGIN || 'https://app.prop-hunters.com').split(',').map(s => s.trim()).filter(Boolean);
  if (origin && !allowed.includes(origin)) return json({ error: 'forbidden_origin' }, 403);
  if (req.method === 'OPTIONS') return new Response(null, { status: 403 });
  const email = await accessEmail(req, env, fetchImpl);
  if (!email) return json({ error: 'sign_in_required' }, 401);
  if (!env.DB) return json({ error: 'not_configured' }, 503);
  if (path === '/me') return req.method === 'GET' ? json({ ok: true, email, now: Date.now() }) : json({ error: 'method' }, 405);
  if (path === '/sync') {
    if (req.method !== 'POST') return json({ error: 'method' }, 405);
    if (req.headers.get('X-PF-Sync') !== '1' || !/^application\/json\b/i.test(req.headers.get('Content-Type') || '')) return json({ error: 'bad_request' }, 400);
    try { return await sync(req, env, email); } catch (e) { return json({ error: 'store_error' }, 500); }
  }
  return json({ error: 'not_found' }, 404);
}

export default { fetch: (req, env) => handle(req, env) };
export const _test = { handle, accessEmail, cleanPush, NS_RE, _resetCerts: () => { certCache = { url: '', at: 0, keys: [] }; schemaOk = false; } };
