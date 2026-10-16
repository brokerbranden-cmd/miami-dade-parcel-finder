/* node tests/unit_skiptrace.js : pure-logic tests for skiptrace.js (no browser) */
const S = require('../skiptrace.js'); let fails = 0;
const eq = (a, b, m) => { const ok = JSON.stringify(a) === JSON.stringify(b); console.log((ok ? 'ok   ' : 'FAIL ') + m + (ok ? '' : '  got ' + JSON.stringify(a) + ' want ' + JSON.stringify(b))); if (!ok) fails++; };
// csv
eq(S.parseCSV('\uFEFFa,b\r\n"x,1","he said ""hi"""\r\n').rows, [['a', 'b'], ['x,1', 'he said "hi"']], 'csv quotes + BOM + CRLF');
eq(S.parseCSV('a\tb\n1\t2').rows, [['a', 'b'], ['1', '2']], 'tab delimited');
eq(S.parseCSV('a;b;c\n1;2;3').delim, ';', 'semicolon delimited');
// phones
eq(S.normPhone('+1 (305) 555-1234'), '3055551234', 'phone +1'); eq(S.normPhone('555-1234'), '', 'short phone rejected'); eq(S.phonesIn('305-555-1234; 786.555.9876'), ['3055551234', '7865559876'], 'two numbers in a cell');
eq(['Y', 'yes', 'TRUE', '1', 'DNC', 'On DNC'].map(S.truthy), [true, true, true, true, true, true], 'DNC truthy'); eq(['', 'N', 'No', '0', 'false', 'Clean', 'Not Listed', 'Not on DNC'].map(S.truthy), [false, false, false, false, false, false, false, false], 'DNC falsy');
eq(S.phoneType('Wireless'), 'm', 'wireless=mobile'); eq(S.phoneType('Landline'), 'l', 'landline'); eq(S.phoneType('VOIP'), 'v', 'voip');
// addresses
const k = a => S.addrKeys(a).full;
eq(k('1206 SW 2 ST'), k('1206 SW 2nd Street'), 'ordinal + suffix'); eq(k('16690 SW 232ND ST'), k('16690 Southwest 232 Street'), 'direction words');
eq(k('5555 COLLEGE Rd 14'), k('5555 College Road, Unit 14, Key West, FL 33040'), 'unit forms'); eq(S.addrKeys('5555 College Rd #14').base, S.addrKeys('5555 COLLEGE RD').base, 'base drops unit');
eq(S.parseMailing('PO BOX 770007, MIAMI, FL 33177-0001'), { street: 'PO BOX 770007', city: 'MIAMI', state: 'FL', zip: '33177-0001' }, 'mailing parse');
eq(S.parseMailing('C/O PASSCO COMPANIES LLC, 2050 Main St Ste 650, Irvine, CA 92614').street, 'C/O PASSCO COMPANIES LLC, 2050 Main St Ste 650', 'c/o stays in street');
// owners (Miami-Dade order = first last)
const ow = (s, order, gov) => { const o = S.parseOwner(s, { order: order || 'first-last', gov }); return [o.type, o.first, o.last, o.company, o.first2, o.last2]; };
eq(ow('MIROLJUB FILIPOVIC'), ['Individual', 'MIROLJUB', 'FILIPOVIC', '', '', ''], 'individual');
eq(ow('ADRIEN ROLANDO VAZQUEZ SALGADO | ADRIANA CARDONA')[1], 'ADRIEN', 'two owners first');
eq(ow('MARC ROCHMAN | JOELLE ROCHMAN'), ['Individual', 'MARC', 'ROCHMAN', '', 'JOELLE', 'ROCHMAN'], 'two owners');
eq(ow('DALE L SPEAR &W WILMA'), ['Individual', 'DALE', 'SPEAR', '', 'WILMA', 'SPEAR'], '&W wife borrows surname');
eq(ow('ENRIQUE MONTES &W BERTHA A')[0], 'Individual', '&W');
eq(ow('ZENON CONTRERAS & | MARIA CONTRERAS'), ['Individual', 'ZENON', 'CONTRERAS', '', 'MARIA', 'CONTRERAS'], 'dangling &');
eq(ow('EDUARDO L IBARRA TRS | EDUARDO L IBARRA REVOCABLE TRUST | MARLENE M IBARRA TRS'), ['Trust', 'EDUARDO', 'IBARRA', '', 'MARLENE', 'IBARRA'], 'trustee individual');
eq(ow('AGUSTIN MOLINA JR | CRISTINA MOLINA')[1], 'AGUSTIN', 'Jr dropped'); eq(ow('PAMI COMPANY LLC'), ['Company', '', '', 'PAMI COMPANY LLC', '', ''], 'company');
eq(ow('NEW JERUSALEM PRIMITIVE | BAPTIST CHURCH INC')[0], 'Company', 'church split over lines'); eq(ow('CEMEX CONSTRUCTION MATERIALS | C/O TAX DEPARTMENT | FLORIDA LLC')[0], 'Company', 'c/o company');
eq(ow('LEACH NANCY PRICE LIVING TRUST', 'last-first')[0], 'Trust', 'trust entity'); eq(ow('HENKEL ROBERT', 'last-first'), ['Individual', 'ROBERT', 'HENKEL', '', '', ''], 'Monroe order last-first');
eq(ow('SMITH JOHN & MARY', 'last-first'), ['Individual', 'JOHN', 'SMITH', '', 'MARY', 'SMITH'], 'Monroe & first name only');
eq(ow('CITY OF MIAMI', 'first-last')[0], 'Government', 'government'); eq(ow('ANYTHING', 'first-last', true)[0], 'Government', 'gov flag');
// keys match across roll order and provider order
eq(S.ownerKeys('HENKEL ROBERT D', { order: 'last-first' })[0], S.ownerKeys('ROBERT HENKEL')[0], 'owner key roll vs provider order');
// export row
const er = S.exportRow({ folio: '1078130000540', folioOut: '10-7813-000-0540', addr: '605 SW 4 ST', city: 'Homestead', zip: '33030', owner: 'ARMANDO CUESTA', mail: '605 SW 4 ST, HOMESTEAD, FL 33030-1111' }, { county: 'Miami-Dade', count: 1 });
eq(er.slice(0, 8), ['605 SW 4 ST', 'Homestead', 'FL', '33030', 'Armando', 'Cuesta', '', 'N'], 'export row'); eq(er.slice(12, 20), ['605 SW 4 ST', 'HOMESTEAD', 'FL', '33030-1111', '10-7813-000-0540', 'Miami-Dade', 1, '10-7813-000-0540'], 'export row mailing/folio');
eq(S.exportRow({ folio: '1', addr: 'X', owner: 'ANEDLA LLC', mail: '' }, {})[6], 'Anedla LLC', 'company name title-cased, LLC upper');
// mapping layouts
const L1 = ['Folio', 'Property Address', 'City', 'State', 'Zip', 'Owner First Name', 'Owner Last Name', 'Phone 1', 'Phone 1 Type', 'Phone 1 DNC', 'Phone 2', 'Phone 2 Type', 'Phone 2 DNC', 'Email 1', 'Email 2'];
const m1 = S.detectMapping(L1); eq([m1.folio, m1.addr, m1.city, m1.zip, m1.first, m1.last], [0, 1, 2, 4, 5, 6], 'layout 1 identity'); eq(m1.phones.map(p => [p.num, p.type, p.dnc]), [[7, 8, 9], [10, 11, 12]], 'layout 1 phone slots'); eq(m1.emails, [13, 14], 'layout 1 emails');
const L2 = ['input_address', 'Input City', 'Owner Name', 'Mailing Address', 'Mailing City', 'Mailing Zip', 'Mobile 1', 'Mobile 2', 'Landline 1', 'DNC Status', 'Email Address', 'Matched Name'];
const m2 = S.detectMapping(L2); eq([m2.addr, m2.city, m2.owner, m2.mail, m2.mailCity, m2.mailZip, m2.rowDnc, m2.name], [0, 1, 2, 3, 4, 5, 9, 11], 'layout 2 identity'); eq(m2.phones.map(p => [p.num, p.implied]), [[6, 'm'], [7, 'm'], [8, 'l']], 'layout 2 implied types'); eq(m2.emails, [10], 'layout 2 email');
const L3 = ['Parcel ID', 'Site Address', 'Wireless Phone 1', 'Wireless 1 DNC', 'Landline Phone 1']; const m3 = S.detectMapping(L3); eq(m3.folio, 0, 'parcel id = folio'); eq(m3.phones.length, 2, 'wireless/landline slots'); eq(m3.phones[0].dnc, 3, 'wireless dnc column linked');
const r1 = S.readRow(['10-7813-000-0540', '605 SW 4 ST', 'Homestead', 'FL', '33030', 'Armando', 'Cuesta', '(305) 555-1234', 'Mobile', 'N', '786-555-0000', 'Landline', 'Y', 'a@B.com', ''], m1);
eq([r1.folio, r1.zip, r1.phones, r1.emails], ['1078130000540', '33030', [['3055551234', 'm', 0], ['7865550000', 'l', 1]], ['a@b.com']], 'readRow layout 1');
// matcher
const rows = [S.readRow(['', '605 SW 4th Street', '', '', '33030', 'Armando', 'Cuesta', '3055551234', 'Mobile', 'N', '', '', '', '', ''], m1), S.readRow(['1078130000540', '', '', '', '', '', '', '3055559999', '', '', '', '', '', '', ''], m1), S.readRow(['', '', '', '', '', 'Jose', 'Nobody', '3055550000', '', '', '', '', '', '', ''], m1)];
const mt = S.matcher(rows, {}); const parcels = [{ folio: '1078130000540', addr: '605 SW 4 ST', zip: '33030', owner: 'ARMANDO CUESTA', mail: '605 SW 4 ST, HOMESTEAD, FL 33030' }, { folio: '1078130000550', addr: '10 NW 1 AVE', zip: '33030', owner: 'X LLC', mail: '' }];
parcels.forEach(p => mt.visit(p)); const res = mt.resolve(); eq(res.map(r => r.how), ['address', 'folio', ''], 'matcher tiers'); eq(res[0].parcels[0].folio, '1078130000540', 'address match resolves folio');
// owner+mailing tier
const L4 = ['Owner Name', 'Mailing Address', 'Mailing Zip', 'Phone']; const m4 = S.detectMapping(L4); const r4 = S.readRow(['Armando Cuesta', '605 SW 4th St', '33030', '305-555-7777'], m4);
const mt4 = S.matcher([r4], {}); parcels.forEach(p => { mt4.visit(p); mt4.visitOwner(p); }); eq(mt4.resolve()[0].how, 'owner', 'owner+mailing tier'); eq(mt4.resolve()[0].parcels.length, 1, 'owner tier parcel');
// store
const mem = {}; const st = S.makeStore('k', { getItem: k => mem[k] || null, setItem: (k, v) => { mem[k] = v; }, removeItem: k => { delete mem[k]; } });
st.merge('1078130000540', { p: [['3055551234', 'm', 0], ['7865550000', 'l', 1]], e: ['a@b.com'] }, 'f.csv', '2026-10-16'); st.merge('1078130000540', { p: [['3055551234', 'm', 1]], e: [] }); st.commit();
eq(st.get('1078130000540').p, [['3055551234', 'm', 1], ['7865550000', 'l', 1]], 'merge updates flags'); eq(st.hasPhone('1078130000540'), true, 'hasPhone'); eq(JSON.parse(mem.k)['1078130000540'].a, '2026-10-16', 'persisted');
st.clear(); eq(st.count(), 0, 'clear'); eq(mem.k, undefined, 'clear removes key');
eq(S.canText(['3055551234', 'm', 0]), true, 'canText mobile'); eq(S.canText(['3055551234', 'l', 0]), false, 'no landline text'); eq(S.canText(['3055551234', 'm', 1]), false, 'no DNC text');
console.log(fails ? fails + ' FAILED' : 'ALL PASS'); process.exit(fails ? 1 : 0);
