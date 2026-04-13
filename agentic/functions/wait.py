"""
wait — an agentic function that decides how long to wait.

After executing an action, the agent needs to decide: should I check
immediately, or wait? And if wait, how long? This function lets the
LLM reason about timing based on what just happened.

Usage:
    from agentic.functions.wait import wait

    seconds = wait(
        action="started model training on 10k samples",
        runtime=runtime,
    )
    # seconds: 600 (LLM decided to wait 10 minutes)
"""

from __future__ import annotations

import time

from agentic.function import agentic_function
from agentic.runtime import Runtime
from agentic.functions._utils import parse_json


_MISSING_RUNTIME = object()


@agentic_function(compress=True, summarize={"depth": 0, "siblings": 0}, input={
    "action": {"description": "What just happened", "placeholder": "e.g. started model training on 10k samples"},
    "runtime": {"hidden": True},
})
def wait(action: str, runtime: Runtime = _MISSING_RUNTIME) -> int:
    """Decide how many seconds to wait before the next step.

    Given what just happened, decide the appropriate wait time.
    Think about what is happening in the background and how long
    it typically takes.

    Guidelines and examples:

    WAIT 0 (check immediately):
    - Just wrote code, need to verify syntax → 0
    - Just started a process, need to confirm it didn't crash → 0
    - Created a file, need to verify it exists → 0
    - Sent a request, response should be instant → 0

    WAIT 5-15 (short wait):
    - Started a server, waiting for it to bind a port → 5
    - Ran a quick test suite (< 100 tests) → 10
    - Installing a small pip package → 5
    - Compiling a small project → 10

    WAIT 30-120 (medium wait):
    - Running a full test suite → 60
    - Building a Docker image → 60
    - npm install on a large project → 30
    - Database migration on moderate data → 60
    - Deploying to staging → 120

    WAIT 300-1800 (long wait):
    - Training a model for a few epochs → 300-600
    - Running a large benchmark → 600
    - Deploying to production with health checks → 300
    - Processing a large dataset → 600-1800

    WAIT 3600+ (very long wait):
    - Full model training run → 3600-86400
    - Large-scale data processing pipeline → 3600
    - Waiting for external review/approval → 3600

    Return JSON:
    {
      "wait": <seconds>,
      "reason": "why this wait time"
    }
    """
    if runtime is _MISSING_RUNTIME or runtime is None:
        raise ValueError("runtime is required for wait()")

    reply = runtime.exec(content=[
        {"type": "text", "text": (
            f"Action just completed: {action}\n\n"
            "How long should we wait before checking the result or "
            "proceeding to the next step? Return JSON with wait/reason."
        )},
    ])

    try:
        result = parse_json(reply)
        seconds = int(result.get("wait", 0))
    except (ValueError, TypeError):
        seconds = 0

    if seconds > 0:
        time.sleep(seconds)

    return seconds
