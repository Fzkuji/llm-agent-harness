/**
 * workdir.js — working directory picker for every function form.
 *
 * Workdir is a runtime-level setting, not a function argument. It travels
 * alongside the normal `run <func> key=val ...` command as `work_dir=<path>`;
 * the server intercepts it before dispatch and routes it into exec_rt.set_workdir().
 *
 * UI: a required field rendered above every function's normal parameters,
 * with "Choose folder" (browse modal) and "Use OpenProgram repo" shortcut.
 * Last value used for a given function on a given conversation is remembered
 * server-side and prefilled on next open.
 */

function buildWorkdirField() {
  // IDs are stable because only one function form is open at a time.
  return (
    '<div class="fn-form-field fn-form-workdir-field">' +
      '<div class="fn-form-label">' +
        '<span class="fn-form-label-name">work_dir</span>' +
        '<span class="fn-form-label-type">str</span>' +
        '<span class="fn-form-label-required">*</span>' +
        '<span class="fn-form-label-desc">Absolute path: codex --cd target. Files the agent writes land here, not in the framework repo.</span>' +
      '</div>' +
      '<div class="fn-form-workdir-row">' +
        '<input class="fn-form-input fn-form-workdir-input" id="fnField_work_dir" ' +
               'placeholder="/Users/you/Documents/your-project" autocomplete="off">' +
        '<button type="button" class="fn-form-workdir-btn" onclick="openFolderPicker()" title="Browse">📁 Choose folder</button>' +
        '<button type="button" class="fn-form-workdir-btn" onclick="applyRepoWorkdir()" title="OpenProgram repo root">Use repo</button>' +
      '</div>' +
    '</div>'
  );
}

async function initWorkdirField(fnName) {
  var input = document.getElementById('fnField_work_dir');
  if (!input) return;
  var convId = (typeof currentConvId !== 'undefined') ? currentConvId : null;
  var url = '/api/workdir/defaults?function_name=' + encodeURIComponent(fnName);
  if (convId) url += '&conv_id=' + encodeURIComponent(convId);
  try {
    var r = await fetch(url);
    var data = await r.json();
    // Stash repo root for the "Use repo" shortcut
    window._workdirRepoRoot = data.repo;
    window._workdirHome = data.home;
    if (data.last) {
      input.value = data.last;
    }
  } catch (e) {
    // Non-fatal — user can still type a path
  }
}

function applyRepoWorkdir() {
  var input = document.getElementById('fnField_work_dir');
  if (!input) return;
  if (window._workdirRepoRoot) {
    input.value = window._workdirRepoRoot;
    input.style.borderColor = '';
  }
}

// ── Folder picker modal ─────────────────────────────────────────────

function openFolderPicker() {
  var input = document.getElementById('fnField_work_dir');
  if (!input) return;
  var startPath = (input.value && input.value.trim()) || window._workdirHome || '';
  _showPickerOverlay(startPath, function(chosen) {
    input.value = chosen;
    input.style.borderColor = '';
  });
}

function _showPickerOverlay(initialPath, onSelect) {
  _closePicker();
  var overlay = document.createElement('div');
  overlay.id = 'folderPickerOverlay';
  overlay.className = 'folder-picker-overlay';
  overlay.innerHTML =
    '<div class="folder-picker">' +
      '<div class="folder-picker-header">' +
        '<span>Choose a folder</span>' +
        '<button type="button" class="folder-picker-close" onclick="_closePicker()">&times;</button>' +
      '</div>' +
      '<div class="folder-picker-crumbs" id="folderPickerCrumbs"></div>' +
      '<div class="folder-picker-list" id="folderPickerList">Loading…</div>' +
      '<div class="folder-picker-footer">' +
        '<span class="folder-picker-current" id="folderPickerCurrent"></span>' +
        '<div class="folder-picker-actions">' +
          '<button type="button" class="folder-picker-btn" onclick="_closePicker()">Cancel</button>' +
          '<button type="button" class="folder-picker-btn folder-picker-btn-primary" id="folderPickerSelect">Select this folder</button>' +
        '</div>' +
      '</div>' +
    '</div>';
  document.body.appendChild(overlay);
  overlay.addEventListener('click', function(e) { if (e.target === overlay) _closePicker(); });
  document.addEventListener('keydown', _pickerKeyHandler);

  document.getElementById('folderPickerSelect').onclick = function() {
    var cur = overlay.dataset.currentPath;
    if (cur && typeof onSelect === 'function') onSelect(cur);
    _closePicker();
  };
  _browseTo(initialPath);
}

function _closePicker() {
  var el = document.getElementById('folderPickerOverlay');
  if (el && el.parentNode) el.parentNode.removeChild(el);
  document.removeEventListener('keydown', _pickerKeyHandler);
}

function _pickerKeyHandler(e) {
  if (e.key === 'Escape') _closePicker();
}

async function _browseTo(path) {
  var list = document.getElementById('folderPickerList');
  var crumbs = document.getElementById('folderPickerCrumbs');
  var current = document.getElementById('folderPickerCurrent');
  var overlay = document.getElementById('folderPickerOverlay');
  if (!list || !overlay) return;
  list.textContent = 'Loading…';
  try {
    var r = await fetch('/api/browse?path=' + encodeURIComponent(path || ''));
    var data = await r.json();
    if (!r.ok) {
      list.textContent = data.error || 'Unable to browse';
      return;
    }
    overlay.dataset.currentPath = data.path;
    current.textContent = data.path;
    crumbs.innerHTML = _renderCrumbs(data.path, data.home);
    if (!data.subdirs || data.subdirs.length === 0) {
      list.innerHTML = '<div class="folder-picker-empty">No subdirectories.</div>';
    } else {
      var html = '';
      if (data.parent) {
        html += '<div class="folder-picker-item folder-picker-parent" ' +
                'onclick="_browseTo(\'' + _escJs(data.parent) + '\')">⬑ .. (parent)</div>';
      }
      for (var i = 0; i < data.subdirs.length; i++) {
        var d = data.subdirs[i];
        html += '<div class="folder-picker-item" onclick="_browseTo(\'' + _escJs(d.path) + '\')">📁 ' + _escHtml(d.name) + '</div>';
      }
      list.innerHTML = html;
    }
  } catch (e) {
    list.textContent = 'Error: ' + e.message;
  }
}

function _renderCrumbs(fullPath, home) {
  // Render each path segment as a clickable crumb.
  var parts = fullPath.split('/').filter(Boolean);
  var html = '<span class="folder-picker-crumb" onclick="_browseTo(\'/\')">/</span>';
  var acc = '';
  for (var i = 0; i < parts.length; i++) {
    acc += '/' + parts[i];
    html += '<span class="folder-picker-crumb-sep">›</span>' +
            '<span class="folder-picker-crumb" onclick="_browseTo(\'' + _escJs(acc) + '\')">' + _escHtml(parts[i]) + '</span>';
  }
  if (home) {
    html += '<span class="folder-picker-crumb-sep">·</span>' +
            '<span class="folder-picker-crumb" onclick="_browseTo(\'' + _escJs(home) + '\')">~ Home</span>';
  }
  return html;
}

function _escHtml(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
function _escJs(s) { return String(s || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'"); }
