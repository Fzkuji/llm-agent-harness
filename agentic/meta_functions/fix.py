"""
fix() — Analyze and rewrite an existing function based on errors and instructions.
"""

from __future__ import annotations

from agentic.function import agentic_function
from agentic.runtime import Runtime
from agentic.meta_functions._helpers import (
    extract_code, validate_code, compile_function,
    save_function, get_source, get_error_log,
    generate_code,
)


@agentic_function(input={
    "fn": {
        "description": "Function name to fix",
        "placeholder": "e.g. sentiment",
        "multiline": False,
    },
    "runtime": {"hidden": True},
    "instruction": {
        "description": "What to fix or change",
        "placeholder": "e.g. handle empty input gracefully",
        "multiline": True,
    },
    "name": {
        "description": "Rename the fixed function",
        "placeholder": "e.g. sentiment_v2",
        "multiline": False,
    },
    "max_rounds": {
        "description": "Max retry rounds",
        "options": ["3", "5", "10"],
    },
})
def fix(
    fn,
    runtime: Runtime,
    instruction: str = None,
    name: str = None,
    max_rounds: int = 5,
):
    """Fix a broken function based on its code, errors, and optional instruction.

    Calls generate_code() in a loop until valid code is produced,
    a follow_up question is raised, or max_rounds is exhausted.

    Args:
        fn: The function to fix.
        runtime: Runtime instance for LLM calls.
        instruction: Optional manual instruction ("change X to Y").
        name: Optional name override.
        max_rounds: Maximum rounds (default 5).

    Returns:
        callable — the fixed function, or
        dict — {"type": "follow_up", "question": "..."} if LLM needs more info.
    """
    description = getattr(fn, '__doc__', '') or getattr(fn, '__name__', 'unknown')
    code = get_source(fn)
    error_log = get_error_log(fn)
    fn_name = name or getattr(fn, '__name__', 'fixed')

    data_parts = [f"Current code:\n```python\n{code}\n```"]
    if error_log:
        data_parts.append(f"Error log:\n{error_log}")
    if instruction:
        data_parts.append(f"Instruction: {instruction}")

    for round_num in range(max_rounds):
        task = "\n\n".join(data_parts)
        task += (
            "\n\nFix the root cause, not just the symptom. "
            "If the error is a format mismatch, make the format explicit in the docstring. "
            "If it's a type error, add validation. "
            "Respond with ONLY the fixed Python code in a ```python fence."
        )

        result = generate_code(task=task, runtime=runtime)

        if result.get("type") == "follow_up":
            return result

        response = result["content"]
        fixed_code = extract_code(response)
        save_function(fixed_code, fn_name, f"Fixed: {description}")
        validate_code(fixed_code, response)
        return compile_function(fixed_code, runtime, fn_name)

    raise RuntimeError(f"fix() exceeded max_rounds ({max_rounds}) without producing valid code.")
