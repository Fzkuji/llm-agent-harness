"""prepare_args — merge LLM-selected args with context-provided values."""

from __future__ import annotations

import inspect
from collections.abc import Callable


def prepare_args(
    action: dict,
    available: dict[str, dict],
    runtime=None,
    context: dict | None = None,
    fix_fn: Callable | None = None,
) -> dict:
    """Prepare kwargs for a dispatch-selected function call.

    Rules:
    - start from LLM-provided args
    - fill `source=context` params from context
    - inject `runtime` when the target function accepts it
    - optionally call fix_fn for still-missing required params
    - drop unknown args before returning
    """
    context = context or {}
    call_name = action.get("call")
    spec = available.get(call_name) or {}
    fn = spec.get("function")
    if fn is None:
        return dict(action.get("args") or {})

    input_spec = spec.get("input") or {}
    args = dict(action.get("args") or {})

    for param, meta in input_spec.items():
        if meta.get("source") == "context" and param not in args and param in context:
            args[param] = context[param]

    signature = inspect.signature(fn)
    if "runtime" in signature.parameters and "runtime" not in args and runtime is not None:
        args["runtime"] = runtime

    missing: list[str] = []
    for name, param in signature.parameters.items():
        if name in args:
            continue
        if name == "runtime" and runtime is not None:
            continue
        if param.default is inspect._empty:
            missing.append(name)

    if missing and fix_fn is not None:
        fixed = fix_fn(func_name=call_name, missing=missing, runtime=runtime)
        if isinstance(fixed, dict):
            args.update({k: v for k, v in fixed.items() if k in signature.parameters})

    return {name: args[name] for name in signature.parameters if name in args}
