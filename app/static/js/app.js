/* StudyOS shared UI: timezone cookie, slide-out menu, confirm dialog, small helpers. */
(function () {
  'use strict';

  // Remember the browser's UTC offset so the server can compute "today" correctly.
  try {
    var secure = location.protocol === 'https:' ? '; Secure' : '';
    document.cookie = 'tzoff=' + new Date().getTimezoneOffset() + '; path=/; max-age=31536000; SameSite=Lax' + secure;
  } catch (e) { /* cookies disabled: server falls back to UTC */ }

  var doc = document.documentElement;
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

  // ---------------------------------------------------------------- menu ----
  var toggle = document.getElementById('menuToggle');
  var sidebar = document.getElementById('sidebar');
  var scrim = document.getElementById('scrim');
  var closeBtn = document.getElementById('menuClose');

  function setMenu(open) {
    if (!sidebar) return;
    doc.classList.toggle('menu-open', open);
    sidebar.toggleAttribute('inert', !open);
    sidebar.setAttribute('aria-hidden', open ? 'false' : 'true');
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    if (open) { scrim.hidden = false; requestAnimationFrame(function () { scrim.classList.add('show'); }); closeBtn.focus({ preventScroll: true }); }
    else { scrim.classList.remove('show'); setTimeout(function () { if (!doc.classList.contains('menu-open')) scrim.hidden = true; }, 260); }
  }
  if (toggle && sidebar) {
    sidebar.setAttribute('aria-hidden', 'true');
    toggle.addEventListener('click', function () { setMenu(!doc.classList.contains('menu-open')); });
    closeBtn.addEventListener('click', function () { setMenu(false); toggle.focus({ preventScroll: true }); });
    scrim.addEventListener('click', function () { setMenu(false); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && doc.classList.contains('menu-open')) { setMenu(false); toggle.focus({ preventScroll: true }); }
    });
    sidebar.querySelectorAll('a.side-link').forEach(function (a) { a.addEventListener('click', function () { setMenu(false); }); });
    // pageshow: restoring from bfcache must not leave the menu open
    window.addEventListener('pageshow', function () { if (doc.classList.contains('menu-open')) setMenu(false); });
  }

  // ------------------------------------------------------------- confirm ----
  var dialog = document.getElementById('confirmDialog');
  function ask(text, okLabel) {
    return new Promise(function (resolve) {
      if (!dialog || typeof dialog.showModal !== 'function') { resolve(window.confirm(text)); return; }
      dialog.querySelector('#confirmText').textContent = text;
      dialog.querySelector('#confirmOk').textContent = okLabel || 'Delete';
      dialog.returnValue = 'cancel';
      dialog.addEventListener('close', function onClose() {
        dialog.removeEventListener('close', onClose);
        resolve(dialog.returnValue === 'ok');
      });
      dialog.showModal();
    });
  }
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.matches || !form.matches('form[data-confirm]') || form.dataset.confirmed === '1') return;
    e.preventDefault();
    ask(form.dataset.confirm, 'Delete').then(function (ok) {
      if (ok) { form.dataset.confirmed = '1'; form.submit(); }
    });
  });

  // ------------------------------------------------------------- helpers ----
  document.querySelectorAll('select[data-autosubmit]').forEach(function (sel) {
    sel.addEventListener('change', function () { if (sel.form) sel.form.requestSubmit(); });
  });
  document.querySelectorAll('input[type="range"][data-output]').forEach(function (r) {
    var out = r.closest('label').querySelector('output');
    r.addEventListener('input', function () { if (out) out.textContent = r.value; });
  });

  // Subject form: a custom color picker overrides the swatch radios.
  var custom = document.querySelector('input[data-color-target]');
  if (custom) {
    var radios = document.querySelectorAll('.swatches input[type="radio"][name="color"]');
    custom.addEventListener('input', function () {
      radios.forEach(function (r) { r.checked = false; });
      custom.name = 'color';
    });
    radios.forEach(function (r) { r.addEventListener('change', function () { custom.removeAttribute('name'); }); });
  }

  // Toasts fade after a few seconds.
  document.querySelectorAll('.toast').forEach(function (t, i) {
    setTimeout(function () { t.classList.add('out'); setTimeout(function () { t.remove(); }, 400); }, 5000 + i * 600);
  });

  window.StudyOS = {
    csrf: csrf,
    confirm: ask,
    post: function (url, body) {
      return fetch(url, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'X-Requested-With': 'fetch' },
        body: JSON.stringify(body)
      }).then(function (r) { return r.json().catch(function () { return { ok: false }; }).then(function (j) { j.httpStatus = r.status; return j; }); });
    }
  };
})();
