"""
meta_function — Generate and fix agentic functions from natural language.

Two primitives:
    create()  — LLM writes a new @agentic_function from a description
    fix()     — LLM analyzes errors and rewrites a broken function

Usage:
    from agentic import Runtime
    from agentic.meta_function import create, fix

    runtime = Runtime(call=my_llm, model="sonnet")

    # Create a function
    summarize = create("Summarize text into 3 bullet points", runtime=runtime)

    # If it fails, fix it
    fixed = fix(
        description="Summarize text into 3 bullet points",
        code=original_code,
        error_log="Attempt 1: ValueError: ...",
        runtime=runtime,
    )
"""

from __future__ import annotations

import re
from typing import Optional

from agentic.function import agentic_function
from agentic.runtime import Runtime


# ── Prompts ─────────────────────────────────────────────────────

_GENERATE_PROMPT = """\
Write a Python function that does the following:

{description}

Rules:
1. Decorate with @agentic_function
2. Write a clear docstring — this becomes the LLM prompt
3. Use runtime.exec() to call the LLM when reasoning is needed
4. Content is a list of dicts: [{{"type": "text", "text": "..."}}]
5. Return a meaningful result (string or dict)
6. Use only standard Python — no imports needed
7. Do NOT use async/await — write a normal synchronous function

`agentic_function` and `runtime` are already available in scope.

Write ONLY the function definition. No imports, no examples, no explanation.
Start with @agentic_function and end with the return statement.
"""

_FIX_PROMPT = """\
The following agentic function was generated but failed during execution.

Original description: {description}

Generated code:
```python
{code}
```

Error log:
{error_log}

Analyze the errors and rewrite the function to fix them.
Keep the same purpose but fix the logic that caused the failures.

Rules:
1. Decorate with @agentic_function
2. Write a clear docstring
3. Use runtime.exec() to call the LLM when reasoning is needed
4. Content is a list of dicts: [{{"type": "text", "text": "..."}}]
5. Return a meaningful result (string or dict)
6. Use only standard Python — no imports needed
7. Do NOT use async/await

`agentic_function` and `runtime` are already available in scope.

Write ONLY the fixed function definition. No imports, no explanation.
"""


# ── Safety ──────────────────────────────────────────────────────

_ALLOWED_BUILTINS = {
    "abs", "all", "any", "bool", "chr", "dict", "dir", "divmod",
    "enumerate", "filter", "float", "format", "frozenset", "hasattr",
    "hash", "hex", "id", "int", "isinstance", "issubclass", "iter",
    "len", "list", "map", "max", "min", "next", "oct", "ord", "pow",
    "print", "range", "repr", "reversed", "round", "set", "slice",
    "sorted", "str", "sum", "tuple", "type", "zip",
    "True", "False", "None", "ValueError", "TypeError", "KeyError",
    "IndexError", "RuntimeError", "Exception",
}


def _make_safe_builtins() -> dict:
    """Create a restricted builtins dict."""
    import builtins
    safe = {}
    for name in _ALLOWED_BUILTINS:
        if hasattr(builtins, name):
            safe[name] = getattr(builtins, name)
    safe["__import__"] = _blocked_import
    return safe


def _blocked_import(name, *args, **kwargs):
    raise ImportError(
        f"Import '{name}' is not allowed in generated functions. "
        f"Use runtime.exec() for any task that needs external libraries."
    )


# ── Internal helpers ────────────────────────────────────────────

def _extract_code(response: str) -> str:
    """Extract Python code from LLM response, stripping markdown fences."""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"(@agentic_function.*)", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return response.strip()


def _validate_code(code: str, response: str) -> None:
    """Validate generated code: no imports, no async, valid syntax."""
    for line in (response + "\n" + code).split("\n"):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            raise ValueError(
                f"Generated code contains import statements (not allowed):\n{code}"
            )
        if stripped.startswith("async def ") or stripped.startswith("async "):
            raise ValueError(
                f"Generated code uses async (not allowed, use sync functions):\n{code}"
            )
    try:
        compile(code, "<generated>", "exec")
    except SyntaxError as e:
        raise SyntaxError(
            f"Generated code has syntax errors:\n{code}\n\nError: {e}"
        ) from e


def _compile_function(code: str, runtime: Runtime, name: str = None) -> callable:
    """Execute code in sandbox and return the generated agentic_function."""
    namespace = {
        "__builtins__": _make_safe_builtins(),
        "agentic_function": agentic_function,
        "runtime": runtime,
    }
    try:
        exec(code, namespace)
    except Exception as e:
        raise ValueError(
            f"Generated code failed to execute:\n{code}\n\nError: {e}"
        ) from e

    fn = _find_function(namespace)
    if fn is None:
        raise ValueError(
            f"Generated code does not contain an @agentic_function:\n{code}"
        )
    if name:
        fn.__name__ = name
        fn.__qualname__ = name
    return fn


def _find_function(namespace: dict) -> Optional[callable]:
    """Find the generated agentic_function in the namespace."""
    for obj_name, obj in namespace.items():
        if obj_name.startswith("_"):
            continue
        if isinstance(obj, agentic_function):
            return obj
    return None


# ── Core: create() ──────────────────────────────────────────────

@agentic_function
def create(description: str, runtime: Runtime, name: str = None) -> callable:
    """Create a new @agentic_function from a natural language description.

    Args:
        description:  What the function should do.
        runtime:      Runtime instance for LLM calls.
        name:         Optional name override for the generated function.

    Returns:
        A callable @agentic_function ready to use.
    """
    response = runtime.exec(content=[
        {"type": "text", "text": _GENERATE_PROMPT.format(description=description)},
    ])
    code = _extract_code(response)
    _validate_code(code, response)
    return _compile_function(code, runtime, name)


# ── Core: fix() ─────────────────────────────────────────────────

@agentic_function
def fix(description: str, code: str, error_log: str, runtime: Runtime, name: str = None) -> callable:
    """Fix a broken @agentic_function by analyzing errors and rewriting.

    Called when a generated function fails repeatedly. Sends the original
    code and error log to the LLM, gets a rewritten version.

    Args:
        description:  Original task description.
        code:         The generated code that failed.
        error_log:    Error messages from failed attempts.
        runtime:      Runtime instance for LLM calls.
        name:         Optional name override.

    Returns:
        A new callable @agentic_function with fixes applied.
    """
    response = runtime.exec(content=[
        {"type": "text", "text": _FIX_PROMPT.format(
            description=description,
            code=code,
            error_log=error_log,
        )},
    ])
    fixed_code = _extract_code(response)
    _validate_code(fixed_code, response)
    return _compile_function(fixed_code, runtime, name)


# ── Core: run_with_fix() ───────────────────────────────────────────

@agentic_function
def run_with_fix(fn, args: dict, runtime: Runtime, description: str = None, code: str = None):
    """Execute a function with automatic error recovery via fix().

    Flow:
        1. Execute fn(**args)
        2. If it fails (after exec retries), call fix() to rewrite the function
        3. Execute the fixed function
        4. If still fails, raise with full error report

    Everything is recorded in one Context tree:
        run_with_fix ✓
        ├── execute (attempt 1) ✗  ← failed, with attempts details
        ├── fix ✓                   ← LLM rewrites the function
        └── execute (attempt 2) ✓  ← fixed version succeeds

    Args:
        fn:           The @agentic_function to execute.
        args:         Arguments to pass to fn.
        runtime:      Runtime instance (for fix() LLM calls).
        description:  What the function is supposed to do (for fix prompt).
                      Defaults to fn's docstring.
        code:         Source code of fn (for fix prompt).
                      Auto-detected via inspect.getsource() if not provided.

    Returns:
        The result of fn (or the fixed version of fn).

    Raises:
        RuntimeError: If fix also fails.
    """
    import inspect

    # Resolve defaults
    if description is None:
        description = getattr(fn, '__doc__', '') or str(fn)
    if code is None:
        try:
            code = inspect.getsource(fn)
        except (OSError, TypeError):
            code = f"# Source not available for {getattr(fn, '__name__', 'unknown')}"

    # Attempt 1: run the original function
    try:
        return fn(**args)
    except (TypeError, NotImplementedError):
        raise  # Programming errors — don't fix
    except Exception as first_error:
        # Build error log from Context attempts if available
        error_log = _build_error_log(fn, first_error)

        # Fix: let LLM rewrite the function
        fixed_fn = fix(
            description=description,
            code=code,
            error_log=error_log,
            runtime=runtime,
            name=getattr(fn, '__name__', 'fixed'),
        )

        # Attempt 2: run the fixed function
        try:
            return fixed_fn(**args)
        except Exception as second_error:
            raise RuntimeError(
                f"run_with_fix failed: original and fixed versions both failed.\n"
                f"Original error: {first_error}\n"
                f"Fixed error: {second_error}\n"
                f"Original code:\n{code}"
            ) from second_error


def _build_error_log(fn, error: Exception) -> str:
    """Build detailed error log from function's Context and exception."""
    lines = [f"Exception: {type(error).__name__}: {error}"]

    # Try to get attempts from Context
    ctx = getattr(fn, 'context', None)
    if ctx is not None:
        # Walk the tree to find nodes with failed attempts
        _collect_attempt_info(ctx, lines)

    return "\n".join(lines)


def _collect_attempt_info(ctx, lines: list, depth: int = 0):
    """Recursively collect attempt info from Context tree."""
    prefix = "  " * depth
    if ctx.attempts:
        for a in ctx.attempts:
            status = "OK" if a["error"] is None else "FAILED"
            lines.append(f"{prefix}{ctx.name} attempt {a['attempt']}: {status}")
            if a["error"]:
                lines.append(f"{prefix}  Error: {a['error']}")
            if a.get("reply") and a["error"]:
                lines.append(f"{prefix}  Reply was: {str(a['reply'])[:300]}")
    elif ctx.error:
        lines.append(f"{prefix}{ctx.name}: {ctx.error}")
    for child in ctx.children:
        _collect_attempt_info(child, lines, depth + 1)
