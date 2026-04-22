"""mixture_of_agents tool."""

from .mixture_of_agents import DESCRIPTION, NAME, SPEC, _tool_check_fn, execute

TOOL = {
    "spec": SPEC,
    "execute": execute,
    "check_fn": _tool_check_fn,
    "max_result_size_chars": 80_000,
}

__all__ = ["NAME", "SPEC", "TOOL", "execute", "DESCRIPTION"]
