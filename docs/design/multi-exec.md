# 两类节点：函数节点 + LLM 调用节点

## 背景

当前上下文树只有一种节点（函数节点）。`exec()` 在函数节点内部记录 LLM 交互（`raw_reply`, `exchanges`），
但 exec 本身不产生树节点。这导致：
1. 多次 exec 的记录需要额外的 `exchanges` 列表（hack）
2. `exec()` 承担了上下文构建的职责（不该是它的事）
3. 树结构没有真实反映执行过程

## 核心设计

### 两种节点

- **函数节点**：`@agentic_function` 创建，代表一个函数调用。docstring 在函数**被调用时**进入树。
- **LLM 调用节点**：`exec()` 创建，代表一次 LLM 交互。是函数节点的子节点。

### 两个时刻的解耦

| 时刻 | 发生什么 | 谁负责 |
|------|---------|--------|
| 函数被调用 | docstring 进入上下文树 | `@agentic_function` 创建函数节点 |
| exec() 被调用 | 从树上读取内容，发给 LLM | exec 节点调 `summarize()` |

**上下文管理**（信息何时进入树）和 **LLM 输入构建**（信息何时发给 LLM）是分离的。
树是"上下文管理器"，`summarize()` 是"LLM 输入构建器"。

### 统一流程：每次 exec 都一样

```python
# 不区分首次/后续。每次 exec 完全相同的流程：
exec_ctx = Context(name="_exec", node_type="exec", parent=parent_ctx, ...)
parent_ctx.children.append(exec_ctx)
context = exec_ctx.summarize(...)   # 从树上读，统一逻辑
reply = self._call(...)             # 调 LLM
```

不需要 `_frozen_preamble`，不需要 `is_continuation`，不需要 `build_exec_context()`。

## 树结构示例

```
my_func (函数节点, running)
├── _exec (LLM 节点, done)     ← 第1次 exec: "分析这个文件"
├── helper (函数节点, done)     ← 两次 exec 之间调用的子函数
└── _exec (LLM 节点, running)  ← 第2次 exec: "根据分析结果修复"
```

完成后，外部看 my_func（作为兄弟节点）：
```
summary:  my_func(file="x.py") → "修复完成"
detail:   展开显示所有子节点（exec + helper）
```

## 每次 exec 的 LLM 输入

exec 节点调 `summarize()`，自然看到祖先 + 兄弟。每次 exec 逻辑完全一样。

### 第 1 次 exec

```
[祖先链]
    my_func(file="x.py")              ← 父函数是祖先
        """my_func 的 docstring"""     ← docstring 在函数被调用时就进了树
    [无兄弟]
    _exec()  <-- Current Call
→ Current Task:
    分析这个文件
```

### 第 2 次 exec（中间调了 helper）

```
[祖先链]
    my_func(file="x.py")              ← 同一个父函数
        """my_func 的 docstring"""     ← 同样的 docstring（见下方 _prompted_functions 修复）
    _exec()                            ← 第1次 exec 作为兄弟
        → 分析这个文件
        ← 文件有 3 个 bug...
    helper(data=...) → {valid: true}   ← 子函数作为兄弟
    _exec()  <-- Current Call
→ Current Task:
    根据分析结果修复
```

第 1 次和第 N 次的逻辑完全一样：创建 exec 节点 → summarize() → 调 LLM。
上下文**只增不减**（每次 exec 多一个兄弟），prompt cache 自然命中前缀。

### _prompted_functions 修复

当前问题：exec_0 的 summarize() 把父函数加入 `_prompted_functions`，导致 exec_1 看不到父函数的 docstring。
但每次 exec 是**独立的 LLM 调用**（无状态 API），LLM 不会"记住"之前的 docstring。

**修复**：exec 节点的 summarize 不把直接父函数加入 `_prompted_functions`。

```python
# summarize() 中渲染祖先时
for a in reversed(ancestors):
    if a.name in prompted_functions:
        ancestor_level = "result"
    else:
        # 只有非直接父节点才加入 prompted_functions
        if a is not self.parent:
            prompted_functions.add(a.name)
```

这样：
- exec_0 看到父函数 docstring ✓，但不把父函数标记为"已发送"
- exec_1 也看到父函数 docstring ✓
- 其他不相关的函数仍受 `_prompted_functions` 优化影响

### API vs Session

| | API（无状态） | Session/Client（有状态） |
|---|---|---|
| 上下文管理 | 相同（树结构） | 相同 |
| LLM 输入 | summarize() 完整输出 | 只发增量（session 记住历史） |

上下文模型是同一个，不同 provider 读取方式不同。

## 实现方案

### 1. Context 新增

```python
@dataclass
class Context:
    node_type: str = "function"
    # "function" — @agentic_function 创建
    # "exec"     — runtime.exec() 创建
```

不需要 `_frozen_preamble`、`build_exec_context()`、`exchanges`。

### 2. runtime.exec() 精简

```python
def exec(self, content, context=None, response_format=None, model=None):
    if self._closed:
        raise RuntimeError("Runtime is closed.")
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]

    parent_ctx = _current_ctx.get(None)
    use_model = model or self.model
    content_text = "\n".join(b["text"] for b in content if b.get("type") == "text")

    # --- 创建 exec 子节点 ---
    exec_ctx = None
    if parent_ctx is not None:
        exec_ctx = Context(
            name="_exec",
            node_type="exec",
            params={"_content": content_text},
            parent=parent_ctx,
            start_time=time.time(),
            render="result",
        )
        parent_ctx.children.append(exec_ctx)
        _emit_event("node_created", exec_ctx)

    # --- 上下文：exec 节点自己 summarize ---
    if context is None and exec_ctx is not None:
        kwargs = dict(parent_ctx._summarize_kwargs) if parent_ctx._summarize_kwargs else {}
        kwargs["prompted_functions"] = self._prompted_functions
        context = exec_ctx.summarize(**kwargs)

    # --- 合并 content ---
    full_content = _merge_content(context, content, exec_ctx)

    # --- 调 LLM ---
    attempts = exec_ctx.attempts if exec_ctx is not None else []
    for attempt in range(self.max_retries):
        try:
            reply = self._call(full_content, model=use_model, response_format=response_format)
            attempts.append({"attempt": attempt + 1, "reply": reply, "error": None})
            if exec_ctx is not None:
                exec_ctx.raw_reply = reply
                exec_ctx.output = reply
                exec_ctx.status = "success"
                exec_ctx.end_time = time.time()
                _emit_event("node_completed", exec_ctx)
                parent_ctx.raw_reply = reply  # 向后兼容
            return reply
        except (TypeError, NotImplementedError):
            raise
        except Exception as e:
            attempts.append({"attempt": attempt + 1, "reply": None, "error": str(e)})
            if attempt == self.max_retries - 1:
                if exec_ctx is not None:
                    exec_ctx.error = str(e)
                    exec_ctx.status = "error"
                    exec_ctx.end_time = time.time()
                    _emit_event("node_completed", exec_ctx)
                raise
```

**关键**：
- exec() 不修改 `_current_ctx`（函数节点始终是当前上下文）
- exec 节点自己调 summarize()（和其他节点一样，统一逻辑）
- 不区分首次/后续

### 3. _merge_content 提取

从 exec() 提取为模块级函数。去掉 `ctx.parent` 守卫。

### 4. summarize() 修复 _prompted_functions

exec 节点渲染祖先时，不把直接父函数标记为"已发送"。

### 5. _render_traceback 更新

exec 节点的渲染：
```python
if self.node_type == "exec":
    content_preview = self.params.get("_content", "")[:200]
    reply_preview = (self.raw_reply or "")[:500]
    return f"{indent}→ {content_preview}\n{indent}← {reply_preview}"
```

### 6. 清理

- 移除 `exchanges` 字段（信息在 exec 子节点中）
- 移除 `is_continuation` / `_frozen_preamble` 相关代码
- 保留 `raw_reply` 指向最后一个 exec 的 reply（向后兼容）

### 7. _to_dict / from_dict

添加 `node_type` 序列化。

## 需要修改的文件

1. **`agentic/context.py`** — 添加 node_type, 修改 summarize() 的 _prompted_functions 逻辑, 更新 _render_traceback, 序列化, 移除 exchanges/_frozen_preamble
2. **`agentic/runtime.py`** — exec() 创建 exec 节点 + 用 summarize(), async_exec() 同步, 提取 _merge_content
3. **`agentic/visualize/static/js/ui.js`** — exec 节点视觉区分
4. **`tests/test_runtime.py`** — 多次 exec 测试
5. **`tests/test_async.py`** — 异步多次 exec 测试

## 验证

```bash
pytest tests/ -v

python -c "
from agentic import agentic_function, Runtime
rt = Runtime(call=lambda c, **kw: 'ok')

@agentic_function
def demo():
    '''My prompt.'''
    rt.exec('first')
    rt.exec('second')

demo()
print(demo.context.tree())
# demo
# ├── _exec → ok
# └── _exec → ok
"
```

## 待讨论

- [ ] exec 节点的 render 默认值（"result"? 自定义？）
- [ ] 子节点渲染的截断策略
- [ ] 可视化器中 exec 节点的样式
- [ ] ask_user() 是否也创建节点
