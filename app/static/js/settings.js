/* Live preview of appearance settings before saving. */
(function () {
  'use strict';
  var form = document.getElementById('appearanceForm');
  if (!form) return;
  var root = document.documentElement;
  var accents = {};
  form.querySelectorAll('input[name="accent"]').forEach(function (r) {
    accents[r.value] = getComputedStyle(r.closest('.swatch')).getPropertyValue('--c').trim();
  });
  function apply() {
    var data = new FormData(form);
    root.dataset.bg = data.get('bg_preset') || root.dataset.bg;
    root.dataset.anim = data.get('bg_animated') ? '1' : '0';
    root.dataset.reduce = data.get('reduce_motion') ? '1' : '0';
    root.style.setProperty('--bg-i', (Number(data.get('bg_intensity')) / 100).toFixed(2));
    var c = accents[data.get('accent')];
    var m = c && c.match(/rgb\(([^)]+)\)/);
    if (m) root.style.setProperty('--accent-rgb', m[1]);
  }
  form.addEventListener('input', apply);
  form.addEventListener('change', apply);
})();
