"""
Tests for Scope-based chain execution.
"""

import pytest
from pydantic import BaseModel
from harness.function import Function
from harness.session import Session
from harness.runtime import Runtime
from harness.scope import Scope


# --- Tracking session ---

class TrackingSession(Session):
    """Tracks identity and messages."""
    _counter = 0

    def __init__(self, reply: str = '{"status": "ok"}'):
        TrackingSession._counter += 1
        self.id = TrackingSession._counter
        self.messages = []
        self._reply = reply

    def send(self, message) -> str:
        self.messages.append(message if isinstance(message, str) else str(message))
        return self._reply

    @classmethod
    def reset_counter(cls):
        cls._counter = 0


class SimpleResult(BaseModel):
    status: str


# --- Scope presets ---

def test_scope_isolated_preset():
    s = Scope.isolated()
    assert s.depth == 0
    assert s.detail == "io"
    assert s.peer == "none"
    assert not s.needs_call_stack
    assert not s.needs_peers
    assert not s.shares_session


def test_scope_chained_preset():
    s = Scope.chained()
    assert s.depth == 0
    assert s.peer == "io"
    assert s.needs_peers
    assert not s.shares_session  # io doesn't share session


def test_scope_aware_preset():
    s = Scope.aware()
    assert s.depth == 1
    assert s.peer == "io"
    assert s.needs_call_stack
    assert s.needs_peers


def test_scope_full_preset():
    s = Scope.full()
    assert s.depth == -1
    assert s.detail == "full"
    assert s.peer == "full"
    assert s.shares_session  # full shares session


def test_scope_custom():
    s = Scope(depth=2, detail="io", peer="full")
    assert s.depth == 2
    assert s.needs_call_stack
    assert s.shares_session


def test_scope_validation():
    with pytest.raises(ValueError):
        Scope(detail="invalid")
    with pytest.raises(ValueError):
        Scope(peer="invalid")


# --- Chain execution with Scope ---

def test_isolated_functions_separate_sessions():
    """peer='none' → each Function gets its own Session."""
    TrackingSession.reset_counter()
    sessions = []

    def factory():
        s = TrackingSession()
        sessions.append(s)
        return s

    runtime = Runtime(session_factory=factory)

    fn1 = Function("fn1", "First", "Do 1", SimpleResult, scope=Scope.isolated())
    fn2 = Function("fn2", "Second", "Do 2", SimpleResult, scope=Scope.isolated())

    results = runtime.execute_chain([fn1, fn2], {"task": "test"})

    assert len(results) == 2
    assert len(sessions) == 2
    assert sessions[0].id != sessions[1].id


def test_full_peer_shares_session():
    """peer='full' → Functions share a Session."""
    TrackingSession.reset_counter()
    sessions = []

    def factory():
        s = TrackingSession()
        sessions.append(s)
        return s

    runtime = Runtime(session_factory=factory)

    fn1 = Function("fn1", "First", "Do 1", SimpleResult, scope=Scope.full())
    fn2 = Function("fn2", "Second", "Do 2", SimpleResult, scope=Scope.full())

    results = runtime.execute_chain([fn1, fn2], {"task": "test"})

    assert len(results) == 2
    assert len(sessions) == 1  # shared
    assert len(sessions[0].messages) >= 2


def test_io_peer_separate_sessions_with_summaries():
    """peer='io' → separate Sessions but receives prior I/O."""
    messages_received = []

    class CapturingSession(Session):
        def send(self, message) -> str:
            messages_received.append(message if isinstance(message, str) else str(message))
            return '{"status": "ok"}'

    runtime = Runtime(session_factory=lambda: CapturingSession())

    fn1 = Function("fn1", "First", "Do 1", SimpleResult, scope=Scope.chained())
    fn2 = Function("fn2", "Second", "Do 2", SimpleResult,
                   scope=Scope.chained(), params=["task"])

    runtime.execute_chain([fn1, fn2], {"task": "test"})

    # fn2 should have _prior_results in its context
    assert len(messages_received) == 2
    # The second function's message should mention fn1's output
    assert "fn1" in messages_received[1]


def test_mixed_scopes_in_chain():
    """Mix of isolated, chained, and full in one chain."""
    TrackingSession.reset_counter()
    sessions = []

    def factory():
        s = TrackingSession()
        sessions.append(s)
        return s

    runtime = Runtime(session_factory=factory)

    fn1 = Function("fn1", "Isolated", "Do 1", SimpleResult, scope=Scope.isolated())
    fn2 = Function("fn2", "Full", "Do 2", SimpleResult, scope=Scope.full())
    fn3 = Function("fn3", "Full", "Do 3", SimpleResult, scope=Scope.full())

    results = runtime.execute_chain([fn1, fn2, fn3], {"task": "test"})

    assert len(results) == 3
    # fn1: own session, fn2+fn3: shared session
    assert len(sessions) == 2


def test_chain_stops_on_failure():
    """Chain stops when a Function fails."""
    class FailSession(Session):
        def send(self, message) -> str:
            return "not valid json"

    runtime = Runtime(session_factory=lambda: FailSession())

    fn1 = Function("fn1", "Fails", "Do 1", SimpleResult,
                   scope=Scope.isolated(), max_retries=1)
    fn2 = Function("fn2", "Never runs", "Do 2", SimpleResult)

    results = runtime.execute_chain([fn1, fn2], {"task": "test"})

    assert len(results) == 1
    from harness.function import FunctionError
    assert isinstance(results[0], FunctionError)


def test_default_scope_is_isolated():
    """Function without scope defaults to Scope.isolated()."""
    fn = Function("test", "Test", "Do it", SimpleResult)
    assert fn.scope.depth == 0
    assert fn.scope.peer == "none"
    assert not fn.scope.shares_session
