/* Skip trace UI: phone/email rendering for cards, drawer and table (tap to call / text), plus the Skip trace panel:
   export for a provider, import their result CSV (column mapping + match report), Text list export that feeds Mark as sent.
   Data layer: skiptrace.js (window.PFSkip). The page bridge (results, packs, sent tracking) is PF.skBridge from app.js.
   Not legal advice: DNC / litigator flags come from the provider; flagged numbers get no tap links and stay out of the Text list. */
(function () {
  'use strict';
  const SK = window.PFSkip, ST = SK.store, PFC = window.PFCounty, API = window.PFSkipApi;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = new Intl.NumberFormat('en-US'), $ = id => document.getElementById(id);
  const TYPE = { m: 'mobile', l: 'landline', v: 'VoIP', '': '' };
  const DNC_TIP = 'Flagged Do Not Call by your skip trace provider, so there is no tap-to-call / text link and it stays out of the Text list. TCPA caution: this is a reminder, not legal advice.';
  const LIT_TIP = 'Flagged as a TCPA litigator / TCPA-restricted number by your skip trace provider: no tap link, excluded from the Text list. Reminder only, not legal advice.';

  /* ---------- rendering (cards / drawer / table) ---------- */
  // grade badge (A+ / A / B / C / F) + Reached owner / Wrong # buttons (drawer only); g = grade from SK.gradeOf (computed when not given)
  const gradeBadge = g => `<span class="phg g${g === 'A+' ? 'ap' : g.toLowerCase()}" title="${esc(SK.GRADE_TIP[g])}">${g}</span>`;
  // WhatsApp click-to-chat: wa.me/<E.164 digits>. Stored numbers are 10-digit NANP (US, PR 787/939), so prefix country code 1.
  // Text prefill: "Hi! I am trying to reach the owner or relative of <site address, city>"; WhatsApp prefill: WA_MSG(<site address, city>) (app.js notes each folio's site address).
  // waURL encodes strictly (RFC 3986: also ' ( ) ! *) so the apostrophe in "it's" can never break the link.
  const waURL = (n, msg) => { let d = String(n || '').replace(/\D/g, ''); if (d.length === 10) d = '1' + d; return 'https://wa.me/' + d + (msg ? '?text=' + encodeURIComponent(msg).replace(/[!'()*]/g, c => '%' + c.charCodeAt(0).toString(16).toUpperCase()) : ''); };
  SK.waURL = waURL;
  const smsURL = (n, msg) => { let d = String(n || '').replace(/\D/g, ''); if (d.length === 10) d = '1' + d; return 'sms:+' + d + (msg ? '?&body=' + encodeURIComponent(msg) : ''); };   // ?&body= works on iOS, Android and Phone Link
  SK.smsURL = smsURL;
  const SITE = new Map(), MSG_PRE = 'Hi! I am trying to reach the owner or relative of ';
  const noteSite = (folio, addr, city) => { addr = String(addr || '').trim(); if (folio && addr) SITE.set(String(folio), addrCase(addr) + (city ? ', ' + titleCase(city) : '')); return ''; };
  const textMsg = folio => { const a = folio != null && SITE.get(String(folio)); return a ? MSG_PRE + a : ''; };
  const WA_MSG = a => `Hey, my name is Branden. I have a property and I think it's near yours at ${a}. Just wanted to see if you would be open to selling?`;
  const waMsg = folio => { const a = folio != null && SITE.get(String(folio)); return a ? WA_MSG(a) : ''; };
  function phoneHTML(q, g, ctl, folio) {
    const n = q[0], t = q[1];   // DNC / litigator flags stay stored in q[2] but are not shown as text (Branden's call); they lower the grade to C
    if (!g) g = SK.gradeOf(q, 0, SK.callResult(n));
    const badges = gradeBadge(g) + (t ? `<span class="phty ${t}">${TYPE[t]}</span>` : '');
    const res = SK.callResult(n);
    const btns = ctl ? `<button type="button" class="lnk stres" data-stres="${n}" data-v="${res === 'reached' ? '' : 'reached'}" title="${res === 'reached' ? 'Undo Reached owner' : 'You reached the owner on this number: grade A+, moves to the top'}">${res === 'reached' ? 'Undo reached' : 'Reached owner'}</button><button type="button" class="lnk stres" data-stres="${n}" data-v="${res === 'wrong' ? '' : 'wrong'}" title="${res === 'wrong' ? 'Undo Wrong number' : 'Wrong number: grade F, hidden from cards'}">${res === 'wrong' ? 'Undo wrong #' : 'Wrong #'}</button>` : '';
    if (g === 'F') return `<span class="stph gF"><s class="stnum">${SK.fmtPhone(n)}</s>${badges}${btns}</span>`;
    return `<span class="stph"><b class="stnum">${SK.fmtPhone(n)}</b>${badges}<a class="stl" href="tel:+1${n}" title="Call ${SK.fmtPhone(n)}">Call</a><a class="stl" href="${esc(smsURL(n, textMsg(folio)))}" title="Text ${SK.fmtPhone(n)}">Text</a><a class="stl stwa" href="${esc(waURL(n, waMsg(folio)))}" target="_blank" rel="noopener" title="WhatsApp ${SK.fmtPhone(n)}">WhatsApp</a>${btns}</span>`;
  }
  const shown = r => SK.graded(r).filter(x => x.g !== 'F');   // cards / table: F hidden, best grade first
  const topPhones = (r, k, folio) => { const a = shown(r); return { html: a.slice(0, k).map(x => phoneHTML(x.q, x.g, false, folio)).join(''), more: Math.max(0, a.length - k) }; };

  const BAD_KEY = 'pf.bademail.v1', BAD_KNOWN = ['cal_l_cox@yahoo.com', 'jamesw830@earthlink.com', 'arinajohanajulio@yahoo.es'];
  const badMap = () => { let o = {}; try { o = JSON.parse(localStorage.getItem(BAD_KEY) || '{}') || {}; } catch (e) {} return o; };
  const isBad = e => { const k = String(e || '').trim().toLowerCase(), o = badMap(); return k in o ? !!o[k] : BAD_KNOWN.includes(k); };
  const setBad = (e, v) => { const o = badMap(); o[String(e).trim().toLowerCase()] = !!v; try { localStorage.setItem(BAD_KEY, JSON.stringify(o)); } catch (x) {} };
  const goodEmails = r => ((r && r.e) || []).filter(e => !isBad(e));
  const mailto = e => isBad(e) ? `<span class="stem bad" title="Marked as a bad email (bounced): left out of Email owner and has no Email button"><s class="stl em">${esc(e)}</s><span class="badem">Bad email</span><button type="button" class="lnk stbad" data-stbad="${esc(e)}" data-v="0" title="Unmark ${esc(e)}">Unmark</button></span>` : `<span class="stem"><a class="stl em" href="mailto:${esc(e)}" title="Email ${esc(e)}">${esc(e)}</a><button type="button" class="stl stemb" data-stemail="${esc(e)}" title="Open a pre-filled email to ${esc(e)} in your Outlook (sent from your own mailbox)">Email</button><button type="button" class="lnk stbad" data-stbad="${esc(e)}" data-v="1" title="Mark ${esc(e)} as a bad email (bounced)">Bad?</button></span>`;

  /* ---------- email owners from your own Outlook (this site never sends mail) ---------- */
  const TPL_KEY = 'pf.emailtpl.v1';
  const TPL_DEF = { mode: 'web', to_addr: 'Branden@prop-hunters.com', my_name: 'Branden', my_phone: '(305) 812-9445', subject: 'Question about {property_address}',
    body: "Hey {first_name}, how are you?\n\nI own a property nearby and was reaching out to owners in the area to see if there's any interest in selling in the near future. I'm here locally in {city} and would love to have a conversation about it if you're open to it. I'd buy as-is.\n\nYou can reach me at (305) 812-9445.\n\nThanks,\nBranden" };
  /* the previous default (Oct 2026): an unedited saved copy moves to the new default too */
  const TPL_PREV_BODY = "Hey {first_name},\n\nMy name is Branden with Prop Hunters. I'm an investor/buyer and wanted to see if you'd consider an offer on {property_address}.\nif you're open to a quick conversation, you can reach me at (305) 812-9445.\n\nThanks,\nBranden";
  /* the earlier default body: a saved template that still equals it moves to the new default; edited ones are kept */
  const TPL_OLD_BODY = "Hi {owner_first},\n\nMy name is {my_name} with Prop Hunters. I'm a local buyer and wanted to see if you'd consider an offer on {property_address}. No repairs or agents needed.\n\nIf you're open to a quick conversation, you can reach me at {my_phone}.\n\nThanks,\n{my_name}\n\nIf you'd rather not hear from me, just reply and let me know.";
  // Branden removed this line everywhere: stripped (with its blank line) from any saved template, edited or not
  const OPT_OUT_RE = /(?:\r?\n[ \t]*)*[ \t]*If you[’']d rather not hear from me, just reply and let me know\.[ \t]*(?=\r?\n|$)/g;
  function tplGet() { let o = {}; try { o = JSON.parse(localStorage.getItem(TPL_KEY) || '{}') || {}; } catch (e) {} const t = { ...TPL_DEF }; if (o.body === TPL_OLD_BODY || o.body === TPL_PREV_BODY) delete o.body; if (typeof o.body === 'string') o.body = o.body.replace(OPT_OUT_RE, ''); for (const k in TPL_DEF) if (typeof o[k] === 'string') t[k] = o[k]; if (t.mode !== 'mailto') t.mode = 'web'; return t; }
  function tplSet(t) { try { localStorage.setItem(TPL_KEY, JSON.stringify(t)); return true; } catch (e) { return false; } }
  const titleCase = s => String(s || '').toLowerCase().replace(/(^|[\s\-'\/(])([a-z])/g, (m, a, b) => a + b.toUpperCase()).replace(/\b(Llc|Inc|Lp|Llp|Pa|Pllc|Ltd|Ii|Iii|Iv)\b/g, w => w.toUpperCase()).replace(/\bMc([a-z])/g, (m, a) => 'Mc' + a.toUpperCase());
  const addrCase = s => titleCase(s).replace(/\b(Nw|Ne|Sw|Se)\b/g, w => w.toUpperCase());
  function ownerNames(owner, order, gov) {
    const o = SK.parseOwner(owner, { order: order || 'first-last', gov: !!gov });
    if (o.isCompany || !o.first) return { first: 'there', name: titleCase(o.isCompany ? (o.company || o.full) : [o.first, o.last].filter(Boolean).join(' ') || o.full) };
    return { first: titleCase(o.first), name: titleCase([o.first, o.last].filter(Boolean).join(' ')) };
  }
  const fill = (s, v) => String(s || '').replace(/\{(first_name|owner_first|owner_name|property_address|city|my_name|my_phone)\}/g, (m, k) => { if (k === 'first_name') k = 'owner_first'; return v[k] == null ? '' : v[k]; });
  function emailUrl(to, vars, t) {
    t = t || tplGet(); const subject = fill(t.subject, vars), body = fill(t.body, vars).replace(/\r\n?/g, '\n'), E = encodeURIComponent;
    if (t.mode === 'mailto') return `mailto:${E(to).replace(/%40/g, '@')}?subject=${E(subject)}&body=${E(body.replace(/\n/g, '\r\n'))}`;
    return `https://outlook.office.com/mail/deeplink/compose?to=${E(to)}&subject=${E(subject)}&body=${E(body)}`;
  }
  function emailVars(B, id, folio) {
    const t = tplGet(); let info = null; try { if (id != null && id >= 0) info = B.info(id); } catch (e) {}
    const r = ST.get(folio) || {}; const on = ownerNames(info ? info.owner : (r.n || ''), B.order, info && info.gov);
    return { owner_first: on.first, owner_name: on.name, property_address: addrCase(info ? info.addr : ''), city: titleCase(info ? info.city : '') || 'South Florida',   // no city: "I'm here locally in South Florida"
      my_name: t.my_name, my_phone: t.my_phone };
  }
  /* Email owner: one message, To = your own address, BCC = the owner's skip-traced emails (deduped, valid only, max BCC_MAX) */
  const BCC_MAX = 5, EMAIL_RE = /^[^\s@<>(),;:"'\[\]\\]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,}$/i;
  const ownerEmails = folio => { const r = ST.get(folio), seen = new Set(), out = []; for (const e of (r && r.e) || []) { const v = String(e || '').trim(); const k = v.toLowerCase(); if (!EMAIL_RE.test(v) || seen.has(k) || isBad(v)) continue; seen.add(k); out.push(v); } return out; };
  const ownerBtn = folio => { const n = ownerEmails(folio).length; return n ? `<button type="button" class="stl stown" data-stown="${esc(folio)}" title="One email from your Outlook: To yourself, the owner's ${n} ${n === 1 ? 'address' : 'addresses'} in BCC">Email owner${n > 1 ? ' (' + Math.min(n, BCC_MAX) + ')' : ''}</button>` : ''; };
  function bccUrl(to, bcc, vars, t) {
    t = t || tplGet(); const subject = fill(t.subject, vars), body = fill(t.body, vars).replace(/\r\n?/g, '\n'), E = encodeURIComponent;
    const mailto = `mailto:${E(to).replace(/%40/g, '@')}?bcc=${bcc.map(E).join(',').replace(/%40/g, '@')}&subject=${E(subject)}&body=${E(body.replace(/\n/g, '\r\n'))}`;
    // Outlook on the web: the compose deeplink documents only to / subject / body, so the whole mailto (with bcc=) goes in mailtouri=
    return t.mode === 'mailto' ? mailto : `https://outlook.office.com/mail/deeplink/compose?mailtouri=${E(mailto)}`;
  }
  function openOwner(B, id, folio, list) {
    const t = tplGet(), to = (t.to_addr || '').trim() || TPL_DEF.to_addr, url = bccUrl(to, list, emailVars(B, id, folio), t);
    window.PF_LAST_EMAIL = { url, folio, to, bcc: list.slice(), mode: t.mode };
    if (t.mode === 'mailto') { const a = document.createElement('a'); a.href = url; a.rel = 'noopener'; document.body.appendChild(a); a.click(); a.remove(); }
    else window.open(url, '_blank', 'noopener');
    B.markEmailed(folio, list, id); const all = ownerEmails(folio).length;
    B.toast(`Opened one email in Outlook with ${list.length} ${list.length === 1 ? 'address' : 'addresses'} in BCC. Marked as emailed.` + (all > list.length ? ` ${all - list.length} more not included (max ${BCC_MAX} per message).` : ''));
  }
  function ownerClick(B, b) {
    const folio = b.dataset.stown, idEl = b.closest('[data-id]') || document.getElementById('savedBox'), id = idEl && idEl.dataset.id != null ? +idEl.dataset.id : -1;
    const all = ownerEmails(folio); if (!all.length) { B.toast('No valid email for this owner.'); return; }
    const fresh = all.filter(e => !B.emailedTo(folio, e)), old = all.filter(e => B.emailedTo(folio, e));
    const pick = a => a.slice(0, BCC_MAX);
    if (!old.length) { openOwner(B, id, folio, pick(all)); return; }
    openModal('Email this owner again?', `<div id="stEmAgain"><div class="stwarn" role="alert">Already emailed:<ul>${old.map(e => `<li><b>${esc(e)}</b> on ${esc(B.emailedTo(folio, e))}</li>`).join('')}</ul>Sending the same owner repeat emails is the quickest way to land in spam or get reported.</div>
      <div class="stact">${fresh.length ? `<button type="button" class="btn primary" id="stEmNew">Email only the ${fresh.length} new</button>` : ''}<button type="button" class="btn${fresh.length ? '' : ' primary'}" id="stEmGo">Email all again</button><button type="button" class="btn" data-stclose>Cancel</button></div></div>`);
    if (fresh.length) $('stEmNew').onclick = () => { closeModal(); openOwner(B, id, folio, pick(fresh)); };
    $('stEmGo').onclick = () => { closeModal(); openOwner(B, id, folio, pick([...fresh, ...old])); };
  }
  function openEmail(B, id, folio, to) {
    const t = tplGet(), url = emailUrl(to, emailVars(B, id, folio), t);
    window.PF_LAST_EMAIL = { url, folio, to, mode: t.mode };
    if (t.mode === 'mailto') { const a = document.createElement('a'); a.href = url; a.rel = 'noopener'; document.body.appendChild(a); a.click(); a.remove(); }
    else window.open(url, '_blank', 'noopener');
    B.markEmailed(folio, to, id); B.toast(`Opened an email to ${to} in Outlook. Marked as emailed.`);
  }
  function emailClick(B, b) {
    const to = b.dataset.stemail, holder = b.closest('[data-skfolio],[data-stfolio]'), folio = holder && (holder.dataset.skfolio || holder.dataset.stfolio) || (b.closest('tr[data-id]') && B.folioOf(+b.closest('tr[data-id]').dataset.id));
    const idEl = b.closest('[data-id]') || document.getElementById('savedBox'); const id = idEl && idEl.dataset.id != null ? +idEl.dataset.id : -1;
    if (!folio) { B.toast('Open the property and try again.'); return; }
    const prev = B.emailedTo(folio, to);
    if (prev) {
      openModal('Email this address again?', `<div id="stEmAgain"><div class="stwarn" role="alert">You already emailed <b>${esc(to)}</b> on <b>${esc(prev)}</b>. Sending the same owner repeat emails is the quickest way to land in spam or get reported.</div>
        <div class="stact"><button type="button" class="btn primary" id="stEmGo">Email again</button><button type="button" class="btn" data-stclose>Cancel</button></div></div>`);
      $('stEmGo').onclick = () => { closeModal(); openEmail(B, id, folio, to); }; return;
    }
    openEmail(B, id, folio, to);
  }
  function templateModal(B) {
    const t = tplGet(), PH = '{first_name} {owner_name} {property_address} {city} {my_name} {my_phone}';
    openModal('Email template', `<div class="sttpl" id="stTpl">
      <p class="note">The <b>Email</b> button next to a skip-traced email opens a pre-filled message in <b>your own Outlook</b>. Nothing is sent from this site: you review it and press Send. Placeholders: <code>${PH}</code></p>
      <fieldset class="stmode"><legend>Open emails in</legend>
        <label class="check"><input type="radio" name="stTplMode" id="stTplWeb" value="web" ${t.mode === 'web' ? 'checked' : ''}> Outlook on the web (outlook.office.com)</label>
        <label class="check"><input type="radio" name="stTplMode" id="stTplMailto" value="mailto" ${t.mode === 'mailto' ? 'checked' : ''}> Desktop Outlook app (mailto: link)</label></fieldset>
      <label class="sttplfull">“Email owner” sends To (your own address; the owner's emails go in BCC) <input type="email" id="stTplTo" value="${esc(t.to_addr)}" autocomplete="email"></label>
      <div class="sttplrow"><label>Your name <input type="text" id="stTplName" value="${esc(t.my_name)}" autocomplete="name"></label><label>Your phone <input type="text" id="stTplPhone" value="${esc(t.my_phone)}" autocomplete="tel"></label></div>
      <label class="sttplfull">Subject <input type="text" id="stTplSubj" value="${esc(t.subject)}"></label>
      <label class="sttplfull">Message (plain text) <textarea id="stTplBody" rows="10">${esc(t.body)}</textarea></label>
      <div class="sttips" id="stTips" role="note"><b>Inbox tips</b><ul><li>Send one at a time at a normal pace, and keep daily volume modest at first (new senders build trust slowly).</li><li>“Email owner” puts at most 5 of an owner's addresses in BCC per message.</li><li>Keep it plain text and personal: short, written like a one-to-one note.</li><li>Avoid links, images and attachments.</li><li>Stop right away if someone asks you to.</li></ul></div>
      <div class="stact"><button type="button" class="btn primary" id="stTplSave">Save template</button><button type="button" class="btn" id="stTplReset">Reset to default</button><button type="button" class="btn" data-stclose>Close</button><span class="note" id="stTplMsg" role="status" aria-live="polite"></span></div></div>`);
    const read = () => ({ mode: $('stTplMailto').checked ? 'mailto' : 'web', to_addr: $('stTplTo').value.trim() || TPL_DEF.to_addr, my_name: $('stTplName').value, my_phone: $('stTplPhone').value, subject: $('stTplSubj').value, body: $('stTplBody').value });
    $('stTplSave').onclick = () => { $('stTplMsg').textContent = tplSet(read()) ? 'Saved.' : "Couldn't save in this browser."; };
    $('stTplReset').onclick = () => { const d = TPL_DEF; $('stTplWeb').checked = true; $('stTplTo').value = d.to_addr; $('stTplName').value = d.my_name; $('stTplPhone').value = d.my_phone; $('stTplSubj').value = d.subject; $('stTplBody').value = d.body; tplSet({ ...d }); $('stTplMsg').textContent = 'Reset to the default template.'; };
  }
  const goBtn = (folio, label) => `<button type="button" class="stgo" data-stgo="${esc(folio)}" title="Look up this owner's phones and emails with BatchData (one record is billed by BatchData only if there is a match)">${label}</button>`;
  function cardLine(folio) {
    const r = ST.get(folio); if (!r) return API ? `<div class="line skgo" data-skfolio="${esc(folio)}"><span class="k">Phone</span><span class="v">${goBtn(folio, 'Skip trace')}</span></div>` : '';
    if (!r.p.length && !r.e.length) return `<div class="line skl" data-skfolio="${esc(folio)}"><span class="k">Skip trace</span><span class="v"><span class="stnone">Traced, no phone found</span></span></div>`;
    const tp = topPhones(r, 2, folio), ph = tp.html, more = tp.more ? `<span class="stmore">+${tp.more} more</span>` : '';
    return `<div class="line skl" data-skfolio="${esc(folio)}"><span class="k">Phone</span><span class="v stv">${ph}${more}${ownerBtn(folio)}${(goodEmails(r)[0] || r.e[0]) ? mailto(goodEmails(r)[0] || r.e[0]) : ''}</span></div>`;
  }
  function cellHTML(folio) {
    const r = ST.get(folio); if (!r) return '–'; if (!r.p.length && !r.e.length) return '<span class="stnone">traced · none</span>';
    const tp = topPhones(r, 2, folio); return (tp.html || '') + (tp.more ? `<span class="stmore">+${tp.more}</span>` : '') + ownerBtn(folio) + ((goodEmails(r)[0] || r.e[0]) ? mailto(goodEmails(r)[0] || r.e[0]) : '');
  }
  function drawerBody(folio) {
    const r = ST.get(folio);
    if (!r) return `${API ? `<div class="stdgo">${goBtn(folio, 'Skip trace this owner')}<span class="note" role="status" aria-live="polite" data-stmsg></span></div>` : ''}<div class="note">No skip trace results for this property yet. Press <b>Skip trace this owner</b>, or use <b>Skip trace these</b> / <b>Skip trace export</b> in the filters panel (export, run the file through your provider, then <b>Import results</b>).</div>`;
    const none = !r.p.length && !r.e.length;
    return `${none ? '<div class="note">Skip traced: the provider found no phone or email.</div>' : ''}
      ${r.p.length ? `<ul class="stlist">${SK.graded(r).map(x => `<li${x.g === 'F' ? ' class="gF"' : ''}>${phoneHTML(x.q, x.g, true, folio)}</li>`).join('')}</ul><div class="note phgnote">Grades: <b>A+</b> you reached the owner · <b>A</b> recent mobile, not on the Do-Not-Call list · <b>B</b> active, older or less certain · <b>C</b> VoIP, weak link or Do-Not-Call: call last · <b>F</b> disconnected / wrong: hidden from cards.</div>` : ''}
      ${r.e.length ? `<div class="stemails">${ownerBtn(folio)}${r.e.map(mailto).join('')}</div>` : ''}
      <div class="note">${r.n ? 'Provider name: ' + esc(r.n) + ' · ' : ''}${r.s === (API && API.SRC) ? 'Skip traced' : 'Imported'} ${esc(r.a || '')}${r.s ? ' · ' + esc(r.s) : ''}. <button type="button" class="lnk" data-stdel="${esc(folio)}">Remove this property's skip trace data</button></div>`;
  }
  const drawerHTML = folio => `<h3>Phones &amp; email</h3><div class="stdraw" data-stfolio="${esc(folio)}">${drawerBody(folio)}</div>`;

  /* ---------- modal ---------- */
  let modalEl = null;
  function closeModal() { if (modalEl) { modalEl.remove(); modalEl = null; document.removeEventListener('keydown', onKey, true); } }
  function onKey(e) { if (e.key === 'Escape') closeModal(); }
  function openModal(title, html) {
    closeModal(); const m = document.createElement('div'); m.className = 'stmodal'; m.id = 'stModal';
    m.innerHTML = `<div class="stbox" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="sth"><h2>${esc(title)}</h2><button type="button" class="btn" data-stclose>Close</button></div><div class="stbody">${html}</div></div>`;
    m.addEventListener('click', e => { if (e.target === m || e.target.closest('[data-stclose]')) closeModal(); });
    document.body.appendChild(m); modalEl = m; document.addEventListener('keydown', onKey, true); return m.querySelector('.stbody');
  }
  const tick = () => new Promise(r => setTimeout(r, 0));
  const dayStr = () => new Date().toLocaleDateString('en-CA');
  const stamp = () => dayStr().replace(/-/g, '');
  const HELP = `<ol class="sthelp"><li><b>Export</b>: filter to the properties you care about, press <b>Skip trace export</b> and send the CSV to your skip tracing provider (BatchData, Terrakotta, REISkip, etc.). Owners are de-duplicated so you only pay for each owner once.</li>
    <li><b>Import</b>: when the provider sends a result CSV back, press <b>Import results</b>, check the column mapping, and the phones / emails are matched to your properties (by folio, then property address, then owner + mailing address). A match report shows what matched.</li>
    <li><b>Work the list</b>: use <b>Has phone</b> and <b>Skip traced</b> filters, tap Call / Text on a card or in the drawer, or press <b>Text list</b> to export name + phone + address for your texting tool, then <b>Mark as sent</b> so nobody is texted twice (use <b>Hide already sent</b>).</li>
    <li><b>Privacy &amp; caution</b>: results are stored only in this browser for this county (about 5 MB of space). Numbers the provider flags DNC or litigator get no tap links and are kept out of the Text list. Calling and texting rules (TCPA, state rules) are your responsibility; this is a reminder, not legal advice.</li></ol>`;

  /* ---------- panel ---------- */
  function refreshPanel() {
    const info = $('stInfo'); if (!info) return; const n = ST.count(), ph = ST.phoneCount();
    info.textContent = n ? `${fmt.format(n)} skip traced · ${fmt.format(ph)} with a phone · ${Math.round(ST.size() / 1024)} KB used in this browser` : 'No skip trace results imported yet for this county.';
    $('stClearData').disabled = !n;
  }

  /* ---------- export for skip trace ---------- */
  async function exportModal(B) {
    const ids = B.results(); if (!ids.length) { B.toast('Nothing to export yet.'); return; }
    const body = openModal('Skip trace export', `
      <p class="note">${fmt.format(ids.length)} ${ids.length === 1 ? 'property matches' : 'properties match'} your current filters in ${esc(PFC.cfg.name)} County. The file has one row per owner with the columns skip tracers ask for (property address, owner first / last or company, mailing address, folio, county).</p>
      <div class="stopts">
        <label class="check"><input type="checkbox" id="stxDedupe" checked> One row per owner (same owner + mailing address counted once)</label>
        <label class="check"><input type="checkbox" id="stxContacted" checked> Skip properties already contacted or marked as sent</label>
        <label class="check"><input type="checkbox" id="stxTraced" checked> Skip properties already skip traced</label>
        <label class="stmax">Max rows <input type="number" id="stxMax" min="1" step="1" placeholder="all" aria-label="Maximum rows"></label>
      </div>
      <div class="stcounts" id="stxCounts" aria-live="polite">Preparing…</div>
      <div class="stwarn" id="stxWarn" hidden role="alert"></div>
      <div class="stact"><button type="button" class="btn primary" id="stxGo" disabled>Download CSV</button><button type="button" class="btn" data-stclose>Cancel</button></div>
      <details class="sthelpd"><summary>How skip tracing works</summary>${HELP}</details>`);
    const q = id => body.querySelector('#' + id); let plan = null, token = 0, armed = false, cache = new Map();
    const info = id => { let x = cache.get(id); if (!x) { x = B.info(id); x.gk = null; if (ids.length < 250000) cache.set(id, x); } return x; };
    async function compute() {
      const my = ++token; armed = false; q('stxGo').disabled = true; q('stxGo').textContent = 'Download CSV'; q('stxWarn').hidden = true; q('stxCounts').textContent = 'Preparing…';
      const dd = q('stxDedupe').checked, exC = q('stxContacted').checked, exT = q('stxTraced').checked, max = +q('stxMax').value || 0;
      try { await B.ensureDetail(); } catch (e) { q('stxCounts').textContent = 'The property details did not load. Close and try again.'; return; }
      let cont = 0, tr = 0; const groups = new Map(), order = [];
      for (let j = 0; j < ids.length; j++) {
        if (my !== token) return; if (j % 20000 === 19999) { q('stxCounts').textContent = `Preparing… ${Math.round(j / ids.length * 100)}%`; await tick(); }
        const x = info(ids[j]);
        if (exC && B.contacted(x.folio)) { cont++; continue; } if (exT && ST.has(x.folio)) { tr++; continue; }
        const k = dd ? (x.gk || (x.gk = SK.ownerGroupKey(x.owner, x.mail, x.addr, { order: B.order, gov: x.gov }))) : x.folio;
        let g = groups.get(k); if (!g) { groups.set(k, g = { x, folios: [], ids: [] }); order.push(g); } g.folios.push(x.folio); g.ids.push(ids[j]);
      }
      if (my !== token) return;
      let rows = order; const total = rows.length; if (max && rows.length > max) rows = rows.slice(0, max);
      const co = rows.filter(g => SK.parseOwner(g.x.owner, { order: B.order, gov: g.x.gov }).isCompany).length;
      plan = { rows, total, cont, tr };
      const props = rows.reduce((a, g) => a + g.folios.length, 0);
      q('stxCounts').innerHTML = `<b>${fmt.format(rows.length)} ${rows.length === 1 ? 'row' : 'rows'}</b> to skip trace${max && total > max ? ` (first ${fmt.format(max)} of ${fmt.format(total)})` : ''} covering ${fmt.format(props)} ${props === 1 ? 'property' : 'properties'} · ${fmt.format(rows.length - co)} individuals, ${fmt.format(co)} companies / trusts / government` +
        ((cont || tr) ? `<br><span class="note">Left out: ${fmt.format(cont)} already contacted / sent, ${fmt.format(tr)} already skip traced.</span>` : '');
      const w = q('stxWarn'); if (rows.length > 1000) { w.hidden = false; w.innerHTML = `<b>Large list: ${fmt.format(rows.length)} rows.</b> Skip trace providers normally charge per record, so check your provider's pricing first. Consider narrowing the filters or setting <b>Max rows</b> to run a first batch. Companies are included at the provider's discretion; many tracers only find people.`; }
      q('stxGo').disabled = !rows.length; if (!rows.length) q('stxCounts').innerHTML += '<br>Nothing left to export with these options.';
      if (rows.length > 1000) q('stxGo').textContent = `Download ${fmt.format(rows.length)} rows…`;
    }
    body.addEventListener('change', e => { if (e.target.closest('.stopts')) compute(); }); body.querySelector('#stxMax').addEventListener('input', () => { clearTimeout(compute.t); compute.t = setTimeout(compute, 400); });
    q('stxGo').onclick = () => {
      if (!plan || !plan.rows.length) return; const big = plan.rows.length > 1000;
      if (big && !armed) { armed = true; q('stxGo').textContent = `Yes, download ${fmt.format(plan.rows.length)} rows`; q('stxGo').classList.add('warn'); return; }
      const out = [SK.EXPORT_HEAD]; const county = PFC.cfg.name;
      for (const g of plan.rows) { const x = g.x; const city = /unincorporated/i.test(x.city) ? '' : x.city; out.push(SK.exportRow({ ...x, city, folioOut: B.folioOut(x.folio) }, { order: B.order, county, count: g.folios.length, folios: g.folios.map(B.folioOut) })); }
      B.download(`${PFC.id}-skiptrace-${plan.rows.length}-${stamp()}.csv`, new Blob([SK.toCSV(out)], { type: 'text/csv' }));
      B.toast(`${fmt.format(plan.rows.length)} rows exported for skip tracing`); closeModal();
    };
    compute();
  }

  /* ---------- text list ---------- */
  async function textModal(B) {
    const ids = B.results(); if (!ids.length) { B.toast('Nothing to export yet.'); return; }
    const withPh = ids.filter(id => ST.hasPhone(B.folioOf(id))).length;
    const body = openModal('Text list', `
      <p class="note">${fmt.format(ids.length)} properties match your filters; ${fmt.format(withPh)} of them have a phone from skip tracing. The Text list has <b>name, phone and address</b> (plus phone type, email and folio) for your texting tool. After the download you can <b>Mark as sent</b> to Text / SMS so the same owners aren't texted twice.</p>
      <div class="stopts">
        <label class="check"><input type="checkbox" id="sttSent" checked> Skip owners already marked as texted (Text / SMS sent)</label>
        <label class="check"><input type="checkbox" id="sttCont"> Also skip anything already contacted (calls, mailers, door knocks)</label>
        <label class="stmax">Numbers per owner <select id="sttPer"><option value="1">Best number only</option><option value="3">Up to 3 numbers</option></select></label>
      </div>
      <div class="stwarn" role="note"><b>DNC / litigator numbers are always left out</b>, and so are numbers known to be landlines. Texting and cold-calling rules (TCPA, Florida's telephone solicitation law and others) are your responsibility. This is a reminder, not legal advice.</div>
      <div class="stcounts" id="sttCounts" aria-live="polite">Preparing…</div>
      <div class="stact"><button type="button" class="btn primary" id="sttGo" disabled>Download text list</button><button type="button" class="btn" data-stclose>Cancel</button></div>`);
    const q = id => body.querySelector('#' + id); let plan = null;
    async function compute() {
      q('sttGo').disabled = true; q('sttCounts').textContent = 'Preparing…'; await B.ensureDetail();
      const exS = q('sttSent').checked, exC = q('sttCont').checked, per = +q('sttPer').value || 1; const rows = [], byPhone = new Map(), folios = new Set(), idmap = new Map();
      let noPh = 0, dnc = 0, lan = 0, bad = 0, sent = 0, cont = 0, dupes = 0;
      for (let j = 0; j < ids.length; j++) {
        if (j % 20000 === 19999) await tick(); const f = B.folioOf(ids[j]); const r = ST.get(f); if (!r || !r.p.length) { noPh++; continue; }
        if (exS && B.sentOf(f, 'sms')) { sent++; continue; } if (exC && B.contacted(f)) { cont++; continue; }
        const ok = [], cand = SK.graded(r); for (const x2 of cand) { const q2 = x2.q; if (x2.g === 'F') { bad++; continue; } if (q2[2] & 3) { dnc++; continue; } if (q2[1] === 'l') { lan++; continue; } q2.g = x2.g; ok.push(q2); }   // best grade first
        if (!ok.length) continue; const x = B.info(ids[j]);
        const o = SK.parseOwner(x.owner, { order: B.order, gov: x.gov }); let fn = o.first, ln = o.last;
        if (o.isCompany || !fn) { const [a, b] = SK.splitName(r.n, 'first-last'); if (a || b) { fn = a; ln = b; } else if (o.isCompany) { fn = ''; ln = o.company; } }
        const T = s => SK.title(s);
        for (const p of ok.slice(0, per)) {
          const prev = byPhone.get(p[0]); if (prev) { prev.folios.push(f); dupes++; folios.add(f); idmap.set(f, ids[j]); continue; }
          const row = { f, vals: [T(fn), o.isCompany && !(fn) ? ln : T(ln), SK.fmtPhone(p[0]), TYPE[p[1]] || '', r.e[0] || '', x.addr, /unincorporated/i.test(x.city) ? '' : x.city, 'FL', SK.zip5(x.zip) || x.zip, x.owner.split(' | ').filter(Boolean).join('; '), B.folioOut(f), PFC.cfg.name, p.g || ''], folios: [f] };
          byPhone.set(p[0], row); rows.push(row); folios.add(f); idmap.set(f, ids[j]);
        }
      }
      plan = { rows, folios: [...folios], idmap }; const props = folios.size;
      q('sttCounts').innerHTML = `<b>${fmt.format(rows.length)} ${rows.length === 1 ? 'number' : 'numbers'}</b> for ${fmt.format(props)} ${props === 1 ? 'property' : 'properties'}.<br><span class="note">Left out: ${fmt.format(noPh)} without a phone, ${fmt.format(dnc)} DNC / litigator numbers, ${fmt.format(lan)} landlines, ${fmt.format(bad)} wrong / disconnected (grade F), ${fmt.format(sent)} already texted${cont ? ', ' + fmt.format(cont) + ' already contacted' : ''}${dupes ? '; ' + fmt.format(dupes) + ' repeat numbers merged' : ''}.</span>`;
      q('sttGo').disabled = !rows.length;
    }
    body.addEventListener('change', e => { if (e.target.closest('.stopts')) compute(); });
    q('sttGo').onclick = () => {
      if (!plan || !plan.rows.length) return; const out = [SK.TEXT_HEAD, ...plan.rows.map(r => r.vals)]; const day = B.dayStr(new Date());
      B.download(`${PFC.id}-text-list-${plan.rows.length}-${stamp()}.csv`, new Blob([SK.toCSV(out)], { type: 'text/csv' }));
      B.setPending({ folios: plan.folios, ids: plan.idmap, day, team: 'sms', list: 'Text list ' + day, what: `${fmt.format(plan.rows.length)} numbers for ${fmt.format(plan.folios.length)} properties` });
      B.toast(`${fmt.format(plan.rows.length)} numbers exported`); closeModal();
    };
    compute();
  }

  /* ---------- import ---------- */
  function importFile(B, file) {
    const rd = new FileReader();
    rd.onerror = () => B.toast('Could not read that file.');
    rd.onload = () => mapModal(B, file.name, String(rd.result || ''));
    rd.readAsText(file);
  }
  function mapModal(B, fname, text) {
    const parsed = SK.parseCSV(text); const rows = parsed.rows;
    if (rows.length < 2) { openModal('Import skip trace results', `<div class="stwarn">That file has no data rows. Save the provider's result file as CSV and try again.</div><div class="stact"><button type="button" class="btn" data-stclose>Close</button></div>`); return; }
    const headers = rows[0].map((h, i) => String(h || '').trim() || 'Column ' + (i + 1)), data = rows.slice(1).filter(r => r.some(c => String(c).trim()));
    const map = SK.detectMapping(headers); while (map.phones.length < 5) map.phones.push({ num: -1, type: -1, dnc: -1, lit: -1, implied: '' }); while (map.emails.length < 3) map.emails.push(-1);
    const sample = i => { for (const r of data.slice(0, 30)) { const v = String(r[i] || '').trim(); if (v) return v.length > 28 ? v.slice(0, 27) + '…' : v; } return ''; };
    const opt = sel => `<option value="-1">— none —</option>` + headers.map((h, i) => `<option value="${i}" ${i === sel ? 'selected' : ''}>${esc(h)}${sample(i) ? ' (' + esc(sample(i)) + ')' : ''}</option>`).join('');
    const sel = (id, v) => `<select id="${id}" data-map="${id}">${opt(v)}</select>`;
    const fieldRows = SK.FIELDS.map(([k, label]) => `<tr><th scope="row"><label for="m_${k}">${esc(label)}</label></th><td>${sel('m_' + k, map[k])}</td></tr>`).join('');
    const phoneRows = map.phones.map((p, j) => `<tr data-slot="${j}" data-implied="${esc(p.implied || '')}"><th scope="row">Phone ${j + 1}</th><td><div class="stslot"><label>Number ${sel('p_num_' + j, p.num)}</label><label>Type (mobile / landline) ${sel('p_type_' + j, p.type)}</label><label>DNC flag ${sel('p_dnc_' + j, p.dnc)}</label><label>Litigator flag ${sel('p_lit_' + j, p.lit)}</label></div></td></tr>`).join('');
    const emailRows = map.emails.map((e, j) => `<tr><th scope="row">Email ${j + 1}</th><td>${sel('e_' + j, e)}</td></tr>`).join('');
    const nPh = map.phones.filter(p => p.num >= 0).length, nEm = map.emails.filter(e => e >= 0).length;
    const body = openModal('Import skip trace results', `
      <p class="note"><b>${esc(fname)}</b> · ${fmt.format(data.length)} rows · importing into <b>${esc(PFC.cfg.name)} County</b> only. Columns were detected automatically (${nPh} phone, ${nEm} email). Check them, change any that are wrong, and choose how rows are matched to your properties.</p>
      <div class="stmapgrid"><table class="stmap"><tbody>${fieldRows}${phoneRows}${emailRows}</tbody></table></div>
      <div class="stopts"><div class="note"><b>Match rows to properties by</b> (tried in this order):</div>
        <label class="check"><input type="checkbox" id="mkFolio" checked> 1. Folio / parcel ID</label>
        <label class="check"><input type="checkbox" id="mkAddr" checked> 2. Property address (normalized: SW 2nd Street = SW 2 ST)</label>
        <label class="check"><input type="checkbox" id="mkOwner" checked> 3. Owner name + mailing address</label>
        <label class="check"><input type="checkbox" id="mkSib" checked> Also apply to the same owner's other properties (same owner + mailing address)</label></div>
      <div class="stprev" id="stPrev"></div>
      <div class="stwarn" role="note">Numbers your provider flags <b>DNC</b> or litigator are kept and shown with a warning, but get no tap-to-call / text link and are left out of the Text list. Reminder only, not legal advice.</div>
      <div class="stact"><button type="button" class="btn primary" id="stImpGo">Import</button><button type="button" class="btn" data-stclose>Cancel</button></div>
      <div class="note" id="stImpMsg" aria-live="polite"></div>`);
    const q = id => body.querySelector('#' + id), gv = id => +q(id).value;
    const readMap = () => { const m = { phones: [], emails: [] }; for (const [k] of SK.FIELDS) m[k] = gv('m_' + k);
      map.phones.forEach((p, j) => { const num = gv('p_num_' + j); if (num >= 0) m.phones.push({ num, type: gv('p_type_' + j), dnc: gv('p_dnc_' + j), lit: gv('p_lit_' + j), implied: num === p.num ? p.implied : '' }); });
      map.emails.forEach((e, j) => { const v = gv('e_' + j); if (v >= 0) m.emails.push(v); }); return m; };
    function preview() {
      const m = readMap(); const rs = data.slice(0, 3).map(r => SK.readRow(r, m));
      const has = { f: m.folio >= 0, a: m.addr >= 0, o: (m.owner >= 0 || m.first >= 0 || m.last >= 0 || m.company >= 0) && m.mail >= 0 };
      q('mkFolio').disabled = !has.f; q('mkAddr').disabled = !has.a; q('mkOwner').disabled = !has.o;
      q('stPrev').innerHTML = `<div class="note"><b>Preview of the first ${rs.length} rows</b></div><ul>` + rs.map((r, i) => `<li>${esc(r.addr || r.owner || r.folio || 'row ' + (i + 1))}: ${r.phones.length ? r.phones.map(p => SK.fmtPhone(p[0]) + (p[1] ? ' ' + TYPE[p[1]] : '') + (p[2] ? ' DNC' : '')).join(', ') : 'no phone'}${r.emails.length ? ' · ' + esc(r.emails.join(', ')) : ''}</li>`).join('') + '</ul>';
      const none = !(has.f || has.a || has.o); q('stImpGo').disabled = none || (!m.phones.length && !m.emails.length);
      q('stImpMsg').textContent = none ? 'Map at least a folio, a property address, or owner name + mailing address so rows can be matched.' : (!m.phones.length && !m.emails.length ? 'Map at least one phone or email column.' : '');
    }
    body.addEventListener('change', preview); preview();
    q('stImpGo').onclick = async () => { q('stImpGo').disabled = true; try { await runImport(B, fname, data, readMap(), { folio: q('mkFolio').checked && !q('mkFolio').disabled, addr: q('mkAddr').checked && !q('mkAddr').disabled, owner: q('mkOwner').checked && !q('mkOwner').disabled, sib: q('mkSib').checked }, headers, body); } catch (e) { console.error(e); body.innerHTML = `<div class="stwarn">Import failed: ${esc(e && e.message || e)}</div><div class="stact"><button type="button" class="btn" data-stclose>Close</button></div>`; } };
  }
  async function runImport(B, fname, data, map, mk, headers, body) {
    const msg = t => { body.innerHTML = `<div class="stcounts" aria-live="polite">${esc(t)}</div>`; };
    msg('Loading all properties…'); await B.loadAll();
    const rows = data.map(r => SK.readRow(r, map)); const order = B.order;
    const mt = SK.matcher(rows, { order, folio: mk.folio, addr: mk.addr, owner: mk.owner });
    await B.scan(p => mt.visit(p), n => msg(`Matching on folio / address… ${n}%`));
    let res = mt.resolve();
    const needOwner = mk.owner && mt.flags.owner && res.some((r, i) => !r.how && rows[i]._mk);
    let sibs = null;
    if (needOwner || mk.sib) {
      // second pass: owner + mailing matches, and the same owner's other properties (found by exact mailing string + owner/mailing key)
      const targets = new Map();
      if (mk.sib) res.forEach(r => { if (r.how === 'folio' || r.how === 'address') r.parcels.forEach(p => { const gk = SK.ownerGroupKey(p.owner, p.mail, p.addr, { order, gov: p.gov }); if (p.mail && !gk.endsWith('|')) { let t = targets.get(p.mail); if (!t) targets.set(p.mail, t = new Map()); t.set(gk, true); } }); });
      sibs = new Map();
      await B.scan(p => { if (needOwner) mt.visitOwner(p); if (targets.size) { const mailStr = p.mail; const t = mailStr && targets.get(mailStr); if (t) { const gk = SK.ownerGroupKey(p.owner, mailStr, p.addr, { order, gov: p.gov }); if (t.has(gk)) { let a = sibs.get(gk); if (!a) sibs.set(gk, a = []); a.push({ folio: p.folio, addr: p.addr }); } } } }, n => msg(`Matching owners and their other properties… ${n}%`));
      res = mt.resolve();
    }
    msg('Saving…'); await tick();
    const day = dayStr(); const seen = new Set(); const rep = { rows: rows.length, how: { folio: 0, address: 0, owner: 0 }, unmatched: [], ambiguous: 0, dup: 0, props: new Set(), sibs: 0, noContact: 0, nums: new Set(), mobile: new Set(), land: new Set(), dnc: new Set(), emails: new Set() };
    const recs = new Map();
    res.forEach((m, i) => {
      const r = rows[i]; const hasData = r.phones.length || r.emails.length;
      if (!m.how || m.how === 'ambiguous') { if (m.how === 'ambiguous') rep.ambiguous++; rep.unmatched.push([i, m.how === 'ambiguous' ? `Ambiguous: ${m.n} properties share this address` : 'No match']); return; }
      rep.how[m.how]++; if (!hasData) rep.noContact++;
      let targets = m.parcels.map(p => p.folio);
      if (sibs && (m.how === 'folio' || m.how === 'address')) { const p0 = m.parcels[0], gk = SK.ownerGroupKey(p0.owner, p0.mail, p0.addr, { order, gov: p0.gov }), list = sibs.get(gk); if (list) for (const s of list) if (!targets.includes(s.folio)) { targets.push(s.folio); rep.sibs++; } }
      if (targets.every(f => seen.has(f))) rep.dup++; targets.forEach(f => seen.add(f));
      for (const f of targets) { let rc = recs.get(f); if (!rc) recs.set(f, rc = { n: '', p: [], e: [] }); if (r.name || r.first || r.last) rc.n = rc.n || r.name || [r.first, r.last].filter(Boolean).join(' '); for (const q of r.phones) { const ex = rc.p.find(x => x[0] === q[0]); if (ex) { ex[2] |= q[2]; if (q[1]) ex[1] = q[1]; } else rc.p.push(q.slice()); } for (const e of r.emails) if (!rc.e.includes(e)) rc.e.push(e); }
      r.phones.forEach(q => { rep.nums.add(q[0]); if (q[1] === 'm') rep.mobile.add(q[0]); if (q[1] === 'l') rep.land.add(q[0]); if (q[2] & 3) rep.dnc.add(q[0]); }); r.emails.forEach(e => rep.emails.add(e));
    });
    for (const [f, rc] of recs) { ST.merge(f, rc, fname, day); rep.props.add(f); }
    const saved = ST.commit();
    const matched = rep.rows - rep.unmatched.length;
    const un = rep.unmatched.slice(0, 8).map(([i, why]) => { const r = rows[i]; return `<li>${esc(r.addr || r.owner || r.folio || 'row ' + (i + 2))} <span class="note">${esc(why)}</span></li>`; }).join('');
    body.innerHTML = `<div class="strep" id="stReport"><h3>Import report</h3>
      <table class="strt"><tbody><tr><th>Rows in file</th><td id="rpRows">${fmt.format(rep.rows)}</td></tr>
      <tr><th>Matched</th><td id="rpMatched">${fmt.format(matched)}</td></tr>
      <tr><th class="sub">by folio / address / owner + mailing</th><td>${rep.how.folio} / ${rep.how.address} / ${rep.how.owner}</td></tr>
      <tr><th>Unmatched</th><td id="rpUnmatched">${fmt.format(rep.unmatched.length)}${rep.ambiguous ? ` (${rep.ambiguous} ambiguous)` : ''}</td></tr>
      <tr><th>Duplicates (extra rows for a property already matched)</th><td id="rpDup">${fmt.format(rep.dup)}</td></tr>
      <tr><th>Properties updated</th><td id="rpProps">${fmt.format(rep.props.size)}${rep.sibs ? ` (${fmt.format(rep.sibs)} more from the same owners)` : ''}</td></tr>
      <tr><th>Phone numbers</th><td id="rpPhones">${fmt.format(rep.nums.size)} (${rep.mobile.size} mobile, ${rep.land.size} landline) · ${fmt.format(rep.emails.size)} emails</td></tr>
      <tr><th>Flagged DNC / litigator</th><td id="rpDnc">${fmt.format(rep.dnc.size)}</td></tr>
      <tr><th>Matched but no phone / email found</th><td>${fmt.format(rep.noContact)}</td></tr></tbody></table>
      ${rep.dnc.size ? '<div class="stwarn" role="note"><b>' + fmt.format(rep.dnc.size) + ' number(s) are flagged DNC / litigator.</b> They are shown with a warning, get no tap-to-call / text link and are left out of the Text list. TCPA caution: reminder only, not legal advice.</div>' : ''}
      ${saved ? '' : `<div class="stwarn" role="alert">${esc(ST.error || 'Could not save in this browser.')}</div>`}
      ${rep.unmatched.length ? `<div class="note">Unmatched rows${rep.unmatched.length > 8 ? ' (first 8)' : ''}:</div><ul class="stun">${un}</ul><button type="button" class="btn" id="stUnDl">Download unmatched rows</button>` : ''}
      <div class="stact"><button type="button" class="btn primary" id="stRepDone">Show properties with phones</button><button type="button" class="btn" data-stclose>Close</button></div></div>`;
    const dl = body.querySelector('#stUnDl'); if (dl) dl.onclick = () => B.download(`unmatched-${stamp()}.csv`, new Blob([SK.toCSV([[...headers, 'Reason'], ...rep.unmatched.map(([i, why]) => [...data[i], why])])], { type: 'text/csv' }));
    body.querySelector('#stRepDone').onclick = () => { closeModal(); B.showPhones(); };
    window.PF_LAST_IMPORT = { rows: rep.rows, matched, unmatched: rep.unmatched.length, dup: rep.dup, props: rep.props.size, sibs: rep.sibs, how: rep.how, dnc: rep.dnc.size, phones: rep.nums.size };
    B.rerender(); refreshPanel();
  }

  /* ---------- one-click skip trace through BatchData (Worker) ---------- */
  const NOADDR = 'BatchData needs a street number plus a city or zip for the property.';
  function refreshFolio(folio) {
    document.querySelectorAll('[data-skfolio]').forEach(el => { if (el.dataset.skfolio === folio) { const h = cardLine(folio); if (h) el.outerHTML = h; } });
    document.querySelectorAll('.stdraw[data-stfolio]').forEach(el => { if (el.dataset.stfolio === folio) el.innerHTML = drawerBody(folio); });
  }
  const plural = (n, a, b) => n === 1 ? a : (b || a + 's');
  function sumLine(sum) {
    const ph = sum.phones.size, em = sum.emails.size;
    if (sum.stopped) return API.messageFor({ code: sum.stopped });
    if (sum.errors && !sum.matched && !sum.nomatch) return Object.keys(sum.errorCodes).includes('bad_address') ? NOADDR : 'BatchData could not process this one. You were not charged. Try again later.';
    if (!sum.matched && sum.nomatch) return 'No match: BatchData has no contact data for this owner (no charge).';
    if (!ph && !em) return 'Matched, but BatchData has no phone or email for this owner.';
    return `Found ${ph} ${plural(ph, 'phone')}, ${em} ${plural(em, 'email')}${sum.dnc.size ? ` (${sum.dnc.size} flagged DNC / TCPA)` : ''}.`;
  }
  // asks for the access code once per device; resolves with the code or '' (cancelled)
  function askCode(B, why) {
    return new Promise(resolve => {
      const body = openModal('Skip trace access code', `
        <p class="note">${why ? esc(why) + ' ' : ''}Skip tracing runs through BatchData using a secure service, so it needs your <b>access code</b>. Enter it once; it is kept in this browser, and your phone or browser can offer to save it in its password manager so other devices fill it in for you.</p>
        <form id="skCodeForm" action="#" method="post" autocomplete="on">
        <input type="text" name="username" id="skCodeUser" autocomplete="username" value="Prop Hunters skip trace" readonly tabindex="-1" aria-hidden="true" style="position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;overflow:hidden">
        <div class="stopts"><label class="stmax" for="skCode">Access code <input type="password" id="skCode" name="password" autocomplete="current-password" autocapitalize="off" spellcheck="false" aria-label="Access code" style="min-width:220px"></label></div>
        <div class="stwarn" id="skCodeMsg" role="alert" hidden></div>
        <div class="stact"><button type="submit" class="btn primary" id="skCodeGo">Save and continue</button><button type="button" class="btn" data-stclose>Cancel</button></div>
        </form>`);
      let settled = false; const done = v => { if (!settled) { settled = true; resolve(v); } };
      const mo = new MutationObserver(() => { if (!document.getElementById('stModal')) { mo.disconnect(); done(''); } }); mo.observe(document.body, { childList: true });
      const inp = body.querySelector('#skCode'), msg = body.querySelector('#skCodeMsg'), go = body.querySelector('#skCodeGo');
      const submit = async () => {
        const v = inp.value.trim(); if (!v) { msg.hidden = false; msg.textContent = 'Enter the access code.'; return; }
        go.disabled = true; go.textContent = 'Checking…'; msg.hidden = true;
        try { const st = await API.status(v); API.setCode(v); window.PF_SKAPI_STATUS = st; mo.disconnect(); done(v); closeModal(); }
        catch (e) { go.disabled = false; go.textContent = 'Save and continue'; msg.hidden = false; msg.textContent = API.messageFor(e); }
      };
      body.querySelector('#skCodeForm').addEventListener('submit', e => { e.preventDefault(); submit(); }); setTimeout(() => inp.focus(), 50);
    });
  }
  const busyFolios = new Set();
  async function traceOne(B, id, folio, btn) {
    if (busyFolios.has(folio)) return;
    let code = API.getCode(); if (!code) { code = await askCode(B, ''); if (!code) return; }
    busyFolios.add(folio); document.querySelectorAll('[data-stgo]').forEach(b => { if (b.dataset.stgo === folio) { b.disabled = true; b.textContent = 'Skip tracing…'; } });
    let sum;
    try {
      await B.ensureDetail();
      const item = API.buildItem(B.info(id), { order: B.order });
      if (!API.hasAddress(item)) sum = Object.assign(API.newSummary(), { errors: 1, errorCodes: { bad_address: 1 } });
      else sum = await API.run([{ id: item.id, folios: [folio], item }], { store: ST, code, chunk: 1 });
    } catch (e) { console.error(e); sum = Object.assign(API.newSummary(), { stopped: 'network' }); }
    busyFolios.delete(folio);
    if (sum.stopped === 'bad_access_code') API.clearCode();
    const line = sumLine(sum) + (sum.stopped === 'bad_access_code' ? ' Press Skip trace again to enter the code.' : '');
    window.PF_LAST_SKAPI_ONE = { folio, stopped: sum.stopped, matched: sum.matched, nomatch: sum.nomatch, errors: sum.errors, phones: sum.phones.size, emails: sum.emails.size, dnc: sum.dnc.size };
    refreshFolio(folio); B.toast(line);
    if (sum.stopped || (sum.errors && !sum.matched && !sum.nomatch)) document.querySelectorAll('[data-stgo]').forEach(b => { if (b.dataset.stgo === folio) { const m = b.parentElement.querySelector('[data-stmsg]') || b.parentElement.appendChild(Object.assign(document.createElement('span'), { className: 'stgomsg note' })); m.textContent = line; } });
    refreshPanel();
  }

  async function apiModal(B) {
    const ids = B.results(); if (!ids.length) { B.toast('Nothing to skip trace yet.'); return; }
    let code = API.getCode(); if (!code) { code = await askCode(B, ''); if (!code) return; }
    const body = openModal('Skip trace these', `<div class="stcounts" id="skaStat" aria-live="polite">Checking your access code…</div>`);
    let svc; try { svc = await API.status(code); } catch (e) { if (e && e.code === 'bad_access_code') { API.clearCode(); closeModal(); const c2 = await askCode(B, 'The saved access code was not accepted.'); if (c2) return apiModal(B); return; } body.innerHTML = `<div class="stwarn" role="alert">${esc(API.messageFor(e))}</div><div class="stact"><button type="button" class="btn" data-stclose>Close</button></div>`; return; }
    window.PF_SKAPI_STATUS = svc; const maxPer = Math.min(50, svc.maxPerRequest || 50);
    body.innerHTML = `
      <p class="note">Looks up phones and emails for the <b>${fmt.format(ids.length)}</b> ${plural(ids.length, 'property')} that match your filters in ${esc(PFC.cfg.name)} County, through BatchData. Results are saved in this browser for this county (same as importing a CSV).</p>
      <div class="stopts">
        <label class="check"><input type="checkbox" id="skaDedupe" checked> One lookup per owner (same owner + mailing address counted once, applied to all of their properties here)</label>
        <label class="check"><input type="checkbox" id="skaTraced" checked> Skip properties already skip traced</label>
        <label class="check"><input type="checkbox" id="skaContacted" checked> Skip properties already contacted or marked as sent</label>
        <label class="stmax">Max records <input type="number" id="skaMax" min="1" step="1" placeholder="all" aria-label="Maximum records"></label>
      </div>
      <div class="stcounts" id="skaCounts" aria-live="polite">Preparing…</div>
      <div class="note" id="skaCost"></div>
      <div class="stwarn" id="skaWarn" hidden role="alert"></div>
      <div class="stact" id="skaAct"><button type="button" class="btn primary" id="skaGo" disabled>Skip trace</button><button type="button" class="btn" data-stclose>Cancel</button><button type="button" class="btn ghost" id="skaForget" title="Remove the access code from this browser">Forget access code</button></div>
      <div id="skaRun" hidden><progress id="skaProg" max="100" value="0" style="width:100%"></progress><div class="stcounts" id="skaProgTxt" aria-live="polite"></div><div class="stact"><button type="button" class="btn" id="skaCancel">Cancel</button></div></div>
      <div id="skaRep"></div>`;
    const q = id => body.querySelector('#' + id); let plan = null, token = 0, armed = false, running = false; const cache = new Map();
    const info = id => { let x = cache.get(id); if (!x) { x = B.info(id); x.gk = null; if (ids.length < 250000) cache.set(id, x); } return x; };
    async function compute() {
      if (running) return; const my = ++token; armed = false; q('skaGo').disabled = true; q('skaGo').textContent = 'Skip trace'; q('skaGo').classList.remove('warn'); q('skaWarn').hidden = true; q('skaCounts').textContent = 'Preparing…'; q('skaCost').textContent = '';
      const dd = q('skaDedupe').checked, exT = q('skaTraced').checked, exC = q('skaContacted').checked, max = +q('skaMax').value || 0;
      try { await B.ensureDetail(); } catch (e) { q('skaCounts').textContent = 'The property details did not load. Close and try again.'; return; }
      let cont = 0, tr = 0, noAddr = 0; const groups = new Map(), order = [];
      for (let j = 0; j < ids.length; j++) {
        if (my !== token) return; if (j % 20000 === 19999) { q('skaCounts').textContent = `Preparing… ${Math.round(j / ids.length * 100)}%`; await tick(); }
        const x = info(ids[j]);
        if (exC && B.contacted(x.folio)) { cont++; continue; } if (exT && ST.has(x.folio)) { tr++; continue; }
        const k = dd ? (x.gk || (x.gk = SK.ownerGroupKey(x.owner, x.mail, x.addr, { order: B.order, gov: x.gov }))) : x.folio;
        let g = groups.get(k); if (!g) { const item = API.buildItem(x, { order: B.order }); if (!API.hasAddress(item)) { noAddr++; groups.set(k, { skip: true }); continue; } groups.set(k, g = { x, item, folios: [], id: item.id }); order.push(g); } else if (g.skip) { noAddr++; continue; }
        g.folios.push(x.folio);
      }
      if (my !== token) return;
      const remaining = svc.remainingToday; let rows = order, total = rows.length; if (max && rows.length > max) rows = rows.slice(0, max);
      const capped = rows.length > remaining; if (capped) rows = rows.slice(0, Math.max(0, remaining));
      plan = { rows, total, cont, tr, noAddr }; const props = rows.reduce((a, g) => a + g.folios.length, 0);
      q('skaCounts').innerHTML = `<b>${fmt.format(rows.length)} ${plural(rows.length, 'lookup')}</b> covering ${fmt.format(props)} ${plural(props, 'property', 'properties')}${(max && total > max) || capped ? ` (first ${fmt.format(rows.length)} of ${fmt.format(total)})` : ''}.` +
        ((cont || tr || noAddr) ? `<br><span class="note">Left out: ${fmt.format(cont)} already contacted / sent, ${fmt.format(tr)} already skip traced, ${fmt.format(noAddr)} without a usable street address.</span>` : '');
      q('skaCost').innerHTML = `Estimated cost: <b>check your BatchData pricing</b>. BatchData bills only for matched records, so up to ${fmt.format(rows.length)} billable ${plural(rows.length, 'record')}; no match means no charge. Daily limit on this service: <b id="skaLeft">${fmt.format(remaining)}</b> of ${fmt.format(svc.dailyCap)} left today.`;
      const w = q('skaWarn'); if (capped) { w.hidden = false; w.innerHTML = `Only ${fmt.format(remaining)} lookups are left today, so the list is cut to the first ${fmt.format(remaining)}. The limit resets at midnight Eastern.`; }
      q('skaGo').disabled = !rows.length; if (!rows.length) q('skaCounts').innerHTML += '<br>Nothing left to skip trace with these options.';
      else q('skaGo').textContent = `Skip trace ${fmt.format(rows.length)} ${plural(rows.length, 'owner')}`;
    }
    // recompute only when an option really changed (typing a max and then tapping Go fires input + change + click)
    const sig = () => [q('skaDedupe').checked, q('skaTraced').checked, q('skaContacted').checked, +q('skaMax').value || 0].join('|'); let lastSig = '';
    const maybe = () => { if (running) return; const g = sig(); if (g !== lastSig) { lastSig = g; compute(); } };
    body.addEventListener('change', e => { if (e.target.closest('.stopts')) { clearTimeout(maybe.t); maybe(); } }); q('skaMax').addEventListener('input', () => { clearTimeout(maybe.t); maybe.t = setTimeout(maybe, 400); });
    q('skaForget').onclick = () => { API.clearCode(); B.toast('Access code removed from this browser.'); closeModal(); };
    let ac = null; q('skaCancel').onclick = () => { if (ac) { ac.abort(); q('skaCancel').disabled = true; q('skaProgTxt').textContent = 'Cancelling after the current batch…'; } };
    q('skaGo').onclick = async () => {
      clearTimeout(maybe.t); if (sig() !== lastSig) { maybe(); return; }
      if (!plan || !plan.rows.length || running) return; const n = plan.rows.length;
      if (n > 25 && !armed) { armed = true; q('skaGo').textContent = `Yes, skip trace ${fmt.format(n)} (uses BatchData credits)`; q('skaGo').classList.add('warn'); return; }
      running = true; ac = new AbortController(); q('skaAct').hidden = true; body.querySelector('.stopts').hidden = true; q('skaRun').hidden = false;
      const prog = (d, t, sm) => { q('skaProg').value = Math.round(d / t * 100); q('skaProgTxt').textContent = `${fmt.format(d)} of ${fmt.format(t)} done · ${fmt.format(sm.phones.size)} phones, ${fmt.format(sm.emails.size)} emails so far`; };
      q('skaProgTxt').textContent = `0 of ${fmt.format(n)} done`;
      const groups = plan.rows.map(g => ({ id: g.id, folios: g.folios, item: g.item }));
      const sum = await API.run(groups, { store: ST, code, chunk: maxPer, signal: ac.signal, onProgress: prog });
      running = false; if (sum.stopped === 'bad_access_code') API.clearCode();
      q('skaRun').hidden = true; showReport(sum, n);
    };
    function showReport(sum, n) {
      const ph = sum.phones.size, em = sum.emails.size, tried = sum.matched + sum.nomatch + sum.errors;
      window.PF_LAST_SKAPI = { requested: n, sent: sum.sent, matched: sum.matched, withContact: sum.withContact, nomatch: sum.nomatch, errors: sum.errors, phones: ph, emails: em, dnc: sum.dnc.size, mobile: sum.mobile, props: sum.props, cancelled: sum.cancelled, stopped: sum.stopped, remaining: sum.remaining };
      q('skaRep').innerHTML = `<div class="strep" id="skaReport"><h3>Skip trace results</h3>
        <table class="strt"><tbody><tr><th>Lookups run</th><td id="skrRun">${fmt.format(tried)} of ${fmt.format(n)}</td></tr>
        <tr><th>Owners with a phone or email</th><td id="skrFound">${fmt.format(sum.withContact)}</td></tr>
        <tr><th>Phone numbers found</th><td id="skrPhones">${fmt.format(ph)} (${fmt.format(sum.mobile)} mobile)</td></tr>
        <tr><th>Emails found</th><td id="skrEmails">${fmt.format(em)}</td></tr>
        <tr><th>Flagged DNC / TCPA</th><td id="skrDnc">${fmt.format(sum.dnc.size)}</td></tr>
        <tr><th>No match (not charged)</th><td id="skrNoMatch">${fmt.format(sum.nomatch)}</td></tr>
        <tr><th>Matched, no contact data</th><td>${fmt.format(sum.matched - sum.withContact)}</td></tr>
        <tr><th>Errors (not saved, can be retried)</th><td id="skrErr">${fmt.format(sum.errors)}</td></tr>
        <tr><th>Properties updated</th><td id="skrProps">${fmt.format(sum.props)}</td></tr>
        ${sum.remaining != null ? `<tr><th>Left in today's limit</th><td>${fmt.format(sum.remaining)}</td></tr>` : ''}</tbody></table>
        ${sum.cancelled ? '<div class="note">Cancelled. Everything finished before cancelling is saved.</div>' : ''}
        ${sum.stopped ? `<div class="stwarn" role="alert"><b>Stopped:</b> ${esc(API.messageFor({ code: sum.stopped }))} Results from earlier batches are saved.</div>` : ''}
        ${sum.dnc.size ? `<div class="stwarn" role="note"><b>${fmt.format(sum.dnc.size)} number(s) are flagged DNC / TCPA.</b> They show a warning, get no tap-to-call / text link and stay out of the Text list. Reminder only, not legal advice.</div>` : ''}
        <div class="stact"><button type="button" class="btn primary" id="skaShow">Show properties with phones</button><button type="button" class="btn" data-stclose>Close</button></div></div>`;
      q('skaShow').onclick = () => { closeModal(); B.showPhones(); };
      B.rerender(); refreshPanel();
    }
    lastSig = sig(); compute();
  }

  /* ---------- wiring ---------- */
  function wire(B) {
    if (!$('stGrp')) return; let busy = false; const guard = fn => async () => { if (busy) return; busy = true; try { await fn(); } catch (e) { console.error(e); B.toast('Skip trace: ' + (e && e.message || e)); } busy = false; };
    if ($('stApiBtn')) $('stApiBtn').onclick = guard(() => apiModal(B));
    document.addEventListener('click', e => { const b = e.target.closest('[data-stgo]'); if (!b || !API) return; e.preventDefault(); e.stopPropagation(); const f = b.dataset.stgo; const holder = b.closest('[data-id]') || document.getElementById('savedBox'); const id = holder && holder.dataset.id != null ? +holder.dataset.id : -1; if (id < 0) { B.toast('Open the property and try again.'); return; } traceOne(B, id, f, b).catch(err => { console.error(err); B.toast('Skip trace: ' + (err && err.message || err)); }); });
    document.addEventListener('click', e => { const b = e.target.closest('[data-stbad]'); if (!b) return; e.preventDefault(); e.stopPropagation(); setBad(b.dataset.stbad, b.dataset.v === '1'); ST.reload(); document.querySelectorAll('.stdraw[data-stfolio]').forEach(x => { x.innerHTML = drawerBody(x.dataset.stfolio); }); }, true);
    document.addEventListener('click', e => { const b = e.target.closest('[data-stres]'); if (!b) return; e.preventDefault(); e.stopPropagation(); SK.setCallResult(b.dataset.stres, b.dataset.v); ST.reload(); document.querySelectorAll('.stdraw[data-stfolio]').forEach(x => { x.innerHTML = drawerBody(x.dataset.stfolio); }); }, true);
    document.addEventListener('click', e => { const b = e.target.closest('[data-stown]'); if (!b) return; e.preventDefault(); e.stopPropagation(); ownerClick(B, b); }, true);
    document.addEventListener('click', e => { const b = e.target.closest('[data-stemail]'); if (!b) return; e.preventDefault(); e.stopPropagation(); emailClick(B, b); }, true);
    if ($('stTplBtn')) $('stTplBtn').onclick = () => templateModal(B);
    $('stExportBtn').onclick = guard(() => exportModal(B)); $('stTextBtn').onclick = guard(() => textModal(B));
    $('stImportLbl').addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('stFile').click(); } });
    $('stFile').addEventListener('change', e => { const f = e.target.files && e.target.files[0]; if (f) importFile(B, f); e.target.value = ''; });
    $('stHelpBtn').onclick = () => openModal('How skip tracing works', HELP + `<div class="stact"><button type="button" class="btn" data-stclose>Close</button></div>`);
    let armedClear = false; $('stClearData').onclick = () => { if (!armedClear) { armedClear = true; $('stClearData').textContent = `Yes, clear ${fmt.format(ST.count())} saved results`; setTimeout(() => { armedClear = false; $('stClearData').textContent = 'Clear skip trace data'; }, 6000); return; } armedClear = false; ST.clear(); $('stClearData').textContent = 'Clear skip trace data'; B.rerender(); B.toast(`Skip trace data cleared for ${PFC.cfg.name} County`); };
    document.addEventListener('click', e => { const b = e.target.closest('[data-stdel]'); if (!b) return; ST.remove(b.dataset.stdel); const box = b.closest('.stdraw'); if (box) box.innerHTML = drawerBody(b.dataset.stdel); B.rerender(); });
    ST.onChange(refreshPanel); refreshPanel();
    window.PFSkipUI.openExport = () => exportModal(B); window.PFSkipUI.openText = () => textModal(B); window.PFSkipUI.openApi = () => apiModal(B); window.PFSkipUI.traceOne = (id, folio) => traceOne(B, id, folio); window.PFSkipUI.importText = (name, text) => mapModal(B, name, text); window.PFSkipUI.openTemplate = () => templateModal(B); window.PFSkipUI.emailUrlFor = (id, folio, to) => emailUrl(to, emailVars(B, id, folio));
  }
  window.PFSkipUI = { noteSite, textMsg, waMsg, gradeBadge, shown, cardLine, cellHTML, drawerHTML, drawerBody, refreshPanel, phoneHTML, emailHTML: mailto, ownerBtn, ownerEmails, BCC_MAX, isBad, setBad, closeModal, ownerNames, titleCase, tplGet, TPL_DEF };
  const start = () => wire(window.PF.skBridge);
  if (window.PF_READY && window.PF) start(); else document.addEventListener('pf:ready', start, { once: true });
})();
