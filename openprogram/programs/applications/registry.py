"""Explicit registry of agentic-function applications.

The applications directory used to be auto-scanned for ``main.py`` —
which also walked into ``.venv`` folders and picked up dozens of false
positives. That is gone: only apps listed here are discovered, loaded,
and shown in the UI.

To expose a new app, add the path to its ``main.py`` (the file holding
the top-level ``@agentic_function``), relative to this directory.
"""

import os

APP_MAIN_FILES: list[str] = [
    "GUI-Agent-Harness/gui_harness/main.py",
    "Research-Agent-Harness/research_harness/main.py",
    "Wiki-Agent-Harness/wiki_agent_harness/main.py",
]

_BASE = os.path.dirname(os.path.abspath(__file__))


def iter_app_main_files():
    """Yield absolute ``main.py`` paths for registered apps.

    Entries whose file is missing are skipped so a stale registry line
    cannot crash discovery.
    """
    for rel in APP_MAIN_FILES:
        path = os.path.join(_BASE, *rel.split("/"))
        if os.path.isfile(path):
            yield path
