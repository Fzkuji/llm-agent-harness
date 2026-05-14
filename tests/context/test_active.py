"""Active-context plumbing — set_active / push_frame / append_node.

These tests cover the ContextVar lifecycle and frame stack without
involving runtime.exec or @agentic_function — those wire-ups come
in Phase 3+ of the context refactor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openprogram.context import active as ac
from openprogram.context.nodes import Call, ROLE_USER, ROLE_LLM
from openprogram.context.session_db import DagSessionDB
from openprogram.context.storage import GraphStore


@pytest.fixture
def store(tmp_path: Path) -> GraphStore:
    db_path = tmp_path / "x.sqlite"
    db = DagSessionDB(db_path)
    db.create_session("s1", agent_id="a")
    return GraphStore(db_path, "s1")


# ── Lifecycle ───────────────────────────────────────────────────────


def test_current_is_none_by_default():
    assert ac.current() is None


def test_set_active_installs_context(store):
    token = ac.set_active(store=store)
    try:
        ctx = ac.current()
        assert ctx is not None
        assert ctx.store is store
        assert ctx.session_id == "s1"
        assert ctx.head_id is None
        assert ctx.frames == []
    finally:
        ac.reset_active(token)
    assert ac.current() is None


def test_set_active_accepts_explicit_head(store):
    token = ac.set_active(store=store, head_id="n0")
    try:
        assert ac.current().head_id == "n0"
    finally:
        ac.reset_active(token)


def test_reset_active_clears(store):
    token = ac.set_active(store=store)
    ac.reset_active(token)
    assert ac.current() is None


# ── Frame stack ─────────────────────────────────────────────────────


def test_push_frame_outside_active_returns_none():
    frame = ac.push_frame(name="x", pending_call_id="id1")
    assert frame is None


def test_push_pop_frame_roundtrip(store):
    token = ac.set_active(store=store, head_id="user-1")
    try:
        f = ac.push_frame(
            name="my_fn",
            pending_call_id="call-42",
            expose="io",
            render_range={"depth": 1},
        )
        assert f is not None
        assert f.name == "my_fn"
        assert f.pending_call_id == "call-42"
        assert f.entry_predecessor == "user-1"
        assert f.render_range == {"depth": 1}

        assert ac.current_frame() is f
        assert len(ac.current().frames) == 1

        ac.pop_frame(f)
        assert ac.current_frame() is None
        assert ac.current().frames == []
    finally:
        ac.reset_active(token)


def test_pop_frame_handles_none(store):
    token = ac.set_active(store=store)
    try:
        ac.pop_frame(None)  # no crash
    finally:
        ac.reset_active(token)


def test_pop_out_of_order_removes_correct_frame(store):
    token = ac.set_active(store=store)
    try:
        a = ac.push_frame(name="a", pending_call_id="A")
        b = ac.push_frame(name="b", pending_call_id="B")
        ac.pop_frame(a)  # pop the bottom one first
        assert ac.current_frame() is b
        assert len(ac.current().frames) == 1
        ac.pop_frame(b)
        assert ac.current().frames == []
    finally:
        ac.reset_active(token)


# ── DAG writes ──────────────────────────────────────────────────────


def test_append_node_no_active_is_noop():
    ac.append_node(Call(id="ghost", role=ROLE_USER, output="x"))
    # No exception — that's the contract.


def test_append_node_persists_and_advances_head(store):
    token = ac.set_active(store=store)
    try:
        n = Call(id="u1", role=ROLE_USER, output="hello")
        ac.append_node(n)
        assert ac.current().head_id == "u1"
        # In-memory graph mirrors the write
        assert "u1" in ac.current().graph.nodes
        # Reloading from disk should also see it
        graph = store.load()
        assert "u1" in graph.nodes
        assert graph.nodes["u1"].output == "hello"
    finally:
        ac.reset_active(token)


def test_append_chain_keeps_seq_monotonic(store):
    token = ac.set_active(store=store)
    try:
        ac.append_node(Call(id="u1", role=ROLE_USER, output="q"))
        ac.append_node(Call(id="m1", role=ROLE_LLM, output="a"))
        ac.append_node(Call(id="u2", role=ROLE_USER, output="q2"))
        seqs = sorted(n.seq for n in ac.current().graph.nodes.values())
        assert seqs == [0, 1, 2]
        assert ac.current().head_id == "u2"
    finally:
        ac.reset_active(token)


def test_update_node_no_active_is_noop():
    ac.update_node("ghost", output="x")


def test_update_node_writes_through(store):
    token = ac.set_active(store=store)
    try:
        ac.append_node(Call(id="f1", role="code", name="fn", output=None,
                             metadata={"expose": "io", "status": "running"}))
        ac.update_node("f1", output="done",
                       metadata={"status": "success"})
        n = ac.current().graph.nodes["f1"]
        assert n.output == "done"
        assert n.metadata["status"] == "success"
        # expose preserved (metadata merged, not replaced)
        assert n.metadata["expose"] == "io"
    finally:
        ac.reset_active(token)
