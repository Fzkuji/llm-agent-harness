<p align="center">
  <img src="docs/images/banner.png" alt="Agentic Programming: Redefining Agent Flow Control" width="900">
</p>

<p align="center">
  <h1 align="center">🧬 Agentic Programming</h1>
  <p align="center">
    <strong>Python functions that think.</strong><br>
    A programming paradigm where Python and LLM co-execute functions.
  </p>
  <p align="center">
    <a href="#quick-start">Quick Start</a> •
    <a href="#how-it-works">How It Works</a> •
    <a href="#api">API</a> •
    <a href="#integration">Integration</a> •
    <a href="docs/API.md">Docs</a> •
    <a href="examples/">Examples</a>
  </p>
  <p align="center">
    <a href="docs/README_CN.md">🇨🇳 中文</a>
  </p>
</p>

> 🚀 **This is a paradigm proposal.** We're sharing a new way to think about LLM-powered programming. The code here is a reference implementation — we'd love to see you take these ideas and build your own version, in any language, for any use case.

**Projects built with Agentic Programming:**

| Project | Description |
|---------|-------------|
| [🖥️&nbsp;GUI&nbsp;Agent&nbsp;Harness](https://github.com/Fzkuji/GUI-Agent-Harness) | Autonomous GUI agent that operates desktop apps via vision detection + agentic functions. Uses Agentic Programming to control observe→plan→act→verify loops with deterministic Python flow. |

---

## Motivation

Current LLM agent frameworks place the LLM as the central scheduler — it decides what to do, when, and how. This creates three fundamental problems: **unpredictable execution paths** (the LLM may skip, repeat, or invent steps regardless of defined workflows), **context explosion** (each tool-call round-trip accumulates history), and **no output guarantees** (the LLM interprets instructions rather than executing them).

<p align="center">
  <img src="docs/images/the_problem.png" alt="Motivation: LLM as Scheduler" width="800">
</p>

The core issue: **the LLM controls the flow, but nothing enforces it.** The LLM may follow a workflow, or it may not — there is no strict constraint. Skills, prompts, and system messages are suggestions, not guarantees. The execution path is fundamentally non-deterministic.

## The Idea

<p align="center">
  <img src="docs/images/the_idea.png" alt="The Idea: Python controls flow, LLM reasons" width="800">
</p>

**Give the flow back to Python. Let the LLM focus on reasoning.**

Python handles scheduling, loops, error handling, and data flow. The LLM only answers questions — when asked, where asked.

- **Deterministic flow** — Python controls `if/else/for/while`. The execution path is guaranteed, not suggested.
- **Minimal LLM calls** — The LLM is called only when reasoning is needed. 2 calls instead of 10.
- **Docstring = Prompt** — Change the function's docstring, change the LLM's behavior. No separate prompt files.

```python
@agentic_function
def observe(task):
    """Look at the screen and describe what you see."""
    
    img = take_screenshot()       # Python: deterministic
    ocr = run_ocr(img)            # Python: deterministic
    
    return runtime.exec(content=[ # LLM: reasoning
        {"type": "text", "text": f"Task: {task}\nOCR: {ocr}"},
        {"type": "image", "path": img},
    ])
```

**Docstring = Prompt.** Change the docstring, change the behavior. Everything else is Python.

---

## Quick Start

### Install

```bash
# Clone the repository
git clone https://github.com/Fzkuji/Agentic-Programming.git
cd Agentic-Programming

# Core package (no provider SDKs)
pip install -e .

# Optional providers
pip install -e ".[anthropic]"   # Anthropic Claude API
pip install -e ".[openai]"      # OpenAI Responses API
pip install -e ".[gemini]"      # Google Gemini API
pip install -e ".[all]"         # everything
```

### Provider setup

Pick one runtime and configure its credential or CLI:

| Runtime | Install | Auth / setup |
|---------|---------|--------------|
| `ClaudeCodeRuntime` | `npm install -g @anthropic-ai/claude-code` | `claude login` |
| `CodexRuntime` | install Codex CLI | `codex login` |
| `GeminiCLIRuntime` | install Gemini CLI | sign in with `gemini` |
| `AnthropicRuntime` | `pip install -e ".[anthropic]"` | `export ANTHROPIC_API_KEY=...` |
| `OpenAIRuntime` | `pip install -e ".[openai]"` | `export OPENAI_API_KEY=...` |
| `GeminiRuntime` | `pip install -e ".[gemini]"` | `export GOOGLE_API_KEY=...` |

### Optional: install skills

```bash
cp -r skills/* ~/.claude/skills/             # Claude Code
cp -r skills/* ~/.openclaw/workspace/skills/ # OpenClaw
cp -r skills/* ~/.gemini/skills/             # Gemini CLI
```

### Use

Once installed, there are **three entry points** — but they all do the same thing: once triggered, **the function takes control**, not the LLM.

**Entry 1: CLI** — Run directly from the command line:

```bash
agentic create "Summarize text into 3 bullet points" --name summarize
agentic run summarize --arg text="Your article here..."
```

**Entry 2: Skill** — Talk to your LLM agent (Claude Code, OpenClaw, Gemini CLI):

> "Create a function that analyzes code quality"

The agent picks up the installed skill, calls `create()`, and the function handles everything from there.

**Entry 3: MCP Tool** *(coming soon)* — For MCP-compatible clients.

---

**The key insight:** regardless of how you trigger it, once an `@agentic_function` starts running, **Python controls the flow**. The LLM is only called when the function explicitly asks for reasoning via `runtime.exec()`.

---

## How It Works

### 1. Functions call LLMs

Every `@agentic_function` can call `runtime.exec()` to invoke an LLM. The framework auto-injects execution context (what happened before) into the prompt.

```python
@agentic_function
def login_flow(username, password):
    """Complete login flow."""
    observe(task="find login form")
    click(element="login button")
    return verify(expected="dashboard")
```

### 2. Context tracks everything

Every call creates a **Context** node. Nodes form a tree:

```
login_flow ✓ 8.8s
├── observe ✓ 3.1s → "found login form at (200, 300)"
├── click ✓ 2.5s → "clicked login button"
└── verify ✓ 3.2s → "dashboard confirmed"
```

When `verify` calls the LLM, it automatically sees what `observe` and `click` returned. No manual context management.

### 3. Functions create functions

```python
from agentic.meta_function import create

summarize = create("Summarize text into 3 bullet points", runtime=runtime)
result = summarize(text="Long article...")
```

LLM writes the code. Framework validates and sandboxes it. You get a real `@agentic_function`.

### 4. Errors recover automatically

```python
runtime = Runtime(call=my_llm, max_retries=2)  # try once + retry once

# Or fix a broken function:
from agentic.meta_function import fix
fixed_fn = fix(
    fn=broken_fn,
    runtime=runtime,
    instruction="use label instead of coordinates",
)
```

`Runtime.exec()` and `Runtime.async_exec()` record every attempt in the current `Context` node. Transient provider failures are retried automatically; programming errors such as `TypeError` and `NotImplementedError` fail immediately.

---

## API

| Component | What it does |
|-----------|-------------|
| [`@agentic_function`](docs/api/agentic_function.md) | Decorator. Records execution into Context tree |
| [`Runtime`](docs/api/runtime.md) | LLM connection. `exec()` calls the LLM with auto-context |
| [`Context`](docs/api/context.md) | Execution tree. `tree()`, `save()`, `traceback()` |
| [`create()`](docs/api/meta_function.md) | Generate new functions from descriptions |
| [`fix()`](docs/api/meta_function.md) | Fix broken functions with LLM analysis |

### Built-in Providers

```python
from agentic.providers import AnthropicRuntime    # Claude (+ prompt caching)
from agentic.providers import OpenAIRuntime       # GPT (+ response_format)
from agentic.providers import GeminiRuntime       # Gemini API
from agentic.providers import ClaudeCodeRuntime   # Claude Code CLI (no API key)
from agentic.providers import CodexRuntime        # Codex CLI (no API key in Python)
from agentic.providers import GeminiCLIRuntime    # Gemini CLI (no API key in Python)
```

See [Provider docs](docs/api/providers.md) for setup.

---

## vs Tool-Calling

|  | Tool-Calling / MCP | Agentic Programming |
|--|---------------------|---------------------|
| **Who schedules?** | LLM | Python |
| **Functions contain** | Code only | Code + LLM reasoning |
| **Context** | One big conversation | Structured tree |
| **Prompt** | Hidden in agent | Docstring = prompt |

MCP is the *transport*. Agentic Programming is the *execution model*. They're orthogonal.

---

## Install & Configuration

### Minimal install

```bash
pip install -e .
```

### Provider-specific installs

```bash
pip install -e ".[anthropic]"  # Anthropic Claude API
pip install -e ".[openai]"     # OpenAI GPT / Responses API
pip install -e ".[gemini]"     # Google Gemini API
pip install -e ".[all]"        # install all provider SDKs
```

### Runtime selection

```python
from agentic.providers import ClaudeCodeRuntime, AnthropicRuntime
from agentic.providers import OpenAIRuntime, GeminiRuntime
from agentic.providers import CodexRuntime, GeminiCLIRuntime

local = ClaudeCodeRuntime(model="sonnet")
strong = AnthropicRuntime(model="claude-sonnet-4-20250514")
json_rt = OpenAIRuntime(model="gpt-4o")
fast = GeminiRuntime(model="gemini-2.5-flash")
codex = CodexRuntime(model="o4-mini")
gemini_cli = GeminiCLIRuntime()
```

### Retry + `fix()` workflow

```python
from agentic import agentic_function, Runtime
from agentic.meta_function import create, fix

runtime = Runtime(call=my_llm, max_retries=3)
extract = create(
    "Extract company name and price from text. Return JSON with keys company and price.",
    runtime=runtime,
    name="extract_quote",
)

try:
    result = extract(text="Acme closed at $42.50 today")
except Exception:
    extract = fix(
        fn=extract,
        runtime=runtime,
        instruction="Validate missing prices and always return valid JSON.",
    )
    result = extract(text="Acme closed at $42.50 today")
```

`fix()` infers the source code and prior error history from `fn`, so you only pass the function object plus any extra guidance.

## Project Structure

```
agentic/
├── __init__.py          # agentic_function, Runtime, Context, create, fix
├── context.py           # Context tree
├── function.py          # @agentic_function decorator
├── runtime.py           # Runtime class (exec + retry)
├── meta_function.py     # create() + fix()
└── providers/           # Anthropic, OpenAI, Gemini, Claude Code CLI

examples/                # runnable demos and provider examples
docs/api/                # API reference
tests/                   # pytest suite for core/runtime/provider behavior
```

## Integration

Use Agentic Programming with your existing tools:

| Guide | Description |
|-------|-------------|
| [Getting Started](docs/GETTING_STARTED.md) | 3-minute setup, provider comparison, runnable examples |
| [Claude Code Integration](docs/INTEGRATION_CLAUDE_CODE.md) | Use without API key via Claude Code CLI |
| [OpenClaw Integration](docs/INTEGRATION_OPENCLAW.md) | Use as OpenClaw skill or MCP tool |
| [API Reference](docs/API.md) | Full API documentation |

---

## Contributing

This project is a **paradigm proposal** with a reference implementation. We welcome:

- 🧠 **Discussions** on the programming model
- 🔧 **Alternative implementations** in other languages or frameworks
- 📝 **Use cases** that validate or challenge the approach
- 🐛 **Bug reports** on the reference implementation

If you build something based on Agentic Programming, let us know!

## License

MIT
