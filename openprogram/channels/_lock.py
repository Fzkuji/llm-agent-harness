"""Single-holder file lock for the channels runner.

Multiple `openprogram` / `openprogram web` / `openprogram channels start`
processes can easily be running at once (different terminals, the
user's experimenting, etc.). Each of them used to spin up its own
Telegram / Discord / WeChat poll loop — meaning N processes racing to
pull the same updates, and the user had no way to predict which
process would answer a given incoming message.

This module gates that: the first process to acquire the lock owns the
channels for as long as it's alive; every other process sees the lock
held and skips channel startup, with the holder PID surfaced so the
user can `kill $pid` or just switch to that terminal.

Lock path: ``<state-dir>/channels.lock`` (routed through
``openprogram.paths.get_state_dir`` so --profile isolates correctly).

Uses ``fcntl.flock`` — works on macOS and Linux. Windows users who
want multi-session gating would need a fallback, but Windows isn't
the main target yet.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import IO, Optional


class ChannelsLock:
    """Exclusive file lock held by the process that owns channels.

    Typical use::

        lock = ChannelsLock()
        if lock.try_acquire():
            # we own channels; start_all() and join on shutdown
            try:
                ...
            finally:
                lock.release()
        else:
            # another process has it — skip
            print(f"channels owned by PID {lock.holder_pid}")
    """

    def __init__(self) -> None:
        from openprogram.paths import get_state_dir
        self.path: Path = get_state_dir() / "channels.lock"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: Optional[IO[str]] = None
        self.holder_pid: Optional[int] = None

    def try_acquire(self) -> bool:
        """Try non-blocking lock acquisition.

        Returns True iff we got it. On False, ``self.holder_pid`` is
        populated with the PID written into the lock file by the
        holding process (best effort — may be None if the file is
        empty or unparseable).
        """
        fh = open(self.path, "a+")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.seek(0)
            raw = fh.read().strip()
            try:
                self.holder_pid = int(raw) if raw else None
            except ValueError:
                self.holder_pid = None
            fh.close()
            return False

        # Got the lock — write our PID so other processes can surface
        # it to the user. Truncate first because `a+` starts at the
        # end of the file.
        fh.seek(0)
        fh.truncate()
        fh.write(f"{os.getpid()}\n")
        fh.flush()
        os.fsync(fh.fileno())
        self._fh = fh
        self.holder_pid = os.getpid()
        return True

    def release(self) -> None:
        """Release the lock if held. Safe to call multiple times.

        Truncates the PID file content too — otherwise ``read_holder_pid``
        on the next launch would see the PID of the now-dead prior
        process and mistakenly report it as "still holding" the lock.
        (The actual fcntl lock is already released by flock UN or by
        process exit, but peek-style callers that read the file
        without touching flock need the content cleared.)
        """
        if self._fh is None:
            return
        try:
            self._fh.seek(0)
            self._fh.truncate()
            self._fh.flush()
        except OSError:
            pass
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            self._fh.close()
        except OSError:
            pass
        self._fh = None


def read_holder_pid() -> Optional[int]:
    """Peek at the current lock holder without trying to acquire.

    Useful for banners that want to show "channels owned by PID N" when
    we're not the owner. Returns None if the file is missing, empty,
    or unparseable.
    """
    from openprogram.paths import get_state_dir
    path = get_state_dir() / "channels.lock"
    if not path.exists():
        return None
    try:
        raw = path.read_text().strip()
        return int(raw) if raw else None
    except (OSError, ValueError):
        return None
