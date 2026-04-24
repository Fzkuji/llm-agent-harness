"""bash tool — run a shell command, return stdout/stderr/exit code.

Layout mirrors Claude Code's src/tools/BashTool/. Protocol pieces split
across files to stay close to the reference:
    prompt.py   — the description the LLM sees
    bash.py     — SPEC + execute()
    __init__.py — exports the tool record for the registry
"""

from __future__ import annotations

from typing import Any

from openprogram.backend import get_active_backend

from .prompt import DEFAULT_MAX_TIMEOUT_MS, DEFAULT_TIMEOUT_MS, DESCRIPTION


NAME = "bash"

SPEC: dict[str, Any] = {
    "name": NAME,
    "description": DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "timeout": {
                "type": "number",
                "description": (
                    f"Optional timeout in milliseconds "
                    f"(default {DEFAULT_TIMEOUT_MS}, max {DEFAULT_MAX_TIMEOUT_MS})."
                ),
            },
            "description": {
                "type": "string",
                "description": (
                    "Short active-voice description of what the command does "
                    "(e.g. 'List files in cwd'). For display only."
                ),
            },
        },
        "required": ["command"],
    },
}


def execute(command: str, timeout: float | None = None, description: str | None = None, **_ignored: Any) -> str:
    """Run `command` via the active backend, return a plain-text result.

    Backend is resolved per-call (local / docker / ssh) so switching
    via `openprogram config backend` takes effect immediately, and
    --profile isolation flows through correctly.
    """
    timeout_ms = min(timeout or DEFAULT_TIMEOUT_MS, DEFAULT_MAX_TIMEOUT_MS)
    timeout_sec = timeout_ms / 1000.0

    backend = get_active_backend()
    result = backend.run(command, timeout=timeout_sec)

    if result.timed_out:
        return (
            f"[timeout after {timeout_sec:.1f}s via {backend.backend_id}]\n"
            f"--- stdout (partial) ---\n{result.stdout}\n"
            f"--- stderr (partial) ---\n{result.stderr}"
        )

    parts = [f"exit_code={result.exit_code}"]
    if backend.backend_id != "local":
        parts[0] += f" (backend={backend.backend_id})"
    if result.stdout:
        parts.append(f"--- stdout ---\n{result.stdout.rstrip()}")
    if result.stderr:
        parts.append(f"--- stderr ---\n{result.stderr.rstrip()}")
    return "\n".join(parts)
