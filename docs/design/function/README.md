# Function 设计总览

本目录描述 Agentic Programming 中函数的设计规范。

## 目录结构

```
function/
├── README.md               ← 本文件
├── pure_python.md          ← 不调用大模型的普通 Python 函数
├── agentic_function.md     ← 调用大模型的 @agentic_function
└── function_calling/       ← 函数调用函数的两种情况
    ├── code_call.md        ← 代码决定调用顺序（固定流程）
    └── llm_call.md         ← 大模型决定调用哪个函数（动态选择）
```

## 核心规则

1. **一个 `@agentic_function` 最多调一次 `runtime.exec()`**
2. **一个函数可以调用任意多个其他 `@agentic_function`**
3. **Docstring 是 prompt**，content 只放数据
4. **大模型只输出它需要决定的参数**，其他由代码自动填充

## 相关文件

- 工具函数：`agentic/functions/build_catalog.py`、`parse_action.py`、`prepare_args.py`
- 完整样例：`agentic/functions/llm_call_example.py`
- 框架核心：`agentic/function.py`（`@agentic_function` 装饰器）
- 框架核心：`agentic/runtime.py`（`Runtime.exec()` 方法）
