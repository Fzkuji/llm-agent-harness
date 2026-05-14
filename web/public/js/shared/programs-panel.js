async function loadProgramsMeta() {
  try {
    var resp = await fetch('/api/programs/meta');
    var data = await resp.json();
    programsMeta = data || { favorites: [], folders: {} };
  } catch(e) {
    programsMeta = { favorites: [], folders: {} };
  }
}

function renderFunctions() {
  // React owns this rendering now (components/sidebar/favorites-list.tsx).
  // Kept as a no-op so legacy callers (the WS `functions_list`
  // handler, refreshFunctions stub above) don't crash if they fire.
}

// `refreshFunctions` was migrated to `web/lib/programs-actions.ts`
// (`refreshFunctionsList`) — the React Sidebar's refresh button
// calls it directly. Nothing on the legacy side reads it anymore.

async function deleteFunction(name) {
  if (!confirm('Delete function "' + name + '"?')) return;
  try {
    var resp = await fetch('/api/function/' + encodeURIComponent(name), { method: 'DELETE' });
    var data = await resp.json();
    if (data.deleted) {
      addAssistantMessage('Deleted function "' + name + '".');
      var fResp = await fetch('/api/functions');
      availableFunctions = await fResp.json();
      renderFunctions();
    } else {
      addAssistantMessage('Cannot delete: ' + (data.error || 'unknown error'));
    }
  } catch(e) { alert('Delete failed: ' + e.message); }
}

async function fixFunction(name) {
  var instruction = prompt('What should be fixed in ' + name + '?');
  if (!instruction) return;
  var input = document.getElementById('chatInput');
  input.value = 'fix ' + name + ' ' + instruction;
  sendMessage();
}

// ===== Function Form =====

function _storeState() {
  var s = window.__sessionStore;
  return (s && typeof s.getState === 'function') ? s.getState() : null;
}

function clickFunction(name, category) {
  var fn = availableFunctions.find(function(f) { return f.name === name; });
  if (!fn) return;
  var p = location.pathname;
  var onChat = p === '/chat' || p.indexOf('/s/') === 0;
  if (!onChat) {
    window.__pendingRunFunction = { name: name, cat: category || '' };
    if (window.__navigate) window.__navigate('/chat');
    return;
  }
  var state = _storeState();
  if (state) state.openFnForm(fn);
}

function clickFnExample(fnName) {
  var fn = availableFunctions.find(function(f) { return f.name === fnName; });
  if (!fn) return;
  var state = _storeState();
  if (state) state.openFnForm(fn);
}

function setInput(text) {
  var state = _storeState();
  if (state) {
    if (state.fnFormFunction) state.closeFnForm();
    state.setComposerInput(text);
    state.focusComposer();
  }
}

