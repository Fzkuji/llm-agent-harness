"""
fix() — Analyze and rewrite an existing function based on errors and instructions.
"""

from __future__ import annotations

from typing import Callable

from agentic.function import agentic_function
from agentic.runtime import Runtime
from agentic.meta_functions._helpers import (
    extract_code, validate_code, compile_function,
    save_function, get_source, get_error_log,
    generate_code,
)


@agentic_function
def fix(
    fn,
    runtime: Runtime,
    instruction: str = None,
    name: str = None,
    on_question: Callable[[str], str] = None,
    max_rounds: int = 5,
) -> callable:
    """Fix a broken function based on its code, errors, and optional instruction.

    Calls generate_code() in a loop until valid code is produced or
    max_rounds is exhausted. Each round is a separate generate_code() call,
    so there is no need for runtime._call() workarounds.

    Args:
        fn: The function to fix.
        runtime: Runtime instance for LLM calls.
        instruction: Optional manual instruction ("change X to Y").
        name: Optional name override.
        on_question: Callback for interactive fixing. fn(question) -> answer.
        max_rounds: Maximum interaction rounds (default 5).

    Returns:
        A new callable function with fixes applied.
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

    extra_context = ""
    for round_num in range(max_rounds):
        task = "\n\n".join(data_parts)
        if extra_context:
            task += extra_context
        task += (
            "\n\nFix the root cause, not just the symptom. "
            "If the error is a format mismatch, make the format explicit in the docstring. "
            "If it's a type error, add validation. "
            "Respond with ONLY the fixed Python code in a ```python fence. "
            "If unsure, respond with ONLY 'QUESTION: <your question>'."
        )

        response = generate_code(task=task, runtime=runtime)

        if response.strip().startswith("QUESTION:"):
            question = response.strip()[len("QUESTION:"):].strip()
            if on_question is None:
                extra_context += "\nNote: You cannot ask questions. Produce the fixed code directly.\n"
                continue
            answer = on_question(question)
            extra_context += f"\nQ: {question}\nA: {answer}\n"
            continue

        fixed_code = extract_code(response)
        save_function(fixed_code, fn_name, f"Fixed: {description}")
        validate_code(fixed_code, response)
        return compile_function(fixed_code, runtime, fn_name)

    raise RuntimeError(f"fix() exceeded max_rounds ({max_rounds}) without producing valid code.")
