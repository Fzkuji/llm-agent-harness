"""
Tests for error recovery: attempts tracking, run_with_fix.
"""

import pytest
from agentic import agentic_function, Runtime
from agentic.meta_function import run_with_fix, fix


# ── attempts tracking ──────────────────────────────────────────

def test_successful_exec_records_attempt():
    """Successful exec records one attempt with reply and no error."""
    runtime = Runtime(call=lambda c, **kw: "ok")

    @agentic_function
    def func():
        return runtime.exec(content=[{"type": "text", "text": "test"}])

    func()
    ctx = func.context
    assert len(ctx.attempts) == 1
    assert ctx.attempts[0]["attempt"] == 1
    assert ctx.attempts[0]["reply"] == "ok"
    assert ctx.attempts[0]["error"] is None


def test_retry_records_all_attempts():
    """Failed then successful exec records both attempts."""
    call_count = [0]

    def flaky(content, model="test", response_format=None):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ConnectionError("timeout")
        return "recovered"

    runtime = Runtime(call=flaky, max_retries=2)

    @agentic_function
    def func():
        return runtime.exec(content=[{"type": "text", "text": "test"}])

    result = func()
    ctx = func.context
    assert result == "recovered"
    assert len(ctx.attempts) == 2
    # First attempt failed
    assert ctx.attempts[0]["error"] is not None
    assert "timeout" in ctx.attempts[0]["error"]
    assert ctx.attempts[0]["reply"] is None
    # Second attempt succeeded
    assert ctx.attempts[1]["reply"] == "recovered"
    assert ctx.attempts[1]["error"] is None


def test_all_retries_failed_records_all_attempts():
    """All retries failed — all attempts recorded."""
    runtime = Runtime(
        call=lambda c, **kw: (_ for _ in ()).throw(ConnectionError("down")),
        max_retries=3,
    )

    @agentic_function
    def func():
        return runtime.exec(content=[{"type": "text", "text": "test"}])

    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        func()

    ctx = func.context
    assert len(ctx.attempts) == 3
    for a in ctx.attempts:
        assert a["error"] is not None
        assert a["reply"] is None


def test_attempts_visible_in_summarize():
    """Failed attempts show up in sibling's summarize context."""
    call_count = [0]

    def flaky(content, model="test", response_format=None):
        call_count[0] += 1
        if call_count[0] <= 1:
            raise ValueError("bad format")
        return "ok"

    runtime = Runtime(call=flaky, max_retries=2)
    received_context = []

    def capture(content, model="test", response_format=None):
        received_context.extend(content)
        return "final"

    runtime2 = Runtime(call=capture)

    @agentic_function
    def parent():
        step_a()
        return step_b()

    @agentic_function
    def step_a():
        return runtime.exec(content=[{"type": "text", "text": "first"}])

    @agentic_function
    def step_b():
        return runtime2.exec(content=[{"type": "text", "text": "second"}])

    parent()
    # step_b's context should contain step_a's failed attempt info
    ctx_text = received_context[0]["text"]
    assert "FAILED" in ctx_text
    assert "bad format" in ctx_text


def test_attempts_in_save(tmp_path):
    """Attempts are saved in JSONL."""
    import json
    from pathlib import Path

    call_count = [0]

    def flaky(content, model="test", response_format=None):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ValueError("oops")
        return "fine"

    runtime = Runtime(call=flaky, max_retries=2)

    @agentic_function
    def func():
        return runtime.exec(content=[{"type": "text", "text": "test"}])

    func()
    path = str(tmp_path / "test.jsonl")
    func.context.save(path)

    data = json.loads(Path(path).read_text().strip().split("\n")[0])
    assert "attempts" in data
    assert len(data["attempts"]) == 2


# ── run_with_fix ───────────────────────────────────────────────

def test_run_with_fix_success_without_fix():
    """run_with_fix returns result when function succeeds first time."""
    runtime = Runtime(call=lambda c, **kw: "ok")

    @agentic_function
    def good_fn(x):
        """Double x."""
        return str(int(x) * 2)

    result = run_with_fix(fn=good_fn, args={"x": "5"}, runtime=runtime)
    assert result == "10"


def test_run_with_fix_recovers():
    """run_with_fix: original fails → fix → fixed version succeeds."""
    def smart_call(content, model="test", response_format=None):
        # fix() asks LLM to rewrite → return valid code
        # The fixed function doesn't use runtime.exec(), just pure Python
        return '''@agentic_function
def broken_fn(x):
    """Fixed: add one to x."""
    return str(int(x) + 1)'''

    runtime = Runtime(call=smart_call)

    @agentic_function
    def broken_fn(x):
        """Add one to x."""
        raise ValueError("I'm broken")

    result = run_with_fix(
        fn=broken_fn,
        args={"x": "5"},
        runtime=runtime,
        description="Add one to x",
    )
    assert result == "6"


def test_run_with_fix_both_fail():
    """run_with_fix raises when both original and fixed fail."""
    def always_fail_call(content, model="test", response_format=None):
        # fix() generates a function that also fails
        return '''@agentic_function
def still_broken(x):
    """Still broken."""
    raise RuntimeError("still broken")'''

    runtime = Runtime(call=always_fail_call)

    @agentic_function
    def broken_fn(x):
        """Do something."""
        raise ValueError("original error")

    with pytest.raises(RuntimeError, match="both failed"):
        run_with_fix(fn=broken_fn, args={"x": "1"}, runtime=runtime)


def test_run_with_fix_context_tree():
    """run_with_fix records everything in one Context tree."""
    call_count = [0]

    def mock_call(content, model="test", response_format=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return '''@agentic_function
def fixed(x):
    """Fixed."""
    return "fixed_result"'''
        return "not used"

    runtime = Runtime(call=mock_call)

    @agentic_function
    def broken(x):
        """Broken."""
        raise ValueError("broken")

    run_with_fix(fn=broken, args={"x": "1"}, runtime=runtime, description="do something")

    ctx = run_with_fix.context
    assert ctx is not None
    assert ctx.name == "run_with_fix"
    # Should have children: broken (failed), fix, fixed (succeeded)
    child_names = [c.name for c in ctx.children]
    assert "broken" in child_names
    assert "fix" in child_names
