"""SSH backend — ``ssh <target> "..."`` per call.

Uses the system ``ssh`` client with ``BatchMode=yes`` so password
prompts don't dead-lock the agent loop. The caller is expected to
have set up key-based auth ahead of time.
"""
from __future__ import annotations

import shlex
import subprocess

from openprogram.backend.base import Backend, RunResult, decode_maybe


class SshBackend(Backend):
    backend_id = "ssh"

    def __init__(self, target: str) -> None:
        if not target:
            raise RuntimeError(
                "ssh backend: `backend.ssh_target` is empty. Run "
                "`openprogram config backend` to set user@host."
            )
        self.target = target

    def run(self, command: str, timeout: float,
            cwd: str | None = None) -> RunResult:
        if cwd:
            command = f"cd {shlex.quote(cwd)} && {command}"
        argv = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            self.target,
            command,
        ]
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return RunResult(proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as e:
            return RunResult(
                exit_code=-1,
                stdout=decode_maybe(e.stdout),
                stderr=decode_maybe(e.stderr),
                timed_out=True,
            )
        except FileNotFoundError:
            return RunResult(
                exit_code=127,
                stdout="",
                stderr="ssh CLI not on PATH — install OpenSSH or switch "
                       "backend via `openprogram config backend`.",
            )
