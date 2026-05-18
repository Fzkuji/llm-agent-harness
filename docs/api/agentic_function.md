# agentic_function

> Source: [`openprogram/agentic_programming/function.py`](../../openprogram/agentic_programming/function.py)

`@agentic_function` 把普通 Python 函数变成 Agentic Function:每次调用记录为 session DAG 的一个 `code` 节点,函数体内的 `runtime.exec` 调用记录为 `llm` 节点。

完整的编写规范——文件布局、docstring 与 `content` 的分工、参数元数据、校验清单、冒烟测试——见 [`skills/agentic-programming/SKILL.md`](../../skills/agentic-programming/SKILL.md)。本文只列装饰器本身。

## 用法

```python
from openprogram import agentic_function

@agentic_function
def f(x: str, runtime) -> str:
    """One-line summary of what f does."""
    return runtime.exec(content=[{"type": "text", "text": f"...{x}..."}])
```

裸用 `@agentic_function` 或带参数 `@agentic_function(...)` 都可以。

## 装饰器参数

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `expose` | `str` | `"io"` | DAG 可见性。`"io"` = 后续 LLM 调用看到本函数的调用 + 返回值,看不到内部 LLM 调用;`"full"` = 内部调用也可见;`"hidden"` = 完全不写 DAG 节点 |
| `render_range` | `dict` | `None` | 限定本函数内部 `runtime.exec` 能看到的 DAG 历史范围。`{"depth": N, "siblings": M}` —— `depth` 限祖先层数,`siblings` 限同辈数。`{"depth":0,"siblings":0}` = 完全隔离 |
| `input` | `dict` | `None` | 每个参数的 UI 元数据(`description` / `placeholder` / `multiline` / `options` / `hidden` 等),WebUI 据此渲染输入表单 |
| `no_tools` | `bool` | `False` | `True` 时本函数的 `runtime.exec` 默认不带工具集 |
| `system` | `str` | `None` | 本函数 LLM 调用的 system prompt(调用期间盖到注入的 runtime 上,调用后恢复) |

函数名、参数名 / 类型 / 默认值、一句话摘要都从函数签名和 docstring 自动读取,不在装饰器里重复(见 SKILL.md §3)。

## 记录到 DAG

- **进入函数**:写一个 `code` 节点(`output=None`, `status="running"`),函数 docstring 一并存进该节点的 `metadata.doc`,渲染上下文时拼在 `函数名(参数)` 前面。
- **函数体内 `runtime.exec`**:每次调用写一个 `llm` 节点。
- **退出函数**:回填同一个 `code` 节点的 `output` / `status`。

`expose="hidden"` 时不写任何节点。standalone 运行(没安装 DAG store)时记录全部 no-op,函数照常执行。
