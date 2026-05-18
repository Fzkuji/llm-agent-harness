---
name: deep-work
description: "Run an autonomous agent on a complex task with quality evaluation. Clarifies upfront, then works fully autonomously until the result meets the standard. Triggers: 'deep work', 'work on this seriously', 'high quality task', 'write a paper', 'complex task', 'do this properly', 'professional quality'."
---

# Deep Work

Run an autonomous agent for complex, high-standard tasks. Clarifies any questions upfront, then works fully autonomously — plan, execute, evaluate, revise — until the result meets the quality standard.

```bash
agentic deep-work "<TASK>" --level <LEVEL>
```

## Quality Levels

| Level | Standard |
|-------|----------|
| `high_school` | Basic correctness, simple structure |
| `bachelor` | Solid understanding, proper methodology (default) |
| `master` | Depth of analysis, critical thinking, good writing |
| `phd` | Novel contribution, rigorous methodology, publication-ready |
| `professor` | Expert/authoritative, top-venue quality (NeurIPS/Nature/OSDI) |

## Examples

```bash
# PhD-level survey paper
agentic deep-work "Write a survey on context management in LLM agents, focus on compaction vs sub-agent trade-offs, target NeurIPS workshop" \
  --level phd

# Production code at master level
agentic deep-work "Build a REST API for user auth with OAuth2, include tests and docs" \
  --level master

# Expert-level analysis
agentic deep-work "Analyze system performance bottlenecks, provide data-backed recommendations" \
  --level professor
```

## Options

| Flag | Description |
|------|-------------|
| `--level`, `-l` | Quality level: high_school / bachelor / master / phd / professor (default: bachelor) |
| `--provider`, `-p` | LLM provider |
| `--model`, `-m` | Model to use |
| `--max-steps` | Max total steps (default: 100) |
| `--max-revisions` | Max evaluation-revision cycles (default: 5) |
| `--no-interactive` | Skip clarification, start immediately |
