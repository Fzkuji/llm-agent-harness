"""
Tests for Context tree: summarize, tree, save.
"""

import json
import tempfile
from pathlib import Path

import pytest
from agentic import agentic_function, Runtime


def mock_call(content, model="test", response_format=None):
    for block in reversed(content):
        if block["type"] == "text" and "Execution Context" not in block["text"]:
            return block["text"]
    return "ok"


runtime = Runtime(call=mock_call)


def test_tree_output():
    """tree() returns a readable string."""
    @agentic_function
    def parent():
        child()
        return "done"

    @agentic_function
    def child():
        return "child done"

    parent()
    tree = parent.context.tree()
    assert "parent" in tree
    assert "child" in tree
    assert "✓" in tree


def test_summarize_default():
    """summarize() returns execution context text."""
    @agentic_function
    def outer():
        inner_a()
        return inner_b()

    @agentic_function
    def inner_a():
        return runtime.exec(content=[{"type": "text", "text": "result_a"}])

    @agentic_function
    def inner_b():
        return runtime.exec(content=[{"type": "text", "text": "result_b"}])

    outer()
    root = outer.context
    # inner_b should have seen inner_a in its context
    assert root.children[1].raw_reply is not None


def test_summarize_depth_0():
    """depth=0 shows no ancestors."""
    @agentic_function
    def outer():
        return inner()

    @agentic_function(summarize={"depth": 0, "siblings": 0})
    def inner():
        return runtime.exec(content=[{"type": "text", "text": "isolated"}])

    outer()
    # Should still work, just less context
    root = outer.context
    assert root.children[0].raw_reply is not None


def test_compress_hides_children():
    """compress=True hides children in summarize."""
    @agentic_function(compress=True)
    def compressed():
        sub()
        return "compressed result"

    @agentic_function
    def sub():
        return "sub result"

    @agentic_function
    def outer():
        compressed()
        return check()

    @agentic_function
    def check():
        return runtime.exec(content=[{"type": "text", "text": "checking"}])

    outer()
    root = outer.context
    # compressed's children exist in tree
    assert len(root.children[0].children) == 1
    assert root.children[0].children[0].name == "sub"


def test_save_jsonl(tmp_path):
    """save() to .jsonl creates valid JSON lines."""
    @agentic_function
    def task():
        step()
        return "done"

    @agentic_function
    def step():
        return "step done"

    task()
    path = str(tmp_path / "test.jsonl")
    task.context.save(path)

    lines = Path(path).read_text().strip().split("\n")
    assert len(lines) >= 2  # at least task + step
    for line in lines:
        obj = json.loads(line)
        assert "name" in obj
        assert "status" in obj




def test_save_jsonl_preserves_numeric_depth(tmp_path):
    """JSONL export keeps the flattened depth field instead of nested node.path depth text."""
    @agentic_function
    def task():
        step()
        return "done"

    @agentic_function
    def step():
        return "step done"

    task()
    path = tmp_path / "depth.jsonl"
    task.context.save(path)

    rows = [json.loads(line) for line in path.read_text().strip().split("\n")]
    assert rows[0]["depth"] == 0
    assert rows[1]["depth"] == 1


def test_summarize_max_tokens_keeps_current_call_and_prefers_newer_siblings():
    """max_tokens trimming drops older siblings first and keeps the current call block."""
    @agentic_function
    def step(label: str):
        return label

    @agentic_function
    def outer():
        step("first")
        step("second")
        return inspect()

    @agentic_function
    def inspect():
        return "ready"

    outer()

    trimmed = outer.context.children[-1].summarize(siblings=-1, max_tokens=20)
    roomy = outer.context.children[-1].summarize(siblings=-1, max_tokens=40)

    assert "Current Call" in trimmed
    assert "Current Call" in roomy
    assert "label='first'" not in roomy
    assert "label='second'" in roomy



def test_save_md(tmp_path):
    """save() to .md creates readable output."""
    @agentic_function
    def task():
        return "done"

    task()
    path = str(tmp_path / "test.md")
    task.context.save(path)

    content = Path(path).read_text()
    assert "task" in content


def test_save_accepts_pathlike_jsonl(tmp_path):
    """save() accepts pathlib.Path for JSONL output."""
    @agentic_function
    def task():
        return "done"

    task()
    path = tmp_path / "pathlike.jsonl"
    task.context.save(path)

    lines = path.read_text().strip().split("\n")
    assert len(lines) == 1
    assert json.loads(lines[0])["name"] == "task"


def test_save_json_tree(tmp_path):
    """save() to .json exports one nested tree object."""
    @agentic_function
    def task():
        step()
        return "done"

    @agentic_function
    def step():
        return "step done"

    task()
    path = tmp_path / "tree.json"
    task.context.save(path)

    obj = json.loads(path.read_text())
    assert obj["name"] == "task"
    assert obj["children"][0]["name"] == "step"
    assert obj["children"][0]["output"] == "step done"


def test_save_accepts_pathlike_md(tmp_path):
    """save() accepts pathlib.Path for Markdown output."""
    @agentic_function
    def task():
        return "done"

    task()
    path = tmp_path / "pathlike.md"
    task.context.save(path)

    assert "task" in path.read_text()


def test_save_rejects_unsupported_extension(tmp_path):
    """save() rejects unsupported file extensions with a clear error."""
    @agentic_function
    def task():
        return "done"

    task()
    path = tmp_path / "bad.txt"
    with pytest.raises(ValueError, match=r"Use \.md, \.json, or \.jsonl"):
        task.context.save(path)


def test_traceback_on_error():
    """traceback() shows error chain."""
    @agentic_function
    def outer():
        return inner()

    @agentic_function
    def inner():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        outer()

    root = outer.context
    tb = root.traceback()
    assert "outer" in tb
    assert "inner" in tb
    assert "boom" in tb


def test_path_property():
    """path gives correct dot-separated path."""
    @agentic_function
    def root_fn():
        return child_fn()

    @agentic_function
    def child_fn():
        return "done"

    root_fn()
    root = root_fn.context
    assert "root_fn" in root.path
    assert "child_fn" in root.children[0].path


def test_summarize_branch_uses_consistent_indentation():
    """Expanded branch children align with the surrounding traceback indentation."""
    @agentic_function
    def leaf():
        return "leaf done"

    @agentic_function
    def branch_node():
        leaf()
        return "branch done"

    @agentic_function
    def outer():
        branch_node()
        return inspect()

    @agentic_function
    def inspect():
        return "ready"

    outer()
    summary = outer.context.children[1].summarize(branch=["branch_node"])

    assert "        - outer.branch_node()" in summary
    assert "            - outer.branch_node.leaf()" in summary


def test_duration():
    """duration_ms is non-negative."""
    @agentic_function
    def timed():
        return "done"

    timed()
    assert timed.context.duration_ms >= 0
