"""@agentic_function bodies — composable LLM-aware functions and harnesses.

Modules under this package register their ``@agentic_function`` entries
via the decorator's side effect when imported. The list of modules to
import is driven by :data:`openprogram.functions._registry.AGENTIC_MODULES`
(NOT by walking the directory) — explicit beats implicit.

Hyphen-named external harness directories (the three ``-Agent-Harness``
symlinks) are loaded via ``importlib.util.spec_from_file_location`` under
clean Python module names like ``gui_agent_harness``, so the resulting
import paths don't carry the hyphen-name double-nesting.
"""
import os as _os

from .._registry import load_agentic_modules as _load_agentic_modules

_load_agentic_modules(_os.path.dirname(__file__))

del _os, _load_agentic_modules
