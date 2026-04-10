# Agentic Function 调用 Function 设计文档

## 概述

在 Agentic Programming 中，一个 `@agentic_function` 可以调用其他 `@agentic_function`。
当调用关系由 LLM 动态决定时（而非 Python 代码写死），我们称之为 **function dispatch**。

本文档描述 function dispatch 的完整设计：何时使用、怎么写、数据怎么流转。

## 三种函数角色

```
┌──────────┬──────────────┬────────────────┬──────────────────────┐
│   角色    │ 调 exec()?   │ 调子函数?       │ 谁决定调哪个?         │
├──────────┼──────────────┼────────────────┼──────────────────────┤
│ 叶子函数  │ 1次          │ 否             │ —                    │
│ 编排函数  │ 可选(总结用)  │ 是，多个        │ Python（写死顺序）    │
│ 入口函数  │ 1次          │ 是，1个         │ LLM（动态选择）       │
└──────────┴──────────────┴────────────────┴──────────────────────┘
```

### 叶子函数

只干活，不调其他函数。调一次 `exec()`，返回结果。

```python
@agentic_function
def translate_to_chinese(text: str, runtime: Runtime) -> str:
    """将英文文本翻译为中文。

    Args:
        text: 需要翻译的英文文本。

    Returns:
        翻译后的中文文本。
    """
    return runtime.exec(content=[
        {"type": "text", "text": f"Translate to Chinese:\n\n{text}"},
    ])
```

### 编排函数

按固定顺序调用多个子函数，用 Python 代码串联。可以不调 `exec()`，也可以调一次做总结。

```python
@agentic_function
def research_pipeline(task: str, runtime: Runtime) -> str:
    """执行完整研究流程：调研 → 找 gap → 生成想法。"""

    survey = survey_topic(topic=task, runtime=runtime)
    gaps = identify_gaps(survey=survey, runtime=runtime)
    ideas = generate_ideas(gaps=gaps, runtime=runtime)

    # 可选：自己调一次 exec 做总结
    return runtime.exec(content=[
        {"type": "text", "text": f"总结研究结果：\n{ideas}"},
    ])
```

Context tree:
```
research_pipeline
├── survey_topic
├── identify_gaps
└── generate_ideas
```

### 入口函数（LLM 动态选择）

调一次 `exec()` 让 LLM 分析任务并选择调用哪个子函数，Python 解析选择后执行。

```python
@agentic_function
def research_assistant(task: str, runtime: Runtime) -> str:
    """分析研究任务，选择合适的子函数完成工作。"""

    available = {
        "summarize_text": { ... },
        "polish_text": { ... },
    }
    catalog = build_catalog(available)

    reply = runtime.exec(content=[
        {"type": "text", "text": f"{task}\n\n== Functions ==\n{catalog}"},
    ])

    action = parse_action(reply)
    if action and action["call"] in available:
        args = prepare_args(action, available, runtime, context={"text": task})
        result = available[action["call"]]["function"](**args)
        return result

    return reply
```

Context tree:
```
research_assistant
└── polish_text        ← LLM 选择的
```

## 函数注册表设计

每个可调用的子函数在注册表中声明完整信息：

```python
available = {
    "polish_text": {
        "function": polish_text,          # 函数对象
        "description": "按指定风格润色文本",  # 给 LLM 看的描述
        "input": {                         # 输入参数定义
            "text": {
                "source": "context",       # 代码自动填充，LLM 不需要提供
            },
            "style": {
                "source": "llm",           # LLM 需要决定
                "type": str,
                "options": ["academic", "casual", "concise"],
                "description": "润色风格",
            },
        },
        "output": {                        # 输出结构
            "polished_text": str,
        },
    },
    "analyze_paper": {
        "function": analyze_paper,
        "description": "分析论文结构和质量",
        "input": {
            "text": {"source": "context"},
        },
        "output": {                        # 多字段输出
            "summary": str,
            "keywords": list,
            "score": float,
            "suggestions": list,
        },
    },
}
```

### 参数来源（source）

| source | 含义 | 谁提供 | LLM 是否可见 |
|--------|------|-------|-------------|
| `"context"` | 从上下文自动填充（如 task → text） | Python 代码 | 否 |
| `"llm"` | LLM 在回复中指定 | LLM | 是 |
| runtime | 框架自动注入 | 框架 | 否 |

核心原则：**LLM 只需要输出它需要决定的参数**。代码能确定的不让 LLM 操心。

### 输出结构（output）

声明函数返回值的字段和类型。不同函数的输出结构可以完全不同：
- 单个字符串：`{"result": str}`
- 多字段：`{"summary": str, "keywords": list, "score": float}`
- 嵌套结构：`{"analysis": dict, "recommendations": list}`

调用方根据 `output` 声明知道如何使用返回值。

## LLM 看到的内容

`build_catalog()` 从注册表生成函数目录，**只展示 `source: "llm"` 的参数**。

LLM 看到的效果：

```
== Functions ==
如需调用函数，在回复末尾附上对应的 JSON。
如果不需要调用，直接返回结果。

summarize_text()
    将文本压缩为简洁的摘要
    调用: {"call": "summarize_text"}

polish_text(style: str)
    按指定风格润色文本
    style: 润色风格 (可选: "academic", "casual", "concise")
    调用: {"call": "polish_text", "args": {"style": "..."}}
```

LLM 只需要输出：
```json
{"call": "polish_text", "args": {"style": "academic"}}
```

Python 自动补全其他参数后调用：
```python
polish_text(text=task, style="academic", runtime=runtime)
```

## 完整数据流

以用户输入 `"帮我用学术风格润色这段话: Machine learning is great."` 为例：

```
步骤 0: 注册表定义
    available = {"polish_text": {"function": ..., "input": {...}, ...}}

步骤 1: 构建 LLM 可见的函数目录
    catalog = build_catalog(available)
    → 只包含 source="llm" 的参数（style）

步骤 2: 调用 LLM
    reply = runtime.exec(content=[task + catalog])
    → LLM 回复: "需要学术润色。{"call": "polish_text", "args": {"style": "academic"}}"

步骤 3: 解析 LLM 输出
    action = parse_action(reply)
    → {"call": "polish_text", "args": {"style": "academic"}}

步骤 4: 准备参数
    args = prepare_args(action, available, runtime, context={"text": task})
    做三件事:
      a. 从 action["args"] 取 LLM 参数:  {"style": "academic"}
      b. 从 context 填 source="context":  {"text": task}
      c. 自动注入 runtime:                {"runtime": runtime}
    → args = {"text": "帮我...", "style": "academic", "runtime": runtime}

步骤 5: 调用函数
    result = available["polish_text"]["function"](**args)
    → polish_text(text="帮我...", style="academic", runtime=runtime)

步骤 6: 后续处理
    result 的结构由 output 定义，可继续使用
```

## 容错机制

| 情况 | 处理方式 |
|------|---------|
| LLM 输出的函数名不在 available 中 | 返回 LLM 原始回复，当作没有 action |
| LLM 多输出了函数不接受的参数 | 过滤掉，只保留函数签名中存在的参数 |
| LLM 漏了必要参数（如 style） | 调 `fix_call_params` 让 LLM 补全 |
| LLM 回复中没有合法 JSON | `parse_action` 返回 None，返回原始回复 |

### fix_call_params

当 LLM 漏了必要参数时，`prepare_args` 会调用 `fix_call_params`：

```python
@agentic_function
def fix_call_params(func_name: str, missing: list, runtime: Runtime) -> dict:
    """补全缺失的函数调用参数。"""
    reply = runtime.exec(content=[
        {"type": "text", "text": f"函数 {func_name} 缺少以下参数: {missing}\n请以 JSON 格式提供。"},
    ])
    result = parse_action(reply)
    return result.get("args", result) if result else {}
```

这是一个独立的 `@agentic_function`，不违反"一个函数一次 exec"的规则。

Context tree:
```
research_assistant          ← exec 一次，选了 polish_text 但漏了 style
├── fix_call_params         ← exec 一次，补全 style
└── polish_text             ← exec 一次，执行润色
```

## 工具函数

| 文件 | 函数 | 作用 |
|------|------|------|
| `build_catalog.py` | `build_catalog(available)` | 从注册表生成 LLM 可见的函数目录 |
| `parse_action.py` | `parse_action(reply)` | 从 LLM 回复中提取 `{"call": ..., "args": ...}` |
| `prepare_args.py` | `prepare_args(action, available, runtime, context, fix_fn)` | 合并所有参数来源，处理缺参 |

这三个是纯工具函数，不是 `@agentic_function`，不调用 LLM。

## 样例

完整样例见 `agentic/functions/llm_call_example.py`，包含：
- 三个叶子函数：`summarize_text`、`translate_to_chinese`、`polish_text`
- 一个补全函数：`fix_call_params`
- 一个入口函数：`research_assistant`
