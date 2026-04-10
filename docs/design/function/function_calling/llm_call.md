# @agentic_function 让大模型选择调用哪个子函数

调用一次大模型，大模型分析任务后决定调用哪个子函数。

## 适用场景

- 用户输入不确定，需要大模型判断该做什么
- 一个入口对接多个功能，由大模型分流
- 例如：用户说"帮我润色" → 大模型选 `polish_text`，用户说"翻译" → 大模型选 `translate_to_chinese`

## 设计要点

- 用 `@agentic_function` 装饰器
- 调一次 `exec()` 让大模型分析任务并选择函数
- 用函数注册表声明可调用的子函数
- 大模型只输出它需要决定的参数，其他由代码自动填充
- 调用完拿到结果后还可以继续处理

## 完整示例

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
        "translate_to_chinese": {
            "function": translate_to_chinese,
            "description": "将英文文本翻译为中文",
            "input": {
                "text": {"source": "context"},
            },
            "output": {"translated_text": str},
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

    # === 1. 构建大模型可见的函数目录 ===
    catalog = build_catalog(available)

    # === 2. 调用大模型 ===
    reply = runtime.exec(content=[
        {"type": "text", "text": (
            f"{task}\n\n"
            "== Functions ==\n"
            "如需调用函数，在回复末尾附上对应的 JSON。\n"
            "如果不需要调用，直接返回结果。\n\n"
            f"{catalog}"
        )},
    ])

    # === 3. 解析大模型输出 ===
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

    # === 6. 后续处理（可扩展）===
    # result 的结构由 available[...]["output"] 定义
    # 可以继续处理 result，比如保存、翻译、格式化等
    return result
```

## 函数注册表

### 结构

```python
{
    "函数名": {
        "function": 函数对象,
        "description": "给大模型看的描述",
        "input": {
            "参数名": {
                "source": "context" 或 "llm",
                "type": 类型,               # 可选
                "options": [...],            # 可选，枚举值
                "description": "参数说明",    # 可选
            },
        },
        "output": {"字段名": 类型},
    },
}
```

### 参数来源（source）

| source | 含义 | 谁提供 | 大模型是否可见 |
|--------|------|-------|-------------|
| `"context"` | 代码从上下文自动填充 | Python 代码 | 否 |
| `"llm"` | 大模型在回复中指定 | 大模型 | 是 |
| runtime | 框架自动注入 | 框架 | 否 |

核心原则：**大模型只输出它需要决定的参数，代码能确定的不让大模型操心。**

### 输出结构（output）

声明函数返回什么。不同函数的输出结构可以完全不同：

```python
# 单个字符串
"output": {"summary": str}

# 多字段、多类型
"output": {"summary": str, "keywords": list, "score": float}
```

## 大模型看到的内容

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

大模型不需要知道 `text` 参数——代码会自动填。

## 大模型输出格式

大模型在回复末尾附上 JSON：
```json
{"call": "polish_text", "args": {"style": "academic"}}
```

如果不需要调用函数，不附 JSON，直接返回文本。

## 完整数据流

以 `"帮我用学术风格润色: Machine learning is great."` 为例：

```
步骤 1: build_catalog
    → 生成函数目录（只有 style 可见）

步骤 2: runtime.exec()
    → 大模型回复: "需要学术润色。{"call": "polish_text", "args": {"style": "academic"}}"

步骤 3: parse_action
    → {"call": "polish_text", "args": {"style": "academic"}}

步骤 4: prepare_args，合并三个来源:
    大模型提供:  {"style": "academic"}
    context 填充: {"text": "帮我用学术风格润色: Machine learning is great."}
    框架注入:     {"runtime": runtime}
    → args = {"text": "帮我...", "style": "academic", "runtime": runtime}

步骤 5: polish_text(text=..., style="academic", runtime=runtime)

步骤 6: 拿到 result，可继续处理
```

## Context Tree

```
research_assistant
└── polish_text        ← 大模型选择的
```

## 容错机制

| 情况 | 处理 |
|------|------|
| 函数名不存在 | 返回大模型原始回复 |
| 多余参数 | 过滤掉函数签名里没有的 |
| 缺少必要参数 | 调 `fix_call_params` 让大模型补全 |
| JSON 解析失败 | 返回大模型原始回复 |

### fix_call_params

当大模型漏了必要参数时，`prepare_args` 自动调用 `fix_call_params` 补全。
这是一个独立的 `@agentic_function`，不违反"一个函数一次 exec"的规则。

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

触发后的 Context Tree：
```
research_assistant
├── fix_call_params     ← 补全了 style
└── polish_text         ← 用完整参数调用
```

## 工具函数

| 函数 | 文件 | 作用 |
|------|------|------|
| `build_catalog` | `build_catalog.py` | 从注册表生成大模型可见的函数目录 |
| `parse_action` | `parse_action.py` | 从大模型回复提取 `{"call": ..., "args": ...}` |
| `prepare_args` | `prepare_args.py` | 合并所有参数来源，处理缺参 |

## 完整样例

见 `agentic/functions/llm_call_example.py`。
