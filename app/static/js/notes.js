/* Note editor autosave: debounced JSON saves; first save creates the note. */
(function () {
  'use strict';
  var form = document.getElementById('noteForm');
  if (!form) return;
  var state = document.getElementById('saveState');
  var noteId = form.dataset.noteId || null;
  var url = form.dataset.autosave;
  var timer = null, saving = false, dirty = false;

  function payload() {
    return { id: noteId, title: form.elements.title.value, content: form.elements.content.value, subject_id: form.elements.subject_id.value };
  }
  function schedule() { dirty = true; state.textContent = 'Unsaved changes…'; clearTimeout(timer); timer = setTimeout(save, 1200); }
  function save() {
    if (saving) { timer = setTimeout(save, 400); return; }
    if (!dirty) return;
    saving = true; dirty = false; state.textContent = 'Saving…';
    window.StudyOS.post(url, payload()).then(function (res) {
      saving = false;
      if (res.ok && res.skipped) { state.textContent = 'Not saved yet'; return; }
      if (res.ok) {
        if (!noteId && res.id) { noteId = String(res.id); history.replaceState(null, '', res.url); }
        state.textContent = dirty ? 'Unsaved changes…' : 'All changes saved';
      } else { dirty = true; state.textContent = 'Could not save — will retry'; timer = setTimeout(save, 5000); }
    }).catch(function () { saving = false; dirty = true; state.textContent = 'Offline — will retry'; timer = setTimeout(save, 5000); });
  }
  ['input', 'change'].forEach(function (ev) { form.addEventListener(ev, function (e) { if (e.target.name !== 'csrf_token') schedule(); }); });
  // flush on leave so the last keystrokes aren't lost
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden' && dirty && !saving) {
      clearTimeout(timer);
      var body = JSON.stringify(payload());
      try { fetch(url, { method: 'POST', keepalive: true, credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.StudyOS.csrf, 'X-Requested-With': 'fetch' }, body: body }); dirty = false; } catch (e) {}
    }
  });
})();
