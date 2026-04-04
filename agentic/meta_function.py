"""
meta_function — Generate and fix agentic functions from natural language.

Two primitives:
    create()  — LLM writes a new @agentic_function from a description
    fix()     — LLM analyzes and rewrites an existing function

Usage:
    from agentic import Runtime
    from agentic.meta_function import create, fix

    runtime = Runtime(call=my_llm, model="sonnet")

    # Create a function from scratch
    summarize = create("Summarize text into 3 bullet points", runtime=runtime)

    # Fix a function (auto-detects code + errors from context)
    fixed = fix(fn=summarize, runtime=runtime)

    # Fix with manual instruction
    fixed = fix(fn=summarize, runtime=runtime, instruction="Use bullet points, not numbered list")
"""

from __future__ import annotations

import inspect
import re
from typing import Callable, Optional

from agentic.function import agentic_function
from agentic.runtime import Runtime


# ── Prompts ─────────────────────────────────────────────────────

_GENERATE_PROMPT = """\
Write a Python function that does the following:

{description}

Rules:
1. If the task requires LLM reasoning (analyzing text, making judgments, generating content),
   decorate with @agentic_function and use runtime.exec() to call the LLM.
   Content is a list of dicts: [{{"type": "text", "text": "..."}}]
2. If the task is purely deterministic (file operations, math, data processing),
   write a normal Python function WITHOUT @agentic_function and WITHOUT runtime.exec().
3. Write a clear docstring describing what the function does.
4. Return a meaningful result (string or dict).
5. Standard library imports are allowed (os, json, re, pathlib, etc.).
6. Do NOT use async/await.

`agentic_function` and `runtime` are available in scope if needed.

Write ONLY the function definition. No extra imports at top level, no examples, no explanation.
"""

_FIX_PROMPT = """\
Fix the following agentic function.

Function description: {description}

Current code:
```python
{code}
```
{error_section}
{instruction_section}
Rewrite the function to fix the issues.

Rules:
1. Decorate with @agentic_function
2. Write a clear docstring
3. Use runtime.exec() to call the LLM when reasoning is needed
4. Content is a list of dicts: [{{"type": "text", "text": "..."}}]
5. Return a meaningful result (string or dict)
6. Use only standard Python — no imports needed
7. Do NOT use async/await

`agentic_function` and `runtime` are already available in scope.

If you are unsure about anything and need clarification, respond with
ONLY a question starting with "QUESTION:" (no code). Otherwise, respond
with ONLY the fixed function definition (no explanation).
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

# Safe standard library modules that generated code may import
_ALLOWED_IMPORTS = {
    "os", "os.path", "sys", "json", "re", "math", "datetime",
    "pathlib", "collections", "itertools", "functools",
    "textwrap", "string", "io", "csv", "hashlib", "base64",
    "time", "random", "copy", "glob", "shutil", "tempfile",
}


def _make_safe_builtins() -> dict:
    """Create a restricted builtins dict."""
    import builtins
    safe = {}
    for name in _ALLOWED_BUILTINS:
        if hasattr(builtins, name):
            safe[name] = getattr(builtins, name)
    safe["__import__"] = _safe_import
    return safe


def _safe_import(name, *args, **kwargs):
    """Allow only whitelisted standard library imports."""
    if name in _ALLOWED_IMPORTS:
        return __builtins__["__import__"](name, *args, **kwargs) if isinstance(__builtins__, dict) else __import__(name, *args, **kwargs)
    raise ImportError(
        f"Import '{name}' is not allowed in generated functions. "
        f"Allowed imports: {', '.join(sorted(_ALLOWED_IMPORTS))}"
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
            # Check if it's an allowed import
            module = stripped.split()[1].split(".")[0].rstrip(",")
            if module not in _ALLOWED_IMPORTS:
                raise ValueError(
                    f"Import '{module}' is not allowed. Allowed: {', '.join(sorted(_ALLOWED_IMPORTS))}\n{code}"
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

    # Bind runtime into the function's globals so it can access it
    if hasattr(fn, '__wrapped__'):
        fn.__wrapped__.__globals__['runtime'] = runtime
    elif hasattr(fn, '_fn') and fn._fn:
        fn._fn.__globals__['runtime'] = runtime
    elif hasattr(fn, '__globals__'):
        fn.__globals__['runtime'] = runtime

    return fn


def _save_function(code: str, fn_name: str, description: str = None) -> str:
    """Save generated function source code to agentic/functions/."""
    import os
    # Skip saving during tests
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return ""
    functions_dir = os.path.join(os.path.dirname(__file__), "functions")
    os.makedirs(functions_dir, exist_ok=True)

    # Write __init__.py if missing
    init_path = os.path.join(functions_dir, "__init__.py")
    if not os.path.exists(init_path):
        with open(init_path, "w") as f:
            f.write("# Auto-generated agentic functions\n")

    # Build file content
    header = f'"""Auto-generated by create(). Description: {description or "N/A"}"""\n\n'
    imports = "from agentic.function import agentic_function\n\n"
    file_content = header + imports + code + "\n"

    filepath = os.path.join(functions_dir, f"{fn_name}.py")
    with open(filepath, "w") as f:
        f.write(file_content)

    return filepath


_CREATE_SKILL_PROMPT = """\
Write a SKILL.md file for an OpenClaw skill. This file tells an LLM agent what this function does and when to use it.

Function name: {fn_name}
Description: {description}
Source code:
```python
{code}
```

The SKILL.md must have this exact format:

---
name: {fn_name}
description: "<one-line description for agent discovery, include trigger words>"
---

# <Title>

<Brief description>

## Setup

<How to install>

## Usage

<Code example showing how to import and call the function>

## Parameters

<Table of parameters>

Rules:
1. The description in the frontmatter must include trigger words (when should an agent use this?)
2. Usage example must be correct Python that actually works
3. If the function uses runtime.exec(), mention that Claude Code CLI is needed
4. Keep it concise — agents read this every message, so shorter is better

Write ONLY the SKILL.md content. No explanation.
"""


def _save_skill_template(fn_name: str, description: str, code: str) -> str:
    """Create a basic template SKILL.md (no LLM needed)."""
    import os
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return ""
    repo_root = os.path.dirname(os.path.dirname(__file__))
    skill_dir = os.path.join(repo_root, "skills", fn_name)
    os.makedirs(skill_dir, exist_ok=True)

    skill_md = f"""---
name: {fn_name}
description: "{description}"
---

# {fn_name}

{description}

## Usage

```python
from agentic.functions.{fn_name} import {fn_name}
result = {fn_name}(...)
```
"""
    filepath = os.path.join(skill_dir, "SKILL.md")
    with open(filepath, "w") as f:
        f.write(skill_md)
    return filepath


@agentic_function
def create_skill(fn_name: str, description: str, code: str, runtime: Runtime) -> str:
    """Create a SKILL.md for a function, using LLM to write a good description.

    Args:
        fn_name:      Function name.
        description:  What the function does.
        code:         Function source code.
        runtime:      Runtime for LLM calls.

    Returns:
        Path to the created SKILL.md.
    """
    import os

    response = runtime.exec(content=[
        {"type": "text", "text": _CREATE_SKILL_PROMPT.format(
            fn_name=fn_name, description=description, code=code,
        )},
    ])

    # Extract content (strip markdown fences if any)
    skill_content = response.strip()
    if skill_content.startswith("```"):
        lines = skill_content.split("\n")
        skill_content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    repo_root = os.path.dirname(os.path.dirname(__file__))
    skill_dir = os.path.join(repo_root, "skills", fn_name)
    os.makedirs(skill_dir, exist_ok=True)

    filepath = os.path.join(skill_dir, "SKILL.md")
    with open(filepath, "w") as f:
        f.write(skill_content)

    return filepath


def _guess_name(code: str) -> Optional[str]:
    """Guess function name from generated code."""
    match = re.search(r"def\s+(\w+)\s*\(", code)
    return match.group(1) if match else None


def _find_function(namespace: dict) -> Optional[callable]:
    """Find the generated function in the namespace (agentic or regular)."""
    # First try to find an @agentic_function
    for obj_name, obj in namespace.items():
        if obj_name.startswith("_"):
            continue
        if isinstance(obj, agentic_function):
            return obj
    # Then try to find any regular function
    import types
    for obj_name, obj in namespace.items():
        if obj_name.startswith("_"):
            continue
        if isinstance(obj, types.FunctionType):
            return obj
    return None


def _get_source(fn) -> str:
    """Get source code of a function. Falls back to docstring if unavailable."""
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):
        doc = getattr(fn, '__doc__', '') or ''
        name = getattr(fn, '__name__', 'unknown')
        return f"# Source not available for {name}\n# Docstring: {doc}"


def _get_error_log(fn) -> str:
    """Build error log from function's Context (attempts + errors)."""
    ctx = getattr(fn, 'context', None)
    if ctx is None:
        return ""

    lines = []
    _collect_attempt_info(ctx, lines)
    return "\n".join(lines) if lines else ""


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
        lines.append(f"{prefix}{ctx.name}: error: {ctx.error}")
    for child in ctx.children:
        _collect_attempt_info(child, lines, depth + 1)


# ── Core: create() ──────────────────────────────────────────────

@agentic_function
def create(description: str, runtime: Runtime, name: str = None, as_skill: bool = False) -> callable:
    """Create a new function from a natural language description.

    Args:
        description:  What the function should do.
        runtime:      Runtime instance for LLM calls.
        name:         Optional name override for the generated function.
        as_skill:     If True, also create a SKILL.md in skills/{name}/
                      so the function is discoverable by LLM agents.
                      Use for top-level entry-point functions.
                      Don't use for internal helper functions.

    Returns:
        A callable function (agentic or regular, LLM decides).
    """
    response = runtime.exec(content=[
        {"type": "text", "text": _GENERATE_PROMPT.format(description=description)},
    ])
    code = _extract_code(response)
    fn_name = name or _guess_name(code) or "generated"

    # Save first, then validate and compile
    _save_function(code, fn_name, description)
    if as_skill:
        _save_skill_template(fn_name, description, code)
    _validate_code(code, response)
    return _compile_function(code, runtime, name)


# ── Core: fix() ─────────────────────────────────────────────────

@agentic_function
def fix(
    fn,
    runtime: Runtime,
    instruction: str = None,
    name: str = None,
    on_question: Callable[[str], str] = None,
    max_rounds: int = 5,
) -> callable:
    """Fix an existing @agentic_function by letting LLM analyze and rewrite it.

    Automatically extracts source code, docstring, and error context from fn.
    Supports interactive mode: if LLM has questions, it calls on_question.

    Args:
        fn:           The function to fix.
        runtime:      Runtime instance for LLM calls.
        instruction:  Optional manual instruction ("change X to Y").
                      If None, LLM auto-analyzes errors from fn.context.
        name:         Optional name override for the fixed function.
        on_question:  Optional callback for interactive fixing.
                      Signature: fn(question: str) -> str (your answer).
                      If None, LLM must produce code without asking.
        max_rounds:   Maximum interaction rounds (default 5).

    Returns:
        A new callable @agentic_function with fixes applied.
    """
    # Auto-extract everything from fn
    description = getattr(fn, '__doc__', '') or getattr(fn, '__name__', 'unknown')
    code = _get_source(fn)
    error_log = _get_error_log(fn)
    fn_name = name or getattr(fn, '__name__', 'fixed')

    # Build prompt sections
    error_section = ""
    if error_log:
        error_section = f"\nError log from previous execution:\n{error_log}\n"

    instruction_section = ""
    if instruction:
        instruction_section = f"\nUser instruction: {instruction}\n"

    # Interaction loop
    extra_context = ""
    for round_num in range(max_rounds):
        prompt = _FIX_PROMPT.format(
            description=description,
            code=code,
            error_section=error_section,
            instruction_section=instruction_section + extra_context,
        )

        # Only the first round uses runtime.exec() (one exec per agentic_function)
        # Subsequent rounds use runtime._call() directly since we need multiple LLM calls
        if round_num == 0:
            response = runtime.exec(content=[
                {"type": "text", "text": prompt},
            ])
        else:
            response = runtime._call(
                [{"type": "text", "text": prompt}],
                model=runtime.model,
            )

        # Check if LLM is asking a question
        if response.strip().startswith("QUESTION:"):
            question = response.strip()[len("QUESTION:"):].strip()
            if on_question is None:
                # No callback — LLM must produce code, retry without question
                extra_context += f"\nNote: You cannot ask questions. Produce the fixed code directly.\n"
                continue
            else:
                answer = on_question(question)
                extra_context += f"\nQ: {question}\nA: {answer}\n"
                continue

        # Got code — save, validate, compile
        fixed_code = _extract_code(response)
        _save_function(fixed_code, fn_name, f"Fixed: {description}")
        _validate_code(fixed_code, response)
        return _compile_function(fixed_code, runtime, fn_name)

    raise RuntimeError(f"fix() exceeded max_rounds ({max_rounds}) without producing valid code.")
