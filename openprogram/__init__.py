"""
OpenProgram — Agentic Programming 理念的产品化实现。

在函数里无缝衔接 LLM 调用。用 `@agentic_function` 装饰一个普通 Python 函数，
函数体里的 docstring 就成了给模型的指令；`runtime.exec(...)` 负责把对话带上
调用历史一起发给模型。上下文树（Context）是副产物，自动积累。

双模式：
  - 初学者：跑我们打包好的应用（CLI / Web UI），零代码。
  - 深度用户：`from openprogram import agentic_function` 自己写。

顶层 re-export 只有 ``agentic_function`` 一个 —— 这是 Agentic Programming
的入口符号，任何用户代码都要 ``from openprogram import agentic_function``。
其它符号（``Runtime`` / ``ask_user`` / 各 provider helper 等）走全路径就行：

    from openprogram.agentic_programming.runtime import Runtime
    from openprogram.functions.agentics.ask_user import ask_user
    from openprogram.providers.registry import create_runtime

新建 / 编辑 / 改进 @agentic_function 走 skill ``agentic-programming``，
agent 直接用 Read / Write / Edit 工具操作 .py 文件，不再有专门的 meta 函数。
"""

from openprogram.agentic_programming import agentic_function

__all__ = ["agentic_function"]
