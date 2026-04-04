# Claude Code Integration | Claude Code 集成指南

[English](#english) | [中文](#中文)

---

<a id="english"></a>

## What Is This?

`ClaudeCodeRuntime` lets you use Agentic Programming **without any API key**. It routes LLM calls through the [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code), which uses your Claude Code subscription.

If you have `claude` installed and logged in, you're ready to go.

## Prerequisites

1. **Install Claude Code CLI:**
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```

2. **Log in:**
   ```bash
   claude login
   ```

3. **Verify it works:**
   ```bash
   claude -p "Hello, world!"
   ```

That's all the setup needed. No API keys, no environment variables.

## Basic Usage

```python
from agentic import agentic_function
from agentic.providers import ClaudeCodeRuntime

# No API key needed — uses Claude Code subscription
runtime = ClaudeCodeRuntime(model="sonnet")

@agentic_function
def explain(concept):
    """Explain a concept clearly and concisely."""
    return runtime.exec(content=[
        {"type": "text", "text": f"Explain '{concept}' in 2-3 sentences. Be clear and concise."},
    ])

result = explain(concept="gradient descent")
print(result)
```

## Configuration Options

```python
runtime = ClaudeCodeRuntime(
    model="sonnet",       # Model name (passed to --model flag)
    timeout=120,          # Max seconds per CLI call (default: 120)
    cli_path=None,        # Path to claude binary (auto-detected)
)
```

### Model Names

The `model` parameter is passed directly to `claude -p --model <model>`. Common values:

| Model | Description |
|-------|-------------|
| `"sonnet"` | Claude Sonnet (default, fast & capable) |
| `"opus"` | Claude Opus (most capable) |
| `"haiku"` | Claude Haiku (fastest, cheapest) |

## How It Works

Under the hood, `ClaudeCodeRuntime`:

1. Combines all content blocks into a text prompt
2. Calls `claude -p <prompt>` as a subprocess
3. Returns the CLI's stdout as the result

```
Your Python code
    → @agentic_function decorator (records context)
        → runtime.exec() (builds prompt with context)
            → claude -p "..." (CLI call)
                → Claude API (via subscription)
            ← response text
        ← recorded in Context tree
    ← return value
```

## Limitations

- **Text only.** Images, audio, and file blocks are converted to text placeholders (`[Image: path]`). For multimodal input, use `AnthropicRuntime` with an API key.
- **Subprocess overhead.** Each call spawns a new process (~0.5-1s overhead). For latency-sensitive applications, use direct API providers.
- **No streaming.** Results are returned after the full response is generated.
- **Timeout.** Long responses may hit the default 120s timeout. Increase with `timeout=300`.

## Complete Example

```python
"""
Claude Code integration demo — no API key needed.
Demonstrates multi-step agentic workflow with context tracking.
"""
from agentic import agentic_function
from agentic.providers import ClaudeCodeRuntime

runtime = ClaudeCodeRuntime(model="sonnet")


@agentic_function
def brainstorm(topic):
    """Generate 3 creative ideas about a topic."""
    return runtime.exec(content=[
        {"type": "text", "text": f"Generate exactly 3 creative ideas about: {topic}\nNumber them 1-3, one per line."},
    ])


@agentic_function
def evaluate(idea):
    """Rate an idea's feasibility on a scale of 1-10 with brief reasoning."""
    return runtime.exec(content=[
        {"type": "text", "text": f"Rate this idea's feasibility (1-10) and explain in one sentence:\n{idea}"},
    ])


@agentic_function
def ideate(topic):
    """Brainstorm ideas and evaluate each one."""
    ideas_text = brainstorm(topic=topic)
    print(f"💡 Ideas:\n{ideas_text}\n")

    lines = [l.strip() for l in ideas_text.split("\n") if l.strip() and l.strip()[0].isdigit()]
    for line in lines[:3]:
        rating = evaluate(idea=line)
        print(f"  📊 {rating}\n")

    return runtime.exec(content=[
        {"type": "text", "text": "Pick the best idea from the evaluation above and explain why in 2 sentences."},
    ])


if __name__ == "__main__":
    result = ideate(topic="improving developer productivity with AI")
    print(f"\n🏆 Best idea:\n{result}")
    print(f"\n🌳 Execution tree:")
    print(ideate.context.tree())
```

## Troubleshooting

| Error | Solution |
|-------|----------|
| `FileNotFoundError: Claude Code CLI not found` | Install: `npm install -g @anthropic-ai/claude-code` |
| `ConnectionError: Claude Code CLI not logged in` | Run: `claude login` |
| `TimeoutError: Claude Code CLI timed out` | Increase timeout: `ClaudeCodeRuntime(timeout=300)` |
| `RuntimeError: Claude Code CLI error` | Check `claude -p "test"` works manually |

---

---

<a id="中文"></a>

## 这是什么？

`ClaudeCodeRuntime` 让你**不需要任何 API key** 就能使用 Agentic Programming。它通过 [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) 路由 LLM 调用，使用你的 Claude Code 订阅。

只要你装了 `claude` 并登录了，就可以直接用。

## 前置条件

1. **安装 Claude Code CLI：**
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```

2. **登录：**
   ```bash
   claude login
   ```

3. **验证：**
   ```bash
   claude -p "Hello, world!"
   ```

不需要 API key，不需要环境变量。

## 基本用法

```python
from agentic import agentic_function
from agentic.providers import ClaudeCodeRuntime

# 不需要 API key，使用 Claude Code 订阅
runtime = ClaudeCodeRuntime(model="sonnet")

@agentic_function
def explain(concept):
    """清晰简洁地解释一个概念。"""
    return runtime.exec(content=[
        {"type": "text", "text": f"用 2-3 句话解释 '{concept}'。要清晰简洁。"},
    ])

result = explain(concept="梯度下降")
print(result)
```

## 配置选项

```python
runtime = ClaudeCodeRuntime(
    model="sonnet",       # 模型名（传给 --model 参数）
    timeout=120,          # 每次 CLI 调用的超时秒数（默认 120）
    cli_path=None,        # claude 二进制文件路径（自动检测）
)
```

### 模型名称

`model` 参数直接传给 `claude -p --model <model>`。常用值：

| 模型 | 说明 |
|------|------|
| `"sonnet"` | Claude Sonnet（默认，速度与能力的平衡） |
| `"opus"` | Claude Opus（最强） |
| `"haiku"` | Claude Haiku（最快最便宜） |

## 工作原理

`ClaudeCodeRuntime` 的内部流程：

1. 把所有 content block 合并为文本 prompt
2. 调用 `claude -p <prompt>`（子进程）
3. 返回 CLI 的 stdout 作为结果

```
你的 Python 代码
    → @agentic_function 装饰器（记录上下文）
        → runtime.exec()（构建带上下文的 prompt）
            → claude -p "..."（CLI 调用）
                → Claude API（通过订阅）
            ← 响应文本
        ← 记录到 Context 树
    ← 返回值
```

## 限制

- **仅支持文本。** 图片、音频、文件 block 会转为文本占位符（`[Image: path]`）。要用多模态输入，请用 `AnthropicRuntime` + API key。
- **子进程开销。** 每次调用启动一个新进程（约 0.5-1 秒开销）。对延迟敏感的应用请用直接 API provider。
- **不支持流式输出。** 结果在完整生成后返回。
- **超时。** 长响应可能触发默认 120 秒超时。用 `timeout=300` 增加。

## 完整示例

```python
"""
Claude Code 集成 demo — 不需要 API key。
演示带上下文追踪的多步 agentic 工作流。
"""
from agentic import agentic_function
from agentic.providers import ClaudeCodeRuntime

runtime = ClaudeCodeRuntime(model="sonnet")


@agentic_function
def brainstorm(topic):
    """针对一个话题生成 3 个创意想法。"""
    return runtime.exec(content=[
        {"type": "text", "text": f"针对以下话题生成 3 个创意想法：{topic}\n编号 1-3，每行一个。"},
    ])


@agentic_function
def evaluate(idea):
    """用 1-10 分评价一个想法的可行性，附简短理由。"""
    return runtime.exec(content=[
        {"type": "text", "text": f"用 1-10 分评价这个想法的可行性，并用一句话解释：\n{idea}"},
    ])


@agentic_function
def ideate(topic):
    """头脑风暴并评估每个想法。"""
    ideas_text = brainstorm(topic=topic)
    print(f"💡 想法：\n{ideas_text}\n")

    lines = [l.strip() for l in ideas_text.split("\n") if l.strip() and l.strip()[0].isdigit()]
    for line in lines[:3]:
        rating = evaluate(idea=line)
        print(f"  📊 {rating}\n")

    return runtime.exec(content=[
        {"type": "text", "text": "从上面的评估中选出最好的想法，用 2 句话解释为什么。"},
    ])


if __name__ == "__main__":
    result = ideate(topic="用 AI 提高开发者效率")
    print(f"\n🏆 最佳想法：\n{result}")
    print(f"\n🌳 执行树：")
    print(ideate.context.tree())
```

## 故障排查

| 错误 | 解决方案 |
|------|----------|
| `FileNotFoundError: Claude Code CLI not found` | 安装：`npm install -g @anthropic-ai/claude-code` |
| `ConnectionError: Claude Code CLI not logged in` | 运行：`claude login` |
| `TimeoutError: Claude Code CLI timed out` | 增加超时：`ClaudeCodeRuntime(timeout=300)` |
| `RuntimeError: Claude Code CLI error` | 手动检查 `claude -p "test"` 是否正常 |
