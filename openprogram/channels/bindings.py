"""Conversation ↔ (platform, external user) bindings.

Design context: previously we hard-coded ``conv_id = f"{platform}_{user_id}"``
which made conversation IDs and channel user IDs the same thing. That
breaks every interesting workflow: you can't start a conversation in
the Web UI and later route WeChat messages into it, you can't detach
a channel from a conversation without losing history, and the same
WeChat user is forever bound to the same thread.

Model:

    Conversation (conv_id, uuid)   <-- first-class; has its own history
        ↕ optional 1:1 binding
    Channel User (platform, external_user_id)

The binding table is the source of truth. A message coming in from a
channel looks up the binding to find the target conversation (creating
one if there isn't one yet). When the user talks back from the Web UI
inside a bound conversation, outbound messages are routed to the same
channel user. Detach severs the link cleanly; reattaching to a
different conversation just rewrites the table.

Storage: ``<state>/channel_bindings.json``. Writes are serialized
with fcntl.flock across processes (the worker daemon and the Web UI
server both touch it). Reads use the in-memory cache and only re-read
the file when another writer bumps its mtime.
"""
from __future__ import annotations

import fcntl
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional


_schema_version = 1


class _BindingsStore:
    """Process-wide singleton that owns the bindings table.

    Not intended to be instantiated directly — grab the module-level
    :data:`_store` via the public accessors below.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, dict[str, Any]] = {}
        self._mtime: float = 0.0
        self._path: Optional[Path] = None
        self._loaded = False

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _ensure_path(self) -> Path:
        if self._path is not None:
            return self._path
        from openprogram.paths import get_state_dir
        root = get_state_dir()
        root.mkdir(parents=True, exist_ok=True)
        self._path = root / "channel_bindings.json"
        return self._path

    # ------------------------------------------------------------------
    # Disk I/O — must hold self._lock
    # ------------------------------------------------------------------

    def _load_from_disk_locked(self) -> None:
        path = self._ensure_path()
        if not path.exists():
            self._data = {}
            self._mtime = 0.0
            self._loaded = True
            return
        try:
            raw = path.read_text(encoding="utf-8")
            parsed = json.loads(raw) if raw.strip() else {}
        except (OSError, json.JSONDecodeError):
            parsed = {}
        self._data = _normalize_loaded(parsed)
        try:
            self._mtime = path.stat().st_mtime
        except OSError:
            self._mtime = 0.0
        self._loaded = True

    def _maybe_reload_locked(self) -> None:
        """If another process wrote the file, pick up its changes."""
        if not self._loaded:
            self._load_from_disk_locked()
            return
        path = self._ensure_path()
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            # File was removed by something else — treat as empty.
            self._data = {}
            self._mtime = 0.0
            return
        if mtime > self._mtime:
            self._load_from_disk_locked()

    def _write_locked(self) -> None:
        """Write self._data atomically (tmp + rename) under fcntl lock.

        Uses a separate lock file so we don't have to hold a writer
        across the rename step.
        """
        path = self._ensure_path()
        lock_path = path.with_suffix(path.suffix + ".lock")
        with open(lock_path, "a+") as lock_fh:
            try:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
            except OSError:
                pass
            # Snapshot for writing; use the schema envelope.
            payload = {
                "v": _schema_version,
                "bindings": dict(self._data),
            }
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True),
                           encoding="utf-8")
            os.replace(tmp, path)
            try:
                self._mtime = path.stat().st_mtime
            except OSError:
                self._mtime = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_conv_for(self, platform: str, user_id: str) -> Optional[str]:
        """Return the conv_id currently bound to (platform, user_id), or None."""
        key = _key(platform, user_id)
        with self._lock:
            self._maybe_reload_locked()
            entry = self._data.get(key)
            return entry["conv_id"] if entry else None

    def get_binding_for_conv(self, conv_id: str) -> Optional[dict[str, Any]]:
        """Inverse lookup: what channel user is this conv bound to?

        Returns ``{"platform": ..., "user_id": ..., "user_display": ...,
        "created_at": ...}`` or None if the conversation has no binding.
        """
        with self._lock:
            self._maybe_reload_locked()
            for key, entry in self._data.items():
                if entry["conv_id"] == conv_id:
                    return dict(entry)
        return None

    def list_all(self) -> list[dict[str, Any]]:
        """All bindings as a list of dicts, sorted by creation time."""
        with self._lock:
            self._maybe_reload_locked()
            items = list(self._data.values())
        items.sort(key=lambda e: e.get("created_at") or 0)
        return [dict(e) for e in items]

    def attach(self, platform: str, user_id: str, conv_id: str,
               user_display: str = "") -> Optional[dict[str, Any]]:
        """Bind (platform, user_id) → conv_id. Replaces any prior binding
        for that (platform, user_id) *and* detaches whatever else might
        have been mapped to conv_id (one conversation, one channel user).

        Returns the previous entry that was displaced, if any — so the
        caller can tell the user "you've just replaced the old binding
        on conversation X".
        """
        with self._lock:
            self._maybe_reload_locked()
            displaced: Optional[dict[str, Any]] = None
            key = _key(platform, user_id)
            if key in self._data:
                displaced = dict(self._data[key])
            # Remove any other binding that currently points at conv_id.
            for k in list(self._data.keys()):
                if k == key:
                    continue
                if self._data[k]["conv_id"] == conv_id:
                    # Only keep one "latest displaced" to report back;
                    # prefer the same-key one if both exist.
                    if displaced is None:
                        displaced = dict(self._data[k])
                    self._data.pop(k, None)
            self._data[key] = {
                "platform": platform,
                "user_id": user_id,
                "conv_id": conv_id,
                "user_display": user_display or user_id,
                "created_at": time.time(),
            }
            self._write_locked()
            return displaced

    def detach(self, *, conv_id: Optional[str] = None,
               platform: Optional[str] = None,
               user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Remove a binding.

        Accepts either a conv_id (removes whatever binding targets that
        conversation) or a (platform, user_id) pair. Returns the entry
        that was removed, or None if there wasn't one.
        """
        if conv_id is None and (platform is None or user_id is None):
            raise TypeError("detach needs either conv_id= or "
                            "(platform=, user_id=)")
        with self._lock:
            self._maybe_reload_locked()
            if conv_id is not None:
                for k, entry in list(self._data.items()):
                    if entry["conv_id"] == conv_id:
                        removed = dict(entry)
                        self._data.pop(k, None)
                        self._write_locked()
                        return removed
                return None
            # (platform, user_id) form
            key = _key(platform, user_id)  # type: ignore[arg-type]
            removed = self._data.pop(key, None)
            if removed is not None:
                self._write_locked()
                return dict(removed)
            return None

    def auto_bind(self, platform: str, user_id: str,
                  user_display: str = "") -> str:
        """The "inbound" helper.

        If (platform, user_id) is already bound, returns that conv_id.
        Otherwise creates a fresh conv_id (UUID, no leaky platform
        prefix), writes the binding, and returns the new id. Callers —
        typically a channel's _handle_message — use this to route a
        message to the right conversation without having to know
        whether it's a first-time contact.

        Also best-effort refreshes user_display if the caller passed a
        friendlier string than what we had stored.
        """
        with self._lock:
            self._maybe_reload_locked()
            key = _key(platform, user_id)
            entry = self._data.get(key)
            if entry is not None:
                if user_display and entry.get("user_display") != user_display:
                    entry["user_display"] = user_display
                    self._write_locked()
                return entry["conv_id"]
            conv_id = f"conv_{uuid.uuid4().hex[:12]}"
            self._data[key] = {
                "platform": platform,
                "user_id": user_id,
                "conv_id": conv_id,
                "user_display": user_display or user_id,
                "created_at": time.time(),
            }
            self._write_locked()
            return conv_id


_store = _BindingsStore()


# --------------------------------------------------------------------------
# Module-level convenience API — these are what the rest of the codebase
# should call. The class exists mainly for locking / test isolation.
# --------------------------------------------------------------------------

def get_conv_for(platform: str, user_id: str) -> Optional[str]:
    return _store.get_conv_for(platform, user_id)


def get_binding_for_conv(conv_id: str) -> Optional[dict[str, Any]]:
    return _store.get_binding_for_conv(conv_id)


def list_all() -> list[dict[str, Any]]:
    return _store.list_all()


def attach(platform: str, user_id: str, conv_id: str,
           user_display: str = "") -> Optional[dict[str, Any]]:
    return _store.attach(platform, user_id, conv_id, user_display)


def detach(*, conv_id: Optional[str] = None,
           platform: Optional[str] = None,
           user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    return _store.detach(conv_id=conv_id, platform=platform, user_id=user_id)


def auto_bind(platform: str, user_id: str, user_display: str = "") -> str:
    return _store.auto_bind(platform, user_id, user_display)


# --------------------------------------------------------------------------
# One-time migration: older builds used conv_id = "{platform}_{user_id}"
# directly — those histories exist on disk as sessions/<platform>_<user>/.
# Migrate them into bindings pointing at that same conv_id (don't rename
# the dir — the conv_id is a random-looking string anyway, and renaming
# would break anyone still referencing the old id in URLs).
# --------------------------------------------------------------------------

_migrated = False
_migrate_lock = threading.Lock()


def migrate_legacy_if_needed() -> int:
    """Scan sessions/ for old ``<platform>_<user_id>`` conversations and
    populate bindings for any that aren't yet there. Safe to call many
    times; only touches each id once per process.

    Returns the number of new bindings written.
    """
    global _migrated
    with _migrate_lock:
        if _migrated:
            return 0
        from openprogram.webui import persistence as _persist
        from openprogram.channels import CHANNEL_CLASSES
        platforms = set(CHANNEL_CLASSES.keys())
        added = 0
        try:
            for conv_id in _persist.list_conversations():
                if "_" not in conv_id:
                    continue
                platform, _, user_id = conv_id.partition("_")
                if platform not in platforms or not user_id:
                    continue
                if _store.get_binding_for_conv(conv_id):
                    continue
                # The legacy id encoded the user id in the conv id, so
                # recover it with the same path-safety normalization the
                # old code used.
                _store.attach(platform, user_id, conv_id,
                              user_display=user_id)
                added += 1
        except Exception:
            pass
        _migrated = True
        return added


# --------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------

def _key(platform: str, user_id: str) -> str:
    """Consistent map key. Separator is ``\\x01`` so it can't collide
    with any real platform or user id character."""
    return f"{platform}\x01{user_id}"


def _normalize_loaded(parsed: Any) -> dict[str, dict[str, Any]]:
    """Rehydrate from on-disk JSON into the in-memory shape.

    The on-disk envelope is ``{"v": N, "bindings": {...}}`` — the
    ``bindings`` values map key strings to entries. Also tolerates a
    bare-dict legacy layout for forward compatibility.
    """
    if not isinstance(parsed, dict):
        return {}
    bindings_blob = parsed.get("bindings") if "bindings" in parsed else parsed
    if not isinstance(bindings_blob, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, raw in bindings_blob.items():
        if not isinstance(raw, dict):
            continue
        platform = raw.get("platform") or ""
        user_id = raw.get("user_id") or ""
        conv_id = raw.get("conv_id") or ""
        if not platform or not user_id or not conv_id:
            continue
        out[_key(platform, user_id)] = {
            "platform": platform,
            "user_id": user_id,
            "conv_id": conv_id,
            "user_display": raw.get("user_display") or user_id,
            "created_at": raw.get("created_at") or 0.0,
        }
    return out


__all__ = [
    "get_conv_for",
    "get_binding_for_conv",
    "list_all",
    "attach",
    "detach",
    "auto_bind",
    "migrate_legacy_if_needed",
]
