"""
Context 树的事件广播 —— 轻量级 pub/sub。

这不是范式原语，是工程性设施：WebUI 靠它实时流式展示 Context 树的变化。
引擎不强依赖 —— 没有订阅者时零开销（emit 自己先检查 list 长度）。
"""

from __future__ import annotations

import threading
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from openprogram.agentic_programming.context import Context


_event_callbacks: list[Callable] = []
_event_lock = threading.Lock()


def on_event(callback: Callable) -> None:
    """
    注册一个 Context 树事件的回调。

    callback 接收 (event_type: str, data: dict)，event_type ∈
    {"node_created", "node_updated", "node_completed"}。

    线程安全。没有订阅者时 _emit_event 会提前返回，零成本。
    """
    with _event_lock:
        _event_callbacks.append(callback)


def off_event(callback: Callable) -> None:
    """注销一个 on_event 注册的回调。"""
    with _event_lock:
        try:
            _event_callbacks.remove(callback)
        except ValueError:
            pass


def _emit_event(event_type: str, ctx: "Context") -> None:
    """给所有订阅者发事件。没有订阅者时零开销。"""
    if not _event_callbacks:
        return
    try:
        data = ctx._to_dict()
        data["event"] = event_type
    except Exception:
        return
    with _event_lock:
        cbs = list(_event_callbacks)
    for cb in cbs:
        try:
            cb(event_type, data)
        except Exception:
            pass
