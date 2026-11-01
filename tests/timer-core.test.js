// Run with:  node --test tests/
const test = require('node:test');
const assert = require('node:assert/strict');
const Core = require('../app/static/js/timer-core.js');

function make(settings, extra) {
  const clock = { t: 1_700_000_000_000 };
  let n = 0;
  const events = { complete: [], skip: [] };
  const engine = Core.createEngine(Object.assign({ now: () => clock.t, makeKey: () => 'key-' + (++n), settings }, extra));
  engine.on('complete', (e) => events.complete.push(e)).on('skip', (e) => events.skip.push(e));
  return { engine, clock, events };
}
const MIN = 60000;

test('countdown uses absolute time and completes a focus session once', () => {
  const { engine, clock, events } = make({ focus: 25 });
  assert.equal(engine.getState().remainingMs, 25 * MIN);
  engine.start();
  clock.t += 10 * MIN; engine.tick();
  assert.equal(engine.getState().remainingMs, 15 * MIN);
  clock.t += 15 * MIN; engine.tick(); engine.tick(); engine.tick();      // repeated ticks must not re-complete
  assert.equal(events.complete.length, 1);
  assert.equal(events.complete[0].kind, 'focus');
  assert.equal(events.complete[0].minutes, 25);
  assert.equal(events.complete[0].sessionKey, 'key-1');
  assert.equal(engine.getState().mode, 'short');            // moved on to a break
  assert.equal(engine.getState().status, 'idle');
});

test('no drift when JavaScript is suspended (phone locked 40 minutes)', () => {
  const { engine, clock, events } = make({ focus: 25 });
  engine.start();
  clock.t += 40 * MIN;                                        // no ticks happened at all
  engine.tick();
  assert.equal(events.complete.length, 1);
  assert.equal(events.complete[0].minutes, 25);               // recorded planned length, not 40
});

test('pause freezes time, resume continues from the same remaining', () => {
  const { engine, clock } = make({ focus: 25 });
  engine.start(); clock.t += 5 * MIN;
  engine.pause();
  clock.t += 30 * MIN; engine.tick();                         // time passes while paused
  assert.equal(engine.getState().status, 'paused');
  assert.equal(engine.getState().remainingMs, 20 * MIN);
  engine.resume(); clock.t += 5 * MIN;
  assert.equal(engine.getState().remainingMs, 15 * MIN);
  assert.equal(engine.getState().sessionKey, 'key-1');        // same session across pause/resume
});

test('reset restores full duration and discards the session', () => {
  const { engine, clock, events } = make({ focus: 25 });
  engine.start(); clock.t += 7 * MIN; engine.reset();
  assert.equal(engine.getState().status, 'idle');
  assert.equal(engine.getState().remainingMs, 25 * MIN);
  clock.t += 60 * MIN; engine.tick();
  assert.equal(events.complete.length, 0);
});

test('breaks complete as kind "break" and are never study time', () => {
  const { engine, clock, events } = make({ focus: 25, short: 5, long: 15, every: 4 });
  engine.setMode('short'); engine.start(); clock.t += 5 * MIN; engine.tick();
  assert.equal(events.complete[0].kind, 'break');
  assert.equal(engine.getState().mode, 'focus');
});

test('long break after N focus sessions, then the cycle restarts', () => {
  const { engine, clock, events } = make({ focus: 25, short: 5, long: 15, every: 3 });
  const seen = [];
  for (let i = 0; i < 7; i++) {
    engine.start(); clock.t += 61 * MIN; engine.tick();
    seen.push(events.complete[i].mode);
  }
  assert.deepEqual(seen, ['focus', 'short', 'focus', 'short', 'focus', 'long', 'focus']);
  assert.equal(events.complete.filter((e) => e.kind === 'focus').length, 4);
});

test('custom durations and custom "count as study" flag', () => {
  const { engine, clock, events } = make({ focus: 25 });
  engine.setMode('custom'); engine.setCustom(90, true);
  assert.equal(engine.getState().totalMs, 90 * MIN);
  engine.start(); clock.t += 90 * MIN; engine.tick();
  assert.equal(events.complete[0].kind, 'focus'); assert.equal(events.complete[0].minutes, 90);
  engine.setCustom(10, false); engine.start(); clock.t += 10 * MIN; engine.tick();
  assert.equal(events.complete[1].kind, 'break');
  engine.setCustom(99999, true);
  assert.equal(engine.getState().customMin, 600);             // clamped
});

test('settings change durations while idle but not mid-session', () => {
  const { engine, clock } = make({ focus: 25 });
  engine.setSettings({ focus: 50 }); assert.equal(engine.getState().totalMs, 50 * MIN);
  engine.start(); clock.t += MIN; engine.setSettings({ focus: 10 });
  assert.equal(engine.getState().totalMs, 50 * MIN);          // running session untouched
});

test('mode cannot change while running', () => {
  const { engine } = make({ focus: 25 });
  engine.start();
  assert.equal(engine.setMode('long'), false);
  assert.equal(engine.getState().mode, 'focus');
});

test('auto-start breaks and auto-start focus', () => {
  const { engine, clock, events } = make({ focus: 25, short: 5, every: 4, autoBreaks: true, autoFocus: true });
  engine.start(); clock.t += 25 * MIN; engine.tick();
  assert.equal(engine.getState().status, 'running'); assert.equal(engine.getState().mode, 'short');
  clock.t += 5 * MIN; engine.tick();
  assert.equal(engine.getState().status, 'running'); assert.equal(engine.getState().mode, 'focus');
  assert.equal(events.complete.length, 2);
  assert.notEqual(events.complete[0].sessionKey, engine.getState().sessionKey);   // fresh key per session
});

test('skip never records study time and advances the cycle sensibly', () => {
  const { engine, clock, events } = make({ focus: 25, short: 5, every: 4 });
  engine.start(); clock.t += 3 * MIN; engine.skip();
  assert.equal(events.complete.length, 0); assert.equal(events.skip[0].from, 'focus');
  assert.equal(engine.getState().mode, 'short'); assert.equal(engine.getState().status, 'idle');
  assert.equal(engine.getState().cycle, 0);                   // skipped focus doesn't count toward a long break
});

test('restore: still running continues; expired completes exactly once', () => {
  const a = make({ focus: 25 });
  a.engine.start(); a.clock.t += 5 * MIN;
  const saved = a.engine.serialize();
  const b = make({ focus: 25 }); b.clock.t = a.clock.t + 2 * MIN;
  assert.equal(b.engine.restore(saved), true);
  assert.equal(b.engine.getState().status, 'running');
  assert.equal(b.engine.getState().remainingMs, 18 * MIN);
  const c = make({ focus: 25 }); c.clock.t = a.clock.t + 3 * 60 * MIN;     // browser reopened 3h later
  c.engine.restore(saved); c.engine.tick(); c.engine.tick();
  assert.equal(c.events.complete.length, 1);
  assert.equal(c.events.complete[0].sessionKey, 'key-1');
  assert.equal(c.engine.restore('not json'), false);
});

test('formatClock rounds up so 00:00 only shows at the true end', () => {
  assert.equal(Core.formatClock(25 * MIN), '25:00');
  assert.equal(Core.formatClock(25 * MIN - 1), '25:00');
  assert.equal(Core.formatClock(59001), '01:00');
  assert.equal(Core.formatClock(1), '00:01');
  assert.equal(Core.formatClock(0), '00:00');
  assert.equal(Core.formatClock(-5), '00:00');
});

test('idle controller: hides after 3s, any activity reveals, first reveal is flagged', () => {
  let now = 0, pending = null;
  const log = [];
  const idle = Core.createIdleController({
    delay: 3000,
    setTimeout: (fn, ms) => { pending = { fn, at: now + ms }; return pending; },
    clearTimeout: (h) => { if (pending === h) pending = null; },
    onHide: () => log.push('hide'), onShow: () => log.push('show')
  });
  const advance = (ms) => { now += ms; if (pending && now >= pending.at) { const p = pending; pending = null; p.fn(); } };

  assert.equal(idle.poke(), false);                 // inactive until the timer runs
  idle.enable();
  advance(2900); assert.equal(idle.isHidden(), false);
  advance(200);  assert.equal(idle.isHidden(), true); assert.deepEqual(log, ['hide']);
  assert.equal(idle.poke(), true);                  // revealing interaction is reported
  assert.equal(idle.isHidden(), false);
  advance(2000); idle.poke();                       // activity restarts the 3s window
  advance(2000); assert.equal(idle.isHidden(), false);
  advance(1100); assert.equal(idle.isHidden(), true);
  idle.disable();                                   // paused/reset: controls come back and stay
  assert.equal(idle.isHidden(), false); assert.equal(log[log.length - 1], 'show');
  advance(10000); assert.equal(idle.isHidden(), false);
});
