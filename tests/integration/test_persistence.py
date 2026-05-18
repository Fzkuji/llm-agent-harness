"""
Tests for JSONL runtime persistence and crash recovery.
"""

import json
import os

import pytest
from openprogram import agentic_function, Runtime
from openprogram.agentic_programming.context import Context


# ── Basic persistence ─────────────────────────────────────────

def test_persist_creates_jsonl_file():
    """Top-level @agentic_function creates a JSONL persist file."""
    runtime = Runtime(call=lambda c, **kw: "ok")

    @agentic_function
    def simple():
        """Simple task."""
        return runtime.exec(content=[{"type": "text", "text": "hello"}])

    simple()
    persist_path = getattr(simple.context, "_persist_path", None)
    assert persist_path is not None
    assert os.path.exists(persist_path)
    # Read and verify structure
    with open(persist_path) as f:
        records = [json.loads(line) for line in f if line.strip()]
    # Should have: enter(simple) + enter(_exec) + exit(_exec) + exit(simple)
    assert len(records) >= 4
    assert records[0]["event"] == "enter"
    assert records[0]["name"] == "simple"
    assert records[-1]["event"] == "exit"
    assert records[-1]["path"] == "simple"
    assert records[-1]["status"] == "success"


def test_persist_enter_exit_pairs():
    """Each node has an enter and exit record."""
    runtime = Runtime(call=lambda c, **kw: "reply")

    @agentic_function
    def parent():
        """Parent."""
        return child()

    @agentic_function
    def child():
        """Child."""
        return runtime.exec(content=[{"type": "text", "text": "test"}])

    parent()
    persist_path = parent.context._persist_path
    with open(persist_path) as f:
        records = [json.loads(line) for line in f if line.strip()]

    # Check that every enter has a matching exit
    enters = [r for r in records if r["event"] == "enter"]
    exits = [r for r in records if r["event"] == "exit"]
    enter_paths = {r["path"] for r in enters}
    exit_paths = {r["path"] for r in exits}
    assert enter_paths == exit_paths


def test_persist_exec_node_recorded():
    """Exec nodes are recorded with enter/exit in persist file."""
    runtime = Runtime(call=lambda c, **kw: "llm_reply")

    @agentic_function
    def func():
        """Test."""
        return runtime.exec(content=[{"type": "text", "text": "prompt"}])

    func()
    persist_path = func.context._persist_path
    with open(persist_path) as f:
        records = [json.loads(line) for line in f if line.strip()]

    exec_enters = [r for r in records if r["event"] == "enter" and r.get("node_type") == "exec"]
    exec_exits = [r for r in records if r["event"] == "exit" and "/_exec_" in r["path"]]
    assert len(exec_enters) == 1
    assert exec_enters[0]["params"]["_content"] == "prompt"
    assert len(exec_exits) == 1
    assert exec_exits[0]["raw_reply"] == "llm_reply"


def test_persist_multiple_exec():
    """Multiple exec calls create multiple exec node pairs."""
    call_count = [0]

    def counting_call(content, model="test", response_format=None):
        call_count[0] += 1
        return f"reply_{call_count[0]}"

    runtime = Runtime(call=counting_call)

    @agentic_function
    def multi():
        """Multi exec."""
        r1 = runtime.exec(content=[{"type": "text", "text": "first"}])
        r2 = runtime.exec(content=[{"type": "text", "text": "second"}])
        return f"{r1}+{r2}"

    multi()
    persist_path = multi.context._persist_path
    with open(persist_path) as f:
        records = [json.loads(line) for line in f if line.strip()]

    exec_enters = [r for r in records if r["event"] == "enter" and r.get("node_type") == "exec"]
    assert len(exec_enters) == 2
    assert exec_enters[0]["params"]["_content"] == "first"
    assert exec_enters[1]["params"]["_content"] == "second"


def test_persist_error_recorded():
    """Errors are recorded in persist file."""
    @agentic_function
    def failing():
        """Will fail."""
        raise ValueError("boom")

    with pytest.raises(ValueError):
        failing()

    persist_path = failing.context._persist_path
    with open(persist_path) as f:
        records = [json.loads(line) for line in f if line.strip()]

    exit_record = [r for r in records if r["event"] == "exit" and r["path"] == "failing"][0]
    assert exit_record["status"] == "error"
    assert "boom" in (exit_record["error"] or "")


def test_persist_retry_attempts():
    """Retry attempts are recorded in exec exit record."""
    call_count = [0]

    def flaky(content, model="test", response_format=None):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ConnectionError("timeout")
        return "recovered"

    runtime = Runtime(call=flaky, max_retries=2)

    @agentic_function
    def func():
        """Test."""
        return runtime.exec(content=[{"type": "text", "text": "test"}])

    func()
    persist_path = func.context._persist_path
    with open(persist_path) as f:
        records = [json.loads(line) for line in f if line.strip()]

    exec_exits = [r for r in records if r["event"] == "exit" and "/_exec_" in r["path"]]
    assert len(exec_exits) == 1
    assert exec_exits[0]["attempts"] is not None
    assert len(exec_exits[0]["attempts"]) == 2


# ── Recovery from JSONL ───────────────────────────────────────

def test_from_jsonl_basic():
    """from_jsonl reconstructs a simple tree."""
    runtime = Runtime(call=lambda c, **kw: "ok")

    @agentic_function
    def simple():
        """Simple."""
        return runtime.exec(content=[{"type": "text", "text": "hello"}])

    simple()
    persist_path = simple.context._persist_path

    # Reconstruct
    restored = Context.from_jsonl(persist_path)
    assert restored.name == "simple"
    assert restored.status == "success"
    assert restored.prompt == "Simple."
    assert len(restored.children) == 1
    assert restored.children[0].node_type == "exec"


def test_from_jsonl_nested():
    """from_jsonl reconstructs a nested tree."""
    runtime = Runtime(call=lambda c, **kw: "reply")

    @agentic_function
    def parent():
        """Parent."""
        return child()

    @agentic_function
    def child():
        """Child."""
        return runtime.exec(content=[{"type": "text", "text": "test"}])

    parent()
    persist_path = parent.context._persist_path

    restored = Context.from_jsonl(persist_path)
    assert restored.name == "parent"
    assert len(restored.children) == 1
    child_node = restored.children[0]
    assert child_node.name == "child"
    assert child_node.parent is restored
    # Child should have exec node
    assert len(child_node.children) == 1
    assert child_node.children[0].node_type == "exec"
    assert child_node.children[0].raw_reply == "reply"


def test_from_jsonl_preserves_output():
    """from_jsonl preserves output and raw_reply."""
    runtime = Runtime(call=lambda c, **kw: "llm_response")

    @agentic_function
    def func():
        """Test."""
        return runtime.exec(content=[{"type": "text", "text": "q"}])

    result = func()
    persist_path = func.context._persist_path

    restored = Context.from_jsonl(persist_path)
    assert restored.output == result
    exec_node = restored.children[0]
    assert exec_node.raw_reply == "llm_response"


def test_from_jsonl_crash_recovery():
    """from_jsonl handles incomplete trees (missing exit records)."""
    import tempfile

    # Simulate a crash: write enter records but no exit for root
    records = [
        {"event": "enter", "path": "root", "name": "root", "node_type": "function",
         "prompt": "Root.", "params": {}, "render": "summary", "compress": False, "ts": 1000.0},
        {"event": "enter", "path": "root/_exec_0", "name": "_exec", "node_type": "exec",
         "params": {"_content": "hello"}, "render": "result", "compress": False, "ts": 1001.0},
        {"event": "exit", "path": "root/_exec_0", "status": "success",
         "output": "reply", "raw_reply": "reply", "duration_ms": 500, "ts": 1001.5},
        # No exit for root — simulates crash
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
        tmp_path = f.name

    try:
        restored = Context.from_jsonl(tmp_path)
        assert restored.name == "root"
        assert restored.status == "running"  # No exit → still running
        assert len(restored.children) == 1
        assert restored.children[0].status == "success"
        assert restored.children[0].raw_reply == "reply"
    finally:
        os.unlink(tmp_path)


def test_from_jsonl_error():
    """from_jsonl preserves error information."""
    @agentic_function
    def failing():
        """Will fail."""
        raise ValueError("test error")

    with pytest.raises(ValueError):
        failing()

    persist_path = failing.context._persist_path
    restored = Context.from_jsonl(persist_path)
    assert restored.status == "error"
    assert "test error" in restored.error


def test_from_jsonl_empty_file_raises():
    """from_jsonl raises on empty file."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        tmp_path = f.name

    try:
        with pytest.raises(ValueError, match="No valid records"):
            Context.from_jsonl(tmp_path)
    finally:
        os.unlink(tmp_path)


def test_persist_child_only_no_persist():
    """Child functions don't create their own persist files."""
    runtime = Runtime(call=lambda c, **kw: "ok")

    @agentic_function
    def parent():
        return child()

    @agentic_function
    def child():
        return runtime.exec(content=[{"type": "text", "text": "test"}])

    parent()
    # Only root gets persist path
    assert getattr(parent.context, "_persist_path", None) is not None
    child_ctx = parent.context.children[0]
    assert getattr(child_ctx, "_persist_path", None) is None


def test_from_jsonl_multiple_exec():
    """from_jsonl correctly reconstructs multiple exec nodes."""
    call_count = [0]

    def counting(content, model="test", response_format=None):
        call_count[0] += 1
        return f"r{call_count[0]}"

    runtime = Runtime(call=counting)

    @agentic_function
    def multi():
        """Multi."""
        a = runtime.exec(content=[{"type": "text", "text": "first"}])
        b = runtime.exec(content=[{"type": "text", "text": "second"}])
        return f"{a}+{b}"

    multi()
    persist_path = multi.context._persist_path

    restored = Context.from_jsonl(persist_path)
    assert restored.name == "multi"
    exec_nodes = [c for c in restored.children if c.node_type == "exec"]
    assert len(exec_nodes) == 2
    assert exec_nodes[0].raw_reply == "r1"
    assert exec_nodes[1].raw_reply == "r2"
