"""canvas tool."""

from .canvas import DESCRIPTION, NAME, SPEC, execute

TOOL = {
    "spec": SPEC,
    "execute": execute,
    "max_result_size_chars": 80_000,
}

__all__ = ["NAME", "SPEC", "TOOL", "execute", "DESCRIPTION"]
