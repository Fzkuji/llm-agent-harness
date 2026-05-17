"""_retry_choice — internal helper used by parse_args to ask the LLM to
re-pick an option after the previous reply failed to parse / validate.

The function is wrapped in ``@agentic_function`` so the retry call is
traced in the DAG like any other LLM-driven step.
"""

from __future__ import annotations

from openprogram.agentic_programming.function import agentic_function
from openprogram.agentic_programming.runtime import Runtime


@agentic_function
def _retry_choice(prev_reply: str, error_msg: str, menu: str, runtime: Runtime) -> str:
    """Ask the LLM to re-pick a menu option after a failed parse."""
    return runtime.exec(content=[
        {"type": "text", "text": (
            f"Previous reply:\n{prev_reply[:500]}\n\n"
            f"Problem: {error_msg}\n\n"
            f"Options:\n{menu}\n\n"
            "Your previous reply failed to parse or validate. Re-pick an "
            "option from the list above, fixing the problem described. "
            "Reply with valid JSON in the format shown in that option's "
            "Call: example line — JSON only, no prose."
        )},
    ])
