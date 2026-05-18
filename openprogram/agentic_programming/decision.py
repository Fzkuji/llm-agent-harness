"""decision — next-step decision making for agentic functions.

Lets the LLM decide what an ``@agentic_function`` does next: it picks one
option from a declared set, and the framework resolves that pick into the
next step's result.

Two entry points, same options and same resolution:

  - ``decision.make(prompt, options)`` — pure decision: the model picks straight
    away, no work first.
  - ``runtime.exec(..., choices=options)`` — the model runs a full turn
    (reasoning, tool calls) and only the *finish* is a decision.

    # inside an @agentic_function
    return decision.make("Pick how to handle this message.", {
        "analyze":  analyze_sentiment,        # a function
        "fallback": fallback_reply,           # a function
        "done":     "CONVERSATION_OVER",      # a plain value
    })

Resolution leaves no branching for the caller:

  - the LLM picked a function → the function runs (with parsed +
    auto-injected args) and its return value is returned
  - the LLM picked a value    → that value is returned as-is

The decision itself encodes what happens next, so the calling
``@agentic_function`` never inspects "which option" or writes an ``if``.

Option containers
-----------------
``dict`` — ``{name: handler}``. ``handler`` is a callable (function
option) or any non-callable (value option). Attach a description to a
value option with ``{name: (value, "description")}``.

``list`` — items are callables, ``(callable, "description")``, or the
string-option forms (``"name"``, ``("name", "description")``,
``("name", "description", schema)``). A bare string option resolves to
its own name.
"""

from __future__ import annotations

import inspect
import json
import re
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Parameters the runtime auto-injects — never surfaced to the LLM as a
# choosable argument, and filled from the runtime on dispatch.
# ---------------------------------------------------------------------------
_AUTO_PARAMS = {"runtime", "exec_runtime", "review_runtime"}
_CALL_KEY_ALIASES = ("call", "action", "function", "tool")
_VALIDATABLE_TYPES = {str, int, float, bool, list, dict}
_TYPE_PLACEHOLDERS = {
    "str": '"<str>"', "int": "0", "float": "0.0",
    "bool": "false", "list": "[]", "dict": "{}",
}


# ===========================================================================
# Option list → registry
# ===========================================================================


def _functions_to_registry(options) -> dict:
    """Build a registry dict from a heterogeneous options list."""
    registry: dict = {}
    for item in options:
        name, entry = _normalize_option(item)
        if name in registry:
            raise ValueError(f"Duplicate option name {name!r} in options list")
        registry[name] = entry
    return registry


def _normalize_option(item) -> tuple[str, dict]:
    # Callable: bare function.
    if callable(item) and not isinstance(item, (tuple, str)):
        return _callable_entry(item, override_desc=None)

    # Text option: bare string name.
    if isinstance(item, str):
        return item, {
            "function": None, "description": "", "input": {}, "_is_text": True,
        }

    # Tuple: dispatch by first element.
    if isinstance(item, tuple):
        if len(item) == 0:
            raise TypeError("Empty tuple in options list")
        first = item[0]
        if callable(first) and not isinstance(first, str):
            override = item[1] if len(item) >= 2 else None
            return _callable_entry(first, override_desc=override)
        if isinstance(first, str):
            name = first
            desc = item[1] if len(item) >= 2 else ""
            schema = item[2] if len(item) >= 3 else {}
            return name, {
                "function": None, "description": desc,
                "input": _normalize_text_schema(schema), "_is_text": True,
            }
        raise TypeError(
            f"First element of option tuple must be callable or str, "
            f"got {type(first).__name__}"
        )

    raise TypeError(
        f"Option must be callable, str, or tuple; got {type(item).__name__}"
    )


def _callable_entry(fn, override_desc) -> tuple[str, dict]:
    raw = getattr(fn, "_fn", fn)
    input_meta = getattr(fn, "input_meta", {}) or {}
    doc = (raw.__doc__ or "").strip()
    desc = (
        override_desc if override_desc
        else (doc.split("\n\n", 1)[0].strip() if doc else "")
    )

    sig = inspect.signature(raw)
    input_spec: dict = {}
    for pname, param in sig.parameters.items():
        meta = input_meta.get(pname, {}) or {}
        is_auto = pname in _AUTO_PARAMS
        is_hidden = bool(meta.get("hidden", False))
        source = "context" if (is_auto or is_hidden) else "llm"
        entry: dict = {
            "source": source,
            "type": (
                param.annotation
                if param.annotation is not inspect.Parameter.empty
                else str
            ),
        }
        if "description" in meta:
            entry["description"] = meta["description"]
        if "options" in meta:
            entry["options"] = meta["options"]
        input_spec[pname] = entry

    return raw.__name__, {
        "function": fn, "description": desc,
        "input": input_spec, "_is_text": False,
    }


def _normalize_text_schema(schema) -> dict:
    """Turn a text option's user-supplied schema into registry input_spec form."""
    if not isinstance(schema, dict):
        raise TypeError(
            f"Text option schema must be a dict, got {type(schema).__name__}"
        )
    out: dict = {}
    for arg_name, value in schema.items():
        if isinstance(value, str):
            out[arg_name] = {"source": "llm", "type": str, "description": value}
        elif isinstance(value, dict):
            entry: dict = {"source": "llm", "type": value.get("type", str)}
            if "description" in value:
                entry["description"] = value["description"]
            if "options" in value:
                entry["options"] = value["options"]
            out[arg_name] = entry
        else:
            raise TypeError(
                f"Schema value for {arg_name!r} must be str or dict, "
                f"got {type(value).__name__}"
            )
    return out


# ===========================================================================
# Menu rendering
# ===========================================================================


def render_options(available) -> str:
    """Render the LLM-facing options menu from an options list/registry.

    Only ``source="llm"`` parameters are shown — runtime / context params
    stay hidden. Each option gets a ``Call:`` example with JSON-native
    placeholder values.
    """
    if isinstance(available, (list, tuple)):
        available = _functions_to_registry(available)

    lines: list[str] = []
    for name, spec in available.items():
        description = spec.get("description", "")
        input_spec = spec.get("input", {})

        llm_params: list[str] = []
        param_details: list[str] = []
        for param_name, param_info in input_spec.items():
            if param_info.get("source") != "llm":
                continue
            type_obj = param_info.get("type", str)
            type_name = getattr(type_obj, "__name__", None) or str(type_obj)
            llm_params.append(f"{param_name}: {type_name}")
            detail = f"    {param_name}"
            if "description" in param_info:
                detail += f": {param_info['description']}"
            if "options" in param_info:
                opts = ", ".join(f'"{o}"' for o in param_info["options"])
                detail += f" (options: {opts})"
            param_details.append(detail)

        sig = f"{name}({', '.join(llm_params)})" if llm_params else f"{name}()"
        lines.append(sig)
        if description:
            lines.append(f"    {description}")
        lines.extend(param_details)

        if llm_params:
            example_args = ", ".join(
                f'"{p.split(":")[0].strip()}": '
                + _TYPE_PLACEHOLDERS.get(p.split(":")[1].strip(), "null")
                for p in llm_params
            )
            lines.append(f'    Call: {{"call": "{name}", "args": {{{example_args}}}}}')
        else:
            lines.append(f'    Call: {{"call": "{name}"}}')
        lines.append("")

    return "\n".join(lines)


# ===========================================================================
# Reply parsing
# ===========================================================================


class _ParseError(Exception):
    def __init__(self, kind: str, message: str):
        self.kind = kind
        self.message = message
        super().__init__(message)


def _iter_json_objects(text: str):
    """Yield every dict that parses as JSON at any '{' position in text."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        yield json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        pass
                    break
        start = text.find("{", start + 1)


def _has_call_key(obj) -> str | None:
    if not isinstance(obj, dict):
        return None
    for k in _CALL_KEY_ALIASES:
        if k in obj:
            return k
    return None


def _normalize_action(obj: dict, matched_key: str) -> dict:
    if matched_key == "call":
        return obj
    out = {"call": obj[matched_key]}
    for k, v in obj.items():
        if k != matched_key:
            out[k] = v
    return out


def extract_action(text: str) -> dict | None:
    """Extract ``{"call": "...", "args": {...}}`` from LLM text, or None."""
    if not text:
        return None
    for fence in re.findall(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL):
        try:
            obj = json.loads(fence)
        except json.JSONDecodeError:
            for obj in _iter_json_objects(fence):
                key = _has_call_key(obj)
                if key:
                    return _normalize_action(obj, key)
            continue
        key = _has_call_key(obj)
        if key:
            return _normalize_action(obj, key)
    for obj in _iter_json_objects(text):
        key = _has_call_key(obj)
        if key:
            return _normalize_action(obj, key)
    return None


def _validate_field(name: str, value, meta: dict) -> None:
    """Type and enum check for a single field. Raises _ParseError on mismatch."""
    expected = meta.get("type")
    if expected in _VALIDATABLE_TYPES:
        if expected in (int, float) and isinstance(value, bool):
            raise _ParseError(
                "type_mismatch",
                f"Field {name!r} must be {expected.__name__}, got bool",
            )
        if expected is float and isinstance(value, int):
            pass
        elif not isinstance(value, expected):
            raise _ParseError(
                "type_mismatch",
                f"Field {name!r} must be {expected.__name__}, "
                f"got {type(value).__name__} ({value!r})",
            )
    enum = meta.get("options")
    if enum and value not in enum:
        raise _ParseError(
            "enum_violation",
            f"Field {name!r} must be one of {list(enum)}, got {value!r}",
        )


def _try_parse(reply: str, registry: dict, runtime, context: dict | None):
    action = extract_action(reply)
    if action is None:
        raise _ParseError(
            "no_action", "Reply contained no parseable JSON with a 'call' field.",
        )

    call = action.get("call")
    if call not in registry:
        raise _ParseError(
            "unknown_call",
            f"Picked {call!r}, which is not an available option. "
            f"Valid options: {list(registry)}",
        )

    spec = registry[call]
    is_text = spec.get("_is_text", False)
    input_spec = spec.get("input", {})
    args = dict(action.get("args") or {})

    if is_text:
        missing = [n for n in input_spec if n not in args]
        if missing:
            raise _ParseError(
                "missing_required",
                f"Option {call!r} is missing required fields: {missing}",
            )
        for fname, meta in input_spec.items():
            _validate_field(fname, args[fname], meta)
        args = {k: v for k, v in args.items() if k in input_spec}
        return call, args

    target = spec["function"]
    raw = getattr(target, "_fn", target)
    sig = inspect.signature(raw)

    if context:
        for pname, pmeta in input_spec.items():
            if pmeta.get("source") == "context" and pname not in args:
                if pname in context:
                    args[pname] = context[pname]

    for p in _AUTO_PARAMS:
        if p in sig.parameters:
            args[p] = runtime

    valid = set(sig.parameters.keys())
    args = {k: v for k, v in args.items() if k in valid}

    missing = [
        n for n, p in sig.parameters.items()
        if p.default is inspect.Parameter.empty and n not in args
    ]
    if missing:
        raise _ParseError(
            "missing_required",
            f"Call {call!r} is missing required arguments: {missing}",
        )

    for fname, meta in input_spec.items():
        if meta.get("source") != "llm" or fname not in args:
            continue
        _validate_field(fname, args[fname], meta)

    return target, args


def parse_args(
    reply: str,
    options,
    runtime,
    *,
    context: dict | None = None,
    max_retries: int = 1,
) -> tuple[Callable | str, dict]:
    """Parse an LLM reply, locate the chosen option, bind its args.

    On a parse/validate failure the LLM is asked to re-pick (up to
    ``max_retries`` times) via a plain ``runtime.exec`` call — the retry
    is itself a model call and lands in the DAG.

    Returns ``(chosen, kwargs)``: ``chosen`` is the function for a
    callable option, or the name string for a text option.
    """
    if runtime is None:
        raise ValueError("runtime is required for parse_args()")

    if isinstance(options, (list, tuple)):
        registry = _functions_to_registry(options)
    else:
        registry = options
    if not registry:
        raise ValueError("options list is empty")

    last_reply = reply
    last_error: _ParseError | None = None

    for attempt in range(max_retries + 1):
        try:
            return _try_parse(last_reply, registry, runtime, context)
        except _ParseError as e:
            last_error = e
            if attempt >= max_retries:
                break
            menu = render_options(registry)
            last_reply = str(runtime.exec(content=[{"type": "text", "text": (
                f"Previous reply:\n{last_reply[:500]}\n\n"
                f"Problem: {e.message}\n\n"
                f"Options:\n{menu}\n\n"
                "Your previous reply failed to parse or validate. Re-pick an "
                "option from the list above, fixing the problem described. "
                "Reply with valid JSON in the format shown in that option's "
                "Call: example line — JSON only, no prose."
            )}]))

    raise ValueError(
        f"parse_args failed after {max_retries + 1} attempt(s). "
        f"Last error ({last_error.kind}): {last_error.message}. "
        f"Last reply head: {last_reply[:200]!r}"
    )


# ===========================================================================
# Decision preparation / resolution — shared by ``decision.make`` and
# ``Runtime.exec(choices=...)``.
# ===========================================================================


# Appended to an ``exec(choices=...)`` prompt: the model does its work
# first, then must finish with a single JSON pick from the menu.
DECISION_FINISH_INSTRUCTION = (
    "\n\nDo whatever work you need to first. When you are finished, the "
    "LAST thing in your reply must be a single JSON object picking exactly "
    "one option from the menu below — in the format shown on that option's "
    "``Call:`` line. Options:\n\n"
)


def _resolve_runtime(runtime):
    """Return ``runtime`` or the ambient one of the enclosing function."""
    if runtime is None:
        from openprogram.agentic_programming.function import _current_runtime
        runtime = _current_runtime.get(None)
    if runtime is None:
        raise RuntimeError(
            "no runtime available — call this inside an @agentic_function, "
            "or pass runtime= explicitly."
        )
    return runtime


def _normalize_options(options):
    """Split a dict/list of options into (menu, value_table).

    ``menu`` is what ``render_options`` / ``parse_args`` consume — a
    registry dict for dict input, a list for list input. ``value_table``
    maps a value-option name to the value it resolves to.
    """
    values: dict[str, Any] = {}

    if isinstance(options, dict):
        # Dict input: the key is the authoritative option name, for
        # function options as well as value options.
        registry: dict = {}
        for name, handler in options.items():
            desc = ""
            if isinstance(handler, tuple) and len(handler) == 2:
                handler, desc = handler
            if callable(handler):
                _, entry = _callable_entry(handler, override_desc=desc or None)
            else:
                _, entry = _normalize_option((name, desc) if desc else name)
                values[name] = handler
            if name in registry:
                raise ValueError(f"Duplicate option name {name!r}")
            registry[name] = entry
        return registry, values

    if not isinstance(options, (list, tuple)):
        raise TypeError(
            f"options must be a dict or list, got {type(options).__name__}"
        )

    menu: list = []
    for item in options:
        menu.append(item)
        if isinstance(item, str):
            values[item] = item
        elif isinstance(item, tuple) and item and isinstance(item[0], str):
            values[item[0]] = item[0]
    return menu, values


def resolve_decision(
    reply: str,
    menu,
    value_table: dict,
    runtime,
    *,
    context: dict | None = None,
    max_retries: int = 1,
) -> Any:
    """Parse an LLM ``reply`` against a prepared menu and resolve the pick.

    ``menu`` / ``value_table`` come from ``_normalize_options``.
    A function option is run and its return value handed back; a value
    option's value is returned as-is. A value option that declared a
    schema returns ``{"decision": name, **llm_supplied_fields}``.
    """
    chosen, args = parse_args(
        reply, menu, runtime, context=context, max_retries=max_retries,
    )
    if isinstance(chosen, str):
        if args:
            return {"decision": chosen, **args}
        return value_table.get(chosen, chosen)
    return chosen(**args)


# ===========================================================================
# Public entry: make
# ===========================================================================


def make(
    prompt: str,
    options,
    *,
    runtime=None,
    context: dict | None = None,
    max_retries: int = 1,
) -> Any:
    """Let the LLM pick the next step from a set of options — no work first.

    The next-step decision primitive of the agentic-function paradigm:
    it hands the model a set of options and resolves the pick into the
    next step's result — a picked function is run and its return value
    handed back, a picked value is returned as-is. The calling
    ``@agentic_function`` writes no ``if``; the decision itself is the
    branch.

        @agentic_function
        def route_message(msg: str) -> str:
            return decision.make("Pick how to handle this message.", {
                "analyze": analyze_sentiment,     # a function
                "done":    "CONVERSATION_OVER",   # a value
            })

    ``decision.make`` is the *pure-decision* shorthand: the model picks straight
    away. When the model should **do work first** (call tools, reason)
    and only *finish* with a pick, use ``runtime.exec(..., choices=...)``
    instead — same options, same resolution, but a full turn before the
    decision.

    Args:
        prompt:   Instruction text; the rendered menu is appended.
        options:  A dict ``{name: handler}`` (handler is a callable or
                  any value; ``{name: (value, "desc")}`` to add a
                  description) or a list of callables / option tuples.
        runtime:  Runtime for the model call. Defaults to the ambient
                  runtime of the enclosing ``@agentic_function``.
        context:  Optional dict for filling ``source="context"`` params
                  of function options.
        max_retries: LLM re-pick attempts on a parse/validate failure.

    Returns:
        The resolved next step — a function option's return value, or a
        value option's value.
    """
    runtime = _resolve_runtime(runtime)
    menu, value_table = _normalize_options(options)
    reply = runtime.exec(content=[
        {"type": "text", "text": f"{prompt}\n\n{render_options(menu)}"},
    ])
    return resolve_decision(
        reply, menu, value_table, runtime,
        context=context, max_retries=max_retries,
    )
