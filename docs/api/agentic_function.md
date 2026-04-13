# agentic_function

> Source: [`agentic/function.py`](../../agentic/function.py)

装饰器类。把普通 Python 函数变成 Agentic Function，自动记录执行过程到 Context 树。

---

## Class: `agentic_function`

```python
class agentic_function(fn=None, *, render="summary", summarize=None, compress=False, input=None)
```

用法跟普通装饰器一样，但内部是一个类（类似 `torch.no_grad`）。

### 构造参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `fn` | `Callable \| None` | `None` | 被装饰的函数（无括号时自动传入） |
| `render` | `str` | `"summary"` | 其他函数通过 `summarize()` 看到此节点时的详细程度 |
| `summarize` | `dict \| None` | `None` | 此函数调用 `runtime.exec()` 时，`summarize()` 的参数 |
| `compress` | `bool` | `False` | 完成后是否在 `summarize()` 中隐藏子节点 |
| `input` | `dict \| None` | `None` | 参数的 UI 元数据，用于 Visualizer 生成结构化输入表单 |

### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `context` | `Context \| None` | 最近一次顶层调用完成后的 Context 树。子函数调用不设置此属性 |

### render 级别

| 值 | 其他函数看到什么 |
|---|---|
| `"summary"` | 函数名、docstring、参数、输出、状态、耗时（默认） |
| `"detail"` | summary 的全部内容 + LLM raw_reply |
| `"result"` | 函数名 + 返回值 |
| `"silent"` | 不显示 |

### summarize 参数

控制此函数在调用 LLM 时看到多少上下文：

```python
summarize=None                            # 默认：全部祖先 + 全部兄弟
summarize={"depth": 1, "siblings": 3}     # 只看父节点 + 最近 3 个兄弟
summarize={"depth": 0, "siblings": 0}     # 不看任何上下文
```

### 自动行为

装饰后的函数在调用时自动：

1. **创建** Context 节点（记录函数名、docstring、参数）
2. **挂载** 到父节点的 `children` 列表（如果有父函数）
3. **执行** 原函数
4. **记录** 返回值或异常、耗时
5. **保存** 如果是顶层函数，自动保存 Context 树到 `agentic/logs/`

---

## 使用方式

### 基本用法（无参数）

```python
from agentic import agentic_function

@agentic_function
def observe(task):
    """Look at the screen and describe what you see."""
    return runtime.exec(content=[
        {"type": "text", "text": f"Find: {task}"},
    ])
```

### 带参数

```python
@agentic_function(render="detail", summarize={"depth": 1, "siblings": 3}, compress=True)
def navigate(target):
    """Navigate to a target UI element."""
    observe(f"find {target}")
    act(target)
    return verify(target)
```

### 嵌套调用

```python
@agentic_function
def login_flow(username, password):
    """Complete login flow."""
    observe(task="find login form")     # 子节点 1
    click(element="login button")       # 子节点 2
    return verify(expected="dashboard") # 子节点 3

# 调用
result = login_flow(username="admin", password="secret")

# 查看 Context 树
print(login_flow.context.tree())
# login_flow ✓ 8800ms → ...
#   observe ✓ 3100ms → ...
#   click ✓ 2500ms → ...
#   verify ✓ 3200ms → ...
```

### compress 示例

```python
@agentic_function(compress=True)
def navigate(target):
    """Navigate to target."""
    observe(f"find {target}")   # 这些子节点
    act(target)                 # 在 compress=True 后
    return verify(target)       # 对其他函数不可见

@agentic_function
def main_task():
    navigate("login")    # 其他函数只看到 navigate 的返回值
    navigate("settings") # 不看到里面的 observe/act/verify
    return do_something()
```

### Async 支持

```python
@agentic_function
async def async_observe(task):
    """Async observation."""
    return await runtime.async_exec(content=[
        {"type": "text", "text": f"Find: {task}"},
    ])

import asyncio
result = asyncio.run(async_observe(task="find button"))
```

---

## input 参数规范

`input` 定义每个函数参数的 UI 元数据。Visualizer 根据这些信息生成结构化输入表单，替代手动拼接 `run func key=val` 命令。

### 数据结构

```python
input: dict[str, dict]  # 参数名 → UI 配置
```

每个参数的 UI 配置支持以下字段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `description` | `str` | 从 docstring Args 提取 | 参数的简短描述，显示在参数名旁边 |
| `placeholder` | `str` | `""` | 输入框的占位文本，应为输入示例（如 `"e.g. Hello world"`） |
| `multiline` | `bool` | `True`（str 类型） / `False`（其他） | 是否渲染为多行文本框 |
| `options` | `list[str]` | `None` | 有限选项列表，渲染为下拉选择框 |
| `hidden` | `bool` | `False` | 是否在表单中隐藏（用于 `runtime` 等框架参数） |

### 信息来源优先级

参数的 UI 信息从三个来源合并，优先级从高到低：

1. **`input={}` 显式定义** — 最高优先级，覆盖一切
2. **docstring `Args:` 段** — 提取 `description`
3. **函数签名** — 提取 `name`、`type`、`default`、`required`

### 设计原则：输入类型层级

函数参数的输入方式遵循一个核心原则：**尽可能降低用户的认知负担**。

按优先级从高到低：

| 优先级 | 输入方式 | 适用场景 | 示例 |
|--------|---------|---------|------|
| 1 | **自由文本** | 开放式、描述性参数，无法预定义选项 | `description`、`task`、`instruction`、`text` |
| 2 | **选择**（toggle / chips） | 有限选项、bool、枚举 | `style`（academic/casual）、`as_skill`（Yes/No） |
| 3 | **结构化输入** | 必须严格格式的参数（尽量避免） | `missing`（JSON list）、`code`（代码块） |

**关键规则：**

- **能用文本就不要用选择**：如果参数的含义是"描述一件事"，用文本框，不要试图把它拆成选项
- **能用选择就不要用输入**：如果参数只有有限个合法值（bool、枚举、固定范围），**必须**用选择控件。用户不应该猜"该填什么"
- **不要让用户猜格式**：如果参数需要特定格式（JSON、代码），在 `placeholder` 中给出完整示例

**反面示例（不要这样做）：**

```python
# 错误：bool 用文本输入
"as_skill": {"placeholder": "True or False"}   # 用户不知道该写 True/true/yes/1？

# 错误：有限选项用文本输入
"style": {"placeholder": "输入风格"}            # 用户不知道有哪些风格可选

# 错误：placeholder 重复 description
"text": {
    "description": "The text to analyze",
    "placeholder": "The text to analyze",       # 没提供任何额外信息
}
```

**正面示例：**

```python
# bool → 自动渲染为 Yes/No toggle（不需要 placeholder）
"as_skill": {"description": "Also create a SKILL.md"}

# 有限选项 → 渲染为可点击的选项 chips
"style": {"description": "Output style", "options": ["academic", "casual", "concise"]}

# 自由文本 → placeholder 是具体的输入示例
"text": {"description": "Text to analyze", "placeholder": "e.g. I love this product!"}
```

### 自动推断与渲染规则

未在 `input` 中声明的参数，按以下规则自动处理：

| 条件 | 自动行为 |
|------|---------|
| 参数名为 `runtime`/`exec_runtime`/`review_runtime`/`callback` | 自动隐藏 |
| `input` 中设置 `hidden: True` | 隐藏 |
| 类型为 `bool` | 渲染为 **Yes/No toggle**，默认值自动高亮 |
| 设置了 `options` 列表 | 渲染为 **可点击选项组**（chips），默认值自动高亮 |
| 类型为 `str` 且 `multiline` 未声明 | 渲染为 **多行文本框** |
| 类型为 `int`/`float`/`dict`/`list` | 渲染为 **单行输入框** |
| 有默认值 | 标记为 optional |
| 无默认值 | 标记为 required（`*`） |

### 完整示例

```python
@agentic_function(input={
    "text": {
        "description": "Text to polish",
        "placeholder": "e.g. This paper proposes a novel approach...",
    },
    "style": {
        "description": "Output style",
        "options": ["academic", "casual", "concise"],
    },
    "runtime": {"hidden": True},
    "verbose": {
        "description": "Print debug info",
    },
})
def polish_text(text: str, style: str, runtime: Runtime, verbose: bool = False) -> str:
    """Polish text in the given style.

    Args:
        text: The text to polish.
        style: academic, casual, or concise.
        runtime: LLM runtime instance.
        verbose: Print debug info.
    """
    ...
```

Visualizer 渲染的表单：

```
┌─────────────────────────────────────────────────────┐
│ polish_text  Polish text in the given style.      × │
├─────────────────────────────────────────────────────┤
│ text  str  *  Text to polish                        │
│ ┌─────────────────────────────────────────────────┐ │
│ │ e.g. This paper proposes a novel approach...    │ │
│ └─────────────────────────────────────────────────┘ │
│                                                     │
│ style  str  *  Output style                         │
│ ┌──────────┐ ┌────────┐ ┌─────────┐                │
│ │ academic │ │ casual │ │ concise │                  │
│ └──────────┘ └────────┘ └─────────┘                 │
│                                                     │
│ verbose  bool  optional  Print debug info           │
│ ┌─────┐ ┌────┐                                      │
│ │ Yes │ │ No │  ← No 高亮（默认 False）               │
│ └─────┘ └────┘                                      │
├─────────────────────────────────────────────────────┤
│ Esc to cancel                               [▶]    │
└─────────────────────────────────────────────────────┘
```

- `runtime` → 隐藏（框架注入）
- `text` → 多行文本框 + placeholder 示例
- `style` → 选项 chips（三选一）
- `verbose` → Yes/No toggle（默认 No 高亮）

### 编写规范

**所有入口函数**（用户可从 Visualizer 直接调用的函数）**必须**声明 `input`。

检查清单：

1. **隐藏框架参数** — `runtime`、`callback` 等标记 `hidden: True`
2. **每个可见参数提供 `description`** — 简短描述，显示在参数名旁边
3. **文本参数提供 `placeholder`** — 写具体示例，不要重复 description
4. **bool 参数** — 只需 `description`，自动渲染为 Yes/No toggle
5. **有限选项参数** — **必须**提供 `options` 列表。如果只有 2-5 个合法值，就是有限选项
6. **不要让用户猜格式** — 如果必须用结构化输入，placeholder 给完整示例

```python
@agentic_function(input={
    # 自由文本：开放式描述
    "task": {
        "description": "What to do",
        "placeholder": "e.g. Write a hello world script",
    },
    # 选择：有限选项
    "level": {
        "description": "Quality level",
        "options": ["draft", "standard", "polished"],
    },
    # 选择：bool
    "verbose": {
        "description": "Show detailed output",
    },
    # 隐藏：框架参数
    "runtime": {"hidden": True},
})
def my_function(task: str, level: str = "standard",
                verbose: bool = False, runtime: Runtime = None) -> str:
    ...
```

**内部函数**（以 `_` 开头或只被其他函数调用的）不需要声明 `input`。
