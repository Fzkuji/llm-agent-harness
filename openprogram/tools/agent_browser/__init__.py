"""LLM-friendly browser tool driven by the npm `agent-browser` package.

Sister tool to ``openprogram.tools.browser`` (the Playwright-direct one).
This one delegates to ``npx agent-browser`` so the ariaSnapshot + ref-ID
abstraction (``@e1`` ``@e2`` element ids) lands in the LLM's hands
without us reimplementing it.
"""

from .agent_browser import (
    NAME, SPEC, DESCRIPTION, execute, check_agent_browser,
)

TOOL = {
    "spec": SPEC,
    "execute": execute,
    "check_fn": check_agent_browser,
    "max_result_size_chars": 60_000,
}

__all__ = ["NAME", "SPEC", "TOOL", "DESCRIPTION", "execute", "check_agent_browser"]
