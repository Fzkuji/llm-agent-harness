// Right sidebar controller — mirrors the left sidebar. The <aside> is
// always in the flex row; `.collapsed` shrinks it to the icon-only
// rail (48px wide, same as left); `data-view` picks which view
// (history | detail) fills the expanded content area.
//
// Public: window.rightDock.{show, close, toggle}
//   show(view)   — expand, set active view
//   close()      — collapse (view state preserved so toggle can restore)
//   toggle(view) — click on a nav icon:
//                    * collapsed       → expand to `view`
//                    * expanded, same  → collapse
//                    * expanded, diff  → switch view
//                  no-arg toggle just collapses/expands at current view.
//
// Legacy shims keep the existing ui.js callers (toggleDetail /
// closeDetail / showDetail) working without edits.

(function () {
  var LS_OPEN = 'rightSidebarOpen';
  var LS_VIEW = 'rightSidebarView';

  function _el() { return document.getElementById('rightSidebar'); }
  function _collapsed(el) { return el.classList.contains('collapsed'); }

  function _syncNav(el) {
    var cur = el.getAttribute('data-view');
    el.querySelectorAll('.right-nav-item').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-view') === cur);
    });
  }

  function _persist(el) {
    try {
      localStorage.setItem(LS_OPEN, _collapsed(el) ? '0' : '1');
      var v = el.getAttribute('data-view');
      if (v) localStorage.setItem(LS_VIEW, v);
    } catch (e) {}
  }

  // Re-apply the saved collapsed/view state after AppShell injects the
  // right sidebar HTML. First-visit users (no key) keep the HTML default,
  // which is `collapsed`.
  function restore() {
    var el = _el();
    if (!el) return;
    try {
      var saved = localStorage.getItem(LS_OPEN);
      if (saved === '1') el.classList.remove('collapsed');
      else if (saved === '0') el.classList.add('collapsed');
      var v = localStorage.getItem(LS_VIEW);
      if (v) el.setAttribute('data-view', v);
    } catch (e) {}
    _syncNav(el);
  }

  function show(view) {
    var el = _el();
    if (!el) return;
    if (view) el.setAttribute('data-view', view);
    el.classList.remove('collapsed');
    _syncNav(el);
    _persist(el);
  }

  function close() {
    var el = _el();
    if (!el) return;
    el.classList.add('collapsed');
    _persist(el);
  }

  function toggle(view) {
    var el = _el();
    if (!el) return;
    if (!view) {
      // Bare toggle — flip collapsed state, keep current view.
      if (_collapsed(el)) show();
      else close();
      return;
    }
    var cur = el.getAttribute('data-view');
    if (_collapsed(el)) show(view);
    else if (cur === view) close();
    else show(view);
  }

  window.rightDock = { show: show, close: close, toggle: toggle, restore: restore };

  // Legacy shims used by ui.js.
  window.toggleDetail = function () { toggle('detail'); };
  window.closeDetail = function () {
    try { if (typeof selectedPath !== 'undefined') selectedPath = null; } catch (e) {}
    close();
  };
  window.toggleHistoryPanel = function () { toggle('history'); };
  window.openHistoryPanel = function () { show('history'); };
  window.closeHistoryPanel = function () { close(); };
})();
