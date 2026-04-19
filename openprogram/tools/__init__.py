"""Tool registry.

Each tool lives under openprogram/tools/<name>/ with at minimum:
    <name>/__init__.py exporting TOOL = {"spec": {...}, "execute": callable}

Registration is lazy — import only the tools you pass to runtime.exec_with_tools.
"""

from __future__ import annotations

from typing import Any

from .bash import TOOL as BASH


ALL_TOOLS: dict[str, dict[str, Any]] = {
    "bash": BASH,
}


def get(name: str) -> dict[str, Any]:
    """Look up a tool record by name. Raises KeyError if not registered."""
    return ALL_TOOLS[name]


def get_many(names: list[str]) -> list[dict[str, Any]]:
    """Look up several tools. Use this when passing to exec_with_tools."""
    return [get(n) for n in names]


__all__ = ["ALL_TOOLS", "BASH", "get", "get_many"]
