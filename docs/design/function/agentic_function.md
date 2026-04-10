# @agentic_function

## 概述

`@agentic_function` 是需要 LLM 参与的函数。装饰器自动将函数执行记录到 Context Tree 中。

核心规则：**一个 @agentic_function 最多调一次 `runtime.exec()`，但可以调用任意多个其他 @agentic_function。**

## 三种使用模式

### 1. 叶子函数

单一任务，调一次 `exec()`，返回结果。不调其他子函数。

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

Context tree:
```
translate_to_chinese  ✓ success
```

### 2. 编排函数

按固定顺序调用多个子函数，Python 代码决定顺序。`exec()` 可选。

```python
@agentic_function
def research_pipeline(task: str, runtime: Runtime) -> dict:
    """执行完整研究流程：调研 → 找 gap → 生成想法。

    Args:
        task: 研究主题。
        runtime: LLM 运行时实例。

    Returns:
        包含 survey、gaps、ideas 的结果字典。
    """
    survey = survey_topic(topic=task, runtime=runtime)

    # 步骤之间可以插入普通 Python 处理
    key_points = extract_key_points(survey)

    gaps = identify_gaps(survey=key_points, runtime=runtime)
    ideas = generate_ideas(gaps=gaps, runtime=runtime)

    return {"survey": survey, "gaps": gaps, "ideas": ideas}
```

Context tree:
```
research_pipeline
├── survey_topic
├── identify_gaps
└── generate_ideas
```

### 3. 动态调用（LLM 选择函数）

LLM 分析任务后决定调哪个子函数。需要函数注册表、目录构建、解析和参数准备。

```python
@agentic_function
def research_assistant(task: str, runtime: Runtime) -> str:
    """分析研究任务，选择合适的子函数完成工作。

    Args:
        task: 用户的研究任务描述。
        runtime: LLM 运行时实例。

    Returns:
        子函数的执行结果，或 LLM 的直接回复。
    """
    # === 0. 函数注册表 ===
    available = {
        "summarize_text": {
            "function": summarize_text,
            "description": "将文本压缩为简洁的摘要",
            "input": {
                "text": {"source": "context"},
            },
            "output": {"summary": str},
        },
        "polish_text": {
            "function": polish_text,
            "description": "按指定风格润色文本",
            "input": {
                "text": {"source": "context"},
                "style": {
                    "source": "llm",
                    "type": str,
                    "options": ["academic", "casual", "concise"],
                    "description": "润色风格",
                },
            },
            "output": {"polished_text": str},
        },
    }

    # === 1. 构建 LLM 可见的函数目录 ===
    catalog = build_catalog(available)

    # === 2. 调用 LLM ===
    reply = runtime.exec(content=[
        {"type": "text", "text": (
            f"{task}\n\n"
            "== Functions ==\n"
            "如需调用函数，在回复末尾附上对应的 JSON。\n"
            "如果不需要调用，直接返回结果。\n\n"
            f"{catalog}"
        )},
    ])

    # === 3. 解析 LLM 输出 ===
    action = parse_action(reply)
    if not action or action["call"] not in available:
        return reply

    # === 4. 准备参数 ===
    args = prepare_args(
        action=action,
        available=available,
        runtime=runtime,
        context={"text": task},
        fix_fn=fix_call_params,
    )

    # === 5. 调用函数 ===
    result = available[action["call"]]["function"](**args)

    # === 6. 后续处理 ===
    return result
```

Context tree:
```
research_assistant
└── polish_text        ← LLM 选择的
```

## 函数注册表

### 结构

```python
{
    "函数名": {
        "function": 函数对象,
        "description": "给 LLM 看的描述",
        "input": {
            "参数名": {
                "source": "context" 或 "llm",
                "type": 类型,               # 可选
                "options": [...],            # 可选
                "description": "参数说明",    # 可选
            },
        },
        "output": {"字段名": 类型},
    },
}
```

### 参数来源

| source | 谁提供 | LLM 是否可见 | 示例 |
|--------|-------|-------------|------|
| `"context"` | Python 代码从上下文填充 | 否 | text ← task |
| `"llm"` | LLM 在回复中指定 | 是 | style = "academic" |
| runtime | 框架自动注入 | 否 | 无需声明 |

核心原则：**LLM 只输出它需要决定的参数，其他由代码自动填充。**

### LLM 看到的效果

`build_catalog()` 只展示 `source: "llm"` 的参数：

```
summarize_text()
    将文本压缩为简洁的摘要
    调用: {"call": "summarize_text"}

polish_text(style: str)
    按指定风格润色文本
    style: 润色风格 (可选: "academic", "casual", "concise")
    调用: {"call": "polish_text", "args": {"style": "..."}}
```

## 参数补全（fix_call_params）

当 LLM 选了函数但漏了必要参数时，`prepare_args` 自动调用 `fix_call_params` 补全：

```python
@agentic_function
def fix_call_params(func_name: str, missing: list, runtime: Runtime) -> dict:
    """补全缺失的函数调用参数。

    Args:
        func_name: 被调用的函数名。
        missing: 缺失的参数名列表。
        runtime: LLM 运行时实例。

    Returns:
        包含补全参数的字典。
    """
    reply = runtime.exec(content=[
        {"type": "text", "text": (
            f"函数 {func_name} 缺少以下参数: {missing}\n"
            "请以 JSON 格式提供这些参数的值。"
        )},
    ])
    result = parse_action(reply)
    return result.get("args", result) if result else {}
```

触发条件：LLM 参数 + context 填充 + 默认值都补不了时才触发。

Context tree:
```
research_assistant
├── fix_call_params     ← 补全了 style
└── polish_text         ← 用完整参数调用
```

## 容错机制

| 情况 | 处理 |
|------|------|
| 函数名不存在 | 返回 LLM 原始回复 |
| 多余参数 | 过滤掉函数签名里没有的 |
| 缺少必要参数 | 调 fix_call_params 补全 |
| JSON 解析失败 | 返回 LLM 原始回复 |

## Docstring 规范

### 必须
- 一行摘要
- 具体指令（输出格式、约束）
- Args + Returns

### 禁止
- "You are a helpful assistant"
- "Complete the task"
- 重复 content 中已有的内容

## Content 规范

`runtime.exec(content=[...])` 只放数据：

```python
# 正确
runtime.exec(content=[{"type": "text", "text": text}])

# 错误
runtime.exec(content=[{"type": "text", "text": f"Please analyze: {text}. Return one word."}])
```

## 工具函数

| 函数 | 文件 | 作用 |
|------|------|------|
| `build_catalog` | `build_catalog.py` | 从注册表生成 LLM 可见的函数目录 |
| `parse_action` | `parse_action.py` | 从 LLM 回复提取 `{"call": ..., "args": ...}` |
| `prepare_args` | `prepare_args.py` | 合并所有参数来源，处理缺参 |

## 完整样例

见 `agentic/functions/llm_call_example.py`。
