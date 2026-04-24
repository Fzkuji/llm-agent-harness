// ===== Channel bindings =====
//
// Shows the current conversation's binding in the top bar ("Channel:
// WeChat: alice" etc.) and gives the user Attach / Detach controls.
// Sidebar gets a small platform emoji next to conversations that have
// a binding so they're visually grouped.

var PLATFORM_ICONS = {
  wechat: '\u{1F4AC}',     // speech balloon
  telegram: '\u{2708}',    // airplane
  discord: '\u{1F3AE}',    // game controller
  slack: '\u{1F4BC}',      // briefcase
};

function platformLabel(p) {
  return ({
    wechat: 'WeChat',
    telegram: 'Telegram',
    discord: 'Discord',
    slack: 'Slack',
  })[p] || p;
}

function platformIcon(p) {
  return PLATFORM_ICONS[p] || '\u{1F517}';
}

function formatBindingBadge(b) {
  if (!b) return 'Channel: none';
  var display = b.user_display || b.user_id;
  return platformIcon(b.platform) + ' ' + platformLabel(b.platform)
    + ': ' + display;
}

function renderChannelBadge() {
  var el = document.getElementById('channelBadge');
  if (!el) return;
  var conv = currentConvId ? conversations[currentConvId] : null;
  var binding = conv && conv.binding;
  el.textContent = formatBindingBadge(binding);
  el.classList.toggle('active', !!binding);
}

function openChannelBindingMenu() {
  if (!currentConvId) {
    alert('Open or start a conversation first.');
    return;
  }
  var conv = conversations[currentConvId];
  var binding = conv && conv.binding;

  var overlay = document.createElement('div');
  overlay.className = 'confirm-overlay visible';

  var body;
  if (binding) {
    body =
      '<div class="confirm-title">Channel binding</div>' +
      '<div class="confirm-message">' +
        'This conversation is linked to <b>' +
        escHtml(platformLabel(binding.platform)) + ': ' +
        escHtml(binding.user_display || binding.user_id) +
        '</b>.<br><br>' +
        'Detaching keeps the conversation history but stops routing ' +
        'messages between this conversation and the channel user. ' +
        'Future messages from that user will land in a new conversation.' +
      '</div>' +
      '<div class="confirm-actions">' +
        '<button class="confirm-btn" id="_bindCancel">Close</button>' +
        '<button class="confirm-btn confirm-btn-danger" id="_bindDetach">Detach</button>' +
      '</div>';
  } else {
    body =
      '<div class="confirm-title">Attach channel</div>' +
      '<div class="confirm-message">' +
        'Route messages from a channel user into this conversation. ' +
        'Replies you send here will be delivered back to that user.' +
        '<br><br>' +
        '<div class="bind-field">' +
          '<label class="bind-label">Platform</label>' +
          '<select id="_bindPlatform" class="bind-input">' +
            '<option value="wechat">WeChat</option>' +
            '<option value="telegram">Telegram</option>' +
            '<option value="discord">Discord</option>' +
            '<option value="slack">Slack</option>' +
          '</select>' +
        '</div>' +
        '<div class="bind-field">' +
          '<label class="bind-label">User id</label>' +
          '<input id="_bindUserId" class="bind-input" placeholder="e.g. 123456 (Telegram chat_id), or channel_user for Discord/Slack">' +
        '</div>' +
        '<div class="bind-field">' +
          '<label class="bind-label">Display name (optional)</label>' +
          '<input id="_bindDisplay" class="bind-input" placeholder="label shown in the sidebar">' +
        '</div>' +
      '</div>' +
      '<div class="confirm-actions">' +
        '<button class="confirm-btn" id="_bindCancel">Cancel</button>' +
        '<button class="confirm-btn" id="_bindAttach">Attach</button>' +
      '</div>';
  }

  overlay.innerHTML = '<div class="confirm-dialog">' + body + '</div>';
  document.body.appendChild(overlay);

  function close() {
    overlay.classList.remove('visible');
    overlay.addEventListener('transitionend', function() { overlay.remove(); });
  }
  var cancelBtn = overlay.querySelector('#_bindCancel');
  if (cancelBtn) cancelBtn.onclick = close;
  var detachBtn = overlay.querySelector('#_bindDetach');
  if (detachBtn) detachBtn.onclick = function() {
    close();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        action: 'detach_channel',
        conv_id: currentConvId,
      }));
    }
  };
  var attachBtn = overlay.querySelector('#_bindAttach');
  if (attachBtn) attachBtn.onclick = function() {
    var platform = overlay.querySelector('#_bindPlatform').value;
    var userId = overlay.querySelector('#_bindUserId').value.trim();
    var display = overlay.querySelector('#_bindDisplay').value.trim();
    if (!userId) {
      alert('User id is required.');
      return;
    }
    close();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        action: 'attach_channel',
        conv_id: currentConvId,
        platform: platform,
        user_id: userId,
        user_display: display || userId,
      }));
    }
  };
  overlay.addEventListener('click', function(e) {
    if (e.target === overlay) close();
  });
}

function handleChannelBindingChanged(data) {
  if (!data || !data.conv_id) return;
  var conv = conversations[data.conv_id];
  if (conv) {
    conv.binding = data.binding || null;
  }
  renderConversations();
  renderChannelBadge();
}
