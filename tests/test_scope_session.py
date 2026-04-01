"""
Tests for Scope + Session integration.
Verifies that Sessions handle Scope parameters correctly.
"""

import pytest
from harness.scope import Scope
from harness.session import Session, Message


# --- Mock Sessions ---

class MockAPISession(Session):
    """Simulates an API Session (no memory, manual history)."""

    def __init__(self):
        self._history = []
        self._compacted = False

    def send(self, message: Message) -> str:
        self._history.append({"role": "user", "content": message})
        reply = '{"status": "ok"}'
        self._history.append({"role": "assistant", "content": reply})
        return reply

    def apply_scope(self, scope, context):
        import json
        if scope.peer and scope.peer != "none" and "_prior_results" in context:
            summary = json.dumps(context["_prior_results"])
            self._history.append({"role": "user", "content": f"[Prior results] {summary}"})
            self._history.append({"role": "assistant", "content": "Understood."})

    def post_execution(self, scope):
        if scope.needs_compact and len(self._history) >= 2:
            self._history[-2:] = [
                {"role": "user", "content": "[Compacted]"},
                {"role": "assistant", "content": "Noted."},
            ]
            self._compacted = True


class MockCLISession(Session):
    """Simulates a CLI Session (has memory, ignores injection)."""

    def __init__(self):
        self._messages_sent = []
        self._session_id = "test-session"
        self._forked = False

    def send(self, message: Message) -> str:
        self._messages_sent.append(message)
        return '{"status": "ok"}'

    @property
    def has_memory(self) -> bool:
        return True

    def apply_scope(self, scope, context):
        # CLI Session ignores injection — has its own memory
        pass

    def post_execution(self, scope):
        if scope.needs_compact:
            self._session_id = "new-session"
            self._forked = True


# --- Tests ---

def test_scope_none_fields():
    """Scope with all None fields is valid."""
    s = Scope()
    assert s.depth is None
    assert s.detail is None
    assert s.peer is None
    assert s.compact is None
    assert not s.needs_call_stack
    assert not s.needs_peers
    assert not s.shares_session
    assert not s.needs_compact


def test_scope_partial_fields():
    """Scope with some fields set, others None."""
    s = Scope(peer="io", compact=True)
    assert s.depth is None
    assert s.peer == "io"
    assert s.compact is True
    assert s.needs_peers
    assert s.needs_compact
    assert not s.needs_call_stack


def test_api_session_injects_context():
    """API Session injects prior results when peer != none."""
    session = MockAPISession()
    scope = Scope(peer="io")
    context = {"_prior_results": [{"function": "observe", "output": {"found": True}}]}

    session.apply_scope(scope, context)

    # Should have injected context into history
    assert len(session._history) == 2  # user + assistant
    assert "Prior results" in session._history[0]["content"]


def test_api_session_no_inject_when_peer_none():
    """API Session doesn't inject when peer is none."""
    session = MockAPISession()
    scope = Scope(peer="none")
    context = {"_prior_results": [{"function": "observe"}]}

    session.apply_scope(scope, context)
    assert len(session._history) == 0


def test_api_session_no_inject_when_peer_null():
    """API Session doesn't inject when peer is None (not set)."""
    session = MockAPISession()
    scope = Scope()  # peer=None
    context = {"_prior_results": [{"function": "observe"}]}

    session.apply_scope(scope, context)
    assert len(session._history) == 0


def test_api_session_compacts():
    """API Session compacts history when compact=True."""
    session = MockAPISession()
    session.send("hello")  # creates 2 history entries

    scope = Scope(compact=True)
    session.post_execution(scope)

    assert session._compacted
    assert "[Compacted]" in session._history[-2]["content"]


def test_api_session_no_compact_when_false():
    """API Session doesn't compact when compact=False."""
    session = MockAPISession()
    session.send("hello")

    scope = Scope(compact=False)
    session.post_execution(scope)

    assert not session._compacted


def test_cli_session_ignores_injection():
    """CLI Session ignores context injection (has own memory)."""
    session = MockCLISession()
    scope = Scope(depth=2, peer="io")
    context = {"_prior_results": [{"function": "observe"}], "_call_stack": ["a", "b"]}

    session.apply_scope(scope, context)

    # CLI Session should not have modified anything
    assert len(session._messages_sent) == 0


def test_cli_session_forks_on_compact():
    """CLI Session forks to new session on compact."""
    session = MockCLISession()
    old_id = session._session_id

    scope = Scope(compact=True)
    session.post_execution(scope)

    assert session._forked
    assert session._session_id != old_id


def test_cli_session_has_memory():
    """CLI Session reports has_memory=True."""
    session = MockCLISession()
    assert session.has_memory


def test_api_session_has_no_memory():
    """API Session reports has_memory=False (default)."""
    session = MockAPISession()
    assert not session.has_memory  # default from base class


def test_scope_str_partial():
    """Scope string representation with partial fields."""
    s = Scope(peer="io", compact=True)
    result = str(s)
    assert "peer=io" in result
    assert "compact=True" in result
    assert "depth" not in result  # None fields omitted
