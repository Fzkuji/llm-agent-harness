# Runtime

> Source: [`agentic/runtime.py`](../../agentic/runtime.py)

LLM 运行时。封装 LLM provider，自动处理 Context 注入和记录。

---

## Class: `Runtime`

```python
class Runtime(call=None, model="default")
```

### 构造参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `call` | `Callable \| None` | `None` | LLM provider 函数。签名：`fn(content: list[dict], model: str, response_format: dict) -> str`。如果不传，需要子类化并重写 `_call()` |
| `model` | `str` | `"default"` | 默认模型名称，每次调用可覆盖 |

### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `model` | `str` | 默认模型名称 |

---

## 方法

### `exec()`

```python
Runtime.exec(content, context=None, response_format=None, model=None) -> str
```

调用 LLM，自动注入 Context。

**在 `@agentic_function` 内部调用时：**
1. 从 Context 树生成 execution context（调用 `summarize()`）
2. 把 context 作为第一个 text block 插入 content 列表
3. 调用 `_call()` 发送请求
4. 把回复记录到当前 Context 节点的 `raw_reply`

**在 `@agentic_function` 外部调用时：** 直接调用 LLM，不注入 context，不记录。

**每个 `@agentic_function` 最多调用一次 `exec()`。** 第二次调用会抛 `RuntimeError`。

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `content` | `list[dict]` | *(必填)* | 内容块列表（见下方格式） |
| `context` | `str \| None` | `None` | 手动覆盖自动生成的 context。`None` = 自动 |
| `response_format` | `dict \| None` | `None` | 输出格式约束（JSON schema），传给 `_call()` |
| `model` | `str \| None` | `None` | 覆盖默认模型 |

#### Content block 格式

```python
{"type": "text",  "text": "Find the login button."}
{"type": "image", "path": "screenshot.png"}
{"type": "audio", "path": "recording.wav"}
{"type": "file",  "path": "data.csv"}
```

#### 返回值

`str` — LLM 的回复文本。

#### 异常

- `RuntimeError` — 同一个 `@agentic_function` 内调用了两次
- `TypeError` — 传入了 async 的 call 函数（应使用 `async_exec()`）
- `NotImplementedError` — 没有配置 call 函数

---

### `async_exec()`

```python
await Runtime.async_exec(content, context=None, response_format=None, model=None) -> str
```

`exec()` 的异步版本。内部调用 `_async_call()`。

参数和行为与 `exec()` 相同。如果传入同步 call 函数，会自动适配（不报错）。

---

### `_call()`

```python
Runtime._call(content, model="default", response_format=None) -> str
```

实际调用 LLM 的方法。**子类化时重写此方法。**

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `content` | `list[dict]` | 完整的内容列表（context + 用户内容） |
| `model` | `str` | 模型名称 |
| `response_format` | `dict \| None` | 输出格式约束 |

#### 返回值

`str` — LLM 回复文本。

---

### `_async_call()`

```python
await Runtime._async_call(content, model="default", response_format=None) -> str
```

`_call()` 的异步版本。子类化时重写此方法以支持异步 provider。

---

## 使用方式

### 方式一：传入 call 函数

```python
from agentic import Runtime, agentic_function

def my_llm(content, model="sonnet", response_format=None):
    # 把 content 转成你的 provider 格式，发请求
    texts = [b["text"] for b in content if b["type"] == "text"]
    return call_my_api("\n".join(texts), model=model)

runtime = Runtime(call=my_llm, model="sonnet")

@agentic_function
def observe(task):
    """Look at the screen."""
    return runtime.exec(content=[
        {"type": "text", "text": f"Find: {task}"},
        {"type": "image", "path": "screenshot.png"},
    ])
```

### 方式二：子类化

```python
class AnthropicRuntime(Runtime):
    def __init__(self, api_key, model="sonnet"):
        super().__init__(model=model)
        self.client = anthropic.Anthropic(api_key=api_key)

    def _call(self, content, model="sonnet", response_format=None):
        messages_content = []
        for block in content:
            if block["type"] == "text":
                messages_content.append({"type": "text", "text": block["text"]})
        response = self.client.messages.create(
            model=model, max_tokens=1024,
            messages=[{"role": "user", "content": messages_content}],
        )
        return response.content[0].text

runtime = AnthropicRuntime(api_key="sk-...", model="claude-sonnet-4-20250514")
```

### 多个 Runtime 共存

```python
fast = Runtime(call=gemini_call, model="gemini-2.5-flash")
strong = Runtime(call=claude_call, model="sonnet")

@agentic_function
def observe(task):
    """Quick observation with cheap model."""
    return fast.exec(content=[...])

@agentic_function
def plan(goal):
    """Complex planning with strong model."""
    return strong.exec(content=[...])
```
