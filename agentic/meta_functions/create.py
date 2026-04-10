"""
create() — Generate a single @agentic_function from a natural language description.
"""

from __future__ import annotations

from agentic.function import agentic_function
from agentic.runtime import Runtime
from agentic.meta_functions._helpers import (
    extract_code, validate_code, compile_function,
    save_function, save_skill_template, guess_name,
    generate_code,
)


@agentic_function
def create(description: str, runtime: Runtime, name: str = None, as_skill: bool = False) -> callable:
    """Create a new Python function from a natural language description.

    Calls generate_code() with the design specification, then extracts,
    validates, compiles, and saves the generated code.

    Args:
        description: What the function should do.
        runtime: Runtime instance for LLM calls.
        name: Optional name override.
        as_skill: If True, also create a SKILL.md for agent discovery.

    Returns:
        A callable function.
    """
    task = (
        f"Write a Python function that does the following:\n\n"
        f"{description}\n\n"
        f"Respond with ONLY the Python code inside a ```python code fence. "
        f"No explanation, no commentary, no markdown outside the fence."
    )
    response = generate_code(task=task, runtime=runtime)

    code = extract_code(response)
    fn_name = name or guess_name(code) or "generated"

    save_function(code, fn_name, description)
    if as_skill:
        save_skill_template(fn_name, description, code)
    validate_code(code, response)
    return compile_function(code, runtime, name)
