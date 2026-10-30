/* Email checks for skip-traced addresses (run by the Worker right after a skip trace, and on demand for stored ones).
   Free checks, always on: syntax, provider username rules (gmail / yahoo / aol / outlook), typo'd and disposable domains,
   MX lookup over DNS-over-HTTPS (cloudflare-dns.com: NXDOMAIN, null MX or no MX = the domain takes no mail), old-ISP heuristic,
   the shared bad list (KV key 'bad_emails', bounced addresses marked from any device), and BatchData's own rank / tested flags.
   Optional real mailbox check (OFF unless configured): EMAIL_VERIFY_PROVIDER = 'quickemailverification' | 'zerobounce'
   plus the API key in the secret EMAIL_VERIFY_API_KEY or KV key 'email_verify_key'; EMAIL_VERIFY_DAILY caps calls per New York day
   (default 90, inside QuickEmailVerification's 100/day free tier). Mailbox results are cached in KV ('ev:<sha256>') so an address
   is checked once. Verdicts: 'verified' | 'risky' | 'bad', with a short reason. Nothing here is logged. */

const DOH = 'https://cloudflare-dns.com/dns-query';
const EMAIL_RE = /^[^\s@<>(),;:"'\[\]\\]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,}$/;
// throwaway inboxes: never worth an email
const DISPOSABLE = new Set(['mailinator.com', 'guerrillamail.com', 'guerrillamail.net', 'sharklasers.com', 'grr.la', '10minutemail.com', 'yopmail.com', 'tempmail.com', 'temp-mail.org',
  'trashmail.com', 'getnada.com', 'dispostable.com', 'maildrop.cc', 'throwawaymail.com', 'fakeinbox.com', 'mailnesia.com', 'mintemail.com', 'spamgourmet.com', 'emailondeck.com', 'mohmal.com',
  'tempinbox.com', 'mailcatch.com', 'trashmail.de', 'discard.email', 'spam4.me', 'mytemp.email', 'tempr.email', 'example.com', 'example.org', 'example.net', 'test.com', 'none.com', 'noemail.com', 'nomail.com']);
// common misspellings of the big mailbox domains (the real domain does not exist or does not belong to the person)
const TYPO = new Set(['gmial.com', 'gmai.com', 'gamil.com', 'gnail.com', 'gmal.com', 'gmaill.com', 'gmail.co', 'gmail.cm', 'gmail.con', 'gmail.om', 'gmaik.com', 'gmali.com', 'gmsil.com', 'gmeil.com',
  'yaho.com', 'yahooo.com', 'yhoo.com', 'yahho.com', 'yahoo.co', 'yahoo.con', 'yaoo.com', 'yahool.com', 'hotmial.com', 'hotmal.com', 'hotmai.com', 'hotmil.com', 'hotmail.co', 'hotmail.con', 'hotmaill.com',
  'outlok.com', 'outloo.com', 'outlook.co', 'aol.co', 'aol.con', 'aoll.com', 'iclod.com', 'icloud.co', 'bellsouth.con', 'comcast.con']);
// old ISP / legacy webmail domains: the domain still takes mail but many of these mailboxes were closed years ago (most of the Oct 2026 bounces)
const LEGACY = new Set(['juno.com', 'netzero.net', 'netzero.com', 'earthlink.net', 'earthlink.com', 'mindspring.com', 'peoplepc.com', 'aol.com', 'aim.com', 'cs.com', 'wmconnect.com', 'netscape.net',
  'compuserve.com', 'verizon.net', 'gte.net', 'bellsouth.net', 'att.net', 'sbcglobal.net', 'prodigy.net', 'pacbell.net', 'swbell.net', 'ameritech.net', 'flash.net', 'nvbell.net', 'wans.net', 'snet.net',
  'msn.com', 'webtv.net', 'adelphia.net', 'insightbb.com', 'localnet.com', 'excite.com', 'lycos.com', 'hughes.net', 'usa.net', 'bigfoot.com', 'altavista.com',
  'worldnet.att.net', 'charter.net', 'rr.com', 'cfl.rr.com', 'tampabay.rr.com']);
// Yahoo-hosted mailboxes (Yahoo, AOL, AT&T / SBC / BellSouth): their servers accept every address during a mailbox check, so a 'valid'
// answer proves nothing (bounced Oct 2026 addresses came back valid). Never shown as Verified: best case is Risky.
const YAHOO_FAMILY = /^(yahoo\.[a-z.]+|ymail\.com|rocketmail\.com|aol\.com|aim\.com|att\.net|sbcglobal\.net|bellsouth\.net|pacbell\.net|swbell\.net|prodigy\.net|ameritech\.net|flash\.net|nvbell\.net|wans\.net|snet\.net)$/;
export const isYahooFamily = dom => YAHOO_FAMILY.test(String(dom || '').toLowerCase());
const YAHOO_WHY = 'Yahoo / AOL / AT&T mailbox: these servers accept every address, so it cannot be confirmed';
const ROLE = /^(info|admin|administrator|office|sales|contact|support|help|noreply|no-reply|donotreply|webmaster|postmaster|hostmaster|abuse|billing|accounts|hello|mail|team|marketing|service|reception|frontdesk)$/;
const PROVIDER_RULES = [
  // [domains, test(local) -> '' ok | reason]
  [/^(gmail\.com|googlemail\.com)$/, l => { const u = l.split('+')[0].replace(/\./g, ''); if (/[^a-z0-9]/.test(u)) return 'Gmail usernames only have letters, numbers and dots'; if (u.length < 6 || u.length > 30) return 'Gmail usernames are 6 to 30 characters'; return ''; }],
  [/^yahoo\.[a-z.]+$|^ymail\.com$|^rocketmail\.com$/, l => { const u = l.split('-')[0]; if (!/^[a-z]/.test(u)) return 'Yahoo usernames start with a letter'; if (/[^a-z0-9_.]/.test(u)) return 'Yahoo usernames only have letters, numbers, _ and .'; if (u.length < 4 || u.length > 32) return 'Yahoo usernames are 4 to 32 characters'; return ''; }],
  [/^(aol\.com|aim\.com)$/, l => { if (!/^[a-z]/.test(l)) return 'AOL usernames start with a letter'; if (/[^a-z0-9_.]/.test(l)) return 'AOL usernames only have letters, numbers, _ and .'; if (l.length < 3 || l.length > 32) return 'AOL usernames are 3 to 32 characters'; return ''; }],
  [/^(hotmail\.[a-z.]+|outlook\.[a-z.]+|live\.[a-z.]+|msn\.com)$/, l => { const u = l.split('+')[0]; if (!/^[a-z]/.test(u)) return 'Outlook / Hotmail usernames start with a letter'; if (/[^a-z0-9_.-]/.test(u)) return 'Outlook / Hotmail usernames only have letters, numbers, . _ and -'; if (u.length > 64) return 'username too long'; return ''; }]
];

export const normEmailV = v => String(v == null ? '' : v).trim().toLowerCase();
// free, offline checks; returns {v, why, src} for a definite verdict or null
export function staticCheck(email) {
  const e = normEmailV(email);
  if (!EMAIL_RE.test(e) || e.length > 254) return { v: 'bad', why: 'not a valid email address', src: 'syntax' };
  const at = e.lastIndexOf('@'), local = e.slice(0, at), dom = e.slice(at + 1);
  if (local.length > 64 || /^\.|\.$|\.\./.test(local)) return { v: 'bad', why: 'not a valid email address', src: 'syntax' };
  if (TYPO.has(dom)) return { v: 'bad', why: 'misspelled domain (' + dom + ')', src: 'syntax' };
  if (DISPOSABLE.has(dom)) return { v: 'bad', why: 'throwaway / placeholder domain', src: 'heuristic' };
  for (const [re, fn] of PROVIDER_RULES) if (re.test(dom)) { const why = fn(local); if (why) return { v: 'bad', why, src: 'syntax' }; break; }
  return null;
}
export const domainOf = e => normEmailV(e).split('@')[1] || '';
export const isLegacy = dom => LEGACY.has(dom) || [...LEGACY].some(d => dom.endsWith('.' + d));

/* ---------- MX over DNS-over-HTTPS ---------- */
const mxCache = new Map();   // domain -> {st: 'ok'|'nxdomain'|'nomx'|'nullmx'|'unknown', at}
async function dohJson(fetchImpl, name, type) {
  const ac = new AbortController(), t = setTimeout(() => ac.abort(), 3500);
  try { const r = await fetchImpl(DOH + '?name=' + encodeURIComponent(name) + '&type=' + type, { headers: { Accept: 'application/dns-json' }, signal: ac.signal }); if (!r.ok) return null; return await r.json(); }
  finally { clearTimeout(t); }
}
const mxFlight = new Map();   // one lookup per domain at a time
export function mxStatus(dom, fetchImpl) {
  const c = mxCache.get(dom); if (c && Date.now() - c.at < (c.st === 'unknown' ? 60e3 : 6 * 3600e3)) return Promise.resolve(c.st);
  if (mxFlight.has(dom)) return mxFlight.get(dom);
  const p = (async () => { let st = await mxLookup(dom, fetchImpl); if (st === 'unknown') st = await mxLookup(dom, fetchImpl); return st; })()
    .then(st => { if (mxCache.size > 2000) mxCache.clear(); mxCache.set(dom, { st, at: Date.now() }); return st; }).finally(() => mxFlight.delete(dom));
  mxFlight.set(dom, p); return p;
}
async function mxLookup(dom, fetchImpl) {
  let st = 'unknown';
  try {
    const j = await dohJson(fetchImpl, dom, 'MX');
    if (j && j.Status === 3) st = 'nxdomain';
    else if (j && j.Status === 0) {
      const mx = (Array.isArray(j.Answer) ? j.Answer : []).filter(a => a && a.type === 15).map(a => String(a.data || '').trim());
      if (mx.length && mx.every(d => /^\d+\s+\.?$/.test(d))) st = 'nullmx';
      else if (mx.length) st = 'ok';
      else st = 'nomx';   // no MX: in practice such a domain takes no mail (e.g. blackplanet.com refuses connections)
    }
  } catch (e) { st = 'unknown'; }
  return st;
}
const MX_WHY = { nxdomain: 'domain does not exist', nullmx: 'domain does not accept email', nomx: 'domain has no mail server (dead domain)' };

/* ---------- shared bad list (KV) ---------- */
export async function badList(env) {
  try { if (env.SK_KV) { const v = await env.SK_KV.get('bad_emails'); if (v) { const o = JSON.parse(v); if (o && typeof o === 'object') return o; } } } catch (e) { /* no list */ }
  return {};
}
export async function saveBadList(env, o) { if (!env.SK_KV) throw new Error('no_kv'); await env.SK_KV.put('bad_emails', JSON.stringify(o)); }

/* ---------- optional real mailbox check ---------- */
const sha = async s => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))].map(b => b.toString(16).padStart(2, '0')).join('');
export async function mailboxKey(env) {
  try { if (env.SK_KV) { const v = await env.SK_KV.get('email_verify_key'); if (v && v.trim()) return v.trim(); } } catch (e) { /* fall back */ }
  return String(env.EMAIL_VERIFY_API_KEY || '').trim();
}
export const mailboxProvider = env => { const p = String(env.EMAIL_VERIFY_PROVIDER || '').trim().toLowerCase(); return p === 'quickemailverification' || p === 'qev' ? 'qev' : p === 'zerobounce' ? 'zerobounce' : ''; };
// -> {v, why} | null (unknown / failed / not configured). Never throws, never returns the key.
async function providerCall(prov, key, email, fetchImpl) {
  const ac = new AbortController(), t = setTimeout(() => ac.abort(), 8000);
  try {
    if (prov === 'qev') {
      const r = await fetchImpl('https://api.quickemailverification.com/v1/verify?email=' + encodeURIComponent(email) + '&apikey=' + encodeURIComponent(key), { headers: { Accept: 'application/json' }, signal: ac.signal });
      if (!r.ok) return null; const j = await r.json(); const res = String(j && j.result || '').toLowerCase(), reason = String(j && j.reason || '').replace(/_/g, ' ');
      if (String(j && j.disposable) === 'true') return { v: 'bad', why: 'throwaway inbox (mailbox check)' };
      if (res === 'invalid') return { v: 'bad', why: 'mailbox check: ' + (reason || 'rejected'), rej: true };
      if (res === 'valid') return String(j.accept_all) === 'true' ? { v: 'risky', why: 'mailbox check: domain accepts every address (cannot confirm)' } : { v: 'verified', why: 'mailbox check: mailbox exists' };
      return null;
    }
    if (prov === 'zerobounce') {
      const r = await fetchImpl('https://api.zerobounce.net/v2/validate?api_key=' + encodeURIComponent(key) + '&email=' + encodeURIComponent(email) + '&ip_address=', { headers: { Accept: 'application/json' }, signal: ac.signal });
      if (!r.ok) return null; const j = await r.json(); const st = String(j && j.status || '').toLowerCase(), sub = String(j && j.sub_status || '').replace(/_/g, ' ');
      if (st === 'valid') return { v: 'verified', why: 'mailbox check: mailbox exists' };
      if (st === 'invalid' || st === 'spamtrap' || st === 'abuse' || st === 'do_not_mail') return { v: 'bad', why: 'mailbox check: ' + (sub || st.replace(/_/g, ' ')), ...(st === 'invalid' ? { rej: true } : {}) };
      if (st === 'catch-all') return { v: 'risky', why: 'mailbox check: domain accepts every address (cannot confirm)' };
      return null;
    }
  } catch (e) { return null; } finally { clearTimeout(t); }
  return null;
}
/* opts: {env, fetchImpl (provider), dnsFetch, reserve(n)->bool (daily quota), bad (shared list object)} ; meta: {rank, tested, owner} */
export async function checkOne(email, meta, opts) {
  const r = await checkOneRaw(email, meta, opts);
  if (r && r.v === 'verified' && isYahooFamily(domainOf(r.e))) return { ...r, v: 'risky', why: YAHOO_WHY };
  return r;
}
async function checkOneRaw(email, meta, opts) {
  const e = normEmailV(email), m = meta || {};
  const b = opts.bad && opts.bad[e]; if (b) return { e, v: 'bad', why: 'marked bad' + (b.w ? ': ' + String(b.w).slice(0, 80) : ''), src: 'list' };
  const st = staticCheck(e); if (st) return { e, ...st };
  const dom = domainOf(e), mx = await mxStatus(dom, opts.dnsFetch);
  if (MX_WHY[mx]) return { e, v: 'bad', why: MX_WHY[mx], src: 'dns' };
  const prov = mailboxProvider(opts.env);
  if (prov && mx !== 'unknown') {
    let cached = null; const ck = 'ev:' + (await sha(e));
    try { const v = opts.env.SK_KV && await opts.env.SK_KV.get(ck); if (v) cached = JSON.parse(v); } catch (x) { cached = null; }
    if (cached && cached.v) return { e, v: cached.v, why: cached.why, src: 'mailbox', ...(cached.rej ? { rej: true } : {}) };
    const key = await mailboxKey(opts.env);
    if (key && (await opts.reserve(1))) {
      const r = await providerCall(prov, key, e, opts.fetchImpl);
      if (r) { try { if (opts.env.SK_KV) await opts.env.SK_KV.put(ck, JSON.stringify({ v: r.v, why: r.why, at: Date.now(), ...(r.rej ? { rej: true } : {}) }), { expirationTtl: (r.v === 'bad' ? 365 : 90) * 86400 }); } catch (x) { /* cache is best effort */ } return { e, ...r, src: 'mailbox' }; }
      await opts.reserve(-1);   // unknown result: provider does not bill, give the call back
    }
  }
  const local = e.split('@')[0];
  if (isLegacy(dom)) return { e, v: 'risky', why: 'old ISP mailbox (' + dom + '): many are closed', src: 'heuristic' };
  if (ROLE.test(local)) return { e, v: 'risky', why: 'shared / role address', src: 'heuristic' };
  if (m.tested === true) return { e, v: 'verified', why: 'BatchData tested it' + (m.rank ? ' (rank ' + m.rank + ')' : '') + '; domain takes mail', src: 'batchdata' };
  return { e, v: 'risky', why: mx === 'unknown' ? 'could not check the domain' : 'domain takes mail; mailbox not confirmed', src: mx === 'unknown' ? 'dns' : 'heuristic' };
}
export async function checkMany(list, opts) {
  const out = [], q = list.slice(); let i = 0;
  const worker = async () => { while (i < q.length) { const k = i++; const it = q[k]; try { out[k] = await checkOne(it.e, it, opts); } catch (x) { out[k] = { e: normEmailV(it.e), v: 'risky', why: 'check failed', src: 'error' }; } } };
  await Promise.all(Array.from({ length: Math.min(6, q.length) }, worker));
  // mailbox check said the address does not exist: add it to the shared bad list (one read-merge-write, skips ones already listed)
  const rej = out.filter(x => x && x.rej && x.v === 'bad'); for (const x of out) if (x) delete x.rej;
  if (rej.length && opts.env && opts.env.SK_KV) {
    try {
      const o = await badList(opts.env), t = new Date().toISOString().replace(/\.\d+Z$/, 'Z'); let n = 0;
      for (const x of rej) if (!o[x.e] && Object.keys(o).length < 20000) { o[x.e] = { w: String(x.why || 'mailbox check: rejected').slice(0, 120), t }; n++; }
      if (n) { await saveBadList(opts.env, o); if (opts.bad) for (const x of rej) opts.bad[x.e] = o[x.e]; }
    } catch (x) { /* best effort: the verdict is still Bad and cached */ }
  }
  return out;
}
export const _emailTest = { isYahooFamily, staticCheck, mxStatus, checkOne, isLegacy, resetMx: () => { mxCache.clear(); mxFlight.clear(); }, LEGACY, TYPO, DISPOSABLE };
