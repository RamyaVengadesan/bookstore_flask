/* Admin console: mobile sidebar, bulk selection, bulk-action fields. */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  var side = $('#adm-side'), scrim = $('#adm-scrim'), burger = $('#adm-burger');
  function toggle(open) { side.classList.toggle('open', open); scrim.classList.toggle('open', open); }
  if (burger) burger.addEventListener('click', function () { toggle(!side.classList.contains('open')); });
  if (scrim) scrim.addEventListener('click', function () { toggle(false); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') toggle(false); });

  var all = $('#check-all'), bar = $('#bulkbar'), n = $('#bulk-n');
  var rows = $$('.row-check');
  function sync() {
    var c = rows.filter(function (r) { return r.checked; }).length;
    if (bar) bar.hidden = c === 0;
    if (n) n.textContent = c;
    if (all) { all.checked = c && c === rows.length; all.indeterminate = c > 0 && c < rows.length; }
  }
  rows.forEach(function (r) { r.addEventListener('change', sync); });
  if (all) all.addEventListener('change', function () { rows.forEach(function (r) { r.checked = all.checked; }); sync(); });

  var act = $('#bulk-action');
  if (act) {
    var cat = $('#bulk-cat'), pct = $('#bulk-pct');
    act.addEventListener('change', function () { cat.hidden = act.value !== 'category'; pct.hidden = act.value !== 'price_pct'; });
    var form = $('#bulk-form');
    form.addEventListener('submit', function (e) {
      if (!act.value) { e.preventDefault(); return PU.toast('Choose an action first.', 'error'); }
      if (act.value === 'delete' && !confirm('Delete the selected books? This can\'t be undone.')) e.preventDefault();
    });
  }
})();
