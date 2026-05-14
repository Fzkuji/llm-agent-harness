"""
Per-session persistence.

Sessions belong to agents. Persistence is now SQLite-only — the
per-conversation meta + message list lives in SessionDB; the DAG
itself (function-call nodes / model-call nodes / user nodes) is
written by the regular runtime path into the same SessionDB.

Every function here takes ``agent_id`` as the first argument so the
caller is always explicit about which agent's store it's touching.
``resolve_agent_for_conv`` scans every agent's record to find the
owner of an existing session key when the caller didn't stash it.
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Optional


def _sessions_root(agent_id: str) -> Path:
    from openprogram.agents.manager import sessions_dir
    return sessions_dir(agent_id)


def sessions_root(agent_id: str) -> Path:
    """Public alias."""
    return _sessions_root(agent_id)


def conv_dir(agent_id: str, session_id: str) -> Path:
    return _sessions_root(agent_id) / session_id


def resolve_agent_for_conv(session_id: str) -> Optional[str]:
    """Which agent's sessions dir contains ``session_id``? None if
    nobody. Small O(agent_count) scan — fine for UI lookups.
    """
    try:
        from openprogram.agents.manager import list_all
        for spec in list_all():
            if (_sessions_root(spec.id) / session_id).is_dir():
                return spec.id
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Locking — per-conversation so unrelated writes don't serialize each other.
# ---------------------------------------------------------------------------

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_key(agent_id: str, session_id: str) -> str:
    return f"{agent_id}/{session_id}"


def _lock_for(agent_id: str, session_id: str) -> threading.Lock:
    key = _lock_key(agent_id, session_id)
    with _locks_guard:
        lk = _locks.get(key)
        if lk is None:
            lk = threading.Lock()
            _locks[key] = lk
        return lk


def _ensure_conv_dir(agent_id: str, session_id: str) -> Path:
    d = conv_dir(agent_id, session_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Meta + messages (low-frequency, whole-file overwrite)
# ---------------------------------------------------------------------------

def save_meta(agent_id: str, session_id: str, meta: dict) -> None:
    """Persist conversation metadata into SessionDB."""
    from openprogram.agent.session_db import default_db
    _ensure_conv_dir(agent_id, session_id)
    db = default_db()
    meta_fields = dict(meta)
    meta_fields.pop("id", None)
    meta_fields.pop("agent_id", None)
    # `session_id` in meta is the LLM runtime's session identifier, not
    # the SessionDB primary key. Rename it before forwarding so the
    # **kwargs expansion doesn't collide with update_session's first
    # positional parameter (also called `session_id`).
    if "session_id" in meta_fields:
        meta_fields["llm_session_id"] = meta_fields.pop("session_id")
    if db.get_session(session_id) is None:
        db.create_session(session_id, agent_id, **meta_fields)
    else:
        db.update_session(session_id, agent_id=agent_id, **meta_fields)


def save_messages(agent_id: str, session_id: str, messages: list) -> None:
    """Sync the message log to SessionDB. Skips messages whose ids are
    already persisted, so callers can keep passing the full in-memory
    list without rewriting the whole transcript every turn."""
    from openprogram.agent.session_db import default_db
    _ensure_conv_dir(agent_id, session_id)
    db = default_db()
    if db.get_session(session_id) is None:
        db.create_session(session_id, agent_id)
    existing_ids = {m["id"] for m in db.get_messages(session_id)}
    new_msgs = [m for m in messages if m.get("id") and m["id"] not in existing_ids]
    if new_msgs:
        db.append_messages(session_id, new_msgs)


def save_conversation(agent_id: str, session_id: str,
                      meta: dict, messages: list) -> None:
    """Save both meta and messages in one call."""
    save_meta(agent_id, session_id, meta)
    save_messages(agent_id, session_id, messages)


# ---------------------------------------------------------------------------
# Whole-conversation I/O
# ---------------------------------------------------------------------------

def list_sessions(agent_id: str = "") -> list[tuple[str, str]]:
    """Return ``[(agent_id, session_id), ...]`` across SessionDB.

    With ``agent_id`` empty (default) we list every agent; otherwise
    just that agent.
    """
    from openprogram.agent.session_db import default_db
    db = default_db()
    rows = db.list_sessions(agent_id=agent_id or None, limit=10_000)
    return [(r["agent_id"], r["id"]) for r in rows]


def load_session(agent_id: str, session_id: str) -> Optional[dict]:
    """Return the conversation state dict (meta + messages).

    Reads SessionDB for meta + messages. Function-tree visualisation
    now reads the DAG directly off the same database via the regular
    GraphStore APIs — no separate JSONL store.
    """
    from openprogram.agent.session_db import default_db
    db = default_db()
    sess = db.get_session(session_id)
    if sess is None:
        return None
    if sess.get("agent_id") != agent_id:
        return None

    messages = db.get_messages(session_id)
    result = dict(sess)
    result["id"] = session_id
    result["agent_id"] = agent_id
    result["messages"] = messages
    return result


def delete_session(agent_id: str, session_id: str) -> None:
    from openprogram.agent.session_db import default_db
    default_db().delete_session(session_id)
    d = conv_dir(agent_id, session_id)
    if d.is_dir():
        shutil.rmtree(d)
    with _locks_guard:
        _locks.pop(_lock_key(agent_id, session_id), None)


# The legacy-file migration shim is retired — fresh installs never had
# a visualizer_sessions.json, and users who used to have one were
# already migrated before this refactor.

def migrate_legacy_file() -> int:
    return 0
