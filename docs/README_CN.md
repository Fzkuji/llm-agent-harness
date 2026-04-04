<p align="center">
  <h1 align="center">🧬 Agentic Programming</h1>
  <p align="center">
    <strong>会思考的 Python 函数。</strong><br>
    一种 Python 与大模型协同执行函数的编程范式。
  </p>
  <p align="center">
    <a href="#快速开始">快速开始</a> •
    <a href="#核心思想">核心思想</a> •
    <a href="#api">API</a> •
    <a href="#集成">集成</a> •
    <a href="../README.md">English</a>
  </p>
</p>

> 🚀 **这是一个范式提案。** 我们提出了一种全新的 LLM 编程思路。这里的代码是参考实现——欢迎你基于这些想法，用任何语言、任何场景，构建自己的版本。

---

## 问题

<p align="center">
  <img src="../docs/images/the_problem.png" alt="问题：LLM 控制路径" width="800">
</p>

核心问题：**LLM 控制了流程。** 你让一个推理引擎同时当调度器、状态机和格式验证器。这不是它擅长的。

- 🎰 **不可控** — 你设计了 A → B → C，但 LLM 可能跳过 B、重复 A、或发明步骤 D。Skills 和 prompt 只是“建议”，不是“指令”。
- 📈 **上下文爆炸** — 每次往返都加内容。第 10 步时 LLM 已在读 50K token 的历史记录。
- 🎯 **没有保证** — 要 JSON？可能加 markdown。要 3 步？可能做 7 步。LLM *理解*指令，但不*执行*指令。

## 思路

<p align="center">
  <img src="../docs/images/the_idea.png" alt="思路：Python 控制流程，LLM 只做推理" width="800">
</p>

**把流程控制权还给 Python。让 LLM 专注推理。**

Python 负责调度、循环、错误处理和数据流。LLM 只在需要时回答问题。

- **确定性流程** — Python 控制 `if/else/for/while`。执行路径是保证的，不是建议的。
- **最少 LLM 调用** — 只在需要推理时调用 LLM。2 次调用，不是 10 次。
- **Docstring = Prompt** — 改函数注释就改 LLM 行为。不需要单独的 prompt 文件。

```python
@agentic_function
def observe(task):
    """观察屏幕，描述你看到的内容。"""
    
    img = take_screenshot()       # Python：确定性操作
    ocr = run_ocr(img)            # Python：确定性操作
    
    return runtime.exec(content=[ # LLM：推理
        {"type": "text", "text": f"任务: {task}\nOCR: {ocr}"},
        {"type": "image", "path": img},
    ])
```

**Docstring = Prompt。** 改注释就改行为。其他都是普通 Python。

---

## 快速开始

```bash
git clone https://github.com/Fzkuji/Agentic-Programming.git
cd Agentic-Programming
pip install -e .
```

### 用 Claude Code（不需要 API key）

```bash
# 先装 Claude Code CLI：npm install -g @anthropic-ai/claude-code && claude login
python examples/quickstart.py
```

### 用 OpenClaw

```bash
pip install -e /path/to/Agentic-Programming
```

```python
from agentic import agentic_function
from agentic.providers import ClaudeCodeRuntime
from agentic.meta_function import create

runtime = ClaudeCodeRuntime()

# 用 create() 创建函数，后续可以反复使用
summarize = create("把文本总结成 3 个要点", runtime=runtime)
result = summarize(text="你的文本...")
```

### 用 API Key（Anthropic / OpenAI / Gemini）

```bash
export ANTHROPIC_API_KEY=sk-ant-...    # 或 OPENAI_API_KEY / GEMINI_API_KEY
python examples/quickstart.py
```

```python
from agentic.providers import AnthropicRuntime   # 或 OpenAIRuntime、GeminiRuntime
runtime = AnthropicRuntime(model="claude-sonnet-4-20250514")
```

> 📖 完整指南：[Getting Started](GETTING_STARTED.md) • [Claude Code](INTEGRATION_CLAUDE_CODE.md) • [OpenClaw](INTEGRATION_OPENCLAW.md)

---

## 核心思想

### 1. 函数调用大模型

每个 `@agentic_function` 都可以调 `runtime.exec()` 来请求 LLM。框架自动把执行上下文（之前发生了什么）注入到 prompt 中。

```python
@agentic_function
def login_flow(username, password):
    """完成登录流程。"""
    observe(task="找到登录表单")
    click(element="登录按钮")
    return verify(expected="仪表盘")
```

### 2. 上下文自动追踪

每次调用创建一个 **Context** 节点，节点组成树：

```
login_flow ✓ 8.8s
├── observe ✓ 3.1s → "在 (200, 300) 处找到登录表单"
├── click ✓ 2.5s → "点击了登录按钮"
└── verify ✓ 3.2s → "确认进入仪表盘"
```

`verify` 调用 LLM 时，自动看到 `observe` 和 `click` 的返回结果。不需要手动管理上下文。

### 3. 函数生成函数

```python
from agentic.meta_function import create

summarize = create("把文本总结成3个要点", runtime=runtime)
result = summarize(text="很长的文章...")
```

LLM 写代码，框架验证并沙箱执行。你得到一个真正的 `@agentic_function`。

### 4. 自动错误恢复

```python
runtime = Runtime(call=my_llm, max_retries=2)  # 失败自动重试

# 或者修复损坏的函数：
from agentic.meta_function import fix
fixed_fn = fix(fn=broken_fn, runtime=runtime, instruction="用 label 代替坐标")
```

---

## API

| 组件 | 功能 |
|------|------|
| [`@agentic_function`](api/agentic_function.md) | 装饰器。记录执行到 Context 树 |
| [`Runtime`](api/runtime.md) | LLM 连接。`exec()` 自动注入上下文 |
| [`Context`](api/context.md) | 执行树。`tree()`、`save()`、`traceback()` |
| [`create()`](api/meta_function.md) | 从描述生成新函数 |
| [`fix()`](api/meta_function.md) | 用 LLM 修复损坏的函数 |

### 内置 Provider

```python
from agentic.providers import AnthropicRuntime   # Claude（支持 prompt caching）
from agentic.providers import OpenAIRuntime       # GPT（支持 response_format）
from agentic.providers import GeminiRuntime       # Gemini
from agentic.providers import ClaudeCodeRuntime   # Claude Code CLI（无需 API key）
```

---

## 对比

|  | Tool-Calling / MCP | Agentic Programming |
|--|---------------------|---------------------|
| **谁调度？** | LLM | Python |
| **函数包含** | 纯代码 | 代码 + LLM 推理 |
| **上下文** | 一整段对话 | 结构化的树 |
| **Prompt** | 写死在 agent 里 | Docstring = prompt |

MCP 是 *传输层*。Agentic Programming 是 *执行模型*。两者正交。

---

## 安装

```bash
pip install -e .                    # 核心（零依赖）
pip install -e ".[anthropic]"       # + Claude
pip install -e ".[openai]"          # + GPT
pip install -e ".[gemini]"          # + Gemini
pip install -e ".[all]"             # 全部
```

## 集成

把 Agentic Programming 和你现有的工具一起用：

| 指南 | 说明 |
|------|------|
| [Getting Started](GETTING_STARTED.md) | 3 分钟上手，provider 对比，可运行示例 |
| [Claude Code 集成](INTEGRATION_CLAUDE_CODE.md) | 不需要 API key，用 Claude Code CLI |
| [OpenClaw 集成](INTEGRATION_OPENCLAW.md) | 作为 OpenClaw skill 或 MCP tool |
| [API 参考](API.md) | 完整 API 文档 |

---

## 许可证

MIT
