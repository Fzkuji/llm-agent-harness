"""prepare_args — merge dispatch arguments from LLM output and context."""

from __future__ import annotations

import inspect


def prepare_args(
    action: dict,
    available: dict,
    runtime=None,
    context: dict | None = None,
    fix_fn=None,
) -> dict:
    """Prepare kwargs for a dispatched function call.

    Rules:
    - Keep only parameters accepted by the target callable.
    - Fill `source=context` params from the provided context dict.
    - Fill `source=llm` params from action["args"].
    - Auto-inject `runtime` when the callable accepts it.
    - If required params are still missing and fix_fn is provided, ask it to fill them.
    """
    call_name = action.get("call")
    if call_name not in available:
        raise KeyError(f"Unknown function: {call_name}")

    spec = available[call_name]
    fn = spec["function"]
    signature = inspect.signature(fn)
    accepted = set(signature.parameters)

    context = context or {}
    action_args = action.get("args") or {}
    input_spec = spec.get("input") or {}
    prepared: dict = {}

    for param, meta in input_spec.items():
        if param not in accepted:
            continue
        meta = meta or {}
        source = meta.get("source")
        if source == "context" and param in context:
            prepared[param] = context[param]
        elif source == "llm" and param in action_args:
            prepared[param] = action_args[param]

    for param, value in action_args.items():
        if param in accepted and param not in prepared:
            prepared[param] = value

    if "runtime" in accepted and runtime is not None and "runtime" not in prepared:
        prepared["runtime"] = runtime

    missing = [
        name
        for name, parameter in signature.parameters.items()
        if parameter.default is inspect._empty
        and name not in prepared
        and name != "runtime"
    ]

    if missing and fix_fn is not None:
        fixed = fix_fn(func_name=call_name, missing=missing, runtime=runtime)
        if isinstance(fixed, dict):
            extra_args = fixed.get("args", fixed)
            for param, value in extra_args.items():
                if param in accepted and param not in prepared:
                    prepared[param] = value

    return prepared
