"""Anthropic provider — API (Messages) and CLI (Claude Code) backends.

Both live under one provider dir, matching openclaw's convention where
``extensions/anthropic/`` hosts ``cli-backend.ts`` alongside the API
plugin. The shared ``CliRunner`` drives the CLI path via
``CLAUDE_CODE_PLUGIN``; the API path stays as before.
"""
from .anthropic import stream_simple
from .cli_backend import CLAUDE_CODE_CONFIG, CLAUDE_CODE_PLUGIN
from .cli_runtime import ClaudeCodeRuntime

__all__ = [
    "stream_simple",
    "CLAUDE_CODE_CONFIG",
    "CLAUDE_CODE_PLUGIN",
    "ClaudeCodeRuntime",
]
