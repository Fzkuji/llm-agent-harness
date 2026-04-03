# agentic.meta.create

```python
agentic.meta.create(description, runtime, name=None) -> callable
```

Generate a new `@agentic_function` from a natural language description.

`create()` is itself an `@agentic_function` — it uses the provided Runtime to ask the LLM to write code, then executes that code in a sandboxed environment and returns the resulting function.

### Parameters

- **description** (`str`) — What the function should do. Be specific about parameters and expected output.

- **runtime** (`Runtime`) — Runtime instance used both to generate the code and injected into the generated function for its own LLM calls.

- **name** (`str | None`, default `None`) — Override the generated function's name. If `None`, uses whatever name the LLM chose.

### Returns

A callable `@agentic_function` with full Context tracking. The function's `.context` attribute is set after each call.

### Safety

Generated code runs in a restricted environment:
- **No imports** — `import` and `from ... import` statements are rejected
- **No async** — only synchronous functions are allowed
- **Restricted builtins** — no `exec`, `eval`, `open`, `__import__`, or file I/O
- **Syntax validation** — code is compiled before execution

The generated function has access to `agentic_function` (decorator) and `runtime` (the provided Runtime instance).

### Errors

- `SyntaxError` — generated code has syntax errors
- `ValueError` — generated code contains imports, uses async, fails to execute, or doesn't define an `@agentic_function`

### Example

```python
from agentic import Runtime
from agentic.meta import create

runtime = Runtime(call=my_llm, model="sonnet")

# Create a function
explain = create(
    "Explain a technical concept using a simple analogy. Take a 'concept' parameter.",
    runtime=runtime,
    name="explain_concept",
)

# Use it
result = explain(concept="prompt caching")
print(result)

# Context is tracked
print(explain.context.tree())
```
