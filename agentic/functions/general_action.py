"""
general_action — an agentic function that gives the LLM full freedom.

Structured agentic functions (observe, click, etc.) control WHAT the LLM
does. general_action is the opposite: you give it an instruction, and the
agent decides how to complete it — running commands, editing files, browsing,
installing packages, or anything else available.

Usage:
    from agentic import create_runtime
    from agentic.general_action import general_action

    runtime = create_runtime()

    result = general_action(
        instruction="Install numpy and verify it imports correctly",
        runtime=runtime,
    )
    # result: {"success": True, "output": "...", "error": None}
"""

from __future__ import annotations

from agentic.function import agentic_function
from agentic.runtime import Runtime
from agentic.functions._utils import parse_json


_MISSING_RUNTIME = object()


@agentic_function(summarize={"depth": 0, "siblings": 0}, input={
    "instruction": {
        "description": "Task to complete",
        "placeholder": "e.g. Install numpy and verify it imports",
        "multiline": True,
    },
    "runtime": {"hidden": True},
})
def general_action(instruction: str, runtime: Runtime = _MISSING_RUNTIME) -> dict:
    """Execute a task using any available tools.

    You are given a specific task to complete. You have full freedom
    to use any tools and methods available to you:
    - Run shell commands (bash)
    - Read and write files
    - Browse the web
    - Install packages
    - Anything else you need

    Complete the task and report the result.

    Return JSON:
    {
      "success": true/false,
      "output": "what you did and the result",
      "error": null or "error description"
    }
    """
    if runtime is _MISSING_RUNTIME or runtime is None:
        raise ValueError("runtime is required for general_action()")

    reply = runtime.exec(content=[
        {"type": "text", "text": (
            f"Task: {instruction}\n\n"
            "Complete this task. Return JSON with success/output/error."
        )},
    ])

    try:
        return parse_json(reply)
    except ValueError:
        return {"success": True, "output": reply[:500], "error": None}
