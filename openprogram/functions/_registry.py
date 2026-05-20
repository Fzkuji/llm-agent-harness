"""Explicit registry of @agentic_function modules to import on package load.

The single role of this file is to drive what gets imported when
``openprogram.functions.agentics`` is loaded: the decorators inside
those modules fire as side effects, populating the shared AgentTool
registry (``_runtime._registry``).

What's *exposed* to LLMs (Layer 2 of the selection cascade) is a
separate concern — that lives in ``TOOLSETS["full"]["tools"]`` in
``openprogram.functions.__init__``. Membership in this AGENTIC_MODULES
list says "load this module so its decorators run"; membership in
``TOOLSETS["full"]["tools"]`` says "let LLMs see this name". A module
can be loaded without all of its decorated functions being exposed —
that's how private @agentic_function helpers (like ``_pick_stage``)
stay internal-only.

Each entry is ``(module_name, file_override)``:

  - ``module_name`` becomes the last segment of the Python module path
    (``openprogram.functions.agentics.<module_name>``).
  - ``file_override`` is ``None`` for standard layouts (the module
    lives at ``agentics/<module_name>.py`` or
    ``agentics/<module_name>/__init__.py``); otherwise it's a path
    relative to ``agentics/`` pointing at a Python file we load under
    the chosen ``module_name`` via ``importlib.util.spec_from_file_location``.
    Used for the three harness apps whose external directories have
    hyphen names that can't be imported as Python modules.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from typing import Iterator, Optional


AGENTIC_MODULES: list[tuple[str, Optional[str]]] = [
    # Framework primitives
    ("ask_user", None),
    ("deep_work", None),
    # Domain functions
    ("word_count", None),
    ("extract_pdf_figures", None),
    ("extract_pdf_tables", None),
    ("llm_call_example", None),
    ("test_framework", None),
    ("test_resume", None),
    # Harness apps — hyphen-named external dirs, load via file path
    # so the resulting Python module name is clean (no double-naming).
    ("gui_agent_harness",
     "GUI-Agent-Harness/gui_harness/main.py"),
    ("research_agent_harness",
     "Research-Agent-Harness/research_harness/main.py"),
    ("wiki_agent_harness",
     "Wiki-Agent-Harness/wiki_agent_harness/main.py"),
]


def load_agentic_modules(agentics_dir: str) -> None:
    """Import every module listed in AGENTIC_MODULES.

    Standard entries (``file_override is None``) are imported by their
    Python module name. Override entries are loaded via
    ``importlib.util.spec_from_file_location`` so an external harness
    living under a hyphen-named directory still gets a clean Python
    module path (``openprogram.functions.agentics.gui_agent_harness``
    instead of one that includes the hyphen-named outer dir).

    Failures are swallowed per-entry so a missing external harness
    symlink (e.g. on a fresh clone without the side repos) doesn't
    kill the whole import. Successful entries still get registered.
    """
    for mod_name, file_override in AGENTIC_MODULES:
        try:
            if file_override is None:
                importlib.import_module(
                    f"openprogram.functions.agentics.{mod_name}"
                )
            else:
                _load_external_file(agentics_dir, mod_name, file_override)
        except Exception as e:
            # Silently skip per-entry so a missing/broken external
            # harness symlink (e.g. cold clone without the side repos)
            # doesn't poison the whole package import. Set the
            # ``OPENPROGRAM_DEBUG_REGISTRY`` env var to surface
            # swallowed errors when debugging registration failures.
            import os as _os
            if _os.environ.get("OPENPROGRAM_DEBUG_REGISTRY"):
                import traceback
                print(f"[registry] failed to load {mod_name}: "
                      f"{type(e).__name__}: {e}")
                traceback.print_exc()
            continue


def _load_external_file(
    agentics_dir: str, mod_name: str, rel_path: str
) -> None:
    """Load ``agentics/<rel_path>`` as the module
    ``openprogram.functions.agentics.<mod_name>``.

    The harness's parent dir is prepended to ``sys.path`` so internal
    imports like ``from gui_harness.constants import X`` still resolve
    inside the loaded file. The harness's own ``main.py`` already does
    a ``sys.path.insert`` dance at the top of the file for the same
    reason; we mirror that so the file behaves identically whether
    invoked as ``python main.py`` or loaded through this path.
    """
    abs_path = os.path.join(agentics_dir, rel_path)
    if not os.path.isfile(abs_path):
        return  # external project not present on this machine

    inner_pkg_dir = os.path.dirname(abs_path)
    sys_path_root = os.path.dirname(inner_pkg_dir)
    if sys_path_root not in sys.path:
        sys.path.insert(0, sys_path_root)

    full_mod = f"openprogram.functions.agentics.{mod_name}"
    spec = importlib.util.spec_from_file_location(full_mod, abs_path)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    # Install BEFORE exec_module so any self-referential imports
    # inside the file can find the partially-loaded module in
    # sys.modules.
    sys.modules[full_mod] = module
    spec.loader.exec_module(module)


def iter_agentic_files(agentics_dir: str) -> Iterator[tuple[str, str, bool]]:
    """Yield ``(module_name, file_path, is_harness)`` for every entry
    in AGENTIC_MODULES whose file exists on disk.

    Used by the webui's function browser and the CLI's
    ``programs list`` command to enumerate agentic functions without
    each consumer re-implementing the AGENTIC_MODULES walk.

    - ``module_name`` is the dotted segment under
      ``openprogram.functions.agentics`` (e.g. ``"ask_user"``,
      ``"gui_agent_harness"``).
    - ``file_path`` is the absolute path to the ``.py`` file the
      decorators live in.
    - ``is_harness`` is True for entries with a file override (the
      three external harness apps).

    Entries whose file is missing on this machine (dangling external
    harness symlink) are silently skipped.
    """
    for mod_name, file_override in AGENTIC_MODULES:
        if file_override is None:
            simple = os.path.join(agentics_dir, f"{mod_name}.py")
            pkg = os.path.join(agentics_dir, mod_name, "__init__.py")
            if os.path.isfile(simple):
                yield mod_name, simple, False
            elif os.path.isfile(pkg):
                yield mod_name, pkg, False
        else:
            abs_path = os.path.join(agentics_dir, file_override)
            if os.path.isfile(abs_path):
                yield mod_name, abs_path, True
