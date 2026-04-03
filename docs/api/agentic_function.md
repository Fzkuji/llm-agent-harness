# agentic_function

> Source: [`agentic/function.py`](../../agentic/function.py)

装饰器类。把普通 Python 函数变成 Agentic Function，自动记录执行过程到 Context 树。

---

## Class: `agentic_function`

```python
class agentic_function(fn=None, *, render="summary", summarize=None, compress=False)
```

用法跟普通装饰器一样，但内部是一个类（类似 `torch.no_grad`）。

### 构造参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `fn` | `Callable \| None` | `None` | 被装饰的函数（无括号时自动传入） |
| `render` | `str` | `"summary"` | 其他函数通过 `summarize()` 看到此节点时的详细程度 |
| `summarize` | `dict \| None` | `None` | 此函数调用 `runtime.exec()` 时，`summarize()` 的参数 |
| `compress` | `bool` | `False` | 完成后是否在 `summarize()` 中隐藏子节点 |

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
