"""Backend ABC + shared RunResult type."""
from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


def decode_maybe(x) -> str:
    """Normalize bytes/None/str into a safe str for RunResult fields."""
    if x is None:
        return ""
    if isinstance(x, bytes):
        return x.decode(errors="replace")
    return x


class Backend(abc.ABC):
    backend_id: str = ""

    @abc.abstractmethod
    def run(self, command: str, timeout: float,
            cwd: str | None = None) -> RunResult:
        """Execute ``command`` and return the full result.

        Implementations MUST:
          * honour ``timeout`` (seconds); set ``timed_out=True`` instead
            of raising when it fires
          * return partial stdout/stderr even on timeout when available
          * never raise from normal execution paths — return a RunResult
            with exit_code != 0 and an informative stderr instead, so
            the calling tool doesn't surface raw exceptions to the LLM
        """
