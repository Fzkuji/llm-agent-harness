"""Skill discovery and prompt formatting.

A *skill* is a directory containing ``SKILL.md`` with YAML-style front matter
declaring ``name`` + ``description``. The body is free-form markdown that
the LLM reads (via the ``read`` tool) when the description matches the
task at hand. Optional sibling files (scripts, references, data) live next
to SKILL.md and are run through the existing ``bash`` / ``execute_code``
tools — skills themselves do not execute anything.

Mechanism (mirrors OpenClaw's agent skills, simplified):

  1. ``load_skills(dirs)`` scans each dir for ``<slug>/SKILL.md``, parses
     the front matter, returns ``[Skill(name, description, file_path, base_dir)]``.
  2. ``format_skills_for_prompt(skills)`` renders an ``<available_skills>``
     XML block to append to the system prompt — name + one-line description
     + absolute path so the LLM can ``read`` it just-in-time.
  3. The LLM decides whether to load; we don't auto-inject full bodies.

We intentionally reuse ``read`` rather than adding a dedicated ``skill``
tool — the lookup machinery adds zero surface area to the tool registry.

Credit: the XML layout tracks OpenClaw's ``formatSkillsForPrompt`` byte-for-
byte so transcripts stay comparable; see
``references/openclaw/src/agents/skills/skill-contract.ts``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Skill:
    """Parsed SKILL.md metadata + location."""
    name: str
    description: str
    file_path: str   # absolute path to SKILL.md — what the LLM should `read`
    base_dir: str    # parent dir — for resolving relative `scripts/foo.sh`

    @property
    def slug(self) -> str:
        return os.path.basename(self.base_dir)


_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# Deliberately permissive YAML subset: `key: value` or `key: "value"`. Skills
# have always used this shape in practice; a full YAML dep isn't justified.
_KV_RE = re.compile(r"""^\s*([A-Za-z_][A-Za-z0-9_\-]*)\s*:\s*(.*?)\s*$""")


def _parse_front_matter(text: str) -> dict[str, str] | None:
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return None
    out: dict[str, str] = {}
    for raw_line in m.group(1).splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith("#"):
            continue
        km = _KV_RE.match(line)
        if not km:
            continue
        key, value = km.group(1), km.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def _load_one(skill_md_path: Path) -> Skill | None:
    try:
        text = skill_md_path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm = _parse_front_matter(text)
    if not fm:
        return None
    name = (fm.get("name") or "").strip()
    description = (fm.get("description") or "").strip()
    if not name or not description:
        return None
    return Skill(
        name=name,
        description=description,
        file_path=str(skill_md_path.resolve()),
        base_dir=str(skill_md_path.parent.resolve()),
    )


def load_skills(dirs: Iterable[str | os.PathLike[str]]) -> list[Skill]:
    """Scan each directory for ``<slug>/SKILL.md`` and return parsed skills.

    Missing directories are silently skipped — callers pass a list of
    candidate locations (repo skills, user skills, plugin skills) and we
    don't want a missing opt-in dir to blow up the runtime.
    Skills are deduplicated by ``name``; first-seen wins, matching how
    Python imports resolve with PYTHONPATH. Ordering of ``dirs`` therefore
    defines override precedence.
    """
    seen: dict[str, Skill] = {}
    for d in dirs:
        root = Path(d)
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                continue
            sk = _load_one(skill_md)
            if sk and sk.name not in seen:
                seen[sk.name] = sk
    return list(seen.values())


def _escape_xml(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&apos;")
    )


def format_skills_for_prompt(skills: list[Skill]) -> str:
    """Render an ``<available_skills>`` XML block for the system prompt.

    Empty input returns ``""`` so callers can unconditionally concatenate.
    """
    if not skills:
        return ""
    lines = [
        "",
        "",
        "The following skills provide specialized instructions for specific tasks.",
        "Use the read tool to load a skill's file when the task matches its description.",
        "When a skill file references a relative path, resolve it against the skill "
        "directory (parent of SKILL.md) and use that absolute path in tool commands.",
        "",
        "<available_skills>",
    ]
    for sk in skills:
        lines.append("  <skill>")
        lines.append(f"    <name>{_escape_xml(sk.name)}</name>")
        lines.append(f"    <description>{_escape_xml(sk.description)}</description>")
        lines.append(f"    <location>{_escape_xml(sk.file_path)}</location>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)


def default_skill_dirs() -> list[str]:
    """Locations the runtime will probe when the caller doesn't override.

    Order defines precedence: user skills override repo skills.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    return [
        os.path.expanduser("~/.openprogram/skills"),
        str(repo_root / "skills"),
    ]


__all__ = [
    "Skill",
    "load_skills",
    "format_skills_for_prompt",
    "default_skill_dirs",
]
