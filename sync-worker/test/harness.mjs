// Local harness for tests/e2e_sync.py: a fake Cloudflare Access (JWKS + signed tokens), the real sync Worker in `wrangler dev` (local D1),
// and a static server for the app that forwards /sync-api/* to the Worker (same origin, like app.prop-hunters.com).
// Usage: node sync-worker/test/harness.mjs <appPort>   -> prints {"ready":true,"tokens":{...}} once up. Ctrl-C / SIGTERM stops everything.
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path'; import { spawn } from 'node:child_process'; import { fileURLToPath } from 'node:url';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..'), APP = +(process.argv[2] || 8190), CERTS = APP + 1, WK = APP + 2;
const TEAM = 'pf-test.cloudflareaccess.com', AUD = 'pf-test-aud';
const enc = o => Buffer.from(JSON.stringify(o)).toString('base64url');
const kp = await crypto.subtle.generateKey({ name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' }, true, ['sign', 'verify']);
const jwk = { ...(await crypto.subtle.exportKey('jwk', kp.publicKey)), kid: 'test1' };
async function tok(email) { const h = enc({ alg: 'RS256', kid: 'test1' }), p = enc({ iss: 'https://' + TEAM, aud: [AUD], email, exp: Math.floor(Date.now() / 1000) + 86400 }); const s = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', kp.privateKey, new TextEncoder().encode(h + '.' + p)); return h + '.' + p + '.' + Buffer.from(s).toString('base64url'); }
http.createServer((q, r) => { r.writeHead(200, { 'Content-Type': 'application/json' }); r.end(JSON.stringify({ keys: [jwk] })); }).listen(CERTS, '127.0.0.1');
const persist = fs.mkdtempSync('/tmp/pf-sync-d1-');
const wr = spawn('npx', ['wrangler', 'dev', '--local', '--port', String(WK), '--ip', '127.0.0.1', '--persist-to', persist, '--show-interactive-dev-session=false',
  '--var', 'ACCESS_TEAM_DOMAIN:' + TEAM, '--var', 'ACCESS_AUD:' + AUD, '--var', 'ACCESS_CERTS_URL:http://127.0.0.1:' + CERTS + '/certs', '--var', 'ALLOWED_ORIGIN:http://127.0.0.1:' + APP],
  { cwd: path.join(ROOT, 'sync-worker'), stdio: ['ignore', 'pipe', 'pipe'], detached: true });
let wlog = ''; wr.stdout.on('data', d => { wlog += d; }); wr.stderr.on('data', d => { wlog += d; });
const stop = () => { try { process.kill(-wr.pid, 'SIGTERM'); } catch (e) {} fs.rmSync(persist, { recursive: true, force: true }); process.exit(0); };
process.on('SIGTERM', stop); process.on('SIGINT', stop);
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.webmanifest': 'application/manifest+json' };
http.createServer((q, r) => {
  const u = new URL(q.url, 'http://x');
  if (u.pathname.startsWith('/sync-api/')) {
    const h = { ...q.headers }; delete h.host;
    const p = http.request({ host: '127.0.0.1', port: WK, path: q.url, method: q.method, headers: h }, pr => { r.writeHead(pr.statusCode, pr.headers); pr.pipe(r); });
    p.on('error', () => { r.writeHead(502); r.end('{"error":"worker_down"}'); }); q.pipe(p); return;
  }
  let f = path.join(ROOT, decodeURIComponent(u.pathname)); if (!f.startsWith(ROOT)) { r.writeHead(403); return r.end(); }
  if (f.endsWith('/')) f += 'index.html';
  fs.stat(f, (e, s) => { if (e || !s.isFile()) { r.writeHead(404); return r.end('not found'); } r.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream', 'Content-Length': s.size }); fs.createReadStream(f).pipe(r); });
}).listen(APP, '127.0.0.1');
for (let i = 0; i < 120; i++) {
  await new Promise(r => setTimeout(r, 1000));
  try { const r = await fetch('http://127.0.0.1:' + WK + '/sync-api/me'); if (r.status === 401) { console.log(JSON.stringify({ ready: true, app: 'http://127.0.0.1:' + APP + '/', tokens: { a: await tok('branden@prop-hunters.com'), b: await tok('teammate@prop-hunters.com') } })); break; } } catch (e) {}
  if (i === 119) { console.log(JSON.stringify({ ready: false, log: wlog.slice(-2000) })); stop(); }
}
