"""Additional regression tests for Context JSON serialization roundtrips."""

from agentic import Context, agentic_function


def test_context_json_roundtrip_preserves_attempts_and_render_metadata():
    """Roundtripping via _to_dict()/from_dict() keeps retry and render fields intact."""

    @agentic_function(render="detail", compress=True)
    def task():
        child()
        return "done"

    @agentic_function(render="result")
    def child():
        return "child output"

    task()

    task.context.attempts = [
        {"attempt": 1, "error": "temporary failure", "raw_reply": None},
        {"attempt": 2, "error": None, "raw_reply": "fixed on retry"},
    ]
    task.context.error = "temporary failure"
    task.context.status = "success"

    restored = Context.from_dict(task.context._to_dict())

    assert restored.attempts == task.context.attempts
    assert restored.error == "temporary failure"
    assert restored.status == "success"
    assert restored.render == "detail"
    assert restored.compress is True

    restored_child = restored.children[0]
    original_child = task.context.children[0]
    assert restored_child.render == original_child.render
    assert restored_child.output == original_child.output
