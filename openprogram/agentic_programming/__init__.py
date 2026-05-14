"""
openprogram.agentic_programming — core engine.

Two primitives:

    1. @agentic_function  — turn a Python function into one that can call an LLM
    2. Runtime            — base class for an LLM-call runtime

Execution traces are persisted as a flat DAG in
``openprogram.context.storage`` (SQLite). Older revisions kept a
parallel in-memory ``Context`` tree + a JSONL trace + an event pubsub
layer; those have all been retired in favour of the DAG.

Zero downstream dependencies: providers / programs / webui depend on
agentic_programming, never the other way around.
"""

from openprogram.agentic_programming.function import (
    agentic_function, traced, auto_trace_module, auto_trace_package,
)
from openprogram.agentic_programming.runtime import Runtime
from openprogram.agentic_programming.session import Session
from openprogram.agentic_programming.skills import (
    Skill, load_skills, format_skills_for_prompt, default_skill_dirs,
)

__all__ = [
    "agentic_function",
    "traced",
    "auto_trace_module",
    "auto_trace_package",
    "Runtime",
    "Session",
    "Skill",
    "load_skills",
    "format_skills_for_prompt",
    "default_skill_dirs",
]
