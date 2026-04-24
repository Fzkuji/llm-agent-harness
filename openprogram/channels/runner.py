"""Runner for chat-channel bots.

Two entry points:

    run_all()  —  blocking. Used by `openprogram channels start`.
                   Starts every enabled+configured channel in a daemon
                   thread, waits for Ctrl-C, then shuts them down.

    start_all() — non-blocking. Used by `openprogram` (CLI chat) and
                   the Web UI to co-host channels alongside the main
                   REPL/server. Returns (stop_event, threads). Caller
                   sets `stop_event` and joins threads on shutdown.
"""
from __future__ import annotations

import threading
import time

from openprogram.channels import (
    build_channel,
    list_channels_status,
    list_enabled_platforms,
)


def start_all(*, quiet: bool = False) -> tuple[threading.Event,
                                                list[tuple[str, threading.Thread]]]:
    """Kick off every enabled+configured channel in a daemon thread.

    Non-blocking — returns immediately with the stop event and thread
    list. Caller is responsible for driving shutdown (``stop.set()``
    then join the threads).

    ``quiet=True`` suppresses the "[pid] enabled but token missing"
    warnings so the CLI chat doesn't dump noise about half-configured
    channels on every launch.
    """
    status = list_channels_status()
    stop = threading.Event()
    threads: list[tuple[str, threading.Thread]] = []

    for row in status:
        if not row.get("enabled"):
            continue
        pid = row["platform"]
        if not row.get("implemented"):
            if not quiet:
                print(f"[{pid}] runtime not implemented yet; skipped.")
            continue
        if not row.get("configured"):
            if not quiet:
                print(f"[{pid}] enabled but token missing "
                      f"(${row.get('env')}); skipped.")
            continue
        try:
            ch = build_channel(pid)
            if ch is None:
                continue
        except Exception as e:  # noqa: BLE001
            print(f"[{pid}] init failed: {type(e).__name__}: {e}")
            continue
        t = threading.Thread(target=_safe_run, args=(pid, ch, stop),
                             daemon=True, name=f"channel-{pid}")
        t.start()
        threads.append((pid, t))

    return stop, threads


def run_all() -> int:
    """Blocking — start every enabled channel and wait for Ctrl-C.

    Entry point for ``openprogram channels start``.
    """
    status = list_channels_status()
    enabled = [r["platform"] for r in status if r["enabled"]]
    if not enabled:
        print("No channels enabled. Configure with "
              "`openprogram config channels`.")
        return 1

    stop, threads = start_all(quiet=False)

    if not threads:
        print("No channel started.")
        return 1

    try:
        while any(t.is_alive() for _, t in threads):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[runner] stopping channels...")
        stop.set()
        for pid, t in threads:
            t.join(timeout=3)
            if t.is_alive():
                print(f"[{pid}] still running; it'll drop on process exit")
    return 0


def _safe_run(pid: str, channel, stop: threading.Event) -> None:
    try:
        channel.run(stop)
    except Exception as e:  # noqa: BLE001
        print(f"[{pid}] crashed: {type(e).__name__}: {e}")
