/* node tests/unit_skiptrace_api.js : client side logic of the one-click skip trace (no browser, mocked fetch) */
const S = require('../skiptrace.js'); globalThis.PFSkip = S;
const A = require('../skiptrace-api.js'); let fails = 0;
const eq = (a, b, m) => { const ok = JSON.stringify(a) === JSON.stringify(b); console.log((ok ? 'ok   ' : 'FAIL ') + m + (ok ? '' : '  got ' + JSON.stringify(a) + ' want ' + JSON.stringify(b))); if (!ok) fails++; };
const mem = () => { const m = new Map(); return { getItem: k => m.has(k) ? m.get(k) : null, setItem: (k, v) => { m.set(k, String(v)); }, removeItem: k => { m.delete(k); } }; };
const store = () => S.makeStore('t', mem());
// buildItem
let it = A.buildItem({ folio: '3030010010010', addr: '1206 SW 2 ST', city: 'Homestead', zip: '33030-1234', owner: 'MIROLJUB FILIPOVIC', mail: 'PO BOX 770007, MIAMI, FL 33177', gov: false }, { order: 'first-last' });
eq([it.id, it.first, it.last, it.company, it.street, it.city, it.state, it.zip, it.mailStreet, it.mailCity, it.mailState, it.mailZip], ['3030010010010', 'Miroljub', 'Filipovic', '', '1206 SW 2 ST', 'Homestead', 'FL', '33030', 'PO BOX 770007', 'MIAMI', 'FL', '33177'], 'person item');
it = A.buildItem({ folio: '1', addr: '5 A ST', city: 'Unincorporated Miami-Dade', zip: '33130', owner: 'ACME HOLDINGS LLC', mail: '' }, {});
eq([it.first, it.last, it.company, it.city, it.mailStreet], ['', '', 'Acme Holdings LLC', '', ''], 'company item, unincorporated city blank');
eq([A.hasAddress(it), A.hasAddress({ street: 'VACANT LAND', zip: '33130', city: '' }), A.hasAddress({ street: '', zip: '33130', city: 'x' }), A.hasAddress({ street: '5 A ST', zip: '', city: '' })], [true, false, false, false], 'hasAddress');
// code storage
globalThis.localStorage = mem(); eq(A.getCode(), '', 'no code'); A.setCode('  ab-12 '); eq(A.getCode(), 'ab-12', 'code trimmed + stored'); A.clearCode(); eq(A.getCode(), '', 'code cleared');
// applyResult
const st = store(), g = { id: 'F1', folios: ['1111111111111', '2222222222222'] };
eq(A.applyResult(st, g, { id: 'F1', status: 'match', name: 'Ana Perez', phones: [['3055550101', 'm', 0], ['3055550102', 'l', 1]], emails: ['a@b.co'] }, '2026-10-16'), true, 'apply match');
eq([st.get('1111111111111').p, st.get('2222222222222').e, st.get('1111111111111').n, st.get('1111111111111').s, st.get('1111111111111').a], [[['3055550101', 'm', 0], ['3055550102', 'l', 1]], ['a@b.co'], 'Ana Perez', 'BatchData API', '2026-10-16'], 'store shape = CSV import shape (sibling folios too)');
eq(st.phoneCount(), 2, 'has phone set'); eq(S.canText(st.get('1111111111111').p[0]), true, 'mobile can text'); eq(S.canText(st.get('1111111111111').p[1]), false, 'DNC landline cannot');
eq(A.applyResult(st, { id: 'F2', folios: ['3333333333333'] }, { status: 'nomatch' }, 'd'), true, 'nomatch stored as traced'); eq([st.has('3333333333333'), st.hasPhone('3333333333333')], [true, false], 'nomatch = traced, no phone');
eq(A.applyResult(st, { id: 'F3', folios: ['4444444444444'] }, { status: 'error', error: 'bad_address' }, 'd'), false, 'error not stored'); eq(st.has('4444444444444'), false, 'error leaves property untraced (retry possible)');
A.applyResult(st, g, { status: 'nomatch' }, 'd2'); eq(st.get('1111111111111').p.length, 2, 'later no-match does not wipe existing phones');
// run with mocked fetch: chunking, summary, cancel, errors
const mkItem = n => ({ id: 'F' + n, first: 'A', last: 'B', street: n + ' SW 1 ST', city: 'Miami', state: 'FL', zip: '33130' });
const mkGroups = n => Array.from({ length: n }, (_, i) => ({ id: 'F' + i, folios: [String(1000000000000 + i)], item: mkItem(i) }));
let reqs = [];
const res = (obj, status) => ({ ok: (status || 200) < 400, status: status || 200, json: async () => obj });
globalThis.fetch = async (url, init) => {
  const b = JSON.parse(init.body); reqs.push({ url, n: b.items.length, code: init.headers['X-Access-Code'] });
  const results = b.items.map((x, k) => { const i = +x.id.slice(1); return i % 5 === 0 ? { id: x.id, status: 'nomatch' } : i % 7 === 0 ? { id: x.id, status: 'error', error: 'provider_error' } : { id: x.id, status: 'match', name: 'N', phones: [['30555' + String(50000 + i).slice(-5), 'm', i % 3 === 0 ? 1 : 0]], emails: i % 2 ? ['e' + i + '@x.co'] : [] }; });
  return res({ ok: true, results, meta: { sent: results.length }, remainingToday: 400 });
};
(async () => {
  const s2 = store(), prog = []; reqs = [];
  const sum = await A.run(mkGroups(120), { store: s2, code: 'CODE', chunk: 50, onProgress: (d, t) => prog.push([d, t]) });
  eq(reqs.map(r => r.n), [50, 50, 20], 'chunks of 50'); eq(reqs[0].url, A.WORKER_URL + '/skiptrace', 'posts to Worker'); eq(reqs[0].code, 'CODE', 'sends access code header');
  eq(prog, [[50, 120], [100, 120], [120, 120]], 'progress callbacks');
  const nm = [...Array(120).keys()].filter(i => i % 5 === 0).length, er = [...Array(120).keys()].filter(i => i % 5 && i % 7 === 0).length;
  eq([sum.nomatch, sum.errors, sum.matched], [nm, er, 120 - nm - er], 'summary counts'); eq(sum.remaining, 400, 'remaining captured'); eq(sum.dnc.size > 0, true, 'dnc counted');
  eq(s2.count(), 120 - er, 'store has every non-error result (nomatch included)'); eq(s2.phoneCount(), 120 - nm - er, 'phones stored');
  // cancel after the first chunk keeps what was saved
  const s3 = store(), ac = new AbortController(); reqs = [];
  const sum3 = await A.run(mkGroups(120), { store: s3, code: 'C', chunk: 50, signal: ac.signal, onProgress: d => { if (d >= 50) ac.abort(); } });
  eq([sum3.cancelled, reqs.length, s3.count() > 0], [true, 1, true], 'cancel stops further chunks, keeps saved results');
  // error stops the run, keeps previous chunks
  let n = 0; const real = globalThis.fetch; globalThis.fetch = async (u, i) => ++n === 2 ? res({ ok: false, error: 'daily_cap', remainingToday: 7 }, 429) : real(u, i);
  const s4 = store(); const sum4 = await A.run(mkGroups(120), { store: s4, code: 'C', chunk: 50 }); eq([sum4.stopped, sum4.remaining, s4.count() > 0, sum4.sent], ['daily_cap', 7, true, 50], 'daily cap stops run, partial kept');
  globalThis.fetch = async () => { throw new TypeError('failed'); }; const sum5 = await A.run(mkGroups(3), { store: store(), code: 'C' }); eq(sum5.stopped, 'network', 'network error reported');
  globalThis.fetch = async () => res({ error: 'bad_access_code' }, 401); try { await A.status('x'); eq('no throw', 'throw', 'status 401 throws'); } catch (e) { eq([e.code, e.status], ['bad_access_code', 401], 'status 401 -> ApiError'); eq(A.messageFor(e).includes('not accepted'), true, 'friendly message'); }
  console.log(fails ? `\n${fails} FAILED` : '\nall passed'); process.exit(fails ? 1 : 0);
})();
