"""Tests for cron tool's ``command`` field (shell entries).

Agent-prompt entries already have their create/list/delete semantics
exercised implicitly by other tests; this file pins the new shell path:

- creating with `command` persists the entry with the right shape
- creating with both prompt+command is rejected
- creating with neither is rejected
- list-mode preview renders shell entries with the ``$`` marker
- worker._spawn runs shell commands via shell=True
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from openprogram.functions.tools.cron import cron as cron_tool
from openprogram.functions.tools.cron import worker


@pytest.fixture
def sched(tmp_path, monkeypatch):
    path = tmp_path / "schedule.json"
    monkeypatch.setenv(cron_tool.DEFAULT_CRON_ENV, str(path))
    yield path


def _create(**kw) -> str:
    return cron_tool.execute(action="create", **kw)


def test_create_with_command_persists_command_field(sched):
    out = _create(cron="*/5 * * * *", command="echo hi")
    assert "Created cron entry" in out
    entries = cron_tool._load(str(sched))
    assert len(entries) == 1
    entry = entries[0]
    assert entry["command"] == "echo hi"
    assert "prompt" not in entry


def test_create_rejects_both_prompt_and_command(sched):
    out = _create(cron="@daily", prompt="be productive", command="echo hi")
    assert "either `prompt`" in out.lower() or "not both" in out.lower()
    assert not cron_tool._load(str(sched))


def test_create_rejects_neither(sched):
    out = _create(cron="@daily")
    assert "required" in out.lower()
    assert not cron_tool._load(str(sched))


def test_list_shows_shell_marker(sched):
    _create(cron="@hourly", command="touch /tmp/heartbeat")
    _create(cron="@daily",  prompt="summarize today")
    out = cron_tool.execute(action="list")
    # command entry uses $, prompt entry uses >
    assert "$ touch /tmp/heartbeat" in out
    assert "> summarize today" in out


def test_worker_spawn_runs_shell_command(tmp_path):
    marker = tmp_path / "ran.txt"
    entry = {
        "id": "test01",
        "cron": "@hourly",
        "command": f"echo ok > {marker}",
    }
    log_dir = tmp_path / "logs"
    proc = worker._spawn(entry, str(log_dir))
    assert proc is not None
    proc.wait(timeout=5)
    assert marker.exists()
    assert marker.read_text().strip() == "ok"


def test_worker_spawn_returns_none_for_empty_entry(tmp_path):
    assert worker._spawn({"id": "x", "cron": "@daily"}, str(tmp_path / "logs")) is None
