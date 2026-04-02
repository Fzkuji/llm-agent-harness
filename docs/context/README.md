# Context System

The Context tree is the execution record for Agentic Programming.
One tree records everything. Queries select what to show.

## Documents

| File | Description |
|---|---|
| [ENGINEERING.md](ENGINEERING.md) | **Context Engineering** — how `summarize()` queries the tree. 6 scenarios with Mermaid diagrams: full tree, depth control, include/exclude paths, branch selection, isolated mode, independent trees, path addressing. |
| [PRACTICE.md](PRACTICE.md) | **Context Practice** — strategies for API mode vs Session mode. Injection levels by tree position, recency decay, progressive detail, cache-aware layout (prompt caching cost optimization), Session compression/checkpoint, ContextPolicy design. |

## Diagrams

Mermaid diagrams for each visibility scenario:

| File | Scenario |
|---|---|
| `01-full-tree.mmd` | Full tree — all ancestors + all siblings |
| `02-depth-1.mmd` | Depth=1 — parent only |
| `03-include-specific.mmd` | Include — path whitelist |
| `04-branch-select.mmd` | Branch — subtree selection |
| `05-isolated.mmd` | Isolated — depth=0, siblings=0 |
| `06-new-tree.mmd` | New tree — context="new" |
| `07-path-addressing.mmd` | Path addressing — precise node selection |

## Code

The Context system is implemented in `agentic/`:

| File | What it does |
|---|---|
| `context.py` | `Context` dataclass + `ContextPolicy` + presets + `summarize()` + tree ops |
| `function.py` | `@agentic_function` decorator — auto-tracks in Context tree |
| `runtime.py` | `runtime.exec()` — LLM call with auto context injection |

## Quick Reference

```python
from agentic import agentic_function, runtime
from agentic import ORCHESTRATOR, PLANNER, WORKER, LEAF, FOCUSED

# Preset policies control what context each function sees:
@agentic_function(context_policy=WORKER)    # Recency decay, sees recent siblings
def observe(task): ...

@agentic_function(context_policy=ORCHESTRATOR)  # Sees all results, no details
def navigate(target): ...

@agentic_function(context_policy=LEAF)      # Zero context, pure computation
def run_ocr(img): ...

@agentic_function(context_policy=FOCUSED)   # Only the most recent sibling
def act(target, location): ...
```

## Design Principles

1. **One tree, record everything.** Recording is never affected by queries.
2. **Query selectively.** Each function controls its own view via ContextPolicy.
3. **Cache stability.** Rendered text is frozen — never mutate old siblings.
4. **Recency over completeness.** Old context decays. Recent context is detailed.
5. **Cost awareness.** Prompt cache hits are 10x cheaper. Stable prefixes matter.
