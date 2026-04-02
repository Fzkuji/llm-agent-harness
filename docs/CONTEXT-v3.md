# Agentic Context

> 每个 Agentic Function 有一个 Context。调用子函数时传入，子函数执行完写回。形成调用栈。

---

## Context

一个函数的执行记录。

```python
@dataclass
class Context:
    name: str               # 函数名
    prompt: str = ""        # docstring
    input: dict = None      # 发给 LLM 的数据
    output: Any = None      # LLM 返回的结果
    error: str = ""         # 错误信息
    children: list = None   # 子函数的 Context
    level: str = "summary"  # 对外暴露粒度：trace / detail / summary / result
```

---

## 规则

1. **每个函数创建自己的 Context**
2. **调用子函数时，把自己的 Context 传入**
3. **子函数完成后，自动挂到父 Context 的 children**
4. **LLM 调用时，从父 Context 读取之前兄弟的摘要**

---

## 用法

```python
def navigate(ctx: Context, target: str):
    """Navigate to the target."""
    
    obs_result = observe(ctx, task=f"find {target}")  # 返回解析后的结果
    
    if obs_result.target_visible:
        act_result = act(ctx, target=target, location=obs_result.location)
        return act_result


def observe(parent_ctx: Context, task: str):
    """Look at the screen and find all visible UI elements."""
    ctx = parent_ctx.child("observe", prompt=observe.__doc__)
    
    # Python 部分
    img = take_screenshot()
    ocr = run_ocr(img)
    ctx.input = {"task": task, "ocr": ocr, "image": img}
    
    # LLM 部分 — 自动拿到兄弟函数的摘要作为上下文
    reply = llm_call(
        prompt=ctx.prompt,
        input=ctx.input,
        context=ctx.sibling_summaries(),
    )
    
    ctx.output = parse(reply)  # ObserveResult
    return ctx.output           # 返回结果，不是 Context


def act(parent_ctx: Context, target: str, location: list):
    """Click the specified target at the given location."""
    ctx = parent_ctx.child("act", prompt=act.__doc__)
    
    ctx.input = {"target": target, "location": location}
    click(location)
    
    ctx.output = {"clicked": True, "target": target}
    return ctx.output
```

---

## 调用栈

执行后 Context 形成树：

```
navigate(target="login")
├── observe(task="find login")
│   input: screenshot + OCR(77)
│   output: {target_visible: true, location: [347, 291]}
├── act(target="login", location=[347, 291])
│   input: template_match
│   output: {clicked: true}
└── verify(expected="logged in")
    input: screenshot
    output: {verified: true}
```

---

## Level（暴露粒度）

子函数的信息传给父/兄弟时，按 level 裁剪：

| Level | 内容 | 示例 |
|-------|------|------|
| `trace` | 所有细节 | prompt + 原始 OCR 数据 + LLM 原始回复 |
| `detail` | 输入输出 | input: 77 OCR items, output: {found: true} |
| `summary` | 一句话 | "observe: found login button at (347, 291)" |
| `result` | 只有返回值 | {target_visible: true} |

默认 `summary`。函数自己声明自己的 level。

---

## Traceback

报错时生成调用链：

```
Agentic Traceback:
  navigate(target="login") → error
    observe(task="find login") → success, 1200ms
    act(target="login") → error: "element not interactable"
```

正常时生成摘要：

```
navigate ✓ 3200ms
├── observe ✓ 1200ms → found 156 elements
├── act ✓ 820ms → clicked login
└── verify ✓ 650ms → verified
```

---

## 持久化

```python
ctx.save("logs/run.jsonl")    # 机器可读
ctx.save("logs/run.md")       # 人类可读
```

就是把整棵树序列化。

---

## 核心就三件事

1. **Context 随函数调用传递**，形成树
2. **Level 控制暴露粒度**，父/兄弟只看摘要
3. **LLM 调用时从 Context 读取上下文**
