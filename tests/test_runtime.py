"""
Tests for Runtime class.
"""

import pytest
from agentic import agentic_function, Runtime


def mock_call(content, model="test", response_format=None):
    """Mock LLM: returns a summary of content types received."""
    types = [b["type"] for b in content]
    texts = [b.get("text", "")[:50] for b in content if b["type"] == "text"]
    return f"types={types}, texts={len(texts)}"


def echo_call(content, model="test", response_format=None):
    """Echo the last text block."""
    for block in reversed(content):
        if block["type"] == "text":
            return block["text"]
    return ""


def test_runtime_basic():
    """Runtime.exec() calls the provider and returns reply."""
    runtime = Runtime(call=echo_call)

    @agentic_function
    def simple():
        """Simple function."""
        return runtime.exec(content=[
            {"type": "text", "text": "hello world"},
        ])

    result = simple()
    assert result == "hello world"


def test_runtime_records_raw_reply():
    """Runtime records raw_reply on Context."""
    runtime = Runtime(call=echo_call)

    @agentic_function
    def func():
        """Test."""
        return runtime.exec(content=[
            {"type": "text", "text": "test reply"},
        ])

    func()
    assert func.context.raw_reply == "test reply"


def test_runtime_context_injection():
    """Runtime prepends execution context to content."""
    received = []

    def capture_call(content, model="test", response_format=None):
        received.extend(content)
        return "ok"

    runtime = Runtime(call=capture_call)

    @agentic_function
    def parent():
        """Parent function."""
        return child()

    @agentic_function
    def child():
        """Child function."""
        return runtime.exec(content=[
            {"type": "text", "text": "user prompt"},
        ])

    parent()
    # First block should be context (auto-generated), last should be user prompt
    assert len(received) >= 2
    assert received[0]["type"] == "text"
    assert "Execution Context" in received[0]["text"]
    assert received[-1]["text"] == "user prompt"


def test_runtime_no_context_outside_function():
    """Runtime works outside @agentic_function without context."""
    received = []

    def capture_call(content, model="test", response_format=None):
        received.extend(content)
        return "ok"

    runtime = Runtime(call=capture_call)
    result = runtime.exec(content=[{"type": "text", "text": "bare call"}])
    assert result == "ok"
    assert len(received) == 1  # no context prepended
    assert received[0]["text"] == "bare call"


def test_runtime_double_exec_raises():
    """Calling exec() twice in one function raises RuntimeError."""
    runtime = Runtime(call=echo_call)

    @agentic_function
    def double():
        """Bad function."""
        runtime.exec(content=[{"type": "text", "text": "first"}])
        runtime.exec(content=[{"type": "text", "text": "second"}])

    with pytest.raises(RuntimeError, match="exec.*twice"):
        double()


def test_runtime_double_exec_empty_reply():
    """Double exec guard works even when first reply is empty string."""
    runtime = Runtime(call=lambda content, model="test", response_format=None: "")

    @agentic_function
    def double_empty():
        """Bad function with empty reply."""
        runtime.exec(content=[{"type": "text", "text": "first"}])
        runtime.exec(content=[{"type": "text", "text": "second"}])

    with pytest.raises(RuntimeError, match="exec.*twice"):
        double_empty()


def test_runtime_model_override():
    """Model can be overridden per-call."""
    models_used = []

    def track_model(content, model="default", response_format=None):
        models_used.append(model)
        return "ok"

    runtime = Runtime(call=track_model, model="base-model")

    @agentic_function
    def func():
        return runtime.exec(content=[{"type": "text", "text": "test"}], model="override-model")

    func()
    assert models_used[-1] == "override-model"


def test_runtime_default_model():
    """Default model from constructor is used."""
    models_used = []

    def track_model(content, model="default", response_format=None):
        models_used.append(model)
        return "ok"

    runtime = Runtime(call=track_model, model="my-model")

    @agentic_function
    def func():
        return runtime.exec(content=[{"type": "text", "text": "test"}])

    func()
    assert models_used[-1] == "my-model"


def test_runtime_response_format_passed():
    """response_format is passed to _call."""
    formats_received = []

    def track_format(content, model="test", response_format=None):
        formats_received.append(response_format)
        return '{"ok": true}'

    runtime = Runtime(call=track_format)
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    @agentic_function
    def func():
        return runtime.exec(
            content=[{"type": "text", "text": "test"}],
            response_format=schema,
        )

    func()
    assert formats_received[-1] == schema


def test_runtime_no_call_raises():
    """Runtime without call function raises NotImplementedError."""
    runtime = Runtime()

    @agentic_function
    def func():
        return runtime.exec(content=[{"type": "text", "text": "test"}])

    with pytest.raises(NotImplementedError):
        func()


def test_runtime_rejects_zero_retries():
    """max_retries must allow at least one attempt."""
    with pytest.raises(ValueError, match="max_retries"):
        Runtime(call=echo_call, max_retries=0)


def test_runtime_subclass():
    """Runtime can be subclassed with custom _call."""
    class CustomRuntime(Runtime):
        def _call(self, content, model="default", response_format=None):
            return "custom reply"

    runtime = CustomRuntime()

    @agentic_function
    def func():
        return runtime.exec(content=[{"type": "text", "text": "test"}])

    result = func()
    assert result == "custom reply"


def test_multiple_runtimes():
    """Multiple Runtime instances can coexist."""
    runtime1 = Runtime(call=lambda c, **kw: "from runtime1", model="model-1")
    runtime2 = Runtime(call=lambda c, **kw: "from runtime2", model="model-2")

    @agentic_function
    def parent():
        a = func_a()
        b = func_b()
        return f"{a}, {b}"

    @agentic_function
    def func_a():
        return runtime1.exec(content=[{"type": "text", "text": "a"}])

    @agentic_function
    def func_b():
        return runtime2.exec(content=[{"type": "text", "text": "b"}])

    result = parent()
    assert "from runtime1" in result
    assert "from runtime2" in result


def test_sync_exec_with_async_call_raises():
    """exec() with an async call function raises TypeError."""
    async def async_call(content, model="test", response_format=None):
        return "async reply"

    runtime = Runtime(call=async_call)

    @agentic_function
    def func():
        return runtime.exec(content=[{"type": "text", "text": "test"}])

    with pytest.raises(TypeError, match="async"):
        func()


def test_async_exec_with_sync_call_works():
    """async_exec() with a sync call function should work (auto-adapts)."""
    import asyncio

    def sync_call(content, model="test", response_format=None):
        return "sync reply"

    runtime = Runtime(call=sync_call)

    @agentic_function
    async def func():
        return await runtime.async_exec(content=[{"type": "text", "text": "test"}])

    result = asyncio.run(func())
    assert result == "sync reply"


def test_async_exec_with_async_call_works():
    """async_exec() with an async call function works normally."""
    import asyncio

    async def async_call(content, model="test", response_format=None):
        return "async reply"

    runtime = Runtime(call=async_call)

    @agentic_function
    async def func():
        return await runtime.async_exec(content=[{"type": "text", "text": "test"}])

    result = asyncio.run(func())
    assert result == "async reply"


def test_content_types():
    """Different content types are passed through."""
    received = []

    def capture(content, model="test", response_format=None):
        received.extend(content)
        return "ok"

    runtime = Runtime(call=capture)

    @agentic_function
    def func():
        return runtime.exec(content=[
            {"type": "text", "text": "analyze this"},
            {"type": "image", "path": "screenshot.png"},
            {"type": "audio", "path": "recording.wav"},
            {"type": "file", "path": "data.csv"},
        ])

    func()
    # All user content blocks should be present (after the context block)
    all_types = [b["type"] for b in received]
    assert all_types.count("text") >= 2  # context + user text
    assert "image" in all_types
    assert "audio" in all_types
    assert "file" in all_types


def test_has_session_injects_docstring():
    """has_session=True skips full context tree but still injects docstring."""
    received = []

    def capture_call(content, model="test", response_format=None):
        received.extend(content)
        return "ok"

    runtime = Runtime(call=capture_call)
    runtime.has_session = True

    @agentic_function
    def my_func():
        """This is the instruction prompt."""
        return runtime.exec(content=[
            {"type": "text", "text": "user input"},
        ])

    my_func()
    # Should have 2 blocks: docstring + user input
    assert len(received) == 2
    assert received[0]["type"] == "text"
    assert "This is the instruction prompt." in received[0]["text"]
    assert received[1]["text"] == "user input"


def test_has_session_skips_context_tree():
    """has_session=True should NOT include 'Execution Context' from summarize()."""
    received = []

    def capture_call(content, model="test", response_format=None):
        received.extend(content)
        return "ok"

    runtime = Runtime(call=capture_call)
    runtime.has_session = True

    @agentic_function
    def parent():
        """Parent doc."""
        return child()

    @agentic_function
    def child():
        """Child doc."""
        return runtime.exec(content=[
            {"type": "text", "text": "data"},
        ])

    parent()
    texts = [b.get("text", "") for b in received if b["type"] == "text"]
    # Should NOT have "Execution Context" (full tree)
    assert not any("Execution Context" in t for t in texts)
    # Should have the child's docstring
    assert any("Child doc." in t for t in texts)


def test_has_session_false_injects_full_context():
    """has_session=False should inject full context tree including 'Execution Context'."""
    received = []

    def capture_call(content, model="test", response_format=None):
        received.extend(content)
        return "ok"

    runtime = Runtime(call=capture_call)
    # has_session defaults to False

    @agentic_function
    def parent():
        """Parent doc."""
        return child()

    @agentic_function
    def child():
        """Child doc."""
        return runtime.exec(content=[
            {"type": "text", "text": "data"},
        ])

    parent()
    texts = [b.get("text", "") for b in received if b["type"] == "text"]
    # Should have "Execution Context" from summarize()
    assert any("Execution Context" in t for t in texts)


def test_has_session_no_docstring():
    """has_session=True with no docstring should not inject empty context."""
    received = []

    def capture_call(content, model="test", response_format=None):
        received.extend(content)
        return "ok"

    runtime = Runtime(call=capture_call)
    runtime.has_session = True

    @agentic_function
    def no_doc():
        return runtime.exec(content=[
            {"type": "text", "text": "bare input"},
        ])

    no_doc()
    # Should only have user content, no empty context block
    assert len(received) == 1
    assert received[0]["text"] == "bare input"


def test_runtime_retry_error_report_outside_function():
    """Retry errors outside @agentic_function still include attempt history."""
    def always_fail(content, model="test", response_format=None):
        raise ConnectionError("offline")

    runtime = Runtime(call=always_fail, max_retries=2)

    with pytest.raises(RuntimeError, match="Attempt 1: ConnectionError: offline") as exc_info:
        runtime.exec(content=[{"type": "text", "text": "bare call"}])

    assert "Attempt 2: ConnectionError: offline" in str(exc_info.value)
