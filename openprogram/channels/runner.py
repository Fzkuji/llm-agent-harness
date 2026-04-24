"""Foreground runner that fires up every enabled channel."""
from __future__ import annotations

import threading
import time

from openprogram.channels import (
    build_channel,
    list_channels_status,
    list_enabled_platforms,
)


def run_all() -> int:
    """Start bot loops for every enabled channel; wait for Ctrl+C."""
    status = list_channels_status()
    enabled = [r["platform"] for r in status if r["enabled"]]
    if not enabled:
        print("No channels enabled. Configure with "
              "`openprogram config channels`.")
        return 1

    stop = threading.Event()
    threads: list[tuple[str, threading.Thread]] = []

    for pid in enabled:
        row = next((r for r in status if r["platform"] == pid), {})
        if not row.get("implemented"):
            print(f"[{pid}] runtime not implemented yet; skipped.")
            continue
        if not row.get("configured"):
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
