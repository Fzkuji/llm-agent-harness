"""
llm_call_example — demonstrates LLM-driven function dispatch.

Shows how an @agentic_function can let the LLM decide which sub-function
to call. The LLM only outputs what it needs to decide (e.g. style),
everything else (text, runtime) is auto-filled by Python.

Context tree:
    research_assistant
    ├── fix_call_params     (only if LLM missed required params)
    └── polish_text

Usage:
    from agentic import create_runtime
    from agentic.functions.llm_call_example import research_assistant

    rt = create_runtime()
    result = research_assistant(task="帮我用学术风格润色这段话: ...", runtime=rt)
"""

from __future__ import annotations

from agentic.function import agentic_function
from agentic.runtime import Runtime
from agentic.functions.build_catalog import build_catalog
from agentic.functions.parse_action import parse_action
from agentic.functions.prepare_args import prepare_args


# ---------------------------------------------------------------------------
# Sub-functions (do actual work)
# ---------------------------------------------------------------------------

@agentic_function(input={
    "text": {"description": "Text to summarize", "placeholder": "Paste your text here..."},
    "runtime": {"hidden": True},
})
def summarize_text(text: str, runtime: Runtime) -> str:
    """将文本压缩为简洁的摘要。

    Args:
        text: 需要总结的原始文本。

    Returns:
        简洁的摘要文本。
    """
    return runtime.exec(content=[
        {"type": "text", "text": f"Please summarize:\n\n{text}"},
    ])


@agentic_function(input={
    "text": {"description": "English text to translate", "placeholder": "e.g. Hello, how are you?"},
    "runtime": {"hidden": True},
})
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


@agentic_function(input={
    "text": {"description": "Text to polish", "placeholder": "Paste your text here..."},
    "style": {"description": "Style", "placeholder": "academic", "options": ["academic", "casual", "concise"]},
    "runtime": {"hidden": True},
})
def polish_text(text: str, style: str, runtime: Runtime) -> str:
    """按指定风格润色文本。

    Args:
        text: 需要润色的文本。
        style: 润色风格，可选 "academic"（学术）、"casual"（口语）、"concise"（精简）。

    Returns:
        润色后的文本。
    """
    return runtime.exec(content=[
        {"type": "text", "text": f"Polish this text in {style} style:\n\n{text}"},
    ])


# ---------------------------------------------------------------------------
# fix_call_params — retry when LLM missed required params
# ---------------------------------------------------------------------------

@agentic_function(input={
    "func_name": {"description": "Function name", "placeholder": "e.g. polish_text", "multiline": False},
    "missing": {"description": "Missing param names", "placeholder": "e.g. [\"style\"]", "multiline": False},
    "runtime": {"hidden": True},
})
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


# ---------------------------------------------------------------------------
# Entry point — LLM decides which function to call
# ---------------------------------------------------------------------------

@agentic_function(input={
    "task": {"description": "Research task", "placeholder": "e.g. 帮我用学术风格润色这段话: ..."},
    "runtime": {"hidden": True},
})
def research_assistant(task: str, runtime: Runtime) -> str:
    """分析研究任务，选择合适的子函数完成工作。

    根据用户输入的任务，调用 LLM 分析后决定是否需要调用子函数。
    如果 LLM 回复中包含函数调用指令，自动解析并执行对应函数。

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

    # === 1. 构建 LLM 看到的函数目录 ===
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

    # === 6. 后续处理（可扩展）===
    # result 的结构由 available[...]["output"] 定义
    # 这里可以继续处理 result，比如保存、翻译、格式化等

    return result
