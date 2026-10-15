/* Light copy deterrents. This only discourages CASUAL copying (right-click save, view-source shortcut, drag-saving images,
   click-drag text selection). The data stays public and fully usable; nothing is gated or encrypted, and anyone technical
   can still get at it (that is by design). Inputs, textareas, links, buttons, downloads and the map are left alone. */
(function () {
  'use strict';
  var EDIT = 'input,textarea,select,[contenteditable=""],[contenteditable="true"]';
  function editable(t) { return !!(t && t.closest && t.closest(EDIT)); }

  // 1. No text selection on UI chrome; inputs/textareas keep selection + copy/paste. Links/buttons still click and tap (tel:, sms:, mailto:).
  try {
    var st = document.createElement('style');
    st.id = 'pf-deterrents';
    st.textContent =
      'html,body{-webkit-user-select:none;user-select:none;-webkit-tap-highlight-color:transparent}' +
      'input,textarea,select,[contenteditable=""],[contenteditable="true"]{-webkit-user-select:text;user-select:text}' +
      'img,svg{-webkit-user-drag:none;user-drag:none;-webkit-touch-callout:none}';
    (document.head || document.documentElement).appendChild(st);
  } catch (e) {}

  // 2. Right-click / long-press context menu (allowed in inputs so paste still works).
  document.addEventListener('contextmenu', function (e) { if (!editable(e.target)) e.preventDefault(); }, true);

  // 3. Selection start (Safari/old Edge), copy/cut and drag outside editable fields; image drag-saving.
  document.addEventListener('selectstart', function (e) { if (!editable(e.target) && !editable(e.target && e.target.parentElement)) e.preventDefault(); }, true);
  ['copy', 'cut'].forEach(function (ev) {
    document.addEventListener(ev, function (e) { if (!editable(e.target) && !editable(document.activeElement)) e.preventDefault(); }, true);
  });
  document.addEventListener('dragstart', function (e) {
    var t = e.target, n = t && t.nodeType === 1 ? t.tagName.toLowerCase() : '';
    if ((n === 'img' || n === 'svg' || n === 'a' || n === 'canvas') && !editable(t)) e.preventDefault();
  }, true);

  // 4. Keyboard: F12, Ctrl/Cmd+S, Ctrl/Cmd+U, Ctrl+Shift+I/J/C/K, Cmd+Opt+I/J/C/U. Everything else (incl. Ctrl+C/V/A/F/P) is untouched.
  document.addEventListener('keydown', function (e) {
    var k = (e.code || '').replace(/^Key/, '') || (e.key || '').toUpperCase(), mod = e.ctrlKey || e.metaKey, hit = false;
    if (e.key === 'F12' || e.code === 'F12') hit = true;
    else if (mod && !e.shiftKey && !e.altKey && (k === 'S' || k === 'U')) hit = true;
    else if (mod && e.shiftKey && (k === 'I' || k === 'J' || k === 'C' || k === 'K')) hit = true;
    else if (e.metaKey && e.altKey && (k === 'I' || k === 'J' || k === 'C' || k === 'U')) hit = true;
    if (hit) { e.preventDefault(); e.stopPropagation(); return false; }
  }, true);
})();
