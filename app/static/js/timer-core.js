/* StudyOS timer core: pure logic, no DOM. Works in browsers and in Node (tests).
 *
 * Time is derived from an absolute end timestamp (endAt = now + remaining), never
 * from counting setInterval ticks, so throttled tabs / locked phones can't drift.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.StudyTimerCore = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var MODES = ['focus', 'short', 'long', 'custom'];
  var LABELS = { focus: 'Focus', short: 'Short break', long: 'Long break', custom: 'Custom' };

  function makeKey(rand) {
    var r = rand || Math.random;
    var hex = '';
    for (var i = 0; i < 24; i++) hex += Math.floor(r() * 16).toString(16);
    return 's-' + Date.now().toString(36) + '-' + hex;
  }

  function formatClock(ms) {
    var total = Math.max(0, Math.ceil(ms / 1000));
    var m = Math.floor(total / 60), s = total % 60;
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
  }

  function createEngine(options) {
    options = options || {};
    var now = options.now || Date.now;
    var keyFn = options.makeKey || makeKey;
    var cfg = { focus: 25, short: 5, long: 15, every: 4, autoBreaks: false, autoFocus: false };
    Object.keys(options.settings || {}).forEach(function (k) { cfg[k] = options.settings[k]; });
    var handlers = { change: [], complete: [], skip: [] };

    var st = {
      mode: 'focus', status: 'idle', totalMs: 0, remainingMs: 0, endAt: 0,
      sessionKey: null, startedAt: null, cycle: 0, customMin: 45, customCounts: true
    };

    function minutesFor(mode) {
      return mode === 'custom' ? st.customMin : cfg[mode];
    }
    function applyMode(mode) {
      st.mode = mode;
      st.totalMs = Math.round(minutesFor(mode) * 60000);
      st.remainingMs = st.totalMs;
      st.status = 'idle'; st.endAt = 0; st.sessionKey = null; st.startedAt = null;
    }
    function emit(name, payload) { handlers[name].forEach(function (fn) { fn(payload); }); }
    function changed() { emit('change', snapshot()); }

    function countsAsStudy(mode) { return mode === 'focus' || (mode === 'custom' && st.customCounts); }

    function snapshot() {
      var remaining = st.status === 'running' ? Math.max(0, st.endAt - now()) : st.remainingMs;
      return {
        mode: st.mode, status: st.status, totalMs: st.totalMs, remainingMs: remaining,
        endAt: st.endAt, sessionKey: st.sessionKey, startedAt: st.startedAt, cycle: st.cycle,
        every: cfg.every, customMin: st.customMin, customCounts: st.customCounts,
        label: LABELS[st.mode], progress: st.totalMs ? 1 - remaining / st.totalMs : 0,
        countsAsStudy: countsAsStudy(st.mode)
      };
    }

    function nextModeAfter(mode) {
      if (mode === 'focus') return st.cycle >= cfg.every ? 'long' : 'short';
      if (mode === 'short' || mode === 'long') return 'focus';
      return 'custom';
    }

    function maybeAutoStart(mode) {
      if (mode === 'focus' && cfg.autoFocus) api.start();
      else if ((mode === 'short' || mode === 'long') && cfg.autoBreaks) api.start();
    }

    function finish() {
      var mode = st.mode;
      var event = {
        mode: mode, kind: countsAsStudy(mode) ? 'focus' : 'break',
        minutes: Math.round(st.totalMs / 60000), sessionKey: st.sessionKey,
        startedAt: st.startedAt, completedAt: new Date(now()).toISOString()
      };
      if (mode === 'focus') st.cycle += 1;
      var next = nextModeAfter(mode);
      if (mode === 'long') st.cycle = 0;
      applyMode(next);
      emit('complete', event);
      changed();
      maybeAutoStart(next);
    }

    var api = {
      on: function (name, fn) { handlers[name].push(fn); return api; },
      getState: snapshot,

      setSettings: function (next) {
        Object.keys(next).forEach(function (k) { cfg[k] = next[k]; });
        if (st.status === 'idle') { applyMode(st.mode); }
        changed();
      },
      setMode: function (mode) {
        if (MODES.indexOf(mode) < 0 || st.status !== 'idle') return false;
        applyMode(mode); changed(); return true;
      },
      setCustom: function (minutes, counts) {
        var m = Math.max(1, Math.min(600, Math.floor(Number(minutes)) || 1));
        st.customMin = m; if (typeof counts === 'boolean') st.customCounts = counts;
        if (st.mode === 'custom' && st.status === 'idle') applyMode('custom');
        changed();
      },
      start: function () {
        if (st.status === 'running') return false;
        if (st.status === 'paused') return api.resume();
        if (st.remainingMs <= 0) return false;
        st.sessionKey = keyFn(); st.startedAt = new Date(now()).toISOString();
        st.endAt = now() + st.remainingMs; st.status = 'running';
        changed(); return true;
      },
      pause: function () {
        if (st.status !== 'running') return false;
        st.remainingMs = Math.max(0, st.endAt - now()); st.endAt = 0; st.status = 'paused';
        changed(); return true;
      },
      resume: function () {
        if (st.status !== 'paused') return false;
        st.endAt = now() + st.remainingMs; st.status = 'running';
        changed(); return true;
      },
      reset: function () { applyMode(st.mode); changed(); return true; },
      skip: function () {
        var from = st.mode;
        if (from === 'long') st.cycle = 0;   // a skipped long break still starts a fresh cycle
        var next = nextModeAfter(from);
        applyMode(next);
        emit('skip', { from: from, to: next });
        changed();
        maybeAutoStart(next);
        return true;
      },
      /** Call often (timer + visibilitychange). Completes at most once. */
      tick: function () {
        if (st.status === 'running' && now() >= st.endAt) finish();
        return snapshot();
      },
      serialize: function () {
        return JSON.stringify({ v: 1, st: st });
      },
      /** Restore saved state; if it expired while away, completes exactly once. */
      restore: function (json) {
        var data;
        try { data = JSON.parse(json); } catch (e) { return false; }
        if (!data || data.v !== 1 || !data.st || MODES.indexOf(data.st.mode) < 0) return false;
        ['mode', 'status', 'totalMs', 'remainingMs', 'endAt', 'sessionKey', 'startedAt', 'cycle', 'customMin', 'customCounts']
          .forEach(function (k) { if (data.st[k] !== undefined) st[k] = data.st[k]; });
        if (['idle', 'running', 'paused'].indexOf(st.status) < 0) st.status = 'idle';
        if (st.status === 'running' && now() >= st.endAt) finish(); else changed();
        return true;
      }
    };

    applyMode('focus');
    return api;
  }

  /** Show-on-activity / hide-after-inactivity controller. Timers are injectable for tests. */
  function createIdleController(opts) {
    var delay = opts.delay || 3000;
    var setT = opts.setTimeout || setTimeout, clearT = opts.clearTimeout || clearTimeout;
    var active = false, hidden = false, handle = null;
    function arm() {
      clearT(handle);
      if (active) handle = setT(function () { hidden = true; opts.onHide(); }, delay);
    }
    return {
      enable: function () { active = true; if (hidden) { hidden = false; opts.onShow(); } arm(); },
      disable: function () { active = false; clearT(handle); if (hidden) { hidden = false; opts.onShow(); } },
      /** Returns true when this interaction revealed hidden controls. */
      poke: function () {
        if (!active) return false;
        var wasHidden = hidden;
        if (hidden) { hidden = false; opts.onShow(); }
        arm();
        return wasHidden;
      },
      isHidden: function () { return hidden; }
    };
  }

  return { createEngine: createEngine, createIdleController: createIdleController, formatClock: formatClock, LABELS: LABELS, makeKey: makeKey };
});
