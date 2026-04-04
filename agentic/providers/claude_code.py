"""
Claude Code CLI provider — routes LLM calls through the Claude Code CLI.

Uses `claude -p` (print mode) which is covered by Claude Code subscription.
No API key needed — uses the logged-in Claude Code session.

Usage:
    from agentic.providers.claude_code import ClaudeCodeRuntime

    runtime = ClaudeCodeRuntime(model="sonnet")

    @agentic_function
    def observe(task):
        return runtime.exec(content=[
            {"type": "text", "text": f"Find: {task}"},
        ])
"""

from __future__ import annotations

import subprocess
import json
import shutil
from typing import Optional

from agentic.runtime import Runtime


class ClaudeCodeRuntime(Runtime):
    """
    Runtime that routes LLM calls through the Claude Code CLI.

    Requires `claude` CLI to be installed and logged in.
    Uses Claude Code subscription (no separate API key needed).

    Args:
        model:      Model to use (default: "sonnet"). Passed to --model flag.
        timeout:    Max seconds per CLI call (default: 120).
        cli_path:   Path to claude CLI binary (auto-detected if not specified).
    """

    def __init__(self, model: str = "sonnet", timeout: int = 120, cli_path: str = None):
        super().__init__(model=model)
        self.timeout = timeout
        self.cli_path = cli_path or shutil.which("claude")
        if self.cli_path is None:
            raise FileNotFoundError(
                "Claude Code CLI not found. Install it first:\n"
                "  npm install -g @anthropic-ai/claude-code\n"
                "Then log in:\n"
                "  claude login"
            )

    def _call(self, content: list[dict], model: str = "sonnet", response_format: dict = None) -> str:
        """Call Claude Code CLI with the content list."""
        # Build prompt from content blocks
        parts = []
        for block in content:
            if block["type"] == "text":
                parts.append(block["text"])
            elif block["type"] == "image":
                parts.append(f"[Image: {block.get('path', 'unknown')}]")
            elif block["type"] == "audio":
                parts.append(f"[Audio: {block.get('path', 'unknown')}]")
            elif block["type"] == "file":
                parts.append(f"[File: {block.get('path', 'unknown')}]")

        prompt = "\n".join(parts)

        # Add response format instruction if needed
        if response_format:
            prompt += f"\n\nRespond with ONLY valid JSON matching this schema: {json.dumps(response_format)}"

        # Call CLI
        cmd = [self.cli_path, "-p"]
        if model and model != "sonnet":
            cmd.extend(["--model", model])
        cmd.append(prompt)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Claude Code CLI timed out after {self.timeout}s")

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            if "Not logged in" in error_msg or "login" in error_msg.lower():
                raise ConnectionError(
                    f"Claude Code CLI not logged in. Run: claude login\n"
                    f"Error: {error_msg}"
                )
            raise RuntimeError(f"Claude Code CLI error (exit {result.returncode}): {error_msg}")

        return result.stdout.strip()
