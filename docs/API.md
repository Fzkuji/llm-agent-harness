# API Reference

> Source: [`agentic/`](../agentic/)

## 核心组件

| 组件 | 源文件 | 说明 |
|------|--------|------|
| [`agentic_function`](api/agentic_function.md) | `function.py` | 装饰器。把普通函数变成 Agentic Function，自动记录到 Context 树 |
| [`Runtime`](api/runtime.md) | `runtime.py` | LLM 运行时类。处理 Context 注入、调用 LLM、记录回复 |
| [`Context`](api/context.md) | `context.py` | 执行记录。每个函数调用一个节点，节点组成树 |
| [`create`, `fix`, `improve`](api/meta_function.md) | `meta_functions/` | Meta functions。创建、修复、优化 `@agentic_function` |
| [`create_runtime` 与内置 providers](api/providers.md) | `providers/` | 自动检测或显式创建 Runtime，支持 Anthropic/OpenAI/Gemini/CLI providers |

## 导入

```python
from agentic import (
    agentic_function,
    Runtime,
    Context,
    create,
    fix,
    improve,
    create_runtime,
)
```

## 快速示例

```python
from agentic import agentic_function, Runtime

# 1. 创建 Runtime
runtime = Runtime(call=my_llm_func, model="sonnet")

# 2. 定义函数
@agentic_function
def observe(task):
    """Look at the screen."""
    return runtime.exec(content=[
        {"type": "text", "text": f"Find: {task}"},
    ])

# 3. 调用
result = observe(task="login button")

# 4. 查看 Context
print(observe.context.tree())
```
