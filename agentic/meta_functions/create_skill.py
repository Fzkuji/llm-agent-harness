"""
create_skill() — Generate a SKILL.md for agent discovery from a function.
"""

from __future__ import annotations

import os

from agentic.function import agentic_function
from agentic.runtime import Runtime


@agentic_function(input={
    "fn_name": {
        "description": "Function name",
        "placeholder": "e.g. sentiment",
        "multiline": False,
    },
    "description": {
        "description": "What the function does",
        "placeholder": "e.g. Analyze text sentiment",
        "multiline": True,
    },
    "code": {
        "description": "Function source code",
        "placeholder": "def sentiment(text: str): ...",
        "multiline": True,
    },
    "runtime": {"hidden": True},
})
def create_skill(fn_name: str, description: str, code: str, runtime: Runtime) -> str:
    """Write a SKILL.md for an OpenClaw skill based on the given function.

    Design pattern: ONE skill, ONE entry function.

    A project should have a single SKILL.md at the top level, pointing to
    a single @agentic_function entry point (e.g. `main` or the project name).
    That entry function's docstring lists ALL available sub-functions and
    capabilities. The LLM reads the docstring and decides what to call.

    This pattern works because:
    - The agent only needs to discover ONE skill to access everything.
    - The entry function's docstring serves as a complete menu/guide.
    - Sub-functions are implementation details, not separate skills.
    - Adding new capabilities = updating the docstring, not creating new skills.

    Example structure:
        SKILL.md              → triggers: "research", "write paper", etc.
                                 usage: /research "<task>"
        project/main.py       → @agentic_function research(task, runtime)
                                 docstring lists all 45+ sub-functions
        project/stages/...    → individual @agentic_function files

    The SKILL.md must follow this exact format:
    ---
    name: <fn_name>
    description: "<one-line for agent discovery, include trigger words>"
    ---
    # <Title>
    ## Usage
    /name "<task description>"
    ## Available Functions
    <Brief list of capabilities the entry function can dispatch to>

    Rules:
    - Description must include trigger words (when should an agent use this?).
    - SKILL.md should guide the agent to call the single entry function.
    - The entry function's docstring handles the rest (what to do, how).
    - Keep concise — agents read this every message.
    - Write ONLY the SKILL.md content, no explanation.

    Args:
        fn_name:      Function name.
        description:  What the function does.
        code:         Function source code.
        runtime:      Runtime for LLM calls.

    Returns:
        Path to the created SKILL.md.
    """
    response = runtime.exec(content=[
        {"type": "text", "text": f"Function: {fn_name}\nSource:\n```python\n{code}\n```"},
    ])

    # Extract content (strip markdown fences if any)
    skill_content = response.strip()
    if skill_content.startswith("```"):
        lines = skill_content.split("\n")
        skill_content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    skill_dir = os.path.join(repo_root, "skills", fn_name)
    os.makedirs(skill_dir, exist_ok=True)

    filepath = os.path.join(skill_dir, "SKILL.md")
    with open(filepath, "w") as f:
        f.write(skill_content)

    return filepath
