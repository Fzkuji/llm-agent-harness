"""Additional regression tests for Context JSON serialization roundtrips."""

from openprogram import Context, agentic_function


def test_context_from_dict_uses_current_defaults_for_legacy_payloads():
    """Missing fields should fall back to current Context defaults."""
    restored = Context.from_dict({"name": "legacy", "children": []})

    assert restored.expose == "io"
    assert restored.status == "running"

def test_context_json_roundtrip_preserves_attempts_and_expose():
    """Roundtripping via _to_dict()/from_dict() keeps retry and expose fields intact."""

    @agentic_function(expose="full")
    def task():
        child()
        return "done"

    @agentic_function(expose="io")
    def child():
        return "child output"

    task()

    task.context.attempts = [
        {"attempt": 1, "error": "temporary failure", "raw_reply": None},
        {"attempt": 2, "error": None, "raw_reply": "fixed on retry"},
    ]
    task.context.error = "temporary failure"
    task.context.status = "success"
    task.context.source_file = "/tmp/task.py"
    task.context.children[0].source_file = "/tmp/child.py"

    restored = Context.from_dict(task.context._to_dict())

    assert restored.attempts == task.context.attempts
    assert restored.error == "temporary failure"
    assert restored.status == "success"
    assert restored.expose == "full"
    assert restored.source_file == "/tmp/task.py"

    restored_child = restored.children[0]
    original_child = task.context.children[0]
    assert restored_child.expose == original_child.expose
    assert restored_child.output == original_child.output
    assert restored_child.source_file == "/tmp/child.py"
