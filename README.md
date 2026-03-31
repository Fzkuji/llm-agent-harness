# Agentic Programming

A programming paradigm where LLM sessions are the compute units.

## Core Idea

Current agent frameworks let the LLM decide everything — what to do, in what order, when to stop — all in one conversation with unbounded context growth.

**Agentic Programming** structures LLM execution the same way programming languages structure CPU execution:

- **Programmer** (LLM): like a human developer — understands the task, selects or writes Functions, checks results, iterates
- **Function**: like source code — has a name, typed inputs/outputs, natural language instructions, and a **Scope** controlling what it can see
- **Runtime** (LLM Session): like a CPU — executes a single Function, returns a typed result

The Programmer never executes. The Runtime never plans. Context visibility is controlled by Scope.

## The Programming Analogy

| Programming | Agentic Programming |
|-------------|---------------------|
| Programmer | Programmer (LLM with persistent Session) |
| Function / source code | Function (name + body + return_type + scope) |
| Type signature | return_type (Pydantic schema) |
| Variable scope (LEGB) | Scope (depth + detail + peer) |
| CPU / interpreter | Runtime (ephemeral LLM Sessions) |
| Call stack + logging | Context (Frame stack + ExecutionLog) |
| Standard library | Function Pool (pre-built Skills) |
| Type checker | Schema Validator |

## Four Primitives

| Concept | Description |
|---------|-------------|
| **Function** | Typed unit of execution — name, docstring, body, params, return_type, scope |
| **Scope** | What a Function can see — call stack depth, detail level, peer visibility |
| **Runtime** | Executes Functions — isolated, chained, or parallel |
| **Programmer** | Plans and iterates — selects/creates Functions, sends to Runtime, checks results |

Plus convenience layers:

| Concept | Description |
|---------|-------------|
| **Context** | Call stack + execution log (like Python's runtime state) |
| **Workflow** | Static mode — fixed sequence of Functions, no Programmer needed |

## Quick Start

### Define Functions

```python
from harness import Function, Scope
from pydantic import BaseModel

class ObserveResult(BaseModel):
    elements: list[str]
    target_visible: bool

observe = Function(
    name="observe",
    docstring="Observe the current screen state.",
    body="Take a screenshot and identify all visible UI elements...",
    params=["task"],
    return_type=ObserveResult,
    scope=Scope.isolated(),       # sees nothing — pure function
)

act = Function(
    name="act",
    docstring="Perform an action on screen.",
    body="Execute the planned action...",
    params=["task", "action"],
    return_type=ActResult,
    scope=Scope.chained(),        # sees prior siblings' I/O
)

analyze = Function(
    name="analyze",
    docstring="Analyze full execution context.",
    body="Review the complete reasoning chain...",
    return_type=AnalysisResult,
    scope=Scope.full(),           # sees everything (shared Session)
)
```

### Scope: Control Context Visibility

Three dimensions, any combination:

```python
Scope(
    depth=0,         # call stack: 0=none, 1=caller, -1=all
    detail="io",     # per layer: "io" (summary) or "full" (reasoning)
    peer="none",     # siblings: "none", "io" (summary), "full" (shared session)
)
```

Presets:

```python
Scope.isolated()   # depth=0, peer="none"  — pure function, sees nothing
Scope.chained()    # depth=0, peer="io"    — sees sibling I/O summaries
Scope.aware()      # depth=1, peer="io"    — sees caller + sibling I/O
Scope.full()       # depth=-1, peer="full" — sees everything, shared Session
```

**Why this matters (KV cache):** `peer="full"` shares a Session → LLM KV cache prefix is preserved → cheaper inference. `peer="io"` gives clean context but no cache hits. Choose based on the cost/isolation trade-off.

### Static Mode (Workflow)

For tasks where the execution order is known:

```python
from harness import Workflow, FunctionCall
from harness.session import AnthropicSession

workflow = Workflow(
    calls=[
        FunctionCall(function=observe),
        FunctionCall(function=learn),
        FunctionCall(function=act),
        FunctionCall(function=verify),
    ],
    default_session=AnthropicSession(),
)
result = workflow.run(task="Click the login button")
```

### Dynamic Mode (Programmer + Runtime)

For complex tasks where the plan isn't known upfront:

```python
from harness import Programmer, Runtime
from harness.session import AnthropicSession

programmer = Programmer(
    session=AnthropicSession(model="claude-sonnet-4-6"),    # persistent
    runtime=Runtime(
        session_factory=lambda: AnthropicSession(model="claude-haiku")  # ephemeral
    ),
    functions=[observe, learn, act, verify],
)

result = programmer.run("Open Safari and search for 'hello world'")
```

The Programmer:
1. Sees the task + available Functions
2. Decides what to call (or creates new Functions)
3. Runtime executes → returns typed result
4. Programmer sees the summary, decides next step
5. Repeats until done or failed

### Chain Mode

Sequential Functions with Scope-controlled context:

```python
results = runtime.execute_chain(
    [observe, learn, act],   # each has its own Scope
    context={"task": "click login"},
)
```

### Parallel Mode

Independent Functions concurrently:

```python
results = await runtime.execute_parallel([
    (observe, {"task": "check screen A"}),
    (observe, {"task": "check screen B"}),
])
```

## Context Isolation

The key mechanism — what the Programmer sees vs what the Runtime sees:

```
Programmer Session (persistent):
  "observe returned: {target_visible: true}"     ← structured summary
  "act returned: {success: true}"                ← structured summary
  → Grows slowly. Only I/O. Never the reasoning.

Runtime Session A (ephemeral):
  "Function: observe. Take a screenshot..."
  → Full reasoning. Created, executed, destroyed.

Runtime Session B (ephemeral):
  "Function: act. Click the login button..."
  → Full reasoning. Created, executed, destroyed.
```

## Project Structure

```
harness/
├── function/      # Function definition and execution
├── session/       # Session interface (Anthropic, OpenAI, CLI, etc.)
├── scope/         # Scope: context visibility rules (depth, detail, peer)
├── context/       # Context: call stack + execution log
├── runtime/       # Runtime: isolated, chained, parallel execution
├── programmer/    # Programmer: decision loop + dynamic Function creation
└── workflow/      # Workflow: static execution (convenience)

skills/
└── programmer/SKILL.md   # Default Programmer instructions

examples/
├── gui_automation.py     # GUI automation example
└── skills/               # Example Function body files

tests/                    # 41 tests covering all components
docs/
└── DESIGN.md             # Full design specification
```

## Sessions

Any class with `send(message) -> str` is a valid Session:

| Session | Backend | Multimodal |
|---------|---------|------------|
| `AnthropicSession` | Anthropic API | Text + images |
| `OpenAISession` | OpenAI API | Text + images |
| `ClaudeCodeSession` | Claude Code CLI | Text + tools |
| `CodexSession` | Codex CLI | Code execution |
| `OpenClawSession` | OpenClaw gateway | Memory + tools |
| `CLISession` | Any CLI | Depends |

## Install & Test

```bash
pip install -e .
pytest tests/ -v   # 41 tests
```

## Design

See [docs/DESIGN.md](docs/DESIGN.md) for the full specification.
