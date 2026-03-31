# Agentic Programming — Design Specification

> A programming paradigm where LLM sessions are the compute units.

---

## 1. Motivation

Current LLM agent frameworks treat the LLM as both brain and hands — it decides what to do and does it, all in one conversation with unbounded context growth. This makes agents powerful but unpredictable.

**Agentic Programming** structures LLM execution the same way programming languages structure CPU execution. In programming, a programmer writes typed functions, and a runtime executes them. The programmer never moves bits; the runtime never decides what to run. We apply the same separation to LLM agents.

---

## 2. Core Concepts

Three concepts. Everything else is built from these.

### 2.1 Function

The fundamental unit of execution. Like a function in Python.

```python
observe = Function(
    name="observe",
    docstring="Observe the current screen state.",
    body="Take a screenshot and identify all visible UI elements...",
    params=["task"],
    return_type=ObserveResult,
    scope=Scope.chained(),
)
```

| Field | Required | Description |
|-------|----------|-------------|
| name | Yes | Identifier, e.g. "observe" |
| docstring | Yes | What this function does (1-2 sentences) |
| body | Yes | How to do it — natural language instructions |
| return_type | Yes | Pydantic model this function MUST return |
| params | No | Which context keys to read (None = all) |
| examples | No | Sample input/output pairs |
| max_retries | No | Retry budget for invalid outputs (default: 3) |
| scope | No | Scope object controlling context visibility (default: isolated) |

**Rules:**
- A Function does not complete until its output matches `return_type`
- A Function is stateless — all input comes from context via `params`
- A Function's `body` is natural language, not code
- A Function can be executed by ANY Session — definition is runtime-agnostic

### 2.2 Runtime

The execution environment. Like Python's interpreter.

```python
runtime = Runtime(session_factory=lambda: AnthropicSession(model="claude-haiku"))

# Single execution (isolated)
result = runtime.execute(observe, context)

# Chain execution (respects Scope)
results = runtime.execute_chain([observe, learn, act], context)

# Parallel execution (each isolated)
results = await runtime.execute_parallel([(fn1, ctx1), (fn2, ctx2)])
```

**Key rules:**
- Each `execute()` creates a fresh Session (ephemeral)
- `execute_chain()` respects each Function's Scope settings
- `execute_parallel()` runs Functions concurrently, each in its own Session
- The Runtime never decides what to run — it only executes what it's given

### 2.3 Programmer

The planning and decision-making agent. Like a human programmer.

```python
programmer = Programmer(
    session=AnthropicSession(model="claude-sonnet"),   # persistent
    runtime=Runtime(session_factory=...),               # ephemeral
    functions=[observe, learn, act, verify],
)
result = programmer.run("Open Safari and search for hello world")
```

The Programmer:
- Has a **persistent Session** (remembers across iterations)
- Sees the task, available Functions, and execution history
- Decides what to call next, or creates new Functions
- Only sees **structured return values** — never execution details
- Is itself driven by a Function (programmer_fn) — within the paradigm

**Decision loop:**

```
Loop:
  1. Programmer Function → returns ProgrammerDecision
  2. Match decision.action:
     - "call"   → Runtime executes the target Function
     - "create" → Build new Function, add to pool
     - "reply"  → Return message to user
     - "done"   → Task complete, exit loop
     - "fail"   → Task impossible, exit loop
  3. Log the result, update context
  4. Continue loop
```

**ProgrammerDecision schema:**

```python
class ProgrammerDecision(BaseModel):
    action: str              # "call" | "create" | "reply" | "done" | "fail"
    reasoning: str           # why this decision
    function_name: str       # for "call"
    function_args: dict      # for "call"
    new_function: dict       # for "create" (name, docstring, body, params, schema)
    reply_text: str          # for "reply"
    failure_reason: str      # for "fail"
```

**What makes the Programmer different from a regular LLM agent:**

| Regular Agent | Programmer |
|---|---|
| Decides and executes in the same conversation | Decides in its Session, executes in separate Sessions |
| Context grows unbounded | Only sees structured summaries |
| Can't create new capabilities | Can define new Functions at runtime |
| Tools are fixed | Function pool grows dynamically |

---

## 3. Scope

Scope defines what a Function can see when it executes. Modeled after Python's variable scoping (LEGB rule).

### Three dimensions

| Dimension | Values | Description |
|-----------|--------|-------------|
| `depth` | 0, 1, 2, ... -1 | How many layers up the call stack are visible. -1 = unlimited. |
| `detail` | "io", "full" | How much of each layer: input/output only, or full reasoning. |
| `peer` | "none", "io", "full" | Visibility of sibling Functions at the same level. |

### Presets

```python
Scope.isolated()   # depth=0, detail="io", peer="none"  — pure function
Scope.chained()    # depth=0, detail="io", peer="io"    — sees sibling I/O
Scope.aware()      # depth=1, detail="io", peer="io"    — sees caller + siblings
Scope.full()       # depth=-1, detail="full", peer="full" — sees everything
```

### Custom

```python
# See two layers of call stack, only sibling I/O
Scope(depth=2, detail="io", peer="io")

# See everything in call stack, but only sibling summaries
Scope(depth=-1, detail="full", peer="io")
```

### Session sharing

Scope determines whether Functions share a Session:

| peer | Session | KV cache | Context |
|------|---------|----------|---------|
| "none" | Own Session | No hits | Clean |
| "io" | Own Session | No hits | Receives I/O summaries |
| "full" | Shared Session | Prefix hits | Full conversation visible |

This is the trade-off between KV cache efficiency and context isolation:
- `peer="full"` → high cache hits but more context
- `peer="io"` → no cache hits but controlled context
- `peer="none"` → completely isolated

### Usage

```python
# Simple, independent task — no context needed
observe = Function(name="observe", ..., scope=Scope.isolated())

# Depends on prior steps — needs their I/O
act = Function(name="act", ..., scope=Scope.chained())

# Complex reasoning — needs full sibling context for continuity
analyze = Function(name="analyze", ..., scope=Scope.full())
```

---

## 4. Context

Execution state management, modeled after Python's runtime.

| Python | Agentic Programming |
|--------|---------------------|
| Frame (locals, code) | Frame (function, caller, reason, depth) |
| Call stack | CallStack (list of Frames) |
| logging module | ExecutionLog (structured entries) |
| locals() | context.scope_for(params) → filtered dict |

### Context object

```python
ctx = Context(task="click login button")

# Push frame (entering a function)
ctx.push("programmer", "observe", reason="need to see the screen")

# Get scoped context for a function
scoped = ctx.scope_for(function.params)

# Store result
ctx["observe"] = result.model_dump()

# Pop frame (leaving function), creates log entry
ctx.pop(status="success", output=result.model_dump())

# View execution log
ctx.print_log()
# ✓ observe() [150ms] called by programmer: need to see the screen
# ✓ act()     [200ms] called by programmer: click the login button
# ✗ verify()  [50ms]  called by programmer: check result — element not found
```

### Properties

- **Dict-compatible**: `ctx["key"]`, `ctx.get("key")`, `"key" in ctx`
- **Call stack**: `ctx.depth`, `ctx.current_frame`, `ctx.stack`
- **Execution log**: `ctx.log` — list of LogEntry with timing, status, summaries
- **Scoping**: `ctx.scope_for(params)` — returns only declared keys + framework keys

---

## 5. Session

The pluggable execution backend. Any class with `send(message) -> str`.

### Input format

Sessions accept flexible input:
- `str` — plain text (all Sessions must support this)
- `dict` — structured, e.g. `{"text": "...", "images": ["path.png"]}`
- `list` — content parts (Anthropic/OpenAI native format)

### Built-in implementations

| Session | Backend | Multimodal | Tools |
|---------|---------|------------|-------|
| AnthropicSession | Anthropic API | Text + images | No |
| OpenAISession | OpenAI API | Text + images | No |
| ClaudeCodeSession | Claude Code CLI | Text | File, code, web |
| CodexSession | Codex CLI | Text | Code execution |
| OpenClawSession | OpenClaw gateway | Text | Memory, tools |
| CLISession | Any CLI | Text | Depends on CLI |

### Two lifecycles

| Lifecycle | Used by | Description |
|-----------|---------|-------------|
| Ephemeral | Runtime | Created for one execution, then destroyed |
| Persistent | Programmer | Survives across iterations |

---

## 6. Execution Modes

### Static: Workflow

For tasks where the order is known. No Programmer needed.

```python
workflow = Workflow(
    calls=[observe, learn, act, verify],
    default_session=AnthropicSession(),
)
result = workflow.run(task="Click login button")
```

### Dynamic: Programmer + Runtime

For tasks where the plan isn't known upfront.

```python
programmer = Programmer(
    session=AnthropicSession(model="claude-sonnet"),
    runtime=Runtime(session_factory=lambda: AnthropicSession(model="claude-haiku")),
    functions=[observe, learn, act, verify],
)
result = programmer.run("Open Safari and search hello world")
```

### Parallel

For independent tasks that can run concurrently.

```python
results = await runtime.execute_parallel([
    (observe, {"task": "check screen A"}),
    (observe, {"task": "check screen B"}),
])
```

### Chain

For sequential tasks with Scope-controlled context sharing.

```python
results = runtime.execute_chain(
    [observe, learn, act],  # each has its own Scope
    context={"task": "click login"},
)
```

---

## 7. Error Handling

Three levels, matching programming conventions:

### Function-level (like a runtime exception)
Function can't produce valid output after `max_retries` → raises `FunctionError`.

### Programmer-level (like a compile error)
Programmer can't make a valid decision → retries, then fails.

### Task-level (like a deliberate exit)
Programmer decides `action: "fail"` — the task is impossible.

---

## 8. Design Principles

| Principle | Description |
|-----------|-------------|
| **Three concepts** | Programmer, Function, Runtime. That's the whole framework. |
| **Scope is parameterized** | depth + detail + peer. Not fixed types. |
| **Outputs are contracts** | Functions return typed results or fail explicitly. |
| **Programmer is a programmer** | Plans, selects, creates — never executes. |
| **Sessions are pluggable** | Any LLM, any platform. Functions don't change. |
| **Context is explicit** | Functions declare what they read via params and Scope. |
| **Failure is loud** | No silent skipping. Errors propagate. |

---

## 9. Comparison

| | Prompted Agent | Tool-calling Agent | Agentic Programming |
|---|---|---|---|
| Who decides next step | LLM (free-form) | LLM (picks tools) | Programmer (structured) |
| Execution isolation | None | Partial | Full (Scope-controlled) |
| Output guarantee | None | Tool-dependent | Pydantic schema enforced |
| Create new capabilities | No | No | Yes (Programmer creates Functions) |
| Context growth | Unbounded | Unbounded | Controlled (Scope + summaries) |
| KV cache optimization | N/A | N/A | Scope.full() preserves prefix |

---

## 10. Project Structure

```
harness/
├── function/      # Function definition and execution
├── session/       # Session interface (Anthropic, OpenAI, CLI, etc.)
├── scope/         # Scope: context visibility rules
├── context/       # Context: call stack + execution log
├── runtime/       # Runtime: isolated, chained, parallel execution
├── programmer/    # Programmer: decision loop + dynamic Function creation
└── workflow/      # Workflow: static execution (convenience)

skills/
└── programmer/SKILL.md   # Default Programmer instructions

examples/
├── gui_automation.py     # Static + dynamic GUI automation example
└── skills/               # Example Function body files

tests/                    # 41 tests covering all components
docs/
└── DESIGN.md             # This file
```
