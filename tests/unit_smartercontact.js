/* node tests/unit_smartercontact.js : pure-logic tests for smartercontact.js (no browser). Fake 555-01xx numbers only. */
const SK = require('../skiptrace.js'), SC = require('../smartercontact.js'); let fails = 0;
const eq = (a, b, m) => { const ok = JSON.stringify(a) === JSON.stringify(b); console.log((ok ? 'ok   ' : 'FAIL ') + m + (ok ? '' : '  got ' + JSON.stringify(a) + ' want ' + JSON.stringify(b))); if (!ok) fails++; };
const HEAD = ['First Name', 'Last Name', 'Phone 1', 'Phone 2', 'Phone 3', 'Phone 4', 'Phone 5', 'Phone 6', 'Phone 7', 'Phone 8', 'Phone 9', 'Phone 10', 'Email',
  'Property Address', 'Property City', 'Property State', 'Property Zip', 'Mailing Address', 'Mailing City', 'Mailing State', 'Mailing Zip',
  'APN', 'Parcel County', 'Parcel State', 'Folio', 'Company', 'Owner Name', 'County', 'Properties', 'All Folios'];
eq(SC.HEAD, HEAD, 'header: Smarter Contact field names, Phone 1-10, custom fields last');
eq(SC.MAXPH, 10, '10 phone columns');
eq(['(305) 555-0101', '+1 305 555 0101', '13055550101', '305555010', '0555550101', '', null].map(SC.norm10), ['3055550101', '3055550101', '3055550101', '', '', '', ''], 'norm10: 10 digits, drops +1, rejects short / bad area code');
// names
const nm = (o, n, ef) => { const r = SC.names(SK, o, n, { order: 'first-last', entityFirst: ef }); return [r.first, r.last, r.company]; };
eq(nm('JOHN SMITH'), ['John', 'Smith', ''], 'individual: first / last');
eq(nm('MARIA GARCIA &H JOSE GARCIA'), ['Maria', 'Garcia', ''], 'couple: first owner');
eq(nm('SUNSHINE HOLDINGS LLC'), ['Owner', 'Sunshine Holdings LLC', 'Sunshine Holdings LLC'], 'LLC: First Name "Owner", entity in Last Name + Company');
eq(nm('SUNSHINE HOLDINGS LLC', '', ''), ['', 'Sunshine Holdings LLC', 'Sunshine Holdings LLC'], 'LLC: blank First Name option');
eq(nm('SUNSHINE HOLDINGS LLC', 'ROBERT JONES'), ['Robert', 'Jones', 'Sunshine Holdings LLC'], 'LLC with the person the skip trace found: their name, entity in Company');
eq(nm('', ''), ['Owner', '', ''], 'no owner name (Puerto Rico): Owner');
eq(SC.names(SK, 'SMITH JOHN', '', { order: 'last-first' }).first, 'John', 'last-first county order');
// build
const recs = {
  A1: { p: [['3055550102', 'l', 0], ['3055550101', 'm', 4], ['3055550103', 'm', 1], ['3055550104', 'm', 8], ['3055550105', 'm', 2]], e: ['bad@example.com', 'a@example.com'] },
  A2: { p: [['3055550101', 'm', 0], ['3055550106', 'm', 0]], e: [] },
  B: { p: [['3055550201', 'm', 0]], e: [] },
  C: { p: [], e: [] },
  D: { p: Array.from({ length: 13 }, (_, k) => ['30555503' + String(k).padStart(2, '0'), 'm', 0]), e: [] },
  E: { p: [['3055550401', 'm', 0], ['3055550402', 'm', 0]], e: [] }, };
const it = (folio, owner, mail, extra) => ({ id: folio, x: Object.assign({ folio, addr: folio + ' MAIN ST', city: 'Homestead', zip: '33030-1234', owner, mail, gov: false }, extra || {}) });
const items = [it('A1', 'JOHN SMITH', '1 OAK AVE, MIAMI, FL 33101'), it('A2', 'JOHN SMITH', '1 OAK AVE, MIAMI, FL 33101'), it('B', 'BLUE SKY LLC', '9 PINE RD, AUSTIN, TX 78701'),
  it('C', 'NO PHONE', ''), it('Z', 'NOT TRACED', ''), it('D', 'MANY PHONES', ''), it('E', 'ALREADY SENT', '')];
const env = (o) => Object.assign({ SK, rec: f => recs[f], res: n => (n === '3055550105' ? 'wrong' : ''), sentPh: new Set(['3055550401']), sentAll: new Set(), badEmail: e => e === 'bad@example.com', folioOut: f => 'F-' + f, county: 'Miami-Dade', state: 'FL', order: 'first-last' }, o || {});
let r = SC.build(items, env(), {});
eq(r.head, HEAD, 'build head');
eq(r.rows.map(x => x.vals[0] + ' ' + x.vals[1]), ['John Smith', 'Owner Blue Sky LLC', 'Many Phones', 'Already Sent'], 'one row per owner, untraced / no-phone rows skipped');
const j = r.rows[0];
eq(j.phones, ['3055550101', '3055550106', '3055550102'], 'phones: both properties united, best grade first, DNC / disconnected / wrong left out, deduped');
eq(j.vals.slice(2, 12), ['3055550101', '3055550106', '3055550102', '', '', '', '', '', '', ''], 'Phone 1-10 cells');
eq(j.vals[12], 'a@example.com', 'first good email');
eq(j.vals.slice(13, 21), ['A1 MAIN ST', 'Homestead', 'FL', '33030', '1 OAK AVE', 'MIAMI', 'FL', '33101'], 'property + mailing address');
eq(j.vals.slice(21), ['F-A1', 'Miami-Dade', 'FL', 'F-A1', '', 'JOHN SMITH', 'Miami-Dade', 2, 'F-A1;F-A2'], 'APN / county / state / Folio / Company / Owner / County / Properties / All Folios');
eq(r.rows[1].vals[25], 'Blue Sky LLC', 'Company column for LLC');
eq(r.rows[2].phones.length, 10, 'capped at 10 phones');
eq(r.rows[3].phones, ['3055550402'], 'number already sent to Smarter Contact left out');
eq([r.n.noTrace, r.n.noPhone, r.n.dnc, r.n.bad, r.n.sent], [1, 1, 1, 2, 1], 'counts: untraced, no phone, DNC, wrong / disconnected, already sent');
eq(r.phByFolio.A2, j.phones, 'sent numbers recorded on every property of the owner');
eq(r.folios, ['A1', 'A2', 'B', 'D', 'E'], 'folios to mark as sent');
r = SC.build(items, env(), { includeSent: true }); eq(r.rows[3].phones, ['3055550401', '3055550402'], 'include already sent');
r = SC.build(items, env(), { noLandline: true }); eq(r.rows[0].phones, ['3055550101', '3055550106'], 'leave out landlines');
r = SC.build(items, env({ sentAll: new Set(['B']) }), {}); eq(r.rows.some(x => x.folios.includes('B')), false, 'property marked sent with no number list counts as sent');
r = SC.build([it('A1', 'JOHN SMITH', ''), it('B', 'OTHER OWNER', '')], env({ rec: f => f === 'B' ? recs.A1 : recs[f] }), {}); eq(r.rows.length, 1, 'same number never on two rows of one file');
eq(SC.sentSets({ X: { sc: { d: '2026-10-29', ph: ['3055550101'] } }, Y: { sc: { d: '2026-10-29' } }, W: { sms: { d: '2026-10-29' } } }), { ph: new Set(['3055550101']), all: new Set(['Y']) }, 'sentSets');
eq([...SC.sentSets({ X: { sc: { ph: ['3055550101'] } } }).ph], ['3055550101'], 'sentSets numbers');
// Puerto Rico: municipio as city, Barrio last
r = SC.build([it('A1', '', '', { city: 'Pueblo' })], env({ county: 'Puerto Rico', state: 'PR', muni: 'Adjuntas' }), { pr: true });
eq(r.head.slice(-1), ['Barrio'], 'PR: Barrio column last'); eq(r.head.slice(0, HEAD.length), HEAD, 'PR: shared columns unchanged');
eq([r.rows[0].vals[0], r.rows[0].vals[14], r.rows[0].vals[15], r.rows[0].vals.slice(-1)[0]], ['Owner', 'Adjuntas', 'PR', 'Pueblo'], 'PR: Owner, municipio city, state PR, barrio');
eq(SC.build([it('A1', 'JOHN SMITH', '', { city: 'Unincorporated County' })], env(), {}).rows[0].vals[14], '', 'unincorporated city left blank');
console.log(fails ? `${fails} FAILED` : 'all passed'); process.exit(fails ? 1 : 0);
