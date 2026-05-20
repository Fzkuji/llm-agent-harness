"""clarify function — pause the agent and ask the user a question.

Thin wrapper over the existing ``ask_user`` infrastructure in
``openprogram.functions.agentics.ask_user``, which handles:
  * WebUI ↔ backend round-trip via registered global handler
  * TTY fallback using ``input()``
  * "no handler anywhere" graceful None return
  * DAG persistence (records the Q&A as a user-role Call)

We surface it as a plain function so any @agentic_function can ask the
user without the caller having to import ask_user directly. Useful for
disambiguation ("did you mean X or Y?") and gating side-effects ("about
to delete 500 rows — proceed?").
"""

from __future__ import annotations

from typing import Any

from ..._helpers import read_string_param
from ..._runtime import function


NAME = "clarify"

DESCRIPTION = (
    "Ask the user a follow-up question and pause until they answer. "
    "Returns the user's response as a string. Returns an error if no "
    "handler is available (e.g. running in a non-interactive batch job "
    "with no WebUI)."
)


# Hand-rolled parameter schema kept verbatim so the LLM sees the exact
# same input contract it has been trained against — the auto-derived
# version from the signature alone wouldn't carry the description and
# would mis-mark the question as optional (it has a default of None).
_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": "The question to show the user.",
        },
    },
    "required": ["question"],
}


@function(
    name=NAME,
    description=DESCRIPTION,
    parameters=_PARAMETERS,
    toolset=["core"],
    max_result_chars=10_000,
)
def clarify(question: str | None = None, **kw: Any) -> str:
    question = question or read_string_param(kw, "question", "prompt", "text")
    if not question:
        return "Error: `question` is required."

    # Lazy import so the function registry loads even when the programs
    # package hasn't been imported yet.
    try:
        from openprogram.functions.agentics.ask_user import ask_user
    except ImportError as e:
        return f"Error: ask_user infrastructure not available: {e}"

    answer = ask_user(question)
    if answer is None:
        return (
            "Error: no ask_user handler is registered and stdin is not a TTY. "
            "Register a handler (webui does this automatically) or run "
            "interactively."
        )
    return str(answer)


# Legacy export kept for the brief window where `SPEC` may still be
# imported by external scripts. New code should consume the AgentTool
# from the registry (``openprogram.functions.get_agent_tool("clarify")``).
SPEC: dict[str, Any] = {
    "name": NAME,
    "description": DESCRIPTION,
    "parameters": _PARAMETERS,
}


__all__ = ["NAME", "SPEC", "DESCRIPTION", "clarify"]
