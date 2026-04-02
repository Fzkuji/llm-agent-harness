# Agentic Context

> 用 `@agentic_function` 装饰器自动追踪调用栈。层级由 Python 调用关系强制决定，不可能传错。

---

## Context

一个函数的执行记录。

```python
@dataclass
class Context:
    name: str                    # 函数名（自动从 __name__ 取）
    prompt: str = ""             # docstring（自动从 __doc__ 取）
    input: dict = None           # 发给 LLM 的数据（用户手动设置）
    output: Any = None           # 返回值（自动记录）
    error: str = ""              # 错误信息（自动捕获）
    status: str = "running"      # running / success / error（自动管理）
    children: list = None        # 子函数的 Context（自动挂载）
    parent: Context = None       # 父 Context（自动设置）
    expose: str = "summary"      # 对外暴露粒度（用户可配置）
    start_time: float = 0        # 开始时间（自动记录）
    end_time: float = 0          # 结束时间（自动记录）
```

---

## @agentic_function

装饰器自动做五件事：
1. 从 `__name__` 取函数名，从 `__doc__` 取 prompt
2. 创建 Context 节点，挂到当前父节点的 children
3. 设为当前活跃 Context（子函数自动成为 child）
4. 函数结束后记录 output / error / 耗时
5. 恢复父节点为当前活跃 Context

```python
from agentic import agentic_function, get_context

@agentic_function
def observe(task):
    """Look at the screen and find all visible UI elements.
    Check if the target described in task is visible."""
    
    ctx = get_context()              # 需要时才取
    ctx.input = {"task": task}       # 手动设置输入
    
    img = take_screenshot()
    ocr = run_ocr(img)               # 自动成为 observe 的 child
    elements = detect_all(img)        # 自动成为 observe 的 child
    
    reply = llm_call(
        prompt=ctx.prompt,            # = observe.__doc__
        input=ctx.input,
        context=ctx.summarize(),      # 到目前为止的上下文摘要
    )
    return parse(reply)               # 自动记录为 ctx.output
```

**用户不需要传 ctx 参数。层级由 Python 调用关系强制决定。**

---

## expose（暴露粒度）

控制 `sibling_summaries()` 返回这个函数时的粒度。通过 decorator 参数设置：

```python
@agentic_function                      # 默认 expose="summary"
def observe(task):
    ...

@agentic_function(expose="detail")     # 兄弟能看到完整输入输出
def observe(task):
    ...

@agentic_function(expose="silent")     # 兄弟完全看不到
def internal_helper(x):
    ...
```

| expose | `sibling_summaries()` 返回的内容 |
|--------|--------------------------------|
| `"trace"` | prompt + 完整输入输出 + LLM 原始回复 |
| `"detail"` | 完整输入和输出 |
| `"summary"` | 一句话摘要（默认） |
| `"result"` | 只有返回值 |
| `"silent"` | 不出现在兄弟摘要中 |

---

## get_context()

在函数内部获取当前 Context。用于：
- 设置 `ctx.input`（告诉 Context 你发了什么给 LLM）
- 调用 `ctx.summarize()`（获取到目前为止的上下文摘要）
- 读取 `ctx.prompt`（= 函数的 docstring）

```python
@agentic_function
def act(target, location):
    """Click the specified target at the given location."""
    ctx = get_context()
    ctx.input = {"target": target, "location": location}
    
    # 获取到目前为止的上下文摘要
    summary = ctx.summarize()
    # → "navigate 调用了 observe(find login) → 找到目标在 (347,291)"
    
    click(location)
    return {"clicked": True}
```

**不调 `get_context()` 也完全没问题** — Context 照样自动追踪，只是你没手动设置 input。

## ctx.summarize()

返回到目前为止跟当前函数相关的所有上下文摘要：

- 父节点信息（谁调用了我）
- 之前兄弟的结果（按 expose level 裁剪）
- 当前函数的 prompt 和 input

摘要的详略程度由兄弟的 `expose` 设置决定。

---

## 完整示例

```python
from agentic import agentic_function, get_context

@agentic_function
def run_ocr(img):
    """Extract text from screenshot using OCR."""
    return {"texts": ["Login", "Password", "Submit"], "count": 3}

@agentic_function
def detect_all(img):
    """Detect all UI elements in screenshot."""
    return {"elements": ["button", "input", "link"], "count": 3}

@agentic_function
def observe(task):
    """Look at the screen and find all visible UI elements."""
    ctx = get_context()
    ctx.input = {"task": task}
    
    img = take_screenshot()
    ocr = run_ocr(img)           # 自动是 observe 的 child
    elements = detect_all(img)    # 自动是 observe 的 child
    
    reply = llm_call(ctx.prompt, input=ctx.input, context=ctx.summarize())
    return parse(reply)

@agentic_function
def act(target, location):
    """Click the specified target at the given location."""
    ctx = get_context()
    ctx.input = {"target": target, "location": location}
    click(location)
    return {"clicked": True}

@agentic_function
def navigate(target):
    """Navigate to the target by observing and acting."""
    obs = observe(task=f"find {target}")
    if obs["target_visible"]:
        result = act(target=target, location=obs["location"])
        return {"success": True}
    return {"success": False}

# 运行
navigate("login")
```

执行后 Context 树：

```
navigate ✓ 3200ms → {success: True}
├── observe ✓ 1200ms → {target_visible: True, location: [347, 291]}
│   ├── run_ocr ✓ 50ms → {texts: [...], count: 3}
│   └── detect_all ✓ 80ms → {elements: [...], count: 3}
└── act ✓ 820ms → {clicked: True}
```

---

## Traceback

报错时自动生成调用链：

```
Agentic Traceback:
  navigate(target="login") → error, 4523ms
    observe(task="find login") → success, 1200ms
    act(target="login") → error, 820ms: "element not interactable"
```

---

## 持久化

```python
root_ctx.save("logs/run.jsonl")    # 机器可读
root_ctx.save("logs/run.md")       # 人类可读
```

---

## 核心就三件事

1. **`@agentic_function` 自动追踪调用栈**（层级由 Python 调用关系强制决定）
2. **`expose` 控制对外暴露粒度**（默认 summary）
3. **`ctx.summarize()` 获取上下文摘要**（父节点 + 兄弟结果 + 当前 prompt/input）
