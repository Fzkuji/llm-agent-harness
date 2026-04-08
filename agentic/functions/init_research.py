"""init_research — create a minimal research project folder structure."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def init_research(name: str, venue: Optional[str] = None, base_dir: str | None = None) -> str:
    """
    Initialize a research project directory and a few common subfolders.

    This helper is intentionally small and dependency-free so `agentic` can
    import it safely even in lightweight environments like test collection.
    """
    base = Path(base_dir or ".").expanduser()
    project_name = venue and f"{name}-{venue}" or name
    project_dir = base / project_name

    for child in (project_dir, project_dir / "notes", project_dir / "sources", project_dir / "drafts"):
        child.mkdir(parents=True, exist_ok=True)

    return str(project_dir)
