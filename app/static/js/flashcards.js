/* One-card-at-a-time revision with flip, shuffle and spaced-repetition grading. */
(function () {
  'use strict';
  var root = document.getElementById('study');
  var dataEl = document.getElementById('deckData');
  if (!root || !dataEl) return;

  var original = JSON.parse(dataEl.textContent);
  var queue = original.slice();
  var total = original.length;
  var idx = 0, flipped = false, done = 0, remembered = 0, revised = 0, shuffled = false;

  var el = function (id) { return document.getElementById(id); };
  var flip = el('flip'), flipCard = el('flipCard'), front = el('frontText'), back = el('backText'),
      subject = el('faceSubject'), progressText = el('progressText'), progressBar = el('progressBar'),
      gradeRow = el('gradeRow'), doneCard = el('doneCard'), shuffleBtn = el('shuffleBtn');

  function setFlipped(v) {
    flipped = v;
    flip.classList.toggle('flipped', v);
    gradeRow.hidden = !v;
    // screen readers should only get the face that is showing
    flip.querySelector('.front').setAttribute('aria-hidden', String(v));
    flip.querySelector('.back').setAttribute('aria-hidden', String(!v));
  }
  function render() {
    if (!queue.length) return finish();
    idx = Math.max(0, Math.min(idx, queue.length - 1));
    var c = queue[idx];
    front.textContent = c.question;
    back.textContent = c.answer;
    subject.textContent = c.subject || 'General';
    setFlipped(false);
    progressText.textContent = 'Card ' + (idx + 1) + ' of ' + queue.length + ' · ' + done + ' reviewed';
    var pct = Math.round(done / total * 100);
    progressBar.firstElementChild.style.width = Math.min(100, pct) + '%';
    progressBar.setAttribute('aria-valuenow', String(Math.min(done, total)));
  }
  function finish() {
    root.hidden = true; doneCard.hidden = false;
    el('doneText').textContent = remembered + ' remembered, ' + revised + ' marked for revision.';
  }
  function move(step) { if (!queue.length) return; idx = (idx + step + queue.length) % queue.length; render(); }
  function shuffleArray(a) { for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; } return a; }

  function grade(result) {
    var card = queue[idx];
    window.StudyOS.post('/flashcards/' + card.id + '/review', { result: result }).then(function (res) {
      if (!res.ok) el('progressText').textContent = 'Could not save that review — try again.';
    }).catch(function () { el('progressText').textContent = 'Offline — review not saved.'; });
    done++;
    if (result === 'remembered') { remembered++; queue.splice(idx, 1); }
    else { revised++; queue.push(queue.splice(idx, 1)[0]); }   // revise: comes back at the end
    if (idx >= queue.length) idx = 0;
    if (!queue.length) { finish(); return; }
    // a revised card re-enters the queue; keep progress honest by capping at 100%
    render();
  }

  flipCard.addEventListener('click', function () { setFlipped(!flipped); });
  el('flipBtn').addEventListener('click', function () { setFlipped(!flipped); });
  el('prevBtn').addEventListener('click', function () { move(-1); });
  el('nextBtn').addEventListener('click', function () { move(1); });
  el('rememberBtn').addEventListener('click', function () { grade('remembered'); });
  el('reviseBtn').addEventListener('click', function () { grade('revise'); });
  shuffleBtn.addEventListener('click', function () {
    shuffled = !shuffled;
    shuffleBtn.setAttribute('aria-pressed', String(shuffled));
    shuffleBtn.classList.toggle('on', shuffled);
    queue = shuffled ? shuffleArray(queue.slice()) : original.filter(function (c) { return queue.indexOf(c) !== -1; });
    idx = 0; render();
  });
  document.addEventListener('keydown', function (e) {
    var tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea' || root.hidden) return;
    if (e.key === ' ' && tag !== 'button') { e.preventDefault(); setFlipped(!flipped); }
    else if (e.key === 'ArrowRight') move(1);
    else if (e.key === 'ArrowLeft') move(-1);
  });
  render();
})();
