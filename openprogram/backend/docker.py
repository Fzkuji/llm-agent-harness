"""Docker backend — ``docker run --rm`` per call.

Per-call container spawn keeps the implementation stateless (no
container lifecycle to manage) at the cost of startup overhead per
bash invocation. For bash-heavy agent workflows the user should
stick with ``local`` or run a dedicated long-lived container and
use ``ssh`` into it; a long-lived docker pool is future work.
"""
from __future__ import annotations

import subprocess

from openprogram.backend.base import Backend, RunResult, decode_maybe


class DockerBackend(Backend):
    backend_id = "docker"

    def __init__(self, image: str = "ubuntu:24.04") -> None:
        self.image = image

    def run(self, command: str, timeout: float,
            cwd: str | None = None) -> RunResult:
        argv = ["docker", "run", "--rm", "-i"]
        if cwd:
            argv += ["-w", cwd]
        argv += [self.image, "sh", "-c", command]
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
                stderr="docker CLI not on PATH — install Docker or "
                       "switch backend via `openprogram config backend`.",
            )
