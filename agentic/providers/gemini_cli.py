"""
Gemini CLI provider — routes LLM calls through the Gemini CLI.

Uses `gemini -p` (prompt mode) which uses your Google account login.
No API key needed.

Usage:
    from agentic.providers.gemini_cli import GeminiCLIRuntime

    runtime = GeminiCLIRuntime()

    @agentic_function
    def observe(task):
        return runtime.exec(content=[
            {"type": "text", "text": f"Find: {task}"},
        ])
"""

from __future__ import annotations

import subprocess
import shutil
import warnings
from typing import Optional

from agentic.runtime import Runtime


class GeminiCLIRuntime(Runtime):
    """
    Runtime that routes LLM calls through the Gemini CLI.

    Requires `gemini` CLI to be installed and logged in.
    Uses Google account (no separate API key needed).

    Args:
        model:      Model to use (default: None = CLI default).
        timeout:    Max seconds per CLI call (default: 120).
        cli_path:   Path to gemini CLI binary (auto-detected if not specified).
        sandbox:    Run in sandbox mode (default: False).
        yolo:       Auto-approve all actions (default: True for non-interactive).
    """

    def __init__(
        self,
        model: str = None,
        timeout: int = 120,
        cli_path: str = None,
        sandbox: bool = False,
        yolo: bool = True,
    ):
        super().__init__(model=model or "default")
        self.timeout = timeout
        self.cli_path = cli_path or shutil.which("gemini")
        self.sandbox = sandbox
        self.yolo = yolo
        if self.cli_path is None:
            raise FileNotFoundError(
                "Gemini CLI not found. Install it first:\n"
                "  npm install -g @anthropic-ai/gemini-cli\n"
                "Then log in:\n"
                "  gemini"
            )

    def _call(self, content: list[dict], model: str = "default", response_format: dict = None) -> str:
        """Call Gemini CLI with the content list."""
        # Build prompt from content blocks
        parts = []
        has_unsupported = False
        for block in content:
            if block["type"] == "text":
                parts.append(block["text"])
            elif block["type"] == "image":
                warnings.warn(
                    "GeminiCLIRuntime: image blocks not supported in CLI mode, "
                    "passing as text placeholder. Use GeminiRuntime (API) for image support.",
                    UserWarning,
                    stacklevel=2,
                )
                parts.append(f"[Image: {block.get('path', block.get('url', 'unknown'))}]")
            elif block["type"] in ("audio", "video", "file"):
                warnings.warn(
                    f"GeminiCLIRuntime: '{block['type']}' blocks not supported in CLI mode. "
                    f"Use GeminiRuntime (API) for full multimodal support.",
                    UserWarning,
                    stacklevel=2,
                )
                parts.append(f"[{block['type'].title()}: {block.get('path', 'unknown')}]")

        prompt = "\n".join(parts)

        if response_format:
            import json
            prompt += f"\n\nRespond with ONLY valid JSON matching this schema: {json.dumps(response_format)}"

        # Build command
        cmd = [self.cli_path, "-p", prompt]

        if model and model != "default":
            cmd.extend(["-m", model])
        if self.sandbox:
            cmd.append("-s")
        if self.yolo:
            cmd.append("-y")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Gemini CLI timed out after {self.timeout}s")

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            raise RuntimeError(f"Gemini CLI error (exit {result.returncode}): {error_msg}")

        return result.stdout.strip()
