from __future__ import annotations

import pytest

from openprogram.functions.tools.todo import todo


@pytest.fixture(autouse=True)
def clear_todos():
    todo._TODOS.clear()
    yield
    todo._TODOS.clear()


def test_read_execute_returns_placeholder_when_empty():
    assert todo.read_execute() == "(no todos)"


def test_write_execute_rejects_non_list_items():
    assert todo.write_execute(items=None) == "Error: items must be an array"
    assert todo.write_execute(items="nope") == "Error: items must be an array"


def test_write_execute_rejects_missing_required_fields():
    result = todo.write_execute(items=[{"id": "1", "status": "pending"}])
    assert result == "Error: item #0 missing required field 'subject'"


@pytest.mark.parametrize("status", ["waiting", "done", "PENDING"])
def test_write_execute_rejects_invalid_status(status: str):
    result = todo.write_execute(
        items=[{"id": "1", "subject": "Test", "status": status}]
    )
    assert result == f"Error: item #0 has invalid status {status!r}"


def test_write_execute_replaces_entire_list_and_read_formats_rows():
    first = todo.write_execute(
        items=[
            {"id": 1, "subject": "Plan task", "status": "pending"},
            {"id": "2", "subject": "Ship fix", "status": "completed"},
        ]
    )
    assert first == "Stored 2 todos (pending=1, in_progress=0, completed=1)"
    assert todo._TODOS == [
        {"id": "1", "subject": "Plan task", "status": "pending"},
        {"id": "2", "subject": "Ship fix", "status": "completed"},
    ]
    assert todo.read_execute().splitlines() == [
        "[pending     ] #1 Plan task",
        "[completed   ] #2 Ship fix",
    ]

    second = todo.write_execute(
        items=[{"id": "3", "subject": "Verify tests", "status": "in_progress"}]
    )
    assert second == "Stored 1 todo (pending=0, in_progress=1, completed=0)"
    assert todo.read_execute() == "[in_progress ] #3 Verify tests"
