"""Persistent conversation wrapper for chat-channel messages.

Before this module existed, every channel just called ``rt.exec(text)``
— stateless, every message independent, the bot couldn't follow up.

Then we added a crude 1:1 mapping (``conv_id = f"{platform}_{user_id}"``)
so history persisted, but that baked the channel identity into the
conversation id and made bindings impossible to change. Now we delegate
to :mod:`openprogram.channels.bindings`: each (platform, user_id) is
bound to a ``conv_id`` in a dedicated table, the conversation has its
own UUID-style id, and a WeChat user's first incoming message either
reuses the existing binding or auto-creates a new conversation +
binding entry.

Per-turn flow:

1. ``auto_bind(platform, user_id)`` → ``conv_id``
2. Load the persisted conversation (meta + messages) off disk.
3. Render history as a ``[User]: ...`` / ``[Assistant]: ...`` prefix
   (bounded by MAX_HISTORY_CHARS) and hand it plus the new user text
   to ``rt.exec``.
4. Append the user message + reply to messages, save, and poke any
   running Web UI so browser tabs see the update live.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from openprogram.webui import persistence as _persist
from openprogram.channels import bindings as _bindings


# Keep the history prefix bounded so a long-running WeChat thread
# doesn't silently blow past the model's context window. The webui
# uses its own limit (_MAX_CONTEXT_CHARS ≈ 200k) — we mirror the
# approximate intent with a smaller cap since channels tend to turn
# more chat-style back-and-forth.
MAX_HISTORY_CHARS = 60_000


def turn_with_history(platform: str, user_id: str, user_text: str, rt,
                      *, user_display: str | None = None) -> str:
    """Run one turn with persistent history.

    Resolves the (platform, user_id) to a conversation via the bindings
    table — creating one on first contact. Loads the conversation,
    appends the user's message, builds a ``[User]: ... [Assistant]:``
    prefix from the recent history, calls ``rt.exec``, appends the
    reply, and saves. Returns the assistant text.

    ``user_display`` is a human-readable label — WeChat nickname,
    Telegram @handle, etc. Only used for the conversation title shown
    in the Web UI list; the prompt itself always says ``[User]:``.
    """
    display = user_display or user_id
    conv_id = _bindings.auto_bind(platform, user_id, user_display=display)
    meta, messages = _load_or_init(conv_id, platform, display)

    user_msg_id = uuid.uuid4().hex[:12]
    messages.append({
        "role": "user",
        "id": user_msg_id,
        "parent_id": messages[-1]["id"] if messages else None,
        "content": user_text,
        "timestamp": time.time(),
        "source": platform,
    })

    history_prefix = _render_history(messages[:-1])
    exec_content = []
    if history_prefix:
        exec_content.append({"type": "text", "text": history_prefix})
    exec_content.append({"type": "text", "text": user_text})

    try:
        reply = rt.exec(content=exec_content)
        reply_text = str(reply or "").strip() or "(empty reply)"
    except Exception as e:  # noqa: BLE001
        reply_text = f"[error] {type(e).__name__}: {e}"

    messages.append({
        "role": "assistant",
        "id": user_msg_id + "_reply",
        "parent_id": user_msg_id,
        "content": reply_text,
        "timestamp": time.time(),
        "source": platform,
    })

    meta["head_id"] = messages[-1]["id"]
    meta["_last_touched"] = time.time()
    _persist.save_meta(conv_id, meta)
    _persist.save_messages(conv_id, messages)

    # Best-effort: if webui is running in this process, patch its
    # in-memory conversation dict so the UI shows the new messages
    # on its next render pass (e.g. page reload). Live WebSocket
    # push is a follow-up — for now a browser refresh surfaces the
    # turn.
    _poke_live_webui(conv_id, messages, meta)

    return reply_text


def _load_or_init(conv_id: str, platform: str,
                  user_display: str) -> tuple[dict, list[dict]]:
    """Load persisted meta+messages or build fresh structures.

    ``persistence.load_conversation`` returns a flat dict with meta
    fields + ``messages`` + ``function_trees``. We split messages out
    and treat the rest as meta.
    """
    data = _persist.load_conversation(conv_id)
    if data:
        messages = list(data.get("messages", []))
        # Drop the non-meta keys so we can round-trip through save_meta
        # without bloating meta.json with messages / function_trees.
        meta = {k: v for k, v in data.items()
                if k not in ("messages", "function_trees")}
        if meta:
            return meta, messages

    meta = {
        "id": conv_id,
        "title": f"{platform}: {user_display}",
        "provider_name": None,
        "model": None,
        "session_id": None,
        "created_at": time.time(),
        # Tag so webui can group / filter / decorate these.
        "source": platform,
        "channel_user_display": user_display,
        "head_id": None,
        "context_tree": None,
        "_titled": True,
        "_last_touched": time.time(),
    }
    return meta, []


def _render_history(messages: list[dict]) -> str:
    """Render message list as the ``[User]: ...`` prefix webui uses.

    Walks backwards to prioritize recent turns when we hit the char
    budget, then re-reverses so the prompt reads oldest-first (the
    order humans and models expect).
    """
    if not messages:
        return ""
    parts: list[str] = []
    total = 0
    for m in reversed(messages):
        role = m.get("role", "")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            entry = f"[User]: {content}"
        elif role == "assistant":
            entry = f"[Assistant]: {content}"
        else:
            continue
        if total + len(entry) > MAX_HISTORY_CHARS:
            break
        parts.append(entry)
        total += len(entry)
    parts.reverse()
    if not parts:
        return ""
    return (
        "── Conversation history ──\n"
        + "\n".join(parts)
        + "\n── End of history ──\n\n"
    )


def _poke_live_webui(conv_id: str, messages: list[dict], meta: dict) -> None:
    """Patch the running webui's in-memory conversation and push live
    WebSocket updates to any browser tabs.

    Noop when webui isn't imported (CLI chat only, or pure
    ``channels start``) — the on-disk save has already happened, so
    the conversation will appear when the user next opens the Web UI.

    Two events are emitted for connected clients:

    * ``conversations_list`` if the conversation is new to the
      in-memory dict — so the sidebar gets the new entry without a
      page reload.
    * ``conversation_reload`` for this conv_id — the frontend only
      reacts if the user is currently viewing it, in which case it
      asks the server to re-send the conversation data. Cheap and
      prevents us from having to re-implement the frontend's message
      merge logic here.
    """
    import json
    try:
        import sys
        srv = sys.modules.get("openprogram.webui.server")
        if srv is None:
            return
    except Exception:
        return

    was_new = False
    try:
        with srv._conversations_lock:
            conv = srv._conversations.get(conv_id)
            if conv is None:
                was_new = True
                from openprogram.agentic_programming.context import Context
                conv = {
                    "id": conv_id,
                    "title": meta.get("title", conv_id),
                    "root_context": Context(name="chat_session", status="idle",
                                             start_time=time.time()),
                    "runtime": None,
                    "provider_name": meta.get("provider_name"),
                    "messages": list(messages),
                    "function_trees": [],
                    "created_at": meta.get("created_at"),
                    "head_id": meta.get("head_id"),
                    "run_active": False,
                    "source": meta.get("source"),
                }
                srv._conversations[conv_id] = conv
            else:
                conv["messages"] = list(messages)
                conv["head_id"] = meta.get("head_id")
    except Exception:
        return

    try:
        if was_new:
            # Rebuild the full sidebar list the same shape the normal
            # `list_conversations` action returns, so clients pick it
            # up through the existing dispatcher. Include the binding
            # entry so the sidebar can show a "WeChat: alice"-style
            # badge the moment the conversation appears.
            conv_list = []
            with srv._conversations_lock:
                for cid, c in srv._conversations.items():
                    runtime = c.get("runtime")
                    sid = getattr(runtime, "_session_id", None) if runtime else None
                    binding = _bindings.get_binding_for_conv(cid)
                    conv_list.append({
                        "id": cid,
                        "title": c.get("title", "Untitled"),
                        "created_at": c.get("created_at"),
                        "has_session": sid is not None,
                        "binding": binding,
                    })
            conv_list.sort(key=lambda c: c.get("created_at") or 0)
            srv._broadcast(json.dumps(
                {"type": "conversations_list", "data": conv_list},
                default=str,
            ))
        srv._broadcast(json.dumps(
            {"type": "conversation_reload", "data": {"conv_id": conv_id}},
            default=str,
        ))
    except Exception:
        pass
