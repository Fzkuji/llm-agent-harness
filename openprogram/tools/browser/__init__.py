"""browser tool."""

from .browser import DESCRIPTION, NAME, SPEC, check_playwright, execute

TOOL = {
    "spec": SPEC,
    "execute": execute,
    "check_fn": check_playwright,
    "max_result_size_chars": 60_000,
}

__all__ = ["NAME", "SPEC", "TOOL", "execute", "DESCRIPTION", "check_playwright"]
