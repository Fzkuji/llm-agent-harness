"""
openprogram.programs.functions — @agentic_function 集合。

哪些函数可用由 ``registry.py`` 的显式列表决定，不再扫描目录。
新增函数 = 往 ``FUNCTION_MODULES`` 里加一行；隐藏 = 删掉那行。
"""

import importlib
import os
from types import ModuleType

from openprogram.programs.functions.registry import FUNCTION_MODULES

_BASE = os.path.dirname(os.path.abspath(__file__))


def iter_function_files(subpkg: str):
    """Yield (dotted_module, filepath) for registered functions in a subpackage.

    Reads the explicit ``registry.FUNCTION_MODULES`` list — no directory
    scan. ``subpkg`` is the first path component ("buildin" /
    "third_party"). Entries whose file is missing are skipped so a stale
    registry line cannot crash discovery.
    """
    for rel in FUNCTION_MODULES:
        parts = rel.split(".")
        if parts[0] != subpkg:
            continue
        filepath = os.path.join(_BASE, *parts) + ".py"
        if not os.path.isfile(filepath):
            continue
        yield "openprogram.programs.functions." + rel, filepath


def resolve_function_module(name: str) -> ModuleType:
    """按函数名在注册表中查找并加载模块。

    先按"模块名最后一段 == 函数名"匹配（最常见，文件名即函数名），
    匹配不到再逐个 import 注册表里的模块、看是否定义了该函数（一个
    模块可能定义多个 @agentic_function）。
    """
    for rel in FUNCTION_MODULES:
        if rel.rsplit(".", 1)[-1] == name:
            try:
                return importlib.import_module(
                    f"openprogram.programs.functions.{rel}"
                )
            except ImportError:
                continue
    for rel in FUNCTION_MODULES:
        try:
            mod = importlib.import_module(f"openprogram.programs.functions.{rel}")
        except ImportError:
            continue
        if hasattr(mod, name):
            return mod
    raise ImportError(
        f"agentic function {name!r} not in registry "
        f"(openprogram/programs/functions/registry.py)"
    )
