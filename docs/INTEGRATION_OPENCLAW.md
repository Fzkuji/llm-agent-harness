# OpenClaw Integration | OpenClaw 集成指南

[English](#english) | [中文](#中文)

---

<a id="english"></a>

## What Is This?

This guide shows how to use **Agentic Programming** within [OpenClaw](https://github.com/nicepkg/openclaw) — as a skill, a utility library, or an MCP tool provider.

Agentic Programming and OpenClaw solve different problems:
- **OpenClaw** orchestrates agents, manages sessions, routes messages
- **Agentic Programming** gives individual functions the ability to think (LLM-in-the-loop)

They compose naturally: OpenClaw's skills can use agentic functions internally.

## Setup

```bash
# In your OpenClaw workspace
cd ~/.openclaw/workspace

# Clone OpenProgram
git clone https://github.com/Fzkuji/OpenProgram.git

# Install it
cd OpenProgram
pip install -e .
```

## Usage Pattern 1: Agentic Functions Inside a Skill

The simplest integration — use agentic functions as building blocks within an OpenClaw skill.

**Skill structure:**
```
~/.openclaw/workspace/skills/my-agentic-skill/
├── SKILL.md
└── scripts/
    └── analyze.py
```

**`scripts/analyze.py`:**
```python
#!/usr/bin/env python3
"""
OpenClaw skill script that uses Agentic Programming internally.
Called by the agent via exec tool.
"""
import sys
import os

# Add Agentic Programming to path (adjust if installed differently)
sys.path.insert(0, os.path.expanduser("~/.openclaw/workspace/Agentic-Programming"))

from openprogram import agentic_function
from openprogram.providers import ClaudeCodeRuntime

runtime = ClaudeCodeRuntime(model="haiku")


@agentic_function
def decompose(task):
    """Break a complex task into actionable steps."""
    return runtime.exec(content=[
        {"type": "text", "text": f"Break this task into 3-5 concrete, actionable steps:\n{task}\n\nNumber each step. Be specific."},
    ])


@agentic_function
def assess(step):
    """Assess difficulty and time estimate for a step."""
    return runtime.exec(content=[
        {"type": "text", "text": f"For this step, give: difficulty (easy/medium/hard) and time estimate.\nFormat: [difficulty] ~Xh\n\nStep: {step}"},
    ])


@agentic_function
def plan(task):
    """Create a detailed plan for a task."""
    steps_text = decompose(task=task)

    lines = [l.strip() for l in steps_text.split("\n") if l.strip() and l.strip()[0].isdigit()]
    assessments = []
    for line in lines[:5]:
        a = assess(step=line)
        assessments.append(f"{line}\n   → {a}")

    return "\n\n".join(assessments)


if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Build a REST API with authentication"
    result = plan(task=task)
    print(result)

    # Save execution tree for debugging
    if plan.context:
        plan.context.save("plan_trace.jsonl")
```

**`SKILL.md`:**
```markdown
# my-agentic-skill

Plan and decompose tasks using Agentic Programming with automatic context tracking.

## Usage

When the user asks to plan, decompose, or break down a task, run:

\`\`\`bash
python3 ~/.openclaw/workspace/skills/my-agentic-skill/scripts/analyze.py "the task description"
\`\`\`
```

## Usage Pattern 2: As a Python Library in Agent Scripts

If your OpenClaw agent runs Python scripts, you can import agentic functions directly:

```python
"""
Script called by OpenClaw agent to analyze code quality.
"""
from openprogram import agentic_function
from openprogram.providers import ClaudeCodeRuntime

runtime = ClaudeCodeRuntime(model="haiku")


@agentic_function
def review_code(code, language="python"):
    """Review code for bugs, style issues, and improvements."""
    return runtime.exec(content=[
        {"type": "text", "text": f"Review this {language} code. List:\n1. Bugs (if any)\n2. Style issues\n3. Suggested improvements\n\n```{language}\n{code}\n```"},
    ])


@agentic_function
def suggest_tests(code):
    """Suggest test cases for the given code."""
    return runtime.exec(content=[
        {"type": "text", "text": f"Suggest 3 test cases for this code. For each, give: test name, input, expected output.\n\n```python\n{code}\n```"},
    ])


@agentic_function
def code_analysis(code):
    """Full code analysis: review + test suggestions."""
    review = review_code(code=code)
    tests = suggest_tests(code=code)
    return f"## Code Review\n{review}\n\n## Suggested Tests\n{tests}"


# Usage from OpenClaw agent:
# result = code_analysis(code=open("my_file.py").read())
```

## Usage Pattern 3: MCP Tool Wrapper

Wrap agentic functions as MCP tools that OpenClaw can call:

```python
#!/usr/bin/env python3
"""
MCP-compatible tool server that exposes agentic functions.
OpenClaw can discover and call these tools via MCP protocol.
"""
import json
import sys

from openprogram import agentic_function
from openprogram.providers import ClaudeCodeRuntime

runtime = ClaudeCodeRuntime(model="haiku")


@agentic_function
def summarize_text(text, style="bullet_points"):
    """Summarize text in the specified style."""
    style_instructions = {
        "bullet_points": "Summarize as 3-5 bullet points.",
        "one_paragraph": "Summarize in one paragraph.",
        "eli5": "Explain like I'm 5.",
    }
    instruction = style_instructions.get(style, style_instructions["bullet_points"])

    return runtime.exec(content=[
        {"type": "text", "text": f"{instruction}\n\nText:\n{text}"},
    ])


# Simple stdin/stdout MCP-style interface
# OpenClaw calls: echo '{"tool":"summarize","args":{"text":"...","style":"bullet_points"}}' | python3 mcp_tools.py
if __name__ == "__main__":
    request = json.loads(sys.stdin.read())
    tool = request.get("tool")
    args = request.get("args", {})

    if tool == "summarize":
        result = summarize_text(**args)
        print(json.dumps({"result": result}))
    else:
        print(json.dumps({"error": f"Unknown tool: {tool}"}))
```

## Why Use Agentic Programming in OpenClaw?

| Without Agentic Programming | With Agentic Programming |
|-----|-----|
| Agent does all reasoning in one LLM call | Reasoning is split into focused function calls |
| Context grows unboundedly | Context is structured as a tree, auto-summarized |
| Hard to debug what the agent "thought" | Full execution tree: `context.tree()`, `context.save()` |
| Retry = retry entire agent turn | Retry = retry just the failed function |

## Tips

1. **Use `ClaudeCodeRuntime` for simplicity** — no extra API keys needed if Claude Code is installed.
2. **Use `AnthropicRuntime` for production** — faster, supports images, prompt caching.
3. **Save execution traces** — `context.save("trace.jsonl")` is invaluable for debugging.
4. **Keep functions small** — each `@agentic_function` should do one thing. Let Python compose them.

---

---

<a id="中文"></a>

## 这是什么？

本指南介绍如何在 [OpenClaw](https://github.com/nicepkg/openclaw) 中使用 **Agentic Programming** — 作为 skill、工具库或 MCP tool provider。

Agentic Programming 和 OpenClaw 解决不同的问题：
- **OpenClaw** 编排 agent、管理会话、路由消息
- **Agentic Programming** 让单个函数具备思考能力（LLM-in-the-loop）

它们天然可组合：OpenClaw 的 skill 内部可以使用 agentic function。

## 配置

```bash
# 在 OpenClaw 工作区
cd ~/.openclaw/workspace

# 克隆 OpenProgram
git clone https://github.com/Fzkuji/OpenProgram.git

# 安装
cd OpenProgram
pip install -e .
```

## 用法 1：在 Skill 中使用 Agentic Function

最简单的集成方式 — 把 agentic function 作为 OpenClaw skill 的内部构建块。

**Skill 结构：**
```
~/.openclaw/workspace/skills/my-agentic-skill/
├── SKILL.md
└── scripts/
    └── analyze.py
```

**`scripts/analyze.py`：**
```python
#!/usr/bin/env python3
"""
使用 Agentic Programming 的 OpenClaw skill 脚本。
Agent 通过 exec 工具调用。
"""
import sys
import os

# 把 Agentic Programming 加到 path（根据安装方式调整）
sys.path.insert(0, os.path.expanduser("~/.openclaw/workspace/Agentic-Programming"))

from openprogram import agentic_function
from openprogram.providers import ClaudeCodeRuntime

runtime = ClaudeCodeRuntime(model="haiku")


@agentic_function
def decompose(task):
    """把复杂任务拆解成可执行的步骤。"""
    return runtime.exec(content=[
        {"type": "text", "text": f"把这个任务拆解成 3-5 个具体、可执行的步骤：\n{task}\n\n编号，要具体。"},
    ])


@agentic_function
def assess(step):
    """评估一个步骤的难度和时间。"""
    return runtime.exec(content=[
        {"type": "text", "text": f"对这个步骤给出：难度（简单/中等/困难）和时间估计。\n格式：[难度] ~X小时\n\n步骤：{step}"},
    ])


@agentic_function
def plan(task):
    """为任务创建详细计划。"""
    steps_text = decompose(task=task)

    lines = [l.strip() for l in steps_text.split("\n") if l.strip() and l.strip()[0].isdigit()]
    assessments = []
    for line in lines[:5]:
        a = assess(step=line)
        assessments.append(f"{line}\n   → {a}")

    return "\n\n".join(assessments)


if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "构建一个带认证的 REST API"
    result = plan(task=task)
    print(result)
```

**`SKILL.md`：**
```markdown
# my-agentic-skill

使用 Agentic Programming 进行任务规划和分解，自动追踪上下文。

## 用法

当用户要求规划、分解或拆解任务时，运行：

\`\`\`bash
python3 ~/.openclaw/workspace/skills/my-agentic-skill/scripts/analyze.py "任务描述"
\`\`\`
```

## 用法 2：在 Agent 脚本中作为 Python 库

如果你的 OpenClaw agent 运行 Python 脚本，可以直接导入 agentic function：

```python
"""
OpenClaw agent 调用的代码审查脚本。
"""
from openprogram import agentic_function
from openprogram.providers import ClaudeCodeRuntime

runtime = ClaudeCodeRuntime(model="haiku")


@agentic_function
def review_code(code, language="python"):
    """审查代码的 bug、风格问题和改进建议。"""
    return runtime.exec(content=[
        {"type": "text", "text": f"审查这段 {language} 代码。列出：\n1. Bug（如果有）\n2. 风格问题\n3. 改进建议\n\n```{language}\n{code}\n```"},
    ])


@agentic_function
def suggest_tests(code):
    """为代码建议测试用例。"""
    return runtime.exec(content=[
        {"type": "text", "text": f"为这段代码建议 3 个测试用例。每个给出：测试名称、输入、期望输出。\n\n```python\n{code}\n```"},
    ])


@agentic_function
def code_analysis(code):
    """完整代码分析：审查 + 测试建议。"""
    review = review_code(code=code)
    tests = suggest_tests(code=code)
    return f"## 代码审查\n{review}\n\n## 建议测试\n{tests}"
```

## 用法 3：MCP Tool 封装

把 agentic function 封装为 OpenClaw 可以调用的 MCP tool：

```python
#!/usr/bin/env python3
"""
MCP 兼容的 tool server，暴露 agentic function。
"""
import json
import sys

from openprogram import agentic_function
from openprogram.providers import ClaudeCodeRuntime

runtime = ClaudeCodeRuntime(model="haiku")


@agentic_function
def summarize_text(text, style="bullet_points"):
    """按指定风格总结文本。"""
    style_instructions = {
        "bullet_points": "用 3-5 个要点总结。",
        "one_paragraph": "用一段话总结。",
        "eli5": "用 5 岁小孩能听懂的话解释。",
    }
    instruction = style_instructions.get(style, style_instructions["bullet_points"])

    return runtime.exec(content=[
        {"type": "text", "text": f"{instruction}\n\n文本：\n{text}"},
    ])


if __name__ == "__main__":
    request = json.loads(sys.stdin.read())
    tool = request.get("tool")
    args = request.get("args", {})

    if tool == "summarize":
        result = summarize_text(**args)
        print(json.dumps({"result": result}))
    else:
        print(json.dumps({"error": f"未知工具: {tool}"}))
```

## 为什么在 OpenClaw 中用 Agentic Programming？

| 不用 Agentic Programming | 用 Agentic Programming |
|---|---|
| Agent 在一次 LLM 调用中完成所有推理 | 推理拆分为聚焦的函数调用 |
| 上下文无限增长 | 上下文是结构化的树，自动摘要 |
| 难以调试 agent "想了什么" | 完整执行树：`context.tree()`、`context.save()` |
| 重试 = 重试整个 agent 回合 | 重试 = 只重试失败的函数 |

## 建议

1. **用 `ClaudeCodeRuntime` 快速上手** — 不需要额外 API key，装了 Claude Code 就行。
2. **生产环境用 `AnthropicRuntime`** — 更快，支持图片，支持 prompt caching。
3. **保存执行 trace** — `context.save("trace.jsonl")` 对调试非常有价值。
4. **保持函数小而精** — 每个 `@agentic_function` 只做一件事，用 Python 组合它们。
