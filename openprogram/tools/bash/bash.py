"""bash tool — run a shell command, return stdout/stderr/exit code.

Layout mirrors Claude Code's src/tools/BashTool/. Protocol pieces split
across files to stay close to the reference:
    prompt.py   — the description the LLM sees
    bash.py     — SPEC + execute()
    __init__.py — exports the tool record for the registry
"""

from __future__ import annotations

import subprocess
from typing import Any

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
    """Run `command` in a shell, return a plain-text result the LLM can read."""
    timeout_ms = min(timeout or DEFAULT_TIMEOUT_MS, DEFAULT_MAX_TIMEOUT_MS)
    timeout_sec = timeout_ms / 1000.0
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as e:
        partial_stdout = (e.stdout or "").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        partial_stderr = (e.stderr or "").decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return (
            f"[timeout after {timeout_sec:.1f}s]\n"
            f"--- stdout (partial) ---\n{partial_stdout}\n"
            f"--- stderr (partial) ---\n{partial_stderr}"
        )

    parts = [f"exit_code={proc.returncode}"]
    if proc.stdout:
        parts.append(f"--- stdout ---\n{proc.stdout.rstrip()}")
    if proc.stderr:
        parts.append(f"--- stderr ---\n{proc.stderr.rstrip()}")
    return "\n".join(parts)
