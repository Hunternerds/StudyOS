/* Focus timer UI: wires StudyTimerCore to the page, immersive mode, sound, saving. */
(function () {
  'use strict';
  var Core = window.StudyTimerCore;
  var page = document.getElementById('timer');
  if (!Core || !page) return;

  var $ = function (id) { return document.getElementById(id); };
  var body = document.body;
  var uid = body.dataset.uid || '0';
  var STORE = 'studyos.timer.v1.' + uid;
  var PENDING = 'studyos.pending.v1.' + uid;
  var cfg = JSON.parse($('timerConfig').textContent);

  var el = {
    clock: $('clock'), ring: $('ringProg'), label: $('stageLabel'), sub: $('stageSub'),
    dots: $('dots'), counter: $('counter'), status: $('status'), subject: $('subjectSel'),
    stageSubject: $('stageSubject'), main: $('btnMain'), mainIcon: $('mainIcon'), mainLabel: $('mainLabel'),
    reset: $('btnReset'), skip: $('btnSkip'), full: $('btnFull'), fullIcon: $('fullIcon'),
    tabs: $('modeTabs'), customRow: $('customRow'), customMin: $('customMin'), customCounts: $('customCounts'),
    controls: $('controls'), form: $('timerForm'), drawer: $('timerSettings')
  };

  function coreSettings(c) {
    return { focus: c.focus_min, short: c.short_min, long: c.long_min, every: c.sessions_before_long,
             autoBreaks: !!c.auto_start_breaks, autoFocus: !!c.auto_start_focus };
  }
  var engine = Core.createEngine({ settings: coreSettings(cfg) });

  // ----------------------------------------------------------------- audio ----
  var audio = { ctx: null, ambient: null };
  function ctx() {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    if (!audio.ctx) audio.ctx = new AC();
    if (audio.ctx.state === 'suspended') audio.ctx.resume();
    return audio.ctx;
  }
  function chime() {
    if (!cfg.sound_enabled) return;
    var c = ctx(); if (!c) return;
    [660, 880, 1320].forEach(function (f, i) {
      var o = c.createOscillator(), g = c.createGain(), t = c.currentTime + i * 0.22;
      o.type = 'sine'; o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.18, t + 0.03); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.7);
      o.connect(g); g.connect(c.destination); o.start(t); o.stop(t + 0.75);
    });
  }
  function noiseBuffer(c, type) {
    var len = c.sampleRate * 3, buf = c.createBuffer(1, len, c.sampleRate), d = buf.getChannelData(0), last = 0;
    for (var i = 0; i < len; i++) {
      var w = Math.random() * 2 - 1;
      if (type === 'brown') { last = (last + 0.02 * w) / 1.02; d[i] = last * 3.5; } else { d[i] = w * 0.6; }
    }
    return buf;
  }
  function startAmbient() {
    stopAmbient();
    if (cfg.ambient === 'off' || !cfg.ambient_volume) return;
    var c = ctx(); if (!c) return;
    var src = c.createBufferSource(); src.buffer = noiseBuffer(c, cfg.ambient === 'brown' ? 'brown' : 'white'); src.loop = true;
    var gain = c.createGain(); gain.gain.value = (cfg.ambient_volume / 100) * 0.35;
    var node = src;
    if (cfg.ambient === 'rain') {
      var hp = c.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 900;
      var lp = c.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 7000;
      src.connect(hp); hp.connect(lp); node = lp;
    }
    node.connect(gain); gain.connect(c.destination); src.start();
    audio.ambient = { src: src, gain: gain };
  }
  function stopAmbient() {
    if (!audio.ambient) return;
    try { audio.ambient.src.stop(); } catch (e) {}
    audio.ambient = null;
  }

  // ------------------------------------------------------------- wake lock ----
  var wake = null;
  function lockScreen() {
    if (!('wakeLock' in navigator) || wake) return;
    navigator.wakeLock.request('screen').then(function (l) { wake = l; l.addEventListener('release', function () { wake = null; }); }).catch(function () {});
  }
  function unlockScreen() { if (wake) { wake.release().catch(function () {}); wake = null; } }

  // ------------------------------------------------------- idle controls ----
  // A press that merely REVEALS hidden controls must not also trigger the button under the finger.
  var swallowClick = false, swallowReset = null;
  var idle = Core.createIdleController({
    delay: 3000,
    onHide: function () { body.classList.add('controls-hidden'); },
    onShow: function () { body.classList.remove('controls-hidden'); }
  });
  function activity(e) {
    var revealed = idle.poke();
    if (revealed && (e.type === 'pointerdown' || e.type === 'touchstart')) {
      swallowClick = true;
      clearTimeout(swallowReset);
      swallowReset = setTimeout(function () { swallowClick = false; }, 700);
    }
  }
  ['pointermove', 'pointerdown', 'touchstart', 'keydown', 'wheel'].forEach(function (name) {
    document.addEventListener(name, activity, { passive: true, capture: true });
  });
  document.addEventListener('click', function (e) {
    if (swallowClick) { swallowClick = false; e.stopPropagation(); e.preventDefault(); }
  }, true);

  // ------------------------------------------------------------- rendering ----
  var lastClock = '', idleOn = false;
  function render() {
    var s = engine.getState();
    var running = s.status === 'running', paused = s.status === 'paused';
    var text = Core.formatClock(s.remainingMs);
    if (text !== lastClock) { el.clock.textContent = text; lastClock = text; }
    el.ring.style.strokeDashoffset = String(Math.round(Math.min(1, Math.max(0, s.progress)) * 1000));
    el.label.textContent = s.label;
    el.sub.textContent = running ? 'Stay with it' : paused ? 'Paused' : 'Ready';
    page.dataset.state = s.status; page.dataset.mode = s.mode;
    var immersive = running;
    body.classList.toggle('immersive', immersive);
    body.classList.toggle('paused', paused);
    if (immersive && !idleOn) { idleOn = true; idle.enable(); }
    else if (!immersive && idleOn) { idleOn = false; idle.disable(); }

    el.mainLabel.textContent = running ? 'Pause' : paused ? 'Resume' : 'Start';
    el.mainIcon.setAttribute('href', running ? '#i-pause' : '#i-play');
    el.subject.disabled = s.status !== 'idle';
    el.customMin.disabled = s.status !== 'idle';
    el.customCounts.disabled = s.status !== 'idle';
    el.tabs.querySelectorAll('[data-mode]').forEach(function (b) {
      var on = b.dataset.mode === s.mode;
      b.classList.toggle('active', on); b.setAttribute('aria-selected', String(on));
      b.disabled = s.status !== 'idle' && !on;
    });
    el.customRow.hidden = s.mode !== 'custom';
    var subjText = el.subject.value ? el.subject.options[el.subject.selectedIndex].text : 'General study';
    el.stageSubject.textContent = (s.mode === 'focus' || (s.mode === 'custom' && s.countsAsStudy)) ? subjText : '';
    var n = s.every;
    el.dots.innerHTML = '';
    for (var i = 0; i < n && n <= 12; i++) {
      var d = document.createElement('i'); if (i < s.cycle) d.className = 'on'; el.dots.appendChild(d);
    }
    el.counter.textContent = s.mode === 'focus'
      ? 'Session ' + (Math.min(s.cycle, n - 1) + 1) + ' of ' + n
      : (s.mode === 'custom' ? 'Custom timer' : s.cycle + ' of ' + n + ' sessions done');
    document.title = (running || paused ? text + ' · ' : '') + s.label + ' · StudyOS';
  }

  var loop = null;
  function startLoop() { if (!loop) loop = setInterval(tick, 250); }
  function stopLoop() { clearInterval(loop); loop = null; }
  function tick() {
    engine.tick();
    var s = engine.getState();
    if (s.status !== 'running') stopLoop();
    render();
  }
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') { tick(); if (engine.getState().status === 'running') lockScreen(); }
  });

  // --------------------------------------------------------------- persist ----
  function persist() { try { localStorage.setItem(STORE, engine.serialize()); } catch (e) {} }

  // ---------------------------------------------------------------- saving ----
  var inflight = {};
  function readPending() { try { return JSON.parse(localStorage.getItem(PENDING) || '[]'); } catch (e) { return []; } }
  function writePending(list) { try { localStorage.setItem(PENDING, JSON.stringify(list)); } catch (e) {} }
  function queue(p) { var l = readPending(); if (!l.some(function (x) { return x.session_key === p.session_key; })) { l.push(p); writePending(l); } }
  function unqueue(key) { writePending(readPending().filter(function (x) { return x.session_key !== key; })); }

  function submit(payload, announce) {
    if (inflight[payload.session_key]) return Promise.resolve();   // never double-submit the same session
    inflight[payload.session_key] = true;
    return window.StudyOS.post('/timer/complete', payload).then(function (res) {
      delete inflight[payload.session_key];
      if (res.ok) {
        unqueue(payload.session_key);
        if (announce) say(res.duplicate ? 'That session was already saved.' : 'Focus session saved · ' + payload.duration + ' min. Today: ' + res.today_minutes + ' min.', 'ok');
      } else if (res.httpStatus >= 400 && res.httpStatus < 500 && res.httpStatus !== 429) {
        unqueue(payload.session_key);       // permanently rejected: don't retry forever
        if (announce) say('Session finished, but it could not be saved.', 'bad');
      } else { throw new Error('retry'); }
    }).catch(function () {
      delete inflight[payload.session_key];
      queue(payload);
      if (announce) say('Session finished. Offline — it will be saved when you reconnect.', 'warn');
    });
  }
  function flushPending() { readPending().forEach(function (p) { submit(p, false); }); }
  window.addEventListener('online', flushPending);

  function say(text, kind) { el.status.textContent = text; el.status.dataset.kind = kind || ''; }

  engine.on('complete', function (ev) {
    stopAmbient(); unlockScreen(); chime();
    if (ev.kind === 'focus') {
      submit({ session_key: ev.sessionKey, duration: ev.minutes, kind: 'focus', started_at: ev.startedAt,
               subject_id: savedSubject() }, true);
      say('Focus session complete. Saving…', 'ok');
    } else {
      say(ev.mode === 'long' ? 'Long break over — ready to focus?' : 'Break over — ready to focus?', 'ok');
    }
  });
  engine.on('change', function (s) {
    persist();
    if (s.status === 'running') { startLoop(); lockScreen(); if (s.countsAsStudy || s.mode === 'focus') startAmbient(); else stopAmbient(); }
    else { stopAmbient(); unlockScreen(); }
  });

  // The subject chosen when the session was started is the one that is saved.
  function savedSubject() {
    try { var raw = JSON.parse(localStorage.getItem(STORE + '.subject') || 'null'); if (raw !== null) return raw; } catch (e) {}
    return el.subject.value || null;
  }
  function rememberSubject() { try { localStorage.setItem(STORE + '.subject', JSON.stringify(el.subject.value || null)); } catch (e) {} }

  // ------------------------------------------------------------------ input ----
  el.main.addEventListener('click', function () {
    ctx();   // unlock audio inside a user gesture
    var s = engine.getState();
    if (s.status === 'running') { engine.pause(); say('Paused.'); }
    else {
      if (s.status === 'idle') { rememberSubject(); say(''); }
      engine.start();
    }
    render();
  });
  el.reset.addEventListener('click', function () { engine.reset(); say('Timer reset.'); render(); });
  el.skip.addEventListener('click', function () {
    var s = engine.getState();
    var needsConfirm = s.status !== 'idle' && s.countsAsStudy;
    (needsConfirm ? window.StudyOS.confirm('Skip this session? It won\u2019t be saved as study time.', 'Skip') : Promise.resolve(true))
      .then(function (ok) { if (ok) { engine.skip(); say('Skipped.'); render(); } });
  });
  el.tabs.addEventListener('click', function (e) {
    var b = e.target.closest('[data-mode]'); if (!b) return;
    engine.setMode(b.dataset.mode); say(''); render();
  });
  function applyCustom() { engine.setCustom(el.customMin.value, el.customCounts.checked); render(); }
  el.customMin.addEventListener('input', applyCustom);
  el.customCounts.addEventListener('change', applyCustom);
  el.subject.addEventListener('change', render);

  document.addEventListener('keydown', function (e) {
    var t = (e.target.tagName || '').toLowerCase();
    if (e.code === 'Space' && !['input', 'select', 'textarea', 'button', 'summary'].includes(t) && !e.target.closest('dialog')) {
      e.preventDefault(); el.main.click();
    }
  });

  // -------------------------------------------------------------- fullscreen ----
  var fsEl = document.documentElement;
  var fsSupported = !!(fsEl.requestFullscreen || fsEl.webkitRequestFullscreen);
  if (fsSupported) el.full.hidden = false;
  function inFs() { return !!(document.fullscreenElement || document.webkitFullscreenElement); }
  el.full.addEventListener('click', function () {
    var p = inFs() ? (document.exitFullscreen || document.webkitExitFullscreen).call(document)
                   : (fsEl.requestFullscreen || fsEl.webkitRequestFullscreen).call(fsEl);
    if (p && p.catch) p.catch(function () {});
  });
  function fsChanged() {
    el.fullIcon.setAttribute('href', inFs() ? '#i-exit-fullscreen' : '#i-fullscreen');
    el.full.setAttribute('aria-label', inFs() ? 'Exit fullscreen' : 'Enter fullscreen');
  }
  document.addEventListener('fullscreenchange', fsChanged);
  document.addEventListener('webkitfullscreenchange', fsChanged);

  // ---------------------------------------------------------- settings drawer ----
  el.form.addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(el.form), params = new URLSearchParams();
    fd.forEach(function (v, k) { if (k !== 'csrf_token') params.append(k, v); });
    fetch(el.form.action, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRF-Token': window.StudyOS.csrf, 'X-Requested-With': 'fetch' },
      body: params.toString() })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok) { say(Object.keys(res.errors || {}).map(function (k) { return res.errors[k]; }).join(' ') || 'Could not save settings.', 'bad'); return; }
        cfg = res.settings; engine.setSettings(coreSettings(cfg));
        if (engine.getState().status === 'running') { if (cfg.ambient === 'off') stopAmbient(); else startAmbient(); }
        say('Timer settings saved.', 'ok'); el.drawer.open = false; render();
      }).catch(function () { say('Could not reach the server.', 'bad'); });
  });

  // ------------------------------------------------------------------ boot ----
  (function boot() {
    var saved = null;
    try { saved = localStorage.getItem(STORE); } catch (e) {}
    if (saved) {
      engine.restore(saved);
      // saved timer may carry old durations; only idle timers adopt the latest settings
      if (engine.getState().status === 'idle') engine.setSettings(coreSettings(cfg));
    }
    var preset = el.subject.value;   // set by ?subject= when arriving from a subject page
    try {
      var stored = JSON.parse(localStorage.getItem(STORE + '.subject') || 'null');
      var wanted = stored === null ? '' : String(stored);
      var running = engine.getState().status !== 'idle';
      var exists = Array.prototype.some.call(el.subject.options, function (o) { return o.value === wanted; });
      if (exists && (running || !preset)) el.subject.value = wanted;   // resume subject / remember last one
    } catch (e) {}
    el.customMin.value = engine.getState().customMin;
    el.customCounts.checked = engine.getState().customCounts;
    render(); fsChanged(); flushPending();
    if (engine.getState().status === 'running') startLoop();
  })();
})();
