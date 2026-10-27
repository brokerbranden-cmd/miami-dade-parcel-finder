// Unit tests for the Worker (node >= 18, no network, no secrets). Run: node worker/test/worker.test.mjs
import { _test } from '../src/index.js';
import assert from 'node:assert/strict';
const { handle, parseUpstream, mapEntry, cleanItem, toRequest, codeOk, Limiter } = _test;
let pass = 0, fail = 0;
const t = async (name, fn) => { try { await fn(); pass++; console.log('PASS ' + name); } catch (e) { fail++; console.log('FAIL ' + name + ': ' + (e && e.message)); } };
const FAKEKEY = 'test-key-not-real', CODE = 'correct-horse-battery-staple', ORIGIN = 'https://brokerbranden-cmd.github.io';

function mkEnv(over) {
  const store = new Map();
  const storage = { get: async k => store.get(k), put: async (k, v) => { store.set(k, v); }, delete: async k => { store.delete(k); }, list: async ({ prefix }) => new Map([...store].filter(([k]) => k.startsWith(prefix))) };
  const lim = new Limiter({ storage });
  const env = { BATCHDATA_API_KEY: FAKEKEY, ACCESS_CODE: CODE, DAILY_CAP: '10', MAX_PER_REQUEST: '5', LIMITER: { idFromName: () => 'x', get: () => ({ fetch: (u, init) => lim.fetch(new Request(u, init)) }) }, ...over };
  return { env, store };
}
const item = (id, o) => ({ id, first: 'Ana', last: 'Perez', street: id + ' SW 2 ST', city: 'Miami', state: 'FL', zip: '33130', mailStreet: '1 Main St', mailCity: 'Tampa', mailState: 'FL', mailZip: '33601', ...o });
const person = (o) => ({ propertyOwner: true, name: { first: 'Ana', last: 'Perez', full: 'Ana Perez' }, phones: [
  { rank: 2, number: '305-555-0102', type: 'Land Line', dnc: false, tcpa: false }, { rank: 1, number: '17865550101', type: 'Mobile', dnc: false, tcpa: false },
  { rank: 3, number: '3055550103', type: 'Mobile', dnc: true, tcpa: false }, { rank: 4, number: '3055550104', type: 'VoIP', dnc: false, tcpa: true }], emails: [{ email: 'Ana@Example.com' }], litigator: false, deceased: false, ...o });
const upstreamOf = (sent, fn) => ({ status: { code: 200 }, result: { data: sent.map((r, k) => fn(r, k)), meta: { results: {} } } });
let calls = [];
const mkFetch = (fn, status) => async (url, init) => { const b = JSON.parse(init.body); calls.push({ url, init, b }); return new Response(JSON.stringify(fn(b.requests)), { status: status || 200 }); };
function req(method, path, { code = CODE, origin, body, headers } = {}) {
  const h = { ...(headers || {}) }; if (code != null) h['X-Access-Code'] = code; if (origin) h['Origin'] = origin; if (body !== undefined) h['Content-Type'] = 'application/json';
  return new Request('https://w.example' + path, { method, headers: h, body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined });
}
const run = async (r, env, f) => { const res = await handle(r, env, {}, f || mkFetch(() => ({}))); let j = null; try { j = await res.clone().json(); } catch (e) {} return { res, j }; };
const ok1 = reqs => upstreamOf(reqs, (r) => ({ input: r, persons: [person()], meta: { matched: true, error: false } }));

await t('health is public and reveals no secrets', async () => { const { env } = mkEnv(); const { res, j } = await run(req('GET', '/health', { code: null }), env); assert.equal(res.status, 200); assert.equal(j.ok, true); assert.equal(j.configured, true); const s = JSON.stringify(j); assert.ok(!s.includes(FAKEKEY) && !s.includes(CODE)); });
await t('unknown route 404, wrong method 405', async () => { const { env } = mkEnv(); assert.equal((await run(req('GET', '/nope'), env)).res.status, 404); assert.equal((await run(req('GET', '/skiptrace'), env)).res.status, 405); assert.equal((await run(req('POST', '/status', { body: {} }), env)).res.status, 405); });
await t('CORS: allowed origin echoed, other origin blocked, preflight', async () => {
  const { env } = mkEnv();
  let r = await run(req('GET', '/status', { origin: ORIGIN }), env); assert.equal(r.res.status, 200); assert.equal(r.res.headers.get('Access-Control-Allow-Origin'), ORIGIN);
  r = await run(req('GET', '/status', { origin: 'https://evil.example' }), env); assert.equal(r.res.status, 403); assert.equal(r.res.headers.get('Access-Control-Allow-Origin'), null);
  r = await run(req('OPTIONS', '/skiptrace', { code: null, origin: ORIGIN }), env); assert.equal(r.res.status, 204); assert.match(r.res.headers.get('Access-Control-Allow-Headers'), /X-Access-Code/);
  r = await run(req('OPTIONS', '/skiptrace', { code: null, origin: 'https://evil.example' }), env); assert.equal(r.res.status, 403);
  r = await run(req('GET', '/health', { code: null, origin: 'https://evil.example' }), env); assert.equal(r.res.headers.get('Access-Control-Allow-Origin'), null);
});
await t('access code required; wrong / missing -> 401; constant-time helper', async () => {
  const { env } = mkEnv();
  assert.equal((await run(req('GET', '/status', { code: null }), env)).res.status, 401); assert.equal((await run(req('GET', '/status', { code: 'nope' }), env)).res.status, 401);
  assert.equal((await run(req('POST', '/skiptrace', { code: 'nope', body: { items: [item('1')] } }), env, mkFetch(ok1))).res.status, 401);
  assert.equal(await codeOk('a', 'a'), true); assert.equal(await codeOk('a', 'b'), false); assert.equal(await codeOk('', ''), false); assert.equal(await codeOk(undefined, 'x'), false);
});
await t('lockout after repeated wrong codes (even the right code is held back)', async () => {
  const { env } = mkEnv(); for (let i = 0; i < 8; i++) assert.equal((await run(req('GET', '/status', { code: 'bad' + i }), env)).res.status, 401);
  const r = await run(req('GET', '/status'), env); assert.equal(r.res.status, 429); assert.equal(r.j.error, 'locked_out'); assert.ok(r.res.headers.get('Retry-After'));
});
await t('not configured -> 503 (no key / no code)', async () => { const { env } = mkEnv({ BATCHDATA_API_KEY: '' }); assert.equal((await run(req('GET', '/status'), env)).res.status, 503); });
await t('status reports cap and usage', async () => { const { env } = mkEnv(); const { j } = await run(req('GET', '/status'), env); assert.deepEqual([j.dailyCap, j.usedToday, j.remainingToday, j.maxPerRequest], [10, 0, 10, 5]); });
await t('validation: no items, bad json, too many, duplicate ids, oversize', async () => {
  const { env } = mkEnv();
  assert.equal((await run(req('POST', '/skiptrace', { body: { items: [] } }), env)).j.error, 'no_items');
  assert.equal((await run(req('POST', '/skiptrace', { body: '{bad' }), env)).j.error, 'bad_json');
  let r = await run(req('POST', '/skiptrace', { body: { items: Array.from({ length: 6 }, (_, i) => item('a' + i)) } }), env); assert.equal(r.res.status, 413); assert.equal(r.j.error, 'too_many_items'); assert.equal(r.j.maxPerRequest, 5);
  assert.equal((await run(req('POST', '/skiptrace', { body: { items: [item('1'), item('1')] } }), env)).j.error, 'duplicate_ids');
  assert.equal((await run(req('POST', '/skiptrace', { body: { items: [null] } }), env)).j.error, 'bad_item');
  assert.equal((await run(req('POST', '/skiptrace', { body: { items: [item('1', { street: 'x'.repeat(200000) })] } }), env)).res.status, 413);
});
await t('happy path: maps phones (type, DNC, TCPA), emails, name; key only in upstream header', async () => {
  const { env } = mkEnv(); calls = [];
  const { res, j } = await run(req('POST', '/skiptrace', { origin: ORIGIN, body: { items: [item('100')] } }), env, mkFetch(ok1));
  assert.equal(res.status, 200); assert.equal(calls.length, 1); assert.equal(calls[0].url, 'https://api.batchdata.com/api/v3/property/skip-trace');
  assert.equal(calls[0].init.headers.Authorization, 'Bearer ' + FAKEKEY);
  const sent = calls[0].b; assert.equal(sent.requests.length, 1); assert.deepEqual(sent.requests[0].propertyAddress, { street: '100 SW 2 ST', state: 'FL', city: 'Miami', zip: '33130' }); assert.deepEqual(sent.requests[0].name, { first: 'Ana', last: 'Perez' }); assert.equal(sent.options.includeTCPABlacklistedPhones, true);
  const r = j.results[0]; assert.equal(r.id, '100'); assert.equal(r.status, 'match'); assert.equal(r.name, 'Ana Perez');
  assert.deepEqual(r.phones, [['7865550101', 'm', 0], ['3055550102', 'l', 0], ['3055550103', 'm', 1], ['3055550104', 'v', 2]]); assert.deepEqual(r.emails, ['ana@example.com']);
  assert.deepEqual([j.meta.matched, j.meta.nomatch, j.meta.errors, j.meta.billable], [1, 0, 0, 1]); assert.equal(j.usedToday, 1);
  assert.ok(!JSON.stringify(j).includes(FAKEKEY));
});
await t('no match is not counted against the cap; nocontact is', async () => {
  const { env } = mkEnv();
  const f = mkFetch(reqs => upstreamOf(reqs, (r, k) => k === 0 ? { input: r, persons: [], meta: { matched: false, error: false } } : k === 1 ? { input: r, persons: [person({ phones: [], emails: [] })], meta: { matched: true, error: false } } : { input: r, persons: [person()], meta: { matched: true } }));
  const { j } = await run(req('POST', '/skiptrace', { body: { items: [item('1'), item('2'), item('3')] } }), env, f);
  assert.deepEqual(j.results.map(r => r.status), ['nomatch', 'nocontact', 'match']); assert.equal(j.usedToday, 2); assert.deepEqual([j.meta.matched, j.meta.withContact, j.meta.nomatch], [2, 1, 1]);
});
await t('bad address rows are not sent and not billed', async () => {
  const { env } = mkEnv(); calls = [];
  const { j } = await run(req('POST', '/skiptrace', { body: { items: [item('1', { street: '' }), item('2', { city: '', zip: '' }), item('3')] } }), env, mkFetch(ok1));
  assert.deepEqual(j.results.map(r => r.status), ['error', 'error', 'match']); assert.equal(j.results[0].error, 'bad_address'); assert.equal(calls[0].b.requests.length, 1); assert.equal(j.usedToday, 1);
});
await t('daily cap enforced, then refused with remaining', async () => {
  const { env } = mkEnv({ DAILY_CAP: '3' }); const f = mkFetch(ok1);
  let r = await run(req('POST', '/skiptrace', { body: { items: [item('1'), item('2'), item('3')] } }), env, f); assert.equal(r.res.status, 200); assert.equal(r.j.remainingToday, 0);
  r = await run(req('POST', '/skiptrace', { body: { items: [item('4')] } }), env, f); assert.equal(r.res.status, 429); assert.equal(r.j.error, 'daily_cap'); assert.equal(r.j.remainingToday, 0);
});
await t('daily cap 0 blocks everything', async () => { const { env } = mkEnv({ DAILY_CAP: '0' }); const r = await run(req('POST', '/skiptrace', { body: { items: [item('1')] } }), env, mkFetch(ok1)); assert.equal(r.res.status, 429); });
await t('rate limit per IP', async () => {
  const { env } = mkEnv({ DAILY_CAP: '1000' }); const f = mkFetch(ok1); let last;
  for (let i = 0; i < 21; i++) last = await run(req('POST', '/skiptrace', { body: { items: [item('r' + i)] } }), env, f);
  assert.equal(last.res.status, 429); assert.equal(last.j.error, 'rate_limited'); assert.ok(last.res.headers.get('Retry-After'));
});
await t('upstream failures: 401/429/500/non-json/network -> mapped error, reservation refunded, no key leak', async () => {
  for (const [st, code] of [[401, 'provider_auth'], [403, 'provider_auth'], [429, 'provider_rate_limited'], [500, 'provider_error'], [402, 'provider_payment']]) {
    const { env } = mkEnv(); const r = await run(req('POST', '/skiptrace', { body: { items: [item('1')] } }), env, mkFetch(() => ({ message: 'secret ' + FAKEKEY }), st));
    assert.equal(r.j.error, code); assert.equal(r.j.upstreamStatus, st); assert.equal(r.j.usedToday, 0); assert.ok(!JSON.stringify(r.j).includes(FAKEKEY)); }
  const { env } = mkEnv(); let r = await run(req('POST', '/skiptrace', { body: { items: [item('1')] } }), env, async () => new Response('<html>', { status: 200 })); assert.equal(r.j.error, 'provider_bad_response');
  r = await run(req('POST', '/skiptrace', { body: { items: [item('1')] } }), env, async () => { throw new Error('boom ' + FAKEKEY); }); assert.equal(r.j.error, 'provider_unreachable'); assert.ok(!JSON.stringify(r.j).includes(FAKEKEY)); assert.equal(r.j.usedToday, 0);
});
await t('partial results: provider error on one row, missing row, correlation by requestId when order differs', async () => {
  const { env } = mkEnv();
  const f = mkFetch(reqs => ({ result: { data: [{ input: reqs[2], persons: [person()], meta: { matched: true } }, { input: reqs[0], persons: [], meta: { matched: false, error: true } }] } }));
  const { j } = await run(req('POST', '/skiptrace', { body: { items: [item('1'), item('2'), item('3')] } }), env, f);
  assert.deepEqual(j.results.map(r => r.status), ['error', 'error', 'match']); assert.equal(j.results[1].error, 'no_result'); assert.equal(j.meta.errors, 2); assert.equal(j.usedToday, 1);
});
await t('mapEntry: owners preferred, deceased skipped, litigator flags all phones, dedupe, caps', async () => {
  const lit = mapEntry({ persons: [person({ litigator: true, phones: [{ number: '3055550199', type: 'Mobile', dnc: false }], emails: [] })] }); assert.deepEqual(lit.phones, [['3055550199', 'm', 2]]);
  const mix = mapEntry({ persons: [{ propertyOwner: false, name: { full: 'Rel Ative' }, phones: [{ number: '3055550001', type: 'Mobile' }] }, person({ deceased: true }), person({ phones: [{ number: '3055550002', type: 'Mobile' }, { number: '(305) 555-0002', type: 'Mobile' }, { number: '123', type: 'Mobile' }], emails: [{ email: 'bad' }, { email: 'a@b.co' }, { email: 'A@B.co' }] })] });
  assert.deepEqual(mix.phones, [['3055550002', 'm', 0]]); assert.deepEqual(mix.emails, ['a@b.co']); assert.equal(mix.name, 'Ana Perez');
  const rel = mapEntry({ persons: [{ propertyOwner: false, phones: [{ number: '3055550001', type: 'Mobile' }] }] }); assert.equal(rel.phones.length, 1);
  assert.equal(mapEntry({ persons: [] }).hasPerson, false);
});
await t('cleanItem / toRequest', async () => {
  assert.equal(cleanItem({ id: '1', street: 'No number', city: 'Miami' }).ok, false); assert.equal(cleanItem({ id: '1', street: '5 A ST', zip: '33130-1234' }).ok, true); assert.equal(cleanItem({ id: '1', street: '5 A ST', zip: '33130-1234' }).zip, '33130'); assert.equal(cleanItem({ street: '5 A ST' }), null);
  const r = toRequest(cleanItem({ id: '1', company: 'ACME LLC', street: '5 A ST', zip: '33130', first: 'x', last: 'y' }), 0); assert.equal(r.name, undefined); assert.equal(r.propertyAddress.city, undefined); assert.equal(r.requestId, '0');
});
await t('exceptions never leak: internal error shape', async () => { const { env } = mkEnv(); env.LIMITER = { idFromName: () => 1, get: () => ({ fetch: async () => { throw new Error(FAKEKEY); } }) }; const mod = (await import('../src/index.js')).default; const res = await mod.fetch(req('GET', '/status'), env, {}); assert.equal(res.status, 500); const tx = await res.text(); assert.ok(!tx.includes(FAKEKEY)); });
await t('source has no embedded secrets', async () => { const fs = await import('node:fs'); const src = fs.readFileSync(new URL('../src/index.js', import.meta.url), 'utf8'); assert.ok(!/Bearer [A-Za-z0-9]{12,}/.test(src)); assert.ok(!src.includes('console.log')); });
await t('KV key wins over the secret; secret is the fallback; /setup-key is gone', async () => {
  const kv = { v: 'kv-key-not-real', get: async function (k) { return k === 'batchdata_key' ? this.v : null; } };
  const { env } = mkEnv({ BATCHDATA_API_KEY: '[REDACTED]', SK_KV: kv }); calls = [];
  const r = await run(req('POST', '/skiptrace', { body: { items: [item('1')] } }), env, mkFetch(ok1)); assert.equal(r.res.status, 200);
  assert.equal(calls[0].init.headers.Authorization, 'Bearer kv-key-not-real');
  kv.v = ''; calls = []; await run(req('POST', '/skiptrace', { body: { items: [item('2')] } }), env, mkFetch(ok1)); assert.equal(calls[0].init.headers.Authorization, 'Bearer [REDACTED]');
  const e2 = mkEnv({ BATCHDATA_API_KEY: '', SK_KV: { get: async () => 'only-in-kv' } }).env; assert.equal((await run(req('GET', '/status'), e2)).res.status, 200);
  const e3 = mkEnv({ SK_KV: { get: async () => { throw new Error('kv down'); } } }).env; assert.equal((await run(req('GET', '/status'), e3)).res.status, 200);
  for (const m of ['PUT', 'GET', 'POST']) assert.equal((await run(req(m, '/setup-key', m === 'GET' ? {} : { body: 'x' }), env)).res.status, 404);
});
await t('Cloudflare Access login: valid JWT replaces the access code; forged / wrong aud / expired / other team rejected; /skiptrace-api prefix; app origin allowed', async () => {
  const { webcrypto } = await import('node:crypto'); const subtle = webcrypto.subtle;
  const kp = await subtle.generateKey({ name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' }, true, ['sign', 'verify']);
  const bad = await subtle.generateKey({ name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' }, true, ['sign', 'verify']);
  const jwk = await subtle.exportKey('jwk', kp.publicKey); jwk.kid = 'k1';
  const TEAM = 'team.cloudflareaccess.com', AUD = 'aud-tag-test', APP = 'https://app.prop-hunters.com';
  const enc = o => Buffer.from(JSON.stringify(o)).toString('base64url');
  const sign = async (pl, key, hdr) => { const h = enc(hdr || { alg: 'RS256', kid: 'k1', typ: 'JWT' }), b = enc(pl); const sig = await subtle.sign('RSASSA-PKCS1-v1_5', (key || kp).privateKey, new TextEncoder().encode(h + '.' + b)); return h + '.' + b + '.' + Buffer.from(sig).toString('base64url'); };
  const now = Math.floor(Date.now() / 1000), good = { iss: 'https://' + TEAM, aud: [AUD], email: 'a@b.c', sub: 'u1', exp: now + 600, iat: now };
  let certCalls = 0;
  const f = async (url, init) => { if (String(url).includes('/cdn-cgi/access/certs')) { certCalls++; assert.equal(url, 'https://' + TEAM + '/cdn-cgi/access/certs'); return new Response(JSON.stringify({ keys: [jwk] })); } return mkFetch(ok1)(url, init); };
  const { env } = mkEnv({ ACCESS_TEAM_DOMAIN: TEAM, ACCESS_AUD: AUD, ALLOWED_ORIGIN: ORIGIN + ',' + APP }); _test._resetCerts();
  const jr = async (tok, path, o) => run(req(o && o.body ? 'POST' : 'GET', path || '/skiptrace-api/status', { code: null, headers: { 'Cf-Access-Jwt-Assertion': tok }, ...(o || {}) }), env, f);
  let r = await jr(await sign(good)); assert.equal(r.res.status, 200); assert.equal(r.j.ok, true);
  r = await run(req('GET', '/skiptrace-api/status', { code: null, headers: { Cookie: 'x=1; CF_Authorization=' + await sign(good) } }), env, f); assert.equal(r.res.status, 200);
  r = await jr(await sign(good), '/skiptrace-api/skiptrace', { body: { items: [item('1')] }, origin: APP }); assert.equal(r.res.status, 200); assert.equal(r.j.results[0].status, 'match');
  for (const tok of [await sign(good, bad), await sign({ ...good, aud: ['other'] }), await sign({ ...good, exp: now - 120 }), await sign({ ...good, iss: 'https://evil.cloudflareaccess.com' }), await sign(good, null, { alg: 'none', kid: 'k1' }), await sign(good, null, { alg: 'RS256', kid: 'nope' }), 'a.b.c', '']) {
    r = await jr(tok); assert.equal(r.res.status, 401, 'rejected token'); }
  const { env: e1 } = mkEnv({ ACCESS_TEAM_DOMAIN: TEAM, ACCESS_AUD: AUD }); r = await run(req('GET', '/skiptrace-api/status'), e1, f); assert.equal(r.res.status, 200, 'access code still works as fallback');
  const { env: e2 } = mkEnv(); r = await run(req('GET', '/status', { code: null, headers: { 'Cf-Access-Jwt-Assertion': await sign(good) } }), e2, f); assert.equal(r.res.status, 401, 'JWT ignored when Access is not configured');
  r = await run(req('GET', '/status', { origin: APP }), e1, f); assert.equal(r.res.status, 403, 'app origin not allowed unless listed'); r = await run(req('GET', '/status', { origin: APP }), mkEnv({ ALLOWED_ORIGIN: ORIGIN + ',' + APP }).env, f); assert.equal(r.res.headers.get('Access-Control-Allow-Origin'), APP);
  assert.ok(certCalls >= 1 && certCalls <= 4, 'certs cached');
});
console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
