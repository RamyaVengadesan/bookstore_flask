/* PU Book Store front-end: toasts, AJAX cart/wishlist, live search, theme, cart page controls. */
(function () {
  'use strict';
  var csrf = (document.querySelector('meta[name=csrf-token]') || {}).content || '';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // ---------- toasts
  var toasts = $('#toasts');
  function toast(msg, kind) {
    var t = document.createElement('div');
    t.className = 'toast ' + (kind || 'info');
    t.setAttribute('role', 'status');
    t.textContent = msg;
    toasts.appendChild(t);
    dismiss(t);
  }
  function dismiss(t) {
    setTimeout(function () { t.classList.add('out'); setTimeout(function () { t.remove(); }, 320); }, 3800);
  }
  $$('.toast', toasts).forEach(dismiss);

  // ---------- fetch helper (always sends CSRF + marks the request as AJAX)
  function post(url, data) {
    var body = new URLSearchParams(data || {});
    return fetch(url, {
      method: 'POST', body: body, credentials: 'same-origin',
      headers: { 'X-Requested-With': 'fetch', 'X-CSRF-Token': csrf, 'Accept': 'application/json' }
    }).then(function (r) {
      return r.json().catch(function () { return { ok: false, message: 'Something went wrong. Please try again.' }; })
        .then(function (j) {
          if (r.status === 401 && j.login) { location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search); }
          return j;
        });
    }).catch(function () { return { ok: false, message: 'Network problem. Check your connection and try again.' }; });
  }
  window.PU = { post: post, toast: toast };

  function setBadge(n) {
    var b = $('#cart-badge');
    if (!b) return;
    b.textContent = n; b.hidden = !n;
    b.classList.remove('bump'); void b.offsetWidth; b.classList.add('bump');
  }

  // ---------- add to cart
  $$('form[data-ajax-add]').forEach(function (f) {
    f.addEventListener('submit', function (e) {
      if (e.submitter && e.submitter.name === 'buy_now') return; // normal submit
      e.preventDefault();
      var btn = f.querySelector('button'); btn.disabled = true;
      post(f.action, new FormData(f)).then(function (j) {
        btn.disabled = false;
        toast(j.message, j.ok ? 'success' : 'error');
        if (j.count !== undefined) setBadge(j.count);
      });
    });
  });

  // ---------- wishlist hearts
  $$('.wish-btn').forEach(function (b) {
    b.addEventListener('click', function () {
      post('/wishlist/toggle/' + b.dataset.id).then(function (j) {
        if (!j.ok) return toast(j.message, 'error');
        b.classList.toggle('on', j.wished);
        b.setAttribute('aria-pressed', j.wished);
        toast(j.message, 'success');
        if (!j.wished && b.closest('[data-wishlist-page]')) b.closest('.card').remove();
      });
    });
  });

  // ---------- header menu
  var menuBtn = $('.menu-btn');
  if (menuBtn) {
    var list = $('.menu-list');
    menuBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      list.hidden = !list.hidden; menuBtn.setAttribute('aria-expanded', !list.hidden);
    });
    document.addEventListener('click', function () { list.hidden = true; menuBtn.setAttribute('aria-expanded', 'false'); });
  }

  // ---------- theme
  var tt = $('#theme-toggle');
  if (tt) tt.addEventListener('click', function () {
    var next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('theme', next); } catch (e) {}
  });

  // ---------- live search suggestions
  var input = $('#search-input'), box = $('#suggest'), timer, idx = -1;
  function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  if (input && box) {
    input.addEventListener('input', function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < 2) { box.hidden = true; return; }
      timer = setTimeout(function () {
        fetch('/api/search?q=' + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (d) {
          idx = -1;
          if (!d.results.length) { box.innerHTML = '<div class="s-meta" style="padding:12px 14px">No matches for “' + esc(q) + '”.</div>'; box.hidden = false; return; }
          box.innerHTML = d.results.map(function (r) {
            return '<a href="' + r.url + '"><div><div class="s-title">' + esc(r.name) + '</div><div class="s-meta">' + esc(r.author) + '</div></div><span class="s-price">₹' + Math.round(r.price) + '</span></a>';
          }).join('');
          box.hidden = false;
        }).catch(function () { box.hidden = true; });
      }, 200);
    });
    input.addEventListener('keydown', function (e) {
      var items = $$('a', box);
      if (!items.length || box.hidden) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        idx = (idx + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        items.forEach(function (a, i) { a.classList.toggle('sel', i === idx); });
      } else if (e.key === 'Enter' && idx >= 0) { e.preventDefault(); location.href = items[idx].href; }
      else if (e.key === 'Escape') { box.hidden = true; }
    });
    document.addEventListener('click', function (e) { if (!box.contains(e.target) && e.target !== input) box.hidden = true; });
  }

  // ---------- confirm dialogs on destructive forms
  $$('form[data-confirm]').forEach(function (f) {
    f.addEventListener('submit', function (e) { if (!confirm(f.dataset.confirm)) e.preventDefault(); });
  });

  // ---------- catalogue: auto-submit filters, mobile filter toggle
  $$('[data-autosubmit]').forEach(function (el) { el.addEventListener('change', function () { el.form.submit(); }); });
  var ft = $('.filter-toggle');
  if (ft) ft.addEventListener('click', function () { $('.filters').classList.toggle('open'); });

  // ---------- cart page: quantity buttons + remove without a reload
  function applyCart(j) {
    if (j.count !== undefined) setBadge(j.count);
    if (j.empty) { location.reload(); return; }
    Object.keys(j.lines || {}).forEach(function (id) {
      var row = $('[data-line="' + id + '"]'); if (!row) return;
      $('output', row).textContent = j.lines[id].qty;
      $('.line-total', row).textContent = j.lines[id].line_total;
    });
    $$('[data-line]').forEach(function (row) { if (!(row.dataset.line in j.lines)) row.remove(); });
    var set = function (k, v) { var el = $('[data-sum="' + k + '"]'); if (el) el.textContent = v; };
    set('subtotal', j.subtotal); set('shipping', j.shipping); set('total', j.total); set('discount', '−' + j.discount);
    var dr = $('[data-sum-row="discount"]'); if (dr) dr.hidden = !j.has_discount;
    var ship = $('[data-ship-note]');
    if (ship) {
      ship.hidden = !j.needs_more;
      var gap = $('[data-ship-gap]'); if (gap) gap.textContent = j.free_ship_gap;
    }
  }
  $$('[data-line]').forEach(function (row) {
    var id = row.dataset.line, out = $('output', row);
    $$('[data-step]', row).forEach(function (b) {
      b.addEventListener('click', function () {
        var q = parseInt(out.textContent, 10) + parseInt(b.dataset.step, 10);
        post('/cart/update/' + id, { qty: q }).then(function (j) { if (!j.ok) toast(j.message, 'error'); else { if (j.message.indexOf('Only') === 0) toast(j.message, 'info'); applyCart(j); } });
      });
    });
    var rm = $('[data-remove]', row);
    if (rm) rm.addEventListener('click', function () {
      post('/cart/remove/' + id).then(function (j) { toast(j.message, j.ok ? 'success' : 'error'); if (j.ok) applyCart(j); });
    });
  });
  $$('[data-coupon]').forEach(function (b) {
    b.addEventListener('click', function () { var i = $('#coupon-code'); if (i) { i.value = b.dataset.coupon; i.focus(); } });
  });

  // ---------- checkout: show new-address fields only when chosen
  var newAddr = $('#new-address');
  if (newAddr) {
    var sync = function () {
      var sel = $('input[name=address_id]:checked');
      var show = !sel || sel.value === 'new';
      newAddr.hidden = !show;
      $$('input, select', newAddr).forEach(function (el) { if (el.dataset.req !== undefined) el.required = show; });
    };
    $$('input[name=address_id]').forEach(function (r) { r.addEventListener('change', sync); });
    sync();
  }
})();
