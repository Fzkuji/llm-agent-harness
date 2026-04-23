"""Tests for the CliRunner one-shot path (phase 1b)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

import pytest

from openprogram.providers._shared.cli_backend import (
    CliBackendConfig,
    CliBackendPlugin,
    CliRunner,
    Done,
    Error,
    SessionInfo,
    TextDelta,
    ToolCall,
    Usage,
)


def _write_fake_cli(
    tmpdir: Path,
    *,
    lines: list[dict],
    exit_code: int = 0,
    stderr: str = "",
    echo_argv: bool = False,
) -> Path:
    """Write an executable shell script that prints ``lines`` as JSONL.

    The script ignores its inputs — we just want to assert the runner
    parses whatever the CLI emits, not that the CLI does anything real.
    """
    script = tmpdir / "fake_cli"
    payload_path = tmpdir / "payload.jsonl"
    with payload_path.open("w") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")
    argv_dump = ""
    if echo_argv:
        argv_dump = 'printf "ARGV=%s\\n" "$*" 1>&2\n'
    stderr_block = ""
    if stderr:
        stderr_block = f'printf "%s" {json.dumps(stderr)} 1>&2\n'
    script.write_text(
        "#!/bin/sh\n"
        + argv_dump
        + f'cat {json.dumps(str(payload_path))}\n'
        + stderr_block
        + f"exit {exit_code}\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def _make_plugin(cmd: str, **config_overrides) -> CliBackendPlugin:
    cfg = CliBackendConfig(
        command=cmd,
        output="jsonl",
        jsonl_dialect="claude-stream-json",
        **config_overrides,
    )
    return CliBackendPlugin(id="fake-cli", config=cfg)


async def _collect(runner: CliRunner, prompt: str, **kw) -> list:
    events = []
    async for ev in runner.run(prompt, model_id=kw.pop("model_id", "claude-sonnet-4-6"), **kw):
        events.append(ev)
    return events


def test_runner_parses_full_turn(tmp_path: Path) -> None:
    cli = _write_fake_cli(tmp_path, lines=[
        {"type": "system", "session_id": "sess-1", "model": "claude-sonnet-4-6"},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Hello"},
            {"type": "tool_use", "id": "t1", "name": "bash", "input": {"cmd": "ls"}},
        ]}},
        {"type": "result", "result": "ok",
         "usage": {"input_tokens": 100, "output_tokens": 50,
                   "cache_read_input_tokens": 20, "cache_creation_input_tokens": 10},
         "modelUsage": {"claude-sonnet-4-6": {"contextWindow": 200000}},
         "duration_ms": 1200, "num_turns": 1},
    ])
    runner = CliRunner(
        plugin=_make_plugin(str(cli)),
        workspace_dir=str(tmp_path),
    )
    events = asyncio.run(_collect(runner, "hi"))

    types = [type(e).__name__ for e in events]
    assert types == ["SessionInfo", "TextDelta", "ToolCall", "Usage", "Done"]

    sess = events[0]
    assert isinstance(sess, SessionInfo)
    assert sess.session_id == "sess-1"
    assert sess.model_id == "claude-sonnet-4-6"

    text = events[1]
    assert isinstance(text, TextDelta) and text.text == "Hello"

    call = events[2]
    assert isinstance(call, ToolCall) and call.name == "bash"
    assert call.input == {"cmd": "ls"}

    usage = events[3]
    assert isinstance(usage, Usage)
    # 100 + 20 + 10 = 130 (total input, including cache reads + creates)
    assert usage.input_tokens == 130
    assert usage.cache_read == 20
    assert usage.cache_create == 10
    assert usage.context_window == 200000

    done = events[4]
    assert isinstance(done, Done)
    assert done.duration_ms >= 0


def test_runner_ignores_unknown_messages(tmp_path: Path) -> None:
    cli = _write_fake_cli(tmp_path, lines=[
        {"type": "something_random", "data": 42},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}},
    ])
    runner = CliRunner(plugin=_make_plugin(str(cli)), workspace_dir=str(tmp_path))
    events = asyncio.run(_collect(runner, "hi"))
    # SessionInfo not emitted because no "system" message; unknown msg skipped.
    assert [type(e).__name__ for e in events] == ["TextDelta", "Done"]


def test_runner_emits_error_on_nonzero_exit(tmp_path: Path) -> None:
    cli = _write_fake_cli(tmp_path, lines=[], exit_code=7, stderr="boom")
    runner = CliRunner(plugin=_make_plugin(str(cli)), workspace_dir=str(tmp_path))
    events = asyncio.run(_collect(runner, "hi"))
    assert len(events) == 1 and isinstance(events[0], Error)
    assert events[0].kind == "ExitCode(7)"
    assert "boom" in events[0].message


def test_runner_emits_error_when_cli_missing(tmp_path: Path) -> None:
    runner = CliRunner(
        plugin=_make_plugin("/nonexistent/no_such_cli_xyzzy"),
        workspace_dir=str(tmp_path),
    )
    events = asyncio.run(_collect(runner, "hi"))
    assert len(events) == 1 and isinstance(events[0], Error)
    assert events[0].recoverable is False
    assert events[0].kind == "FileNotFoundError"


def test_argv_builder_model_and_session_and_system(tmp_path: Path) -> None:
    cli = _write_fake_cli(tmp_path, lines=[
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "x"}]}},
    ], echo_argv=True)

    plugin = _make_plugin(
        str(cli),
        args=("--permission-mode", "bypassPermissions"),
        model_arg="--model",
        session_arg="--session-id",
        session_mode="always",
        system_prompt_arg="--append-system-prompt",
        input="arg",
    )
    runner = CliRunner(plugin=plugin, workspace_dir=str(tmp_path))

    # Peek at argv by patching _build_argv indirectly: build once and inspect.
    argv = runner._build_argv(
        prompt="hello",
        model_id="claude-sonnet-4-6",
        system_prompt="be helpful",
        image_paths=(),
        resume=False,
    )
    assert argv[0] == str(cli)
    assert "--model" in argv and "claude-sonnet-4-6" in argv
    assert "--session-id" in argv
    assert "--append-system-prompt" in argv and "be helpful" in argv
    assert argv[-1] == "hello"


def test_session_id_captured_and_persisted(tmp_path: Path) -> None:
    """After run 1 emits SessionInfo, run 2 should inject it via resume_args."""
    state_path = tmp_path / "sess.json"
    cli = _write_fake_cli(tmp_path, lines=[
        {"type": "system", "session_id": "sess-captured", "model": "claude-sonnet-4-6"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "x"}]}},
    ])
    plugin = _make_plugin(
        str(cli),
        resume_args=("--resume", "{sessionId}"),
        session_mode="existing",
    )
    # Run #1: no prior session → no resume_args.
    r1 = CliRunner(plugin=plugin, workspace_dir=str(tmp_path),
                   session_state_path=str(state_path))
    argv1 = r1._build_argv(prompt="hi", model_id="claude-sonnet-4-6",
                           system_prompt=None, image_paths=(), resume=True)
    assert "--resume" not in argv1
    asyncio.run(_collect(r1, "hi"))
    assert r1._session_id == "sess-captured"
    # State file contains the id.
    blob = json.loads(state_path.read_text())
    assert blob["fake-cli"] == "sess-captured"

    # Run #2: brand new runner instance reads the state file and resumes.
    r2 = CliRunner(plugin=plugin, workspace_dir=str(tmp_path),
                   session_state_path=str(state_path))
    argv2 = r2._build_argv(prompt="hi", model_id="claude-sonnet-4-6",
                           system_prompt=None, image_paths=(), resume=True)
    assert "--resume" in argv2 and "sess-captured" in argv2


def test_bump_auth_epoch_clears_session(tmp_path: Path) -> None:
    state_path = tmp_path / "sess.json"
    cli = _write_fake_cli(tmp_path, lines=[
        {"type": "system", "session_id": "sess-A", "model": "claude-sonnet-4-6"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "x"}]}},
    ])
    plugin = _make_plugin(
        str(cli),
        resume_args=("--resume", "{sessionId}"),
        session_mode="existing",
    )
    r = CliRunner(plugin=plugin, workspace_dir=str(tmp_path),
                  session_state_path=str(state_path))
    asyncio.run(_collect(r, "hi"))
    assert r._session_id == "sess-A"
    r.bump_auth_epoch()
    assert r._session_id is None
    # State file no longer carries the id under this plugin key.
    blob = json.loads(state_path.read_text())
    assert "fake-cli" not in blob


def test_watchdog_kills_silent_cli(tmp_path: Path) -> None:
    """CLI that prints nothing then sleeps forever must be killed and
    produce an ``Error(kind="WatchdogStall", recoverable=True)``."""
    script = tmp_path / "silent_cli"
    # Sleep long enough to outrun the 200ms watchdog; we'll kill it.
    script.write_text("#!/bin/sh\nsleep 30\n")
    script.chmod(0o755)
    plugin = _make_plugin(str(script))
    runner = CliRunner(
        plugin=plugin,
        workspace_dir=str(tmp_path),
        overall_timeout_ms=200,  # short overall → watchdog clamps to this
    )
    events = asyncio.run(_collect(runner, "hi"))
    assert len(events) == 1 and isinstance(events[0], Error)
    assert events[0].kind == "WatchdogStall"
    assert events[0].recoverable is True


def test_watchdog_does_not_fire_when_output_flows(tmp_path: Path) -> None:
    """Output arriving before the budget expires must reset the timer."""
    script = tmp_path / "dripping_cli"
    # Two lines separated by 30ms; watchdog at ~200ms shouldn't fire.
    script.write_text(
        "#!/bin/sh\n"
        'printf \'{"type":"assistant","message":{"content":[{"type":"text","text":"a"}]}}\\n\'\n'
        "sleep 0.03\n"
        'printf \'{"type":"assistant","message":{"content":[{"type":"text","text":"b"}]}}\\n\'\n'
    )
    script.chmod(0o755)
    plugin = _make_plugin(str(script))
    runner = CliRunner(
        plugin=plugin,
        workspace_dir=str(tmp_path),
        overall_timeout_ms=1_000,
    )
    events = asyncio.run(_collect(runner, "hi"))
    texts = [e.text for e in events if isinstance(e, TextDelta)]
    assert texts == ["a", "b"]
    assert any(isinstance(e, Done) for e in events)


def _write_live_echo_cli(tmp_path: Path) -> Path:
    """Fake live-session CLI.

    Reads one JSON line from stdin per turn, emits an ``assistant`` text
    block echoing the user's prompt, then a ``result`` message to mark
    turn end, then waits for the next line. Exits cleanly on EOF.
    """
    script = tmp_path / "live_cli"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    try:\n"
        "        msg = json.loads(line)\n"
        "    except Exception:\n"
        "        continue\n"
        "    text = msg.get('message', {}).get('content', [{}])[0].get('text', '')\n"
        "    print(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':'echo:'+text}]}}), flush=True)\n"
        "    print(json.dumps({'type':'result','result':'ok','usage':{'input_tokens':1,'output_tokens':1}}), flush=True)\n"
    )
    script.chmod(0o755)
    return script


def test_live_session_reuses_process_across_turns(tmp_path: Path) -> None:
    cli = _write_live_echo_cli(tmp_path)
    plugin = _make_plugin(str(cli), live_session="claude-stdio", input="stdin")
    runner = CliRunner(plugin=plugin, workspace_dir=str(tmp_path))

    async def scenario():
        ev1 = await _collect(runner, "hello")
        proc_id_after_turn1 = id(runner._live_proc)
        ev2 = await _collect(runner, "world")
        proc_id_after_turn2 = id(runner._live_proc)
        await runner.close()
        return ev1, ev2, proc_id_after_turn1, proc_id_after_turn2

    ev1, ev2, p1, p2 = asyncio.run(scenario())

    texts1 = [e.text for e in ev1 if isinstance(e, TextDelta)]
    texts2 = [e.text for e in ev2 if isinstance(e, TextDelta)]
    assert texts1 == ["echo:hello"]
    assert texts2 == ["echo:world"]
    # Same process object across turns — not respawned.
    assert p1 == p2
    # Each turn ends with Done (synthesized at ``result`` boundary).
    assert any(isinstance(e, Done) for e in ev1)
    assert any(isinstance(e, Done) for e in ev2)
    assert runner._live_proc is None


def test_live_session_close_tears_down(tmp_path: Path) -> None:
    cli = _write_live_echo_cli(tmp_path)
    plugin = _make_plugin(str(cli), live_session="claude-stdio", input="stdin")
    runner = CliRunner(plugin=plugin, workspace_dir=str(tmp_path))

    async def scenario():
        await _collect(runner, "hi")
        proc = runner._live_proc
        assert proc is not None and proc.returncode is None
        await runner.close()
        return proc

    proc = asyncio.run(scenario())
    assert runner._live_proc is None
    # Underlying proc has exited.
    assert proc.returncode is not None


def test_stdin_mode_feeds_prompt(tmp_path: Path) -> None:
    # Fake CLI that reads stdin and echoes it wrapped in a text block.
    script = tmp_path / "echo_stdin"
    script.write_text(
        "#!/bin/sh\n"
        "INPUT=$(cat)\n"
        'printf \'{"type":"assistant","message":{"content":[{"type":"text","text":"%s"}]}}\n\' "$INPUT"\n'
    )
    script.chmod(0o755)
    plugin = _make_plugin(str(script), input="stdin")
    runner = CliRunner(plugin=plugin, workspace_dir=str(tmp_path))
    events = asyncio.run(_collect(runner, "piped-prompt"))
    texts = [e.text for e in events if isinstance(e, TextDelta)]
    assert texts == ["piped-prompt"]
