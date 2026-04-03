# API Reference

> Source: [`agentic/`](../agentic/)

## 核心组件

| 组件 | 源文件 | 说明 |
|------|--------|------|
| [`agentic_function`](api/agentic_function.md) | `function.py` | 装饰器。把普通函数变成 Agentic Function，自动记录到 Context 树 |
| [`Runtime`](api/runtime.md) | `runtime.py` | LLM 运行时类。处理 Context 注入、调用 LLM、记录回复 |
| [`Context`](api/context.md) | `context.py` | 执行记录。每个函数调用一个节点，节点组成树 |
| [`create`](api/meta.md) | `meta.py` | Meta function。用自然语言描述生成新的 @agentic_function |

## 导入

```python
from agentic import agentic_function, Runtime, Context, create
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
