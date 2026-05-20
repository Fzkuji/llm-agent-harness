"""Prompt text for the bash tool (description shown to the LLM).

Condensed from Claude Code's src/tools/BashTool/prompt.ts (leaked source,
reference-only) — we keep only the instructions that matter without a tool
catalogue, permission system, or sandbox. Callers are free to override.
"""

from __future__ import annotations

DEFAULT_MAX_TIMEOUT_MS = 10 * 60 * 1000   # 10 min
DEFAULT_TIMEOUT_MS = 2 * 60 * 1000        # 2 min

DESCRIPTION = (
    "Execute a bash command and return its stdout, stderr, and exit code.\n"
    "\n"
    "The working directory persists between commands in the same session, but "
    "shell state (exported variables, aliases) does not. The shell environment "
    "is initialized from the user's profile (bash or zsh).\n"
    "\n"
    "Guidelines:\n"
    "- Quote paths that contain spaces with double quotes (e.g. cd \"my dir\").\n"
    "- Prefer absolute paths over cd'ing around.\n"
    "- For independent commands that can run in parallel, emit multiple tool "
    "calls in one turn. For commands that must run in order, chain them with "
    "&& in a single call.\n"
    "- Use ';' only when you do not care whether earlier commands fail.\n"
    "- Do NOT use newlines to separate commands (newlines are fine inside quoted strings).\n"
    "- Avoid unnecessary sleep commands; if you need to wait for a process, "
    "poll with a check command.\n"
    "- For git operations, prefer creating new commits rather than amending. "
    "Never skip hooks (--no-verify) unless explicitly asked.\n"
)
