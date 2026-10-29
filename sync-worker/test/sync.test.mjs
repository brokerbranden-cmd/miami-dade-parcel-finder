// Unit tests for the sync Worker (node >= 22, no network). Run: node sync-worker/test/sync.test.mjs
import { _test } from '../src/index.js';
import { makeD1 } from './d1shim.mjs';
import assert from 'node:assert/strict';
const { handle, _resetCerts } = _test;
let pass = 0, fail = 0;
const t = async (name, fn) => { try { _resetCerts(); await fn(); pass++; console.log('PASS ' + name); } catch (e) { fail++; console.log('FAIL ' + name + ': ' + (e && e.stack || e)); } };
const TEAM = 'team.example.cloudflareaccess.com', AUD = 'aud123', APP = 'https://app.prop-hunters.com';
const enc = o => Buffer.from(JSON.stringify(o)).toString('base64url');
const kp = await crypto.subtle.generateKey({ name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' }, true, ['sign', 'verify']);
const other = await crypto.subtle.generateKey({ name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' }, true, ['sign', 'verify']);
const jwk = { ...(await crypto.subtle.exportKey('jwk', kp.publicKey)), kid: 'k1' };
async function jwt(pl, key = kp.privateKey, kid = 'k1') { const h = enc({ alg: 'RS256', kid, typ: 'JWT' }), p = enc(pl); const sig = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', key, new TextEncoder().encode(h + '.' + p)); return h + '.' + p + '.' + Buffer.from(sig).toString('base64url'); }
const now = () => Math.floor(Date.now() / 1000);
const tok = (email, over) => jwt({ iss: 'https://' + TEAM, aud: [AUD], email, exp: now() + 3600, iat: now(), ...over });
const certs = async url => { assert.equal(url, 'https://' + TEAM + '/cdn-cgi/access/certs'); return new Response(JSON.stringify({ keys: [jwk] })); };
const mkEnv = () => ({ ACCESS_TEAM_DOMAIN: TEAM, ACCESS_AUD: AUD, ALLOWED_ORIGIN: APP, DB: makeD1() });
async function call(env, method, path, { token, body, origin = APP, headers = {} } = {}) {
  const h = { ...headers }; if (token) h['Cf-Access-Jwt-Assertion'] = token; if (origin) h.Origin = origin; if (body !== undefined) { h['Content-Type'] = 'application/json'; h['X-PF-Sync'] = '1'; }
  const res = await handle(new Request(APP + path, { method, headers: h, body: body !== undefined ? JSON.stringify(body) : undefined }), env, certs);
  let j = null; try { j = await res.clone().json(); } catch (e) {} return { res, j };
}
const rec = (ns, k, v, at) => ({ ns, k, v: v == null ? null : JSON.stringify(v), at });

await t('no Access login -> 401 everywhere, nothing returned', async () => {
  const env = mkEnv();
  for (const [m, p, b] of [['GET', '/sync-api/me'], ['POST', '/sync-api/sync', { since: 0 }], ['GET', '/sync-api/nope']]) { const { res, j } = await call(env, m, p, { body: b }); assert.equal(res.status, 401); assert.deepEqual(Object.keys(j), ['error']); }
});
await t('forged, wrong-aud, expired, other-team, no-email (service token) and mismatched header tokens rejected', async () => {
  const env = mkEnv(); const A = 'a@prop-hunters.com';
  const bad = [await tok(A, {}).then(x => x.slice(0, -4) + 'AAAA'), await jwt({ iss: 'https://' + TEAM, aud: [AUD], email: A, exp: now() + 99 }, other.privateKey), await tok(A, { aud: ['nope'] }), await tok(A, { exp: now() - 120 }),
    await tok(A, { iss: 'https://evil.cloudflareaccess.com' }), await tok('', { common_name: 'svc.access' }), await tok(A, { nbf: now() + 600 })];
  for (const b of bad) assert.equal((await call(env, 'GET', '/sync-api/me', { token: b })).res.status, 401);
  assert.equal((await call(env, 'GET', '/sync-api/me', { token: await tok(A), headers: { 'Cf-Access-Authenticated-User-Email': 'b@x.com' } })).res.status, 401);
  const ok = await call(env, 'GET', '/sync-api/me', { token: await tok('A@Prop-Hunters.com'), headers: { 'Cf-Access-Authenticated-User-Email': 'a@prop-hunters.com' } });
  assert.equal(ok.res.status, 200); assert.equal(ok.j.email, 'a@prop-hunters.com'); assert.ok(ok.j.now > 0);
});
await t('CF_Authorization cookie accepted; cross-origin refused; POST needs X-PF-Sync + JSON', async () => {
  const env = mkEnv(), T = await tok('a@x.com');
  assert.equal((await call(env, 'GET', '/sync-api/me', { headers: { Cookie: 'x=1; CF_Authorization=' + T } })).res.status, 200);
  assert.equal((await call(env, 'GET', '/sync-api/me', { token: T, origin: 'https://brokerbranden-cmd.github.io' })).res.status, 403);
  const r = await handle(new Request(APP + '/sync-api/sync', { method: 'POST', headers: { 'Cf-Access-Jwt-Assertion': T, 'Content-Type': 'text/plain' }, body: '{}' }), env, certs); assert.equal(r.status, 400);
  assert.equal((await call(env, 'GET', '/sync-api/sync', { token: T })).res.status, 405);
  const o = await handle(new Request(APP + '/sync-api/sync', { method: 'OPTIONS', headers: { Origin: APP } }), env, certs); assert.equal(o.status, 403); assert.equal(o.headers.get('Access-Control-Allow-Origin'), null);
});
await t('push then pull from another user: records, who edited, cursor, counties kept apart', async () => {
  const env = mkEnv(), A = await tok('a@x.com'), B = await tok('b@x.com');
  let { j } = await call(env, 'POST', '/sync-api/sync', { token: A, body: { since: 0, push: [rec('mdpf.saved.v1', '3059010010010', { folio: '3059010010010', note: 'hi' }, 1000), rec('mdpf.saved.v1.broward', '474131AA0010', { note: 'bw' }, 1000), rec('pf.skip.v1', '3059010010010', { p: [['3055550101', 'm', 0]], e: [] }, 1000)] } });
  assert.equal(j.ok, true); assert.equal(j.accepted, 3); assert.equal(j.changes.length, 3); assert.ok(j.changes.every(c => c.by === 'a@x.com'));
  ({ j } = await call(env, 'POST', '/sync-api/sync', { token: B, body: { since: 0 } }));
  const md = j.changes.find(c => c.ns === 'mdpf.saved.v1'), bw = j.changes.find(c => c.ns === 'mdpf.saved.v1.broward');
  assert.equal(JSON.parse(md.v).note, 'hi'); assert.equal(md.k, '3059010010010'); assert.equal(JSON.parse(bw.v).note, 'bw'); assert.equal(bw.k, '474131AA0010');
  const cur = j.cursor; ({ j } = await call(env, 'POST', '/sync-api/sync', { token: B, body: { since: cur } })); assert.equal(j.changes.length, 0); assert.equal(j.cursor, cur);
});
await t('last edit wins per record; older push rejected and the newer copy returned; deletes are tombstones', async () => {
  const env = mkEnv(), A = await tok('a@x.com'), B = await tok('b@x.com');
  await call(env, 'POST', '/sync-api/sync', { token: A, body: { since: 0, push: [rec('mdpf.saved.v1', 'F1', { note: 'A new' }, 2000)] } });
  let { j } = await call(env, 'POST', '/sync-api/sync', { token: B, body: { since: 999, push: [rec('mdpf.saved.v1', 'F1', { note: 'B old' }, 1500), rec('mdpf.saved.v1', 'F2', { note: 'B2' }, 1500)] } });
  assert.equal(j.accepted, 1); assert.equal(j.rejected.length, 1); assert.equal(JSON.parse(j.rejected[0].v).note, 'A new'); assert.equal(j.rejected[0].by, 'a@x.com');
  ({ j } = await call(env, 'POST', '/sync-api/sync', { token: B, body: { since: 0, push: [rec('mdpf.saved.v1', 'F1', null, 3000)] } }));
  const f1 = j.changes.filter(c => c.k === 'F1'); assert.equal(f1.length, 1); assert.equal(f1[0].v, null); assert.equal(f1[0].by, 'b@x.com');
  ({ j } = await call(env, 'POST', '/sync-api/sync', { token: A, body: { since: 0, push: [rec('mdpf.saved.v1', 'F1', { note: 'resurrect old' }, 2500)] } }));
  assert.equal(j.rejected[0].v, null);
});
await t('bad input dropped: unknown storage keys, bad ids, bad JSON values, too many', async () => {
  const env = mkEnv(), A = await tok('a@x.com');
  let { j } = await call(env, 'POST', '/sync-api/sync', { token: A, body: { since: 0, push: [rec('pf.ui.v1', 'x', {}, 5), rec('mdpf.saved.v1', 'bad id!', {}, 5), { ns: 'pf.skip.v1', k: '1', v: '{nope', at: 5 }, rec('pf.skip.v1', '2', {}, -1), rec('pf.phoneres.v1', '3055550101', { r: 'reached' }, 5), rec('pf.send.v1.monroe', 'tags/00012345678901', { pm: 'x' }, 5)] } });
  assert.equal(j.accepted, 2); assert.deepEqual(j.changes.map(c => c.ns).sort(), ['pf.phoneres.v1', 'pf.send.v1.monroe']);
  const many = Array.from({ length: 401 }, (_, i) => rec('pf.skip.v1', String(1e6 + i), {}, 5));
  assert.equal((await call(env, 'POST', '/sync-api/sync', { token: A, body: { since: 0, push: many } })).res.status, 413);
});
await t('paging: more + cursor walk returns every change once', async () => {
  const env = mkEnv(), A = await tok('a@x.com');
  for (let b = 0; b < 5; b++) await call(env, 'POST', '/sync-api/sync', { token: A, body: { since: 0, push: Array.from({ length: 400 }, (_, i) => rec('pf.skip.v1', String(1e6 + b * 400 + i), { a: '2026-10-29' }, 10)) } });
  let since = 0, seen = new Set(), pages = 0, more = true;
  while (more) { const { j } = await call(env, 'POST', '/sync-api/sync', { token: A, body: { since } }); j.changes.forEach(c => { assert.ok(!seen.has(c.k)); seen.add(c.k); }); since = j.cursor; more = j.more; pages++; }
  assert.equal(seen.size, 2000); assert.equal(pages, 2);
});
console.log(`\n${pass} passed, ${fail} failed`); if (fail) process.exit(1);
