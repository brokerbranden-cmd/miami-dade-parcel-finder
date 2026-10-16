/* Skip trace data layer (pure logic + per-county browser storage). No network: skip tracing happens at the provider of your choice
   through a CSV round trip (export -> provider -> import). Everything here is plain functions so it can be unit tested in node
   (tests/unit_skiptrace.js) and used by the page (window.PFSkip).
   Storage: localStorage[PFCounty.key('pf.skip.v1')] = { <folio digits>: {a:'YYYY-MM-DD', s:'source file', n:'provider name',
     p:[[10-digit phone, type 'm'|'l'|'v'|'', flags (1 = DNC, 2 = litigator)]], e:[emails]} }   (a record with no p/e = traced, nothing found)
   Not legal advice: the DNC / litigator flags are whatever the provider returned. */
(function (root) {
  'use strict';
  const MAXP = 8, MAXE = 5;

  /* ---------- CSV ---------- */
  function parseCSV(text) {
    text = String(text == null ? '' : text).replace(/^\uFEFF/, '');
    const first = text.slice(0, 4000).split(/\r?\n/)[0] || '';
    const cnt = ch => (first.match(new RegExp(ch === '\t' ? '\\t' : '\\' + ch, 'g')) || []).length;
    let delim = ','; if (cnt('\t') > cnt(',') && cnt('\t') > 0) delim = '\t'; else if (cnt(';') > cnt(',')) delim = ';';
    const rows = []; let row = [], f = '', q = false, i = 0; const n = text.length;
    for (; i < n; i++) {
      const c = text[i];
      if (q) { if (c === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c; }
      else if (c === '"' && f === '') q = true;
      else if (c === delim) { row.push(f); f = ''; }
      else if (c === '\n' || c === '\r') { if (c === '\r' && text[i + 1] === '\n') i++; row.push(f); f = ''; rows.push(row); row = []; }
      else f += c;
    }
    if (f !== '' || row.length) { row.push(f); rows.push(row); }
    while (rows.length && rows[rows.length - 1].every(x => x === '')) rows.pop();
    return { rows, delim };
  }
  const csvq = s => { s = s == null ? '' : String(s); return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  const toCSV = rows => rows.map(r => r.map(csvq).join(',')).join('\n') + '\n';

  /* ---------- phones / emails ---------- */
  function normPhone(v) {
    let d = String(v == null ? '' : v).replace(/\D/g, '');
    if (d.length === 11 && d[0] === '1') d = d.slice(1);
    return d.length === 10 && !/^[01]/.test(d) ? d : '';
  }
  // a cell can hold several numbers ("305-555-1234; 786-555-9876")
  function phonesIn(v) {
    const s = String(v == null ? '' : v); const one = normPhone(s); if (one) return [one];
    const out = []; for (const part of s.split(/[;|\/\n]+|,\s*(?=\+?1?[\s.(-]*\d{3})/)) { const p = normPhone(part); if (p && !out.includes(p)) out.push(p); }
    return out;
  }
  const fmtPhone = p => /^\d{10}$/.test(p) ? '(' + p.slice(0, 3) + ') ' + p.slice(3, 6) + '-' + p.slice(6) : p;
  const normEmail = v => { const s = String(v == null ? '' : v).trim().toLowerCase(); return /^[^\s@,;]+@[^\s@,;]+\.[a-z]{2,}$/.test(s) ? s : ''; };
  function phoneType(v) {
    const s = String(v == null ? '' : v).toLowerCase();
    if (/mobile|wireless|cell/.test(s)) return 'm'; if (/land|wireline|fixed|residential/.test(s)) return 'l'; if (/voip|internet|virtual/.test(s)) return 'v'; return '';
  }
  const TYPE_NAME = { m: 'mobile', l: 'landline', v: 'VoIP', '': '' };
  // DNC / litigator flag cells. Y / yes / true / 1 / "DNC" / "on dnc list" = flagged; N / no / false / 0 / blank / "clean" / "not listed" = not
  function truthy(v) {
    const s = String(v == null ? '' : v).trim().toLowerCase(); if (!s) return false;
    if (/^(n|no|false|f|0|clean|none|not listed|not on dnc|not dnc|ok|pass|passed|safe|-|n\/a|na)$/.test(s)) return false;
    if (/^(not|no |non)/.test(s) && !/dnc/.test(s.replace(/^(not|no|non)\W*(on\W*)?(dnc|do not call)/, ''))) return false;
    return /^(y|yes|true|t|1|dnc|x|listed|flag|flagged|block|blocked|fail|failed|do not call|on dnc|on list)/.test(s) || /\b(dnc|do not call|litigator|tcpa)\b/.test(s) && !/\bnot\b|\bno\b|clean/.test(s);
  }

  /* ---------- addresses ---------- */
  const SUF = { STREET: 'ST', STR: 'ST', AVENUE: 'AVE', AV: 'AVE', ROAD: 'RD', DRIVE: 'DR', COURT: 'CT', TERRACE: 'TER', TERR: 'TER', PLACE: 'PL', BOULEVARD: 'BLVD', LANE: 'LN', HIGHWAY: 'HWY', PARKWAY: 'PKWY', CIRCLE: 'CIR', TRAIL: 'TRL', CAUSEWAY: 'CSWY', SQUARE: 'SQ', PLAZA: 'PLZ', ALLEY: 'ALY', CRESCENT: 'CRES', EXPRESSWAY: 'EXPY', TURNPIKE: 'TPKE', BOULV: 'BLVD', BLV: 'BLVD' };
  const DIR = { NORTH: 'N', SOUTH: 'S', EAST: 'E', WEST: 'W', NORTHEAST: 'NE', NORTHWEST: 'NW', SOUTHEAST: 'SE', SOUTHWEST: 'SW' };
  const UNIT_WORDS = new Set(['APT', 'APARTMENT', 'UNIT', 'STE', 'SUITE', 'BLDG', 'BUILDING', 'FL', 'FLOOR', 'LOT', 'RM', 'ROOM', 'NO', 'NUM', 'NUMBER', 'SPC', 'SPACE', 'PH', 'PENTHOUSE', 'TRLR', 'OFC']);
  const STREET_TYPES = new Set(Object.values(SUF).concat(['WAY', 'LOOP', 'PATH', 'ROW', 'RUN', 'WALK', 'PASS', 'CV', 'COVE', 'KEY', 'KEYS', 'PT', 'POINT', 'ISLE', 'ISLAND', 'BAY', 'BCH', 'BEACH', 'HTS', 'HEIGHTS', 'GRV', 'GROVE', 'PARK', 'PK', 'RDG', 'RIDGE', 'XING', 'CROSSING', 'TRCE', 'HOLW', 'BND', 'BEND']));
  // key for a street address: 'NUMBER DIR NAME TYPE [UNIT]' normalized; also base (without a trailing unit)
  function addrKeys(raw) {
    let s = String(raw == null ? '' : raw).toUpperCase().replace(/&/g, ' AND ');
    if (s.includes(',')) { const parts = s.split(','); const wi = parts.findIndex(p => /\d/.test(p) && !/^\s*(C\/O|ATTN|%)/.test(p)); const at = wi >= 0 ? wi : 0; s = parts[at]; for (let j = at + 1; j < parts.length && /^\s*(APT|APARTMENT|UNIT|STE|SUITE|BLDG|FL|FLOOR|LOT|RM|ROOM|#)\b/.test(parts[j]); j++) s += ' ' + parts[j]; }
    s = s.replace(/#/g, ' # ').replace(/[^A-Z0-9# ]+/g, ' ').replace(/\s+/g, ' ').trim();
    if (!s) return { full: '', base: '' };
    const toks = []; for (let t of s.split(' ')) {
      if (!t) continue; if (/^\d+(ST|ND|RD|TH)$/.test(t)) t = t.replace(/(ST|ND|RD|TH)$/, '');
      if (t === '#' || UNIT_WORDS.has(t)) { toks.push('~'); continue; }
      toks.push(SUF[t] || DIR[t] || t);
    }
    // drop unit designator markers, keeping the unit value; remember where the unit starts
    let unitAt = -1; const out = []; for (const t of toks) { if (t === '~') { if (unitAt < 0) unitAt = out.length; continue; } out.push(t); }
    if (unitAt < 0) { // no designator: unit = trailing token(s) after the street type ("5555 COLLEGE RD 14")
      let ti = -1; for (let k = out.length - 2; k >= 1; k--) if (STREET_TYPES.has(out[k]) && k < out.length - 1) { ti = k; break; }
      if (ti >= 0 && out.length - ti - 1 <= 2 && ti >= 2) unitAt = ti + 1;
    }
    const full = out.join(' '), base = unitAt >= 0 ? out.slice(0, unitAt).join(' ') : full;
    return { full, base };
  }
  const zip5 = z => { const m = String(z == null ? '' : z).match(/\b(\d{5})(?:-\d{4})?\b/); return m ? m[1] : ''; };
  // "street, CITY, ST 33130-1234" -> parts. C/O and attention lines stay in the street part.
  function parseMailing(s) {
    s = String(s == null ? '' : s).replace(/\s+/g, ' ').trim(); if (!s) return { street: '', city: '', state: '', zip: '' };
    let m = s.match(/^(.*?),\s*([^,]+?),?\s+([A-Za-z]{2})\s+(\d{5})(?:-(\d{4}))?\s*$/);
    if (m) return { street: m[1].trim(), city: m[2].trim(), state: m[3].toUpperCase(), zip: m[4] + (m[5] ? '-' + m[5] : '') };
    m = s.match(/^(.*?),?\s+([A-Za-z]{2})\s+(\d{5})(?:-(\d{4}))?\s*$/);
    if (m) return { street: m[1].trim(), city: '', state: m[2].toUpperCase(), zip: m[3] + (m[4] ? '-' + m[4] : '') };
    return { street: s, city: '', state: '', zip: '' };
  }
  const mailKey = mail => { const m = parseMailing(mail); const k = addrKeys(m.street).base; return k ? k + '|' + zip5(m.zip) : ''; };

  /* ---------- owner names ---------- */
  const CO_RE = /\b(LLC|L L C|LLP|LP|LTD|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|PA|PLLC|PC|BANK|ASSOC|ASSOCIATION|ASSN|HOLDINGS?|INVESTMENTS?|INVESTORS?|PROPERT(?:Y|IES)|REALTY|ENTERPRISES?|PARTNERS|PARTNERSHIP|VENTURES?|GROUP|DEVELOPMENT|DEVELOPERS?|CHURCH|MINISTRIES|MINISTRY|FOUNDATION|CONDOMINIUM|CONDO|HOMEOWNERS?|DST|FUND|CAPITAL|MANAGEMENT|MGMT|APARTMENTS?|MARINA|CLUB|HOSPITAL|HOTEL|RESORT|SERVICES?|CONSTRUCTION|BUILDERS?|HOMES|TOWERS?|ASSOCIATES|INTERNATIONAL|INTL|SOLUTIONS|TRADING|MOTORS|RESTAURANT|SCHOOL|COOPERATIVE|ASSETS?|EQUITY|MORTGAGE|FINANCIAL|LENDING|AUTHORITY|DISTRICT|BOARD|CITY|COUNTY|STATE|UNITED STATES|DEPARTMENT|DEPT|HOUSING|FLORIDA|FL|MIAMI|KEYS|ISLAND|ISLANDS|BAPTIST|CATHOLIC|METHODIST|TEMPLE|MOSQUE|CHAPEL|TRUST COMPANY|TRUSTEES?|NOMINEES?|C\/O|ATTN)\b/;
  const GOV_RE = /\b(CITY OF|COUNTY|STATE OF|BOARD OF|DISTRICT|AUTHORITY|UNITED STATES|DEPT|DEPARTMENT|HOUSING|SCHOOL BOARD|BOT|TIIF|NATIONAL PARK|USA|U S A|TOWN OF|VILLAGE OF|FLORIDA DEP|FDOT|MDC|WASD)\b/;
  const TRUST_ENT = /\b(TRUST|REVOCABLE|IRREVOCABLE|LIVING|FAMILY|LIV TR|REV TR|FBO|TRUSTEES)\b/;
  const TRUSTEE_TAIL = /\s+(JTRS|TRS|TRUSTEES?|TTEES?|TR|TTEE)\s*$/;
  const ESTATE_RE = /\b(ESTATE OF|EST OF|ESTATE|HEIRS|HEIR|DECEASED|DECD|LIFE ESTATE|LE)\b/;
  const SUFFIX = new Set(['JR', 'SR', 'II', 'III', 'IV', 'V', 'JUNIOR', 'SENIOR', 'ET', 'AL', 'ETAL', 'UX', 'ETUX', 'VIR', 'ETVIR', 'LE', 'DEC', 'DECD', 'EST', 'MD', 'DDS', 'ESQ']);
  const TRUST_TAIL = /\b(LIVING|REVOCABLE|IRREVOCABLE|FAMILY|LIV|REV|TRUST|TR|TRS|TRUSTEE|TRUSTEES|JTRS|TTEE|UNDER WILL OF|AS TRUSTEE|U\/A|DTD|DATED)\b.*$/;
  function cleanSeg(s) {
    return String(s || '').toUpperCase().replace(/&AMP;|&H;|&W;/g, ' & ').replace(/\s*&[WH]\s+/g, ' & ').replace(/\s*&[WH]?\s*$/g, '').replace(/[.,]/g, ' ').replace(/\s+/g, ' ').trim();
  }
  function personOf(tokens, order) {
    tokens = tokens.filter(t => t && !SUFFIX.has(t)); if (!tokens.length) return null;
    if (tokens.length === 1) return { first: '', last: tokens[0], single: true };
    return order === 'last-first' ? { first: tokens[1], last: tokens[0], single: false } : { first: tokens[0], last: tokens[tokens.length - 1], single: false };
  }
  // people in one roll segment ("JOSE L SUAREZ", "SMITH JOHN & MARY", "DALE L SPEAR &W WILMA")
  function peopleOfSeg(seg, order) {
    const parts = seg.split(/\s+(?:&|AND)\s+/).map(p => p.trim().split(' ').filter(Boolean)).filter(p => p.length);
    const people = parts.map(p => personOf(p, order)).filter(Boolean);
    const multi = people.find(p => !p.single);
    return people.map(p => { if (p.single && multi) { return order === 'last-first' ? { first: p.last, last: multi.last } : { first: p.last, last: multi.last }; } return p; });
  }
  const upper = s => String(s == null ? '' : s).toUpperCase();
  function classifySeg(seg, opts) {
    const u = cleanSeg(seg); if (!u) return null;
    if (opts && opts.gov) return { u, kind: 'gov' };
    if (GOV_RE.test(u) && !/\bTRS?\b/.test(u)) return { u, kind: 'gov' };
    if (/\d/.test(u) && !/^\d+\s*(ST|ND|RD|TH)\b/.test(u)) return { u, kind: 'company' };
    const trusteeTail = TRUSTEE_TAIL.test(u);
    if (!trusteeTail && TRUST_ENT.test(u)) return { u, kind: 'trust-entity' };
    if (!trusteeTail && CO_RE.test(u)) return { u, kind: 'company' };
    const est = ESTATE_RE.test(u);
    let name = u.replace(TRUSTEE_TAIL, '').replace(/\b(ESTATE OF|EST OF|LIFE ESTATE|HEIRS OF|HEIRS|DECEASED|DECD)\b/g, ' ').replace(/\s+(LE|ETAL|ET AL|ETUX|ET UX|ET VIR)\s*$/, '').replace(/\s+/g, ' ').trim();
    if (trusteeTail && TRUST_TAIL.test(name)) name = name.replace(TRUST_TAIL, '').trim();
    const people = peopleOfSeg(name, (opts && opts.order) || 'first-last');
    if (!people.length || (people.length === 1 && people[0].single)) return { u, kind: 'fragment' };
    return { u, kind: trusteeTail ? 'trustee' : est ? 'estate' : 'person', people };
  }
  // owner roll string ("A | B") -> structure used by the exports
  function parseOwner(owner, opts) {
    opts = opts || {}; const segs = String(owner == null ? '' : owner).split(/\s*\|\s*|;\s+/).map(s => s.trim()).filter(Boolean);
    const cl = segs.map(s => classifySeg(s, opts)).filter(Boolean);
    const full = segs.join('; ');
    const peopleSegs = cl.filter(c => c.people); const people = []; for (const c of peopleSegs) for (const p of c.people) people.push(p);
    // roll names wrap over lines ("NEW JERUSALEM PRIMITIVE | BAPTIST CHURCH INC"): any company-looking line makes the whole owner a company
    const coSeg = cl.some(c => (c.kind === 'company' || c.kind === 'gov') && !/^(C\/O|ATTN|%)/.test(c.u));
    if (people.length && !coSeg) {
      const prim = peopleSegs[0];
      return { type: prim.kind === 'trustee' ? 'Trust' : prim.kind === 'estate' ? 'Estate' : 'Individual', isCompany: false, first: people[0].first, last: people[0].last, first2: (people[1] || {}).first || '', last2: (people[1] || {}).last || '', company: '', full, people };
    }
    const names = cl.filter(c => !/^(C\/O|ATTN|%)/.test(c.u)).map(c => c.u);
    const gov = cl.length && cl.every(c => c.kind === 'gov'), trust = cl.some(c => c.kind === 'trust-entity');
    return { type: gov ? 'Government' : trust ? 'Trust' : 'Company', isCompany: true, first: '', last: '', first2: '', last2: '', company: names.join(' ') || full, full, people: [] };
  }
  const CO_SUFFIX = /\b(LLC|L L C|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LLP|LP|PA|PLLC|THE)\b/g;
  const companyKey = s => upper(s).replace(/[^A-Z0-9 ]+/g, ' ').replace(CO_SUFFIX, ' ').split(/\s+/).filter(Boolean).sort().join(' ');
  const personKey = (first, last) => { const a = upper(first).replace(/[^A-Z]/g, ' ').trim().split(/\s+/)[0] || '', b = upper(last).replace(/[^A-Z]/g, ' ').trim().split(/\s+/).pop() || ''; return a && b ? [a, b].sort().join(' ') : ''; };
  // every identity an owner roll string can be matched on (each person, or the company)
  function ownerKeys(owner, opts) {
    const o = parseOwner(owner, opts); if (o.isCompany) { const k = companyKey(o.company); return k ? ['C:' + k] : []; }
    const out = []; for (const p of o.people) { const k = personKey(p.first, p.last); if (k && !out.includes('P:' + k)) out.push('P:' + k); } return out;
  }
  // grouping key for "same owner at the same mailing address" (dedupe + applying one result to all of that owner's properties)
  function ownerGroupKey(owner, mail, propAddr, opts) {
    const k = ownerKeys(owner, opts)[0] || 'X:' + upper(owner).replace(/[^A-Z0-9]+/g, ' ').trim(); const m = mailKey(mail);
    return k + '|' + (m || 'P:' + addrKeys(propAddr).base);
  }

  /* ---------- skip trace export ---------- */
  const EXPORT_HEAD = ['Property Address', 'City', 'State', 'Zip', 'Owner First Name', 'Owner Last Name', 'Company Name', 'Is Company', 'Owner Type', 'Owner Name (full)', 'Owner 2 First Name', 'Owner 2 Last Name', 'Mailing Address', 'Mailing City', 'Mailing State', 'Mailing Zip', 'Folio', 'County', 'Property Count', 'All Folios'];
  const title = s => String(s || '').replace(/\w\S*/g, w => w[0] + w.slice(1).toLowerCase()).replace(/\b(Llc|Lp|Llp|Inc|Pllc|Dst|Pa)\b/g, m => m.toUpperCase());
  // p: {folio, addr, city, zip, owner, mail, gov}; opts: {order, county, state, count, folios}
  function exportRow(p, opts) {
    opts = opts || {}; const o = parseOwner(p.owner, { order: opts.order, gov: !!p.gov }), m = parseMailing(p.mail);
    const nm = s => title(s);
    return [p.addr || '', p.city || '', opts.state || 'FL', zip5(p.zip) || p.zip || '', nm(o.first), nm(o.last), o.company ? title(o.company) : '', o.isCompany ? 'Y' : 'N', o.type, o.full,
      nm(o.first2), nm(o.last2), m.street, m.city, m.state, m.zip, p.folioOut || p.folio, opts.county || '', opts.count || 1, (opts.folios || [p.folioOut || p.folio]).join(';')];
  }

  /* ---------- text list ---------- */
  const TEXT_HEAD = ['First Name', 'Last Name', 'Phone', 'Phone Type', 'Email', 'Property Address', 'City', 'State', 'Zip', 'Owner Name', 'Folio', 'County'];
  const splitName = (n, order) => { const t = String(n || '').trim().split(/\s+/).filter(Boolean); if (!t.length) return ['', '']; if (t.length === 1) return [t[0], '']; return order === 'last-first' ? [t[1], t[0]] : [t[0], t[t.length - 1]]; };

  /* ---------- column detection ---------- */
  const normH = h => String(h == null ? '' : h).toLowerCase().replace(/[_\-\/.:]+/g, ' ').replace(/([a-z])(\d)/g, '$1 $2').replace(/(\d)([a-z])/g, '$1 $2').replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim();
  const FIELDS = [['folio', 'Folio / parcel ID'], ['addr', 'Property address'], ['city', 'Property city'], ['zip', 'Property zip'], ['owner', 'Owner name (full)'], ['first', 'Owner first name'], ['last', 'Owner last name'], ['company', 'Company name'],
    ['mail', 'Mailing address'], ['mailCity', 'Mailing city'], ['mailZip', 'Mailing zip'], ['name', 'Person found (name from provider)'], ['rowDnc', 'Row-level DNC flag'], ['rowLit', 'Row-level litigator flag']];
  function detectMapping(headers) {
    const H = headers.map(normH), used = new Set(), map = { phones: [], emails: [] };
    const take = (k, test) => { for (let i = 0; i < H.length; i++) if (!used.has(i) && test(H[i], i)) { map[k] = i; used.add(i); return; } map[k] = -1; };
    const isMail = h => /\bmail/.test(h) || /\bowner (street|address|city|zip)/.test(h);
    // phones first so "phone" columns are never taken as names
    const phoneHead = h => /\b(phone|mobile|cell|cellular|wireless|landline|telephone|tel|ph|phn)\b/.test(h) && !/\b(email|fax)\b/.test(h);
    const subOf = h => /\b(type|line type|linetype|usage|kind)\b/.test(h) ? 'type' : /\b(dnc|do not call|nodnc|tcpa|litigator|scrub|registry|dncflag)\b/.test(h) ? (/litig/.test(h) ? 'lit' : 'dnc') : /\b(score|rank|confidence|status|verified|valid|last|age|date|carrier|source|provider|reachable|connected|ranking|label|seen|first seen)\b/.test(h) ? 'skip' : 'num';
    const slotKey = h => { const kind = /\b(mobile|cell|cellular|wireless)\b/.test(h) ? 'm' : /\b(landline|wireline)\b/.test(h) ? 'l' : /\bvoip\b/.test(h) ? 'v' : ''; const d = (h.match(/\b(\d{1,2})\b/) || [])[1] || ''; return kind + ':' + d; };
    const slots = [], subs = [];
    H.forEach((h, i) => { if (!phoneHead(h)) return; const s = subOf(h); if (s === 'skip') return; if (s === 'num') slots.push({ i, key: slotKey(h), implied: slotKey(h).split(':')[0], type: -1, dnc: -1, lit: -1 }); else subs.push({ i, s, key: slotKey(h) }); });
    const fits = (sl, sub) => sl.key === sub.key || (sl.key.split(':')[1] === sub.key.split(':')[1] && !sub.key.split(':')[0]) || (!sub.key.split(':')[1] && sl.implied === sub.key.split(':')[0]);
    for (const sub of subs) { let best = slots.find(sl => sl[sub.s] < 0 && sl.key === sub.key) || slots.find(sl => sl[sub.s] < 0 && fits(sl, sub)); if (!best && slots.length === 1) best = slots[0]; if (best) { best[sub.s] = sub.i; used.add(sub.i); } }
    slots.forEach(s => used.add(s.i)); map.phones = slots.slice(0, 12).map(s => ({ num: s.i, type: s.type, dnc: s.dnc, lit: s.lit, implied: s.implied }));
    // emails
    H.forEach((h, i) => { if (!used.has(i) && /\be ?mail\b|\bemail/.test(h) && !/\b(status|valid|verified|type|score|date|confidence|source|opt)\b/.test(h) && map.emails.length < MAXE) { map.emails.push(i); used.add(i); } });
    take('folio', h => /\b(folio|parcel|apn|pin|account|tax id|strap|re number|property id|parcel id)\b/.test(h) && !/\b(count|all)\b/.test(h));
    take('mailCity', h => isMail(h) && /\bcity\b/.test(h)); take('mailZip', h => isMail(h) && /\b(zip|postal|zipcode)\b/.test(h));
    take('mail', h => isMail(h) && /\b(address|addr|street|line|mailing)\b/.test(h) && !/\b(city|state|zip|postal)\b/.test(h));
    take('addr', h => !isMail(h) && (/\b(property|site|situs|subject|input|house|prop)\b.*\b(address|addr|street)\b/.test(h) || /^(street )?address( 1| line 1)?$|^street$|^addr$/.test(h)) && !/\b(city|state|zip|count|full)\b/.test(h));
    take('city', h => !isMail(h) && /^((property|site|input|situs|prop) )?city$/.test(h)); take('zip', h => !isMail(h) && /^((property|site|input|situs|prop) )?(zip|postal|zip ?code|zipcode)( code)?$/.test(h));
    take('first', h => /\b(owner )?(first|given) name\b|^(owner )?first$|^fname$|\bowner 1 first\b/.test(h) && !/\bowner 2\b/.test(h)); take('last', h => /\b(owner )?(last|sur|family) name\b|^(owner )?last$|^lname$|\bowner 1 last\b/.test(h) && !/\bowner 2\b/.test(h));
    take('company', h => /\b(company|business|entity|organization|organisation|corp)\b( name)?$|^company/.test(h) && !/\b(is|flag|type|count)\b/.test(h));
    take('owner', h => /^(owner|owner 1|full|contact|input owner|property owner)?\s*(full )?name( full)?$|^owner( name)?( full)?$|^owner name \( ?full ?\)$|^owner name full$|\bowner name\b/.test(h) && !/\b(first|last|2|two|company)\b/.test(h));
    take('name', h => /\b(person|found|matched|output|result|resident|contact|primary)\b.*\bname\b|^name$|^full name$/.test(h));
    take('rowDnc', h => /\b(dnc|do not call)\b/.test(h) && !/\b(phone|mobile|cell)\b/.test(h) && !/\b(lit|litigator)\b/.test(h)); take('rowLit', h => /\b(litigator|tcpa)\b/.test(h));
    return map;
  }
  const getv = (row, i) => i >= 0 && i < row.length ? String(row[i] == null ? '' : row[i]).trim() : '';

  /* Turn one import row into what we need: match info + contact record. map as from detectMapping (or edited by the user). */
  function readRow(row, map, opts) {
    opts = opts || {};
    const r = { folio: '', addr: '', zip: '', owner: '', first: '', last: '', company: '', mail: '', name: '', phones: [], emails: [] };
    r.folio = getv(row, map.folio).replace(/\D/g, ''); r.addr = getv(row, map.addr); r.zip = zip5(getv(row, map.zip)) || zip5(r.addr);
    const first = getv(row, map.first), last = getv(row, map.last), company = getv(row, map.company), owner = getv(row, map.owner);
    r.first = first; r.last = last; r.company = company; r.owner = owner || [first, last].filter(Boolean).join(' ') || company;
    const mailStreet = getv(row, map.mail), mc = getv(row, map.mailCity), mz = getv(row, map.mailZip);
    r.mail = mailStreet ? (mc || mz ? mailStreet + ', ' + mc + ', FL ' + mz : mailStreet) : ''; r.mailStreet = mailStreet; r.mailZip = zip5(mz) || zip5(mailStreet);
    r.name = getv(row, map.name);
    const rowDnc = map.rowDnc >= 0 && truthy(getv(row, map.rowDnc)), rowLit = map.rowLit >= 0 && truthy(getv(row, map.rowLit));
    for (const sl of map.phones) {
      const cell = getv(row, sl.num); if (!cell) continue; const nums = phonesIn(cell); if (!nums.length) continue;
      let t = sl.type >= 0 ? phoneType(getv(row, sl.type)) : ''; if (!t && sl.implied) t = sl.implied;
      let fl = 0; if (rowDnc || (sl.dnc >= 0 && truthy(getv(row, sl.dnc)))) fl |= 1; if (rowLit || (sl.lit >= 0 && truthy(getv(row, sl.lit)))) fl |= 2;
      for (const n of nums) if (!r.phones.some(p => p[0] === n)) r.phones.push([n, t, fl]);
    }
    for (const ei of map.emails) { const e = normEmail(getv(row, ei)); if (e && !r.emails.includes(e)) r.emails.push(e); }
    return r;
  }

  /* ---------- matching ---------- */
  // rows: readRow() results. Build once, then visit() every parcel ({folio digits, addr, zip, owner, mail, order}).
  function matcher(rows, opts) {
    opts = opts || {}; const order = opts.order || 'first-last';
    const useF = opts.folio !== false, useA = opts.addr !== false, useO = opts.owner !== false;
    const byFolio = new Map(), byFull = new Map(), byBase = new Map(), byOwner = new Map();
    const push = (m, k, i) => { if (!k) return; let a = m.get(k); if (!a) m.set(k, a = []); a.push(i); };
    rows.forEach((r, i) => {
      r._ok = ownerKeys(r.owner || r.name, { order: opts.rowOrder || 'first-last' });
      if (r.first && r.last) { const k = personKey(r.first, r.last); if (k) r._ok = ['P:' + k]; }
      else if (r.company) { const k = companyKey(r.company); if (k) r._ok = ['C:' + k]; }
      if (useF && r.folio) { const d = r.folio.length <= 13 ? r.folio.padStart(13, '0') : r.folio.length <= 14 ? r.folio.padStart(14, '0') : r.folio; push(byFolio, d, i); }
      if (useA && r.addr) { const k = addrKeys(r.addr); r._ak = k; push(byFull, k.full, i); if (k.base !== k.full) push(byBase, k.base, i); else push(byBase, k.base, i); }
      if (useO && r._ok.length && r.mailStreet !== undefined && r.mailStreet) { r._mk = (addrKeys(r.mailStreet).base || '') + '|' + (r.mailZip || ''); for (const k of r._ok) push(byOwner, k + '||' + r._mk, i); }
    });
    const hits = rows.map(() => ({ folio: [], full: [], base: [], owner: [] }));
    // cheap prefilters so a scan over ~1M parcels only normalizes the few that can match
    const nums = new Set(), mq = new Set(); rows.forEach(r => { const m = /^\s*(\d+)/.exec(r.addr || ''); if (m) nums.add(m[1]); const n = /^\s*(\d+)/.exec(r.mailStreet || ''); if (n) mq.add(n[1] + '|' + (r.mailZip || '')); });
    const snap = p => ({ folio: p.folio, addr: p.addr, zip: p.zip, owner: p.owner, mail: p.mail, gov: p.gov }), memo = new Map();
    const once = p => { let q = memo.get(p.folio); if (!q) memo.set(p.folio, q = snap(p)); return q; };
    function visit(p) {
      if (byFolio.size) { const f = p.folio; let a = byFolio.get(f); if (a) { const q = once(p); a.forEach(i => hits[i].folio.push(q)); } if (f.length > 14) { a = byFolio.get(f.slice(-14)); if (a) { const q = once(p); a.forEach(i => hits[i].folio.push(q)); } } }
      if (byFull.size) { const ad = p.addr; if (!ad) return; const m = /^\s*(\d+)/.exec(ad); if (!m || !nums.has(m[1])) return;
        const k = addrKeys(ad); let a = byFull.get(k.full); if (a) { const q = once(p); a.forEach(i => hits[i].full.push(q)); }
        if (k.base) { a = byBase.get(k.base); if (a) { const q = once(p); a.forEach(i => { if (!hits[i].full.includes(q)) hits[i].base.push(q); }); } } }
    }
    function visitOwner(p) {
      if (!byOwner.size) return; const mail = p.mail; if (!mail) return; const n = /^\s*(\d+)/.exec(mail); if (!n || !mq.has(n[1] + '|' + zip5(mail))) return;
      const mk = (addrKeys(parseMailing(mail).street).base || '') + '|' + zip5(mail); if (mk === '|') return;
      for (const k of ownerKeys(p.owner, { order, gov: p.gov })) { const a = byOwner.get(k + '||' + mk); if (a) { const q = once(p); a.forEach(i => hits[i].owner.push(q)); } }
    }
    const nameHit = (r, p) => { if (!r._ok.length) return false; const ks = ownerKeys(p.owner, { order, gov: p.gov }); return ks.some(k => r._ok.includes(k)); };
    function resolve() {
      return rows.map((r, i) => {
        const h = hits[i]; let list, how;
        const uniq = a => { const s = new Map(); a.forEach(p => s.set(p.folio, p)); return [...s.values()]; };
        if (h.folio.length) { list = uniq(h.folio); how = 'folio'; }
        else if (h.full.length || h.base.length) {
          let c = uniq(h.full.length ? h.full : h.base);
          if (c.length > 1 && r.zip) { const z = c.filter(p => zip5(p.zip) === r.zip); if (z.length) c = z; }
          if (c.length > 1) { const nm = c.filter(p => nameHit(r, p)); if (nm.length) c = nm; }
          if (c.length > 1 && r._ak && r._ak.full !== r._ak.base) { /* unit given but several candidates */ }
          if (c.length === 1) { list = c; how = 'address'; } else if (c.length > 1) return { how: 'ambiguous', parcels: [], n: c.length };
        }
        if (!list && h.owner.length) { list = uniq(h.owner); how = 'owner'; }
        return list ? { how, parcels: list } : { how: '', parcels: [] };
      });
    }
    return { hits, visit, visitOwner, resolve, rows, flags: { folio: byFolio.size > 0, addr: byFull.size > 0, owner: byOwner.size > 0 } };
  }

  /* ---------- store ---------- */
  function makeStore(key, storage) {
    let data = {}, rev = 1, err = ''; const subs = new Set();
    const clean = o => { const out = {}; if (o && typeof o === 'object') for (const [f, x] of Object.entries(o)) { if (!/^\d{6,24}$/.test(f) || !x || typeof x !== 'object') continue; out[f] = { a: String(x.a || '').slice(0, 10), s: String(x.s || '').slice(0, 60), n: String(x.n || '').slice(0, 80), p: (Array.isArray(x.p) ? x.p : []).filter(q => Array.isArray(q) && /^\d{10}$/.test(q[0])).slice(0, MAXP).map(q => [q[0], ['m', 'l', 'v'].includes(q[1]) ? q[1] : '', (q[2] | 0) & 3]), e: (Array.isArray(x.e) ? x.e : []).filter(e => typeof e === 'string').slice(0, MAXE) }; } return out; };
    const load = () => { try { data = clean(JSON.parse(storage.getItem(key) || '{}')); } catch (e) { data = {}; } };
    const save = () => { try { storage.setItem(key, JSON.stringify(data)); err = ''; return true; } catch (e) { err = 'Browser storage is full: import a smaller file or clear old skip trace data.'; return false; } };
    let idx = null; const ix = () => idx || (idx = { phone: new Set(Object.keys(data).filter(f => data[f].p.length)), traced: new Set(Object.keys(data)) });
    const emit = () => { rev++; idx = null; subs.forEach(fn => { try { fn(); } catch (e) { console.warn(e); } }); };
    load();
    return {
      key, get rev() { return rev; }, get error() { return err; }, count: () => Object.keys(data).length, phoneCount: () => ix().phone.size,
      get: f => data[f] || null, has: f => !!data[f], hasPhone: f => !!(data[f] && data[f].p.length), phoneSet: () => ix().phone, tracedSet: () => ix().traced,
      size: () => { try { return (storage.getItem(key) || '').length; } catch (e) { return 0; } },
      onChange: fn => { subs.add(fn); return () => subs.delete(fn); }, reload() { load(); emit(); },
      // merge one result into a folio: phones/emails are united; a re-import updates flags/types of numbers already stored
      merge(f, rec, src, day) {
        const cur = data[f] || { a: '', s: '', n: '', p: [], e: [] }; const out = { a: day || cur.a, s: src || cur.s, n: rec.n || cur.n, p: cur.p.map(q => q.slice()), e: cur.e.slice() };
        for (const q of rec.p || []) { const ex = out.p.find(x => x[0] === q[0]); if (ex) { if (q[1]) ex[1] = q[1]; ex[2] = q[2] | 0; } else out.p.push([q[0], q[1] || '', q[2] | 0]); }
        for (const e of rec.e || []) if (!out.e.includes(e)) out.e.push(e);
        // best first: mobile and callable numbers on top
        const rank = q => (q[2] ? 4 : 0) + (q[1] === 'm' ? 0 : q[1] === '' ? 1 : q[1] === 'v' ? 2 : 3);
        out.p.sort((x, y) => rank(x) - rank(y)); out.p = out.p.slice(0, MAXP); out.e = out.e.slice(0, MAXE); data[f] = out; return out;
      },
      commit() { const ok = save(); emit(); return ok; },
      remove(f) { if (data[f]) { delete data[f]; save(); emit(); } },
      clear() { data = {}; try { storage.removeItem(key); } catch (e) {} emit(); },
      all: () => data
    };
  }

  const best = rec => { if (!rec) return null; return rec.p.filter(q => !(q[2] & 3)).sort((a, b) => (a[1] === 'm' ? 0 : a[1] === '' || a[1] === 'v' ? 1 : 2) - (b[1] === 'm' ? 0 : b[1] === '' || b[1] === 'v' ? 1 : 2))[0] || null; };
  const canText = q => !!q && q[1] !== 'l' && !(q[2] & 3);   // not DNC / litigator, and not a known landline

  root.PFSkip = { parseCSV, toCSV, csvq, normPhone, phonesIn, fmtPhone, normEmail, phoneType, TYPE_NAME, truthy, addrKeys, zip5, parseMailing, mailKey, parseOwner, ownerKeys, ownerGroupKey, personKey, companyKey, title,
    EXPORT_HEAD, exportRow, TEXT_HEAD, splitName, FIELDS, detectMapping, readRow, matcher, makeStore, best, canText, MAXP, MAXE };
  if (typeof module !== 'undefined' && module.exports) module.exports = root.PFSkip;
  if (typeof window !== 'undefined') {
    try { const PFC = window.PFCounty; root.PFSkip.store = makeStore(PFC ? PFC.key('pf.skip.v1') : 'pf.skip.v1', window.localStorage); } catch (e) { root.PFSkip.store = makeStore('pf.skip.v1', { getItem() { return null; }, setItem() { throw new Error('no storage'); }, removeItem() {} }); }
  }
})(typeof window !== 'undefined' ? window : globalThis);
