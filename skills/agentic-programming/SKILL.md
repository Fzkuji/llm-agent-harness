---
name: agentic-programming
description: "Create, run, and fix LLM-powered Python functions using Agentic Programming. Use when: (1) need to create a new function from a description, (2) need to fix a broken function, (3) want to run an existing function from the agentic library. Triggers on: 'create a function', 'agentic function', 'fix this function', 'run agentic', 'generate a function'."
---

# Agentic Programming Skill

Agentic Programming = Python controls the flow, LLM only does reasoning.

## Setup

This skill requires the `agentic` package. Install from the skill directory:

```bash
pip install -e <skill_dir>/..
```

Where `<skill_dir>` is the directory containing this SKILL.md (resolve it from the skill location).

## Capabilities

### 1. Create a new function

Use `create()` to generate a function from a natural language description:

```python
from agentic.meta_function import create
from agentic.providers import ClaudeCodeRuntime

runtime = ClaudeCodeRuntime()
fn = create("<DESCRIPTION>", runtime=runtime, name="<NAME>")
result = fn(<PARAMS>)
```

- If the task needs LLM reasoning → generates `@agentic_function` with `runtime.exec()`
- If the task is purely deterministic → generates a normal Python function
- Function is auto-saved to `agentic/functions/<NAME>.py` for reuse

### 2. Fix a broken function

Use `fix()` to let the LLM analyze errors and rewrite a function:

```python
from agentic.meta_function import fix
from agentic.providers import ClaudeCodeRuntime

runtime = ClaudeCodeRuntime()
fixed = fix(fn=broken_function, runtime=runtime, instruction="<WHAT_TO_CHANGE>")
```

- Auto-extracts source code and error context from the function
- `instruction` is optional — omit to let LLM auto-analyze

### 3. Run an existing function

Functions saved by `create()` or `fix()` live in `agentic/functions/`:

```python
from agentic.functions.list_files import list_files
print(list_files(path="/some/dir"))

from agentic.functions.sentiment import sentiment
print(sentiment(text="I love this!"))
```

### Available functions

| Function | Type | Description |
|----------|------|-------------|
| `list_files(path)` | Pure Python | List files and folders in a directory |
| `sentiment(text)` | Agentic (LLM) | Analyze text sentiment: positive/negative/neutral |

New functions appear here as they are created with `create()`.
