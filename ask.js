/* Ask: turns a plain-English request into the Parcel Finder's own filter state (no AI service, runs in the browser).
   PFAsk.parse(text, ctx) -> { county, jump:{folio}|null, parts:[{key,label,set,preset}], hints:[...], unknown:[...] }
   ctx: { county:'miami-dade'|'monroe'|'broward', cities:[...], has(layer)->bool, ideas:[available preset labels] }
   Each part's `set` is a partial filter state (same shape as app.js readState / applyState); app.js merges them on top of
   BLANK() (or a preset). Pure: no DOM, so tests/unit_ask.js runs it in node. */
(function (root) {
  'use strict';
  const COUNTIES = { 'miami-dade': 'Miami-Dade', monroe: 'Monroe', broward: 'Broward' };
  const CITY_OF = {   // for "... in Fort Lauderdale" while another county is open
    'miami-dade': ['Aventura','Bal Harbour','Bay Harbor Islands','Biscayne Park','Coral Gables','Cutler Bay','Doral','El Portal','Florida City','Golden Beach','Hialeah','Hialeah Gardens','Homestead','Indian Creek','Key Biscayne','Medley','Miami','Miami Beach','Miami Gardens','Miami Lakes','Miami Shores','Miami Springs','North Bay Village','North Miami','North Miami Beach','Opa-locka','Palmetto Bay','Pinecrest','South Miami','Sunny Isles Beach','Surfside','Sweetwater','Virginia Gardens','West Miami'],
    monroe: ['Key West','Key Largo','Marathon','Key Colony Beach','Big Pine Key','Plantation Key','Duck Key','Big Coppitt Key','Sugarloaf Key','Summerland Key','Islamorada','Tavernier','Stock Island','Cudjoe Key','Ramrod Key','Little Torch Key','Ocean Reef'],
    broward: ['Parkland','Coconut Creek','Deerfield Beach','Coral Springs','Margate','Tamarac','North Lauderdale','Pompano Beach','Lighthouse Point','Hillsboro Beach','Weston','Sunrise','Plantation','Lauderdale Lakes','Lauderhill','Fort Lauderdale','Oakland Park','Wilton Manors','Lauderdale By The Sea','Sea Ranch Lakes','Southwest Ranches','Pembroke Pines','Davie','Cooper City','Dania Beach','Hollywood','Miramar','West Park','Pembroke Park','Hallandale Beach']
  };
  /* Miami-Dade neighborhoods -> ZIP codes (approximate: a neighborhood rarely follows ZIP lines; the chip says so) */
  const HOODS = { 'little havana': ['33135', '33130'], 'wynwood': ['33127'], 'overtown': ['33136'], 'liberty city': ['33147', '33142'], 'little haiti': ['33138', '33137'], 'allapattah': ['33142', '33125'],
    'brickell': ['33129', '33131'], 'coconut grove': ['33133'], 'the grove': ['33133'], 'edgewater': ['33137'], 'kendall': ['33156', '33176', '33183', '33186'], 'westchester': ['33155', '33165'], 'flagami': ['33144', '33174'],
    'model city': ['33147'], 'little river': ['33150'], 'shenandoah': ['33145'], 'coral way': ['33145'], 'fontainebleau': ['33172', '33126'], 'olympia heights': ['33165', '33175'], 'goulds': ['33170'], 'princeton': ['33032'],
    'naranja': ['33032'], 'leisure city': ['33033'], 'richmond heights': ['33176'], 'perrine': ['33157'], 'brownsville': ['33142'], 'gladeview': ['33147'], 'the hammocks': ['33196'], 'kendale lakes': ['33183'], 'country club': ['33015'],
    'upper east side': ['33137', '33138'], 'design district': ['33137'], 'downtown miami': ['33131', '33132'], 'little gables': ['33134'], 'west kendall': ['33193', '33196'] };
  /* preset phrases -> idea label prefix (app.js IDEAS) */
  const PRESETS = [[/\bhott?est leads?\b|\bhot leads?\b/, 'Hottest leads'], [/\bpre[- ]?foreclosures?\b/, 'Pre-foreclosure'], [/\b(likely )?vacant (and|\/|or) neglected\b|\bneglected\b|\blikely vacant\b/, 'Likely vacant'],
    [/\bmulti[- ]property (motivated )?owners?\b/, 'Multi-property'], [/\bowners? with (5|five)\+? (or more )?properties\b/, 'Owners with 5+'], [/\binfill lots?\b/, 'Vacant infill'], [/\bhouses? on (multi[- ]?family|mf) (land|zoning|lots?)\b/, 'Houses on multifamily'],
    [/\btired landlords?\b/, 'Tired landlords'], [/\blots? owned from far away\b/, 'Lots owned from far'], [/\bstrong teardowns?\b/, 'Strong teardowns'], [/\blots? that (could|can) be split\b|\bsplit(table|able)? lots?\b/, 'Lots that could be split'],
    [/\bcommercial distress\b/, 'Commercial distress'], [/\bclosed gas stations?\b/, 'Closed gas'], [/\bgas stations?\b/, 'Gas stations'], [/\bwarehouses?\b/, 'Warehouses'], [/\bretail( stores?| centers?)?\b|\bshopping centers?\b/, 'Retail'],
    [/\boffice buildings?\b|\boffices\b/, 'Office buildings'], [/\brestaurants?\b|\bfast food\b/, 'Restaurants'], [/\bhotels?\b|\bmotels?\b/, 'Hotels'], [/\bauto (sales|repair|shops?|dealers?)\b|\bcar (lots?|dealers?)\b/, 'Auto sales'],
    [/\bvacant commercial (land|lots?)\b/, 'Vacant commercial land'], [/\bassemblages? with (combined[- ]site )?upside\b/, 'Assemblages with'], [/\bassemblages?\b/, 'Assemblages'], [/\bunder (the )?zone min(imum)?\b/, 'Houses on lots under zone'],
    [/\bbuildable lots?,? green( only)?\b/, 'Buildable lots, green'], [/\bbuildable teardowns?\b/, 'Buildable teardowns'], [/\bbuildable lots?\b/, 'Buildable lots'], [/\brogo\b/, 'ROGO'], [/\bduplex[- ]zoned\b/, 'Duplex-zoned'],
    [/\bfamily transfers?,? (and |with )?(owner )?out[- ]of[- ]state\b/, 'Family transfers, owner out'], [/\b(family|relative) transfers?\b/, 'Family transfers (last'], [/\blife estates?\b/, 'Life estate'], [/\bbig lots?\b/, 'Big lots']];
  const STOP = new Set('a an the in on at of for with and or to from by that are is be which who whose show me find get give list all any some properties property parcels parcel homes? ones owned owner owners own please i want need looking look search me my near around inside within county city area zone also plus only just like have has having where there them those these than then it its into as'.split(' ').concat(['homes', 'deals', 'leads', 'stuff', 'listings']));
  const num = s => +String(s).replace(/,/g, '');
  const money = (n, u) => { n = num(n); u = (u || '').toLowerCase(); return Math.round(u === 'k' || u === 'thousand' ? n * 1e3 : u === 'm' || u === 'mm' || u === 'million' || u === 'mil' ? n * 1e6 : n); };
  const fmtMoney = v => v >= 1e6 ? '$' + (Math.round(v / 1e5) / 10) + 'M' : v >= 1e3 ? '$' + Math.round(v / 1e3) + 'K' : '$' + v;
  const fmtN = v => String(Math.round(v)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const title = s => s.replace(/\b[a-z]/g, c => c.toUpperCase());

  function parse(text, ctx) {
    ctx = ctx || {}; const county = ctx.county || 'miami-dade', has = ctx.has || (() => true), ideas = ctx.ideas || [];
    const out = { county, jump: null, parts: [], hints: [], unknown: [], raw: String(text || '') };
    let w = ' ' + String(text || '').toLowerCase().replace(/[\u2013\u2014]/g, '-').replace(/[’‘]/g, "'").replace(/(\d),(\d{3})\b/g, '$1$2').replace(/\s+/g, ' ').trim() + ' ';
    const add = (key, label, set, extra) => { out.parts.push(Object.assign({ key, label, set }, extra || {})); };
    const eat = re => { let m = null; w = w.replace(re, (...a) => { if (!m) m = a; return ' '.repeat(a[0].length); }); return m; };   // first match only, replaced by spaces
    const eatAll = re => { const ms = []; w = w.replace(re, (...a) => { ms.push(a); return ' '.repeat(a[0].length); }); return ms; };
    const raw = out.raw.trim();

    /* 1. folio / address -> jump */
    const dig = raw.replace(/[^0-9]/g, '');
    if (/^[\d\s-]+$/.test(raw) && dig.length >= 10) { out.jump = { folio: dig }; add('folio', 'Folio ' + raw, { q: dig }); return out; }
    if (county === 'broward' && /^\d{6}\s*[a-z]{2}\s*\d{4}$/i.test(raw)) { out.jump = { folio: raw.replace(/\s/g, '').toUpperCase() }; add('folio', 'Folio ' + raw.toUpperCase(), { q: raw.replace(/\s/g, '').toUpperCase() }); return out; }
    const ST = { street: 'ST', st: 'ST', avenue: 'AVE', ave: 'AVE', av: 'AVE', road: 'RD', rd: 'RD', terrace: 'TER', ter: 'TER', terr: 'TER', drive: 'DR', dr: 'DR', court: 'CT', ct: 'CT', place: 'PL', pl: 'PL', lane: 'LN', ln: 'LN', boulevard: 'BLVD', blvd: 'BLVD', way: 'WAY', circle: 'CIR', cir: 'CIR', highway: 'HWY', hwy: 'HWY', parkway: 'PKWY', pkwy: 'PKWY', trail: 'TRL', path: 'PATH', causeway: 'CSWY', cswy: 'CSWY' };
    const DIRS = { northwest: 'NW', northeast: 'NE', southwest: 'SW', southeast: 'SE', north: 'N', south: 'S', east: 'E', west: 'W', nw: 'NW', ne: 'NE', sw: 'SW', se: 'SE', n: 'N', s: 'S', e: 'E', w: 'W' };
    const am = /^\s*(\d{1,6})\s+((?:[a-z0-9.'-]+\s+){0,5}?)(street|st|avenue|ave|av|road|rd|terrace|terr?|drive|dr|court|ct|place|pl|lane|ln|boulevard|blvd|way|circle|cir|highway|hwy|parkway|pkwy|trail|path|causeway|cswy)\b\.?(.*)$/i.exec(raw.toLowerCase().replace(/,/g, ' '));
    if (am && !/\b(under|over|owned|years?|with|teardowns?|lots?)\b/.test(am[2])) {
      const mid = am[2].trim().split(/\s+/).filter(Boolean).map(t => DIRS[t] || t.replace(/^(\d+)(st|nd|rd|th)$/, '$1').toUpperCase()), q = [am[1], ...mid, ST[am[3]]].join(' ');
      const rest = am[4].trim().split(/\s+/).filter(Boolean).map(t => DIRS[t.replace(/\./g, '')] || '').filter(Boolean);   // trailing direction (Broward "123 Main St N")? keep the search tight
      out.jump = { address: q }; add('address', 'Address ' + q, { q }); void rest; return out;
    }

    /* 2. county */
    const cm = eat(/\b(?:in |the )?(broward|monroe|miami[- ]dade|dade|the (?:florida )?keys|florida keys)(?: county)?\b/);
    if (cm) { const c = /broward/.test(cm[1]) ? 'broward' : /monroe|keys/.test(cm[1]) ? 'monroe' : 'miami-dade'; out.county = c; if (c !== county) add('county', COUNTIES[c] + ' County', {}, { county: c }); }
    const cc = out.county, hasC = l => cc === county ? has(l) : ({ 'miami-dade': ['distress', 'zoning', 'vacancy', 'commercial', 'asm', 'owners', 'teardown'], monroe: ['mscreen', 'rogo', 'mtax', 'teardown', 'owners'], broward: ['mscreen', 'broward', 'mtax', 'mtdeed', 'teardown', 'owners'] }[cc] || []).includes(l);

    /* 3. presets (whole phrases) */
    for (const [re, lab] of PRESETS) { const m = eat(re); if (!m) continue; const label = cc === county ? ideas.find(l => l.replace(/^[^\w]+/, '').startsWith(lab)) : lab;
      if (label || cc !== county) add('preset', (label || lab).replace(/^[^\w]+/, ''), {}, { preset: lab }); else out.hints.push(`“${m[0].trim()}” is a preset that isn't available in ${COUNTIES[cc]}.`); }

    /* homestead phrases before cities (Homestead is also a city) */
    if (eat(/\bno homestead(?: exemption)?\b|\bnon[- ]?homestead(?:ed)?\b|\bwithout (?:a )?homestead(?: exemption)?\b|\bnot homesteaded\b|\bnon[- ]owner[- ]occupied\b|\bnot owner[- ]occupied\b/)) add('flag', 'No homestead', { flags: { homestead: 'no' } });
    else if (eat(/\bowner[- ]occupied\b|\bhomesteaded\b|\bhomestead exemption\b|\bowners? lives? there\b/)) add('flag', 'Owner lives there (homestead)', { flags: { homestead: 'yes' } });
    /* 4. owner name: "owned by john smith", "owner john smith", "properties of john smith" */
    const KIND = /^(individuals?|people|persons?|a person|private (owners?|individuals?)|llcs?|an llc|a company|companies|corporations?|corporate|businesses|investors?|trusts?|a trust|families|family)$/;
    const om = /\b(?:owned by|belonging to|owner(?: named| is| name)?|properties of|property of|owners? called)\s+([a-z][a-z.'&-]*(?:\s+[a-z][a-z.'&-]*){0,4}?)(?=\s+(?:in|with|over|under|above|below|and|that|who|built|owned|for|on|near|zoned|from)\b|\s*$|\s*,)/.exec(w);
    if (om && !KIND.test(om[1].trim()) && !/\b(over|under|\d)\b/.test(om[1])) {
      const toks = om[1].trim().toUpperCase().replace(/[.,]/g, '').split(/\s+/);
      const q = (ctx.nameOrder || (cc === 'miami-dade' ? 'first-last' : 'last-first')) === 'last-first' && toks.length >= 2 ? [toks[toks.length - 1], ...toks.slice(0, -1)].join(' ') : toks.join(' ');
      w = w.replace(om[0], ' '.repeat(om[0].length)); add('owner', 'Owner name contains “' + q + '”', { q, qScope: 'ao' });
    }

    /* 5. neighborhoods + cities */
    if (cc === 'miami-dade') for (const h of Object.keys(HOODS).sort((a, b) => b.length - a.length)) { if (eat(new RegExp('\\b' + h + '\\b'))) { add('zip', title(h) + ' (ZIP ' + HOODS[h].join(', ') + ')', { zips: HOODS[h].join(', ') }); break; } }
    const cityList = (cc === county && ctx.cities && ctx.cities.length ? ctx.cities : CITY_OF[cc] || []).filter(Boolean);
    for (const c of [...cityList].sort((a, b) => b.length - a.length)) { const re = new RegExp('\\b' + c.toLowerCase().replace(/[-]/g, '[- ]?').replace(/ /g, '[ -]') + '\\b'); if (eat(re)) { add('city', c, { city: c }); break; } }
    if (!out.parts.some(p => p.key === 'city')) for (const [k, list] of Object.entries(CITY_OF)) { if (k === cc) continue; for (const c of [...list].sort((a, b) => b.length - a.length)) { if (new RegExp('\\b' + c.toLowerCase() + '\\b').test(w) && !(k === 'miami-dade' && c === 'Miami' && /miami[- ]dade/.test(raw.toLowerCase()))) { out.hints.push(`${c} is in ${COUNTIES[k]} County. Ask again with “in ${COUNTIES[k]}” or switch county.`); eat(new RegExp('\\b' + c.toLowerCase() + '\\b')); break; } } }

    /* 6. taxes (before years owned: "tax delinquent 2+ years") */
    const tx = eat(/\b(?:tax(?:es)?[- ]delinquen\w*|delinquent(?: on)?(?: property)? tax(?:es)?|back taxes|unpaid taxes|behind on (?:their )?taxes|owes? taxes)(?:\s+(?:for\s+)?(?:at least\s+|over\s+|more than\s+)?(\d)\s*(\+|plus|or more)?\s*(?:years?|yrs?))?(?:\s+(?:unpaid|delinquent|behind))?/);
    if (tx) { const y = tx[1] ? +tx[1] : 0;
      if (hasC('mtax')) { const k = y >= 3 ? 'y3' : y >= 2 ? 'y2' : 'any'; add('tax', k === 'any' ? 'Tax delinquent' : k === 'y2' ? '2+ years unpaid' : '3+ years unpaid', { mr: { tax: [k] } }); }
      else if (hasC('distress')) { add('dsig', 'Delinquent taxes', { dsig: ['TX'] }); if (y >= 2) out.hints.push(`${COUNTIES[cc]} has no years-unpaid count; showing every delinquent-tax property.`); }
      else out.hints.push('Tax delinquency is not in this county\'s data.'); }
    if (eat(/\btax (?:lien )?certificates?\b|\btax certs?\b/)) { if (hasC('mtax')) add('tax', 'Investor holds a certificate', { mr: { tax: ['cert'] } }); else if (hasC('distress')) add('dsig', 'Tax certificates', { dsig: ['TC'] }); }
    if (eat(/\btax[- ]deeds?(?: (?:sales?|auctions?|applications?|applied))?\b/)) { if (hasC('mtdeed')) add('tax', 'Tax deed auction upcoming', { mr: { tax: ['deed'] } }); else if (hasC('distress')) add('dsig', 'Tax deed', { dsig: ['TD'] }); else if (hasC('mscreen')) add('msig', 'Tax-deed notice', { mr: { sig: ['taxdeed'] } }); }

    /* 7. years owned */
    let ym = eat(/\b(?:owned|held|ownership|owner for|owners? (?:of|for))\s+(?:for\s+)?(over|more than|at least|longer than|under|less than|fewer than|below)?\s*(\d{1,2})\s*(\+|plus|or more)?\s*(?:years?|yrs?)\b/) || eat(/\b(\d{1,2})\s*(\+|plus|or more)\s*(?:years?|yrs?)(?:\s+(?:owned|of ownership|held))?\b/) || eat(/\b(over|more than|at least)\s+(\d{1,2})\s*(?:years?|yrs?)\s+(?:owned|of ownership|held)\b/);
    if (ym) { const a = ym.slice(1, 4).filter(x => x != null); const cmp = a.find(x => /[a-z]/.test(x || '') && !/plus|more$/.test(x) ) || '', n = +a.find(x => /^\d+$/.test(x || '')), up = /under|less|fewer|below/.test(cmp);
      if (up) add('held', `Owned under ${n} years`, { hdMax: n }); else add('held', `Owned ${n}+ years`, { hdMin: n }); }
    else if (eat(/\blong[- ]?(?:time|term) owners?\b/)) add('held', 'Owned 20+ years', { hdMin: 20 });

    /* 8. year built, units, beds */
    const yb = eat(/\b(?:built\s+)?(before|prior to|pre|older than|after|since|newer than)[- ]?(\d{4})\b/) || eat(/\bbuilt in (?:the )?(\d{4})s\b/);
    if (yb) { if (yb[2] && /before|prior|pre|older/.test(yb[1])) add('built', 'Built before ' + yb[2], { ybMax: +yb[2] - 1 }); else if (yb[2]) add('built', 'Built after ' + yb[2], { ybMin: +yb[2] + 1 }); else add('built', `Built in the ${yb[1]}s`, { ybMin: +yb[1], ybMax: +yb[1] + 9 }); }
    const un = eat(/\b(\d{1,3})\s*(?:-|to)\s*(\d{1,3})\s*units?\b/) || eat(/\b(?:at least |over |more than )?(\d{1,3})\s*(\+|plus|or more)?\s*units?\b/);
    if (un) { if (un[2] && /^\d+$/.test(un[2])) add('units', `${un[1]}–${un[2]} units`, { unMin: +un[1], unMax: +un[2] }); else add('units', `${un[1]}+ units`, { unMin: +un[1] }); }
    const bd = eat(/\b(\d)\s*(\+|plus|or more)?\s*(?:bed(?:room)?s?|br|bd)\b/); if (bd) add('beds', `${bd[1]}+ bedrooms`, { bdMin: +bd[1] });

    /* 9. sizes (lot vs building) */
    const UNIT = '(sq\\.? ?ft\\.?|sqft|sf|square f(?:ee|oo)t|acres?|ac)\\b';
    const sizeVal = (n, k, u) => { let v = num(n) * (k ? 1000 : 1); if (/^ac/.test(u)) v = Math.round(v * 43560); return v; };
    const blank = m => { const st = m.index + (m[1] || '').length, en = m.index + m[0].length - (m[m.length - 1] || '').length; w = w.slice(0, st) + ' '.repeat(en - st) + w.slice(en); };   // keep the context words around a size for other rules
    const isBldg = s => /\b(building|house|home|living|heated|structure|livable)\b/.test(s);
    let sm;
    while ((sm = new RegExp('((?:\\b[a-z]+\\s+){0,2})\\b(between|from)\\s+(\\d+(?:\\.\\d+)?)\\s*(k)?\\s*(?:' + UNIT + ')?\\s*(?:and|to|-)\\s*(\\d+(?:\\.\\d+)?)\\s*(k)?\\s*' + UNIT + '(\\s+[a-z]+)?').exec(w))) {
      const u = sm[8], a = sizeVal(sm[3], sm[4], sm[5] || u), b = sizeVal(sm[6], sm[7], u), bl = isBldg((sm[1] || '') + (sm[9] || ''));
      add(bl ? 'bsize' : 'lot', `${bl ? 'Building' : 'Lot'} ${fmtN(a)}–${fmtN(b)} sq ft`, bl ? { sfMin: a, sfMax: b } : { lotMin: a, lotMax: b }); blank(sm); }
    while ((sm = new RegExp('((?:\\b[a-z]+\\s+){0,2})\\b(over|above|more than|at least|bigger than|larger than|min(?:imum)?|under|below|less than|smaller than|max(?:imum)?|up to)?\\s*(\\d+(?:\\.\\d+)?)\\s*(k)?\\s*(\\+|plus)?\\s*' + UNIT + '\\s*(\\+|plus|or more|or bigger|or larger|or less|or smaller)?(\\s+[a-z]+)?').exec(w))) {
      const v = sizeVal(sm[3], sm[4], sm[6]), up = /under|below|less|smaller|max|up to/.test((sm[2] || '') + (sm[7] || '')), bl = isBldg((sm[1] || '') + (sm[8] || '')), k = bl ? (up ? 'sfMax' : 'sfMin') : (up ? 'lotMax' : 'lotMin');
      add(bl ? 'bsize' : 'lot', `${bl ? 'Building' : 'Lot'} ${up ? 'under' : 'over'} ${/^ac/.test(sm[6]) ? sm[3] + ' acre' + (+sm[3] === 1 ? '' : 's') : fmtN(v) + ' sq ft'}`, { [k]: v }); blank(sm); }
    const ha = eat(/\b(under|less than|below|smaller than|over|more than|at least|above)?\s*(?:a )?half[- ](?:an[- ])?acre\+?(?: or (?:more|bigger))?\b/); if (ha) { if (/under|less|below|smaller/.test(ha[1] || '')) add('lot', 'Lot under 1/2 acre', { lotMax: 21780 }); else add('lot', 'Lot over 1/2 acre', { lotMin: 21780 }); }
    if (!ha && eat(/\b(?:an? )?acre\+?(?: lots?| or more| plus)\b/)) add('lot', 'Lot over 1 acre', { lotMin: 43560 });

    /* 10. money (market value) */
    const M = '\\$?\\s?(\\d+(?:\\.\\d+)?)\\s*(k|m|mm|mil|million|thousand)?';
    const isMoney = (s, u) => !!u || /\$/.test(s);
    let mm = new RegExp('\\b(?:between|from)?\\s*' + M + '\\s*(?:and|to|-)\\s*' + M + '(?=\\s|$)').exec(w);
    if (mm && isMoney(mm[0], mm[2] || mm[4]) && (mm[2] || mm[4] || /\$/.test(mm[0]))) { const u2 = mm[4] || mm[2], a = money(mm[1], mm[2] || u2), b = money(mm[3], u2); add('value', `Value ${fmtMoney(a)}–${fmtMoney(b)}`, { mvMin: a, mvMax: b }); w = w.replace(mm[0], ' '.repeat(mm[0].length)); }
    for (;;) { const r = new RegExp('\\b(under|below|less than|cheaper than|max(?:imum)?|up to|no more than|over|above|more than|at least|min(?:imum)?|starting at)\\s+' + M + '(?:\\s*(?:value|market value|in value|worth))?(?=\\s|$)').exec(w);
      if (!r || !isMoney(r[0], r[3])) break; const v = money(r[2], r[3]), up = /under|below|less|cheaper|max|up to|no more/.test(r[1]); add('value', `Value ${up ? 'under' : 'over'} ${fmtMoney(v)}`, up ? { mvMax: v } : { mvMin: v }); w = w.replace(r[0], ' '.repeat(r[0].length)); }
    const mp = new RegExp('(?:^|\\s)' + M + '\\s*(\\+|plus|or more|and up)(?=\\s|$)').exec(w); if (mp && (mp[2] || /\$/.test(mp[0]))) { const v = money(mp[1], mp[2]); add('value', `Value over ${fmtMoney(v)}`, { mvMin: v }); w = w.replace(mp[0], ' '.repeat(mp[0].length)); }

    /* 11. distress (Miami-Dade distress layer; Monroe / Broward screening signals) */
    const D = [[/\blis pendens\b|\blis-pendens\b|\bpre[- ]?foreclosures?\b|\bforeclosure filings?\b/, 'LP', 'Lis pendens', 'fc_open'], [/\bforeclosures?(?: sales?| auctions?)?\b|\bauctions?\b|\bbank[- ]owned\b/, 'FC', 'Foreclosure sale', 'fc_open'],
      [/\bunsafe(?: structures?)?\b/, 'US', 'Unsafe structure'], [/\bbuilding violations?\b/, 'BV', 'Building violation'], [/\bcode (?:cases?|violations?|enforcement)\b|\bviolations?\b/, 'CC', 'Code case', 'code'], [/\bliens?\b/, 'LN', 'Lien'],
      [/\brecert(?:ification)?s?(?: (?:overdue|late|past due|due))?\b|\b40[- ]year (?:recert|inspection)s?\b/, 'RC', 'Recert overdue'], [/\bprobate\b|\bestate (?:cases?|filings?)\b/, 'PR', 'Probate / estate', 'pr_open'], [/\bdeceased(?: owners?)?\b|\bowners? (?:died|deceased|passed away)\b|\bdeath\b|\bdead owners?\b/, 'DC', 'Owner deceased']];
    for (const [re, code, label, ms] of D) { const m = eat(re); if (!m) continue;
      if (hasC('distress')) add('dsig', label, { dsig: [code] });
      else if (ms && hasC('mscreen') && !(cc === 'broward' && ['code', 'pr_open'].includes(ms))) { const lab = ms === 'fc_open' ? (cc === 'broward' ? 'Foreclosure auction scheduled' : 'Foreclosure case open') : ms === 'code' ? 'Code case' : 'Probate case open';
        if (code === 'LP') out.hints.push(`Lis pendens isn't in the ${COUNTIES[cc]} data; the closest filter is “${lab}”.`); else add('msig', lab, { mr: { sig: [ms] } }); }
      else out.hints.push(`“${m[0].trim()}” is not in the ${COUNTIES[cc]} data.`); }
    if (eat(/\bdistress(?:ed)?(?: score)?(?: (?:over|above|at least) (\d+))?\b/)) { if (hasC('distress')) add('ds', 'Distress score 35+', { dsMin: 35, sort: 'ds_d' }); }

    /* 12. teardowns */
    if (eat(/\btear[- ]?downs?\b|\bknock[- ]?downs?\b/)) { if (hasC('teardown')) add('tier', 'Teardown', { tier: 'basic' }); }

    /* 13. zoning */
    const zm = eat(/\b(?:zoned(?: for)?|zoning)\s+(single[- ]family|sf|duplex|townhouses?|multi[- ]?family|mf|commercial|industrial|mixed[- ]use)\b|\b(single[- ]family|duplex|multi[- ]?family|commercial|industrial|mixed[- ]use) (?:zoning|zoned|land)\b/);
    if (zm) { const v = (zm[1] || zm[2]).replace(/[- ]/g, ''), z = /^(singlefamily|sf)$/.test(v) ? 'sf' : v === 'duplex' ? 'duplex' : /townhouse/.test(v) ? 'th' : /^(multifamily|mf)$/.test(v) ? 'mf' : v === 'commercial' ? 'com' : v === 'industrial' ? 'ind' : 'mixed';
      const lab = { sf: 'Single family', duplex: 'Duplex', th: 'Townhouse', mf: 'Multifamily', com: 'Commercial', ind: 'Industrial', mixed: 'Mixed use' }[z];
      if (hasC('zoning')) add('zone', 'Zoned ' + lab.toLowerCase(), { zones: [z] }); else if (hasC('mscreen') && z !== 'th') add('zone', 'Zoned ' + lab.toLowerCase(), { mr: { zt: [z] } }); else out.hints.push('Zoning type is not in this county\'s data.'); }

    /* 14. property types */
    const T = [[/\bvacant (?:lots?|land|parcels?)\b|\bempty lots?\b|\bvacant\b|\bland\b/, 'vacant', 'Vacant land'], [/\bsingle[- ]family(?: homes?| houses?)?\b|\bhouses?\b|\bhomes?\b|\bsfh\b|\bsfr\b/, 'sf', 'Single family'],
      [/\btown ?(?:houses?|homes?)\b/, 'th', 'Townhouse'], [/\bcondos?(?:miniums?)?(?: units?)?\b/, 'condo', 'Condo units'], [/\b(?:duplex(?:es)?|triplex(?:es)?|fourplex(?:es)?|quadplex(?:es)?|small multi[- ]?family|2[- ]9 units)\b|\bmulti[- ]?family\b|\bmultiplex(?:es)?\b/, 'mf29', '2–9 units'],
      [/\bapartments?(?: buildings?| complex(?:es)?)?\b/, 'apt10', '10+ unit apartments'], [/\bmixed[- ]use\b/, 'mixed', 'Mixed use'], [/\bcommercial\b|\bstorefronts?\b/, 'com', 'Commercial'], [/\bindustrial\b|\bwarehouses?\b|\bfactor(?:y|ies)\b/, 'ind', 'Industrial'],
      [/\bmobile homes?\b|\btrailers?\b/, 'mobile', 'Mobile home'], [/\bchurch(?:es)?\b|\bschools?\b|\bnon[- ]?profits?\b/, 'inst', 'Church, school, nonprofit']];
    for (const [re, k, label] of T) if (eat(re)) add('type', label, { types: [k] });
    if (!out.parts.some(p => p.key === 'type' || p.key === 'preset') && eat(/\blots?\b|\bparcels? of land\b/)) add('type', 'Vacant land', { types: ['vacant'] });
    eatAll(/\blots?\b/);

    /* 15. owner kind + owner situation */
    if (eat(/\b(?:by |owned by )?(?:individuals?|people|persons?|a person|private (?:owners?|individuals?)|individual owners?|real people|non[- ]?corporate)\b/)) add('okind', 'Individuals', { owner: 'person' });
    else if (eat(/\b(?:by |owned by )?(?:an? )?(?:llcs?|compan(?:y|ies)|corporat(?:e|ions?)|business(?:es)?|investors?|entities|entity)(?: owned| owners?)?\b/)) add('okind', 'Companies & organizations', { owner: 'corp' });
    else if (eat(/\b(?:by |owned by |in )?(?:an? )?trusts?(?: owned| owners?)?\b/)) add('okind', 'Trusts', { owner: 'trust' });
    if (eat(/\bout[- ]of[- ](?:state|town)(?: owners?)?\b|\bnon[- ]?residents?\b/)) add('flag', 'Owner mails from out of state', { flags: { oos: 'yes' } });
    if (eat(/\babsentee(?: owners?)?\b|\blandlords?\b|\brentals?\b|\binvestment propert(?:y|ies)\b/)) add('flag', 'Absentee owner', { flags: { absz: 'yes' } });
    if (eat(/\bestates?\b|\bheirs?\b|\binherited\b/)) add('flag', 'Estate or heirs', { flags: { estate: 'yes' } });
    if (eat(/\bseniors?(?: exemption| owners?| citizens?)?\b|\belderly(?: owners?)?\b/)) add('flag', 'Senior exemption', { flags: { senior: 'yes' } });

    /* 16. sort words */
    if (eat(/\b(?:biggest|largest) lots? first\b/)) add('sort', 'Biggest lot first', { sort: 'lot_d' });
    else if (eat(/\bcheapest(?: first)?\b|\blowest value(?: first)?\b/)) add('sort', 'Lowest value first', { sort: 'mv_a' });
    else if (eat(/\boldest(?: buildings?)?(?: first)?\b/)) add('sort', 'Oldest building first', { sort: 'yb_a' });

    /* leftovers */
    out.unknown = w.replace(/[^a-z0-9$+%' -]/g, ' ').split(/\s+/).filter(t => t && !STOP.has(t) && !/^(-|\+|s|'s|homes?)$/.test(t) && !/^(owned|years?|yrs|held|over|under|built|zoned)$/.test(t));
    if (!out.parts.length && !out.hints.length) out.hints.push('I could not match that to a filter. Try a city, a property type, a price like “under 500k”, “owned 20+ years”, a distress word like “lis pendens”, an address or a folio.');
    return out;
  }
  /* merge one part's partial state into st (arrays union, flags / fx / mr merged) */
  function merge(st, set) {
    for (const [k, v] of Object.entries(set || {})) {
      if (Array.isArray(v)) st[k] = [...new Set([...(st[k] || []), ...v])];
      else if (k === 'flags' || k === 'fx') st[k] = Object.assign({}, st[k] || {}, v);
      else if (k === 'mr') { const m = Object.assign({}, st.mr || {}); for (const [a, b] of Object.entries(v)) m[a] = Array.isArray(b) ? [...new Set([...(m[a] || []), ...b])] : b; st.mr = m; }
      else st[k] = v;
    }
    return st;
  }
  /* sort that fits what was asked, when nothing set one */
  function sortFor(st) { if (st.sort && st.sort !== 'lot_d') return st.sort; if ((st.dsig || []).length || st.dsMin) return 'ds_d'; if (st.mr && (st.mr.tax || []).length) return 'tx_d'; if (st.tier && st.tier !== 'any') return 'lp_d'; if (st.hdMin) return 'held_d'; if (st.mvMax && !st.mvMin) return 'mv_a'; return st.sort || 'lot_d'; }
  const api = { parse, merge, sortFor, HOODS, CITY_OF, PRESETS };
  root.PFAsk = api; if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
