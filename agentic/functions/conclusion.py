"""
conclusion — summarize task results into a user-friendly response.

Called at the end of an entry-point function to transform raw structured
results into a natural language summary for the user.

Usage:
    from agentic.functions.conclusion import conclusion

    result = some_function(task=task, runtime=runtime)
    summary = conclusion(task=task, runtime=runtime)
    # summary is a natural language string
"""

from __future__ import annotations

from agentic.function import agentic_function
from agentic.runtime import Runtime


@agentic_function(compress=True, summarize={"siblings": -1}, input={
    "task": {"description": "The completed task", "placeholder": "e.g. Write a summary of the research findings"},
    "runtime": {"hidden": True},
})
def conclusion(task: str, runtime: Runtime) -> str:
    """Summarize the completed task for the user.

    You have just finished a task. All previous steps and their results
    are visible in context (above). Based on this full execution history,
    write a clear, concise response for the user.

    Rules:
    - Write in the same language as the task
    - Focus on WHAT was accomplished, not HOW
    - Include key results, numbers, or outputs
    - If the task was a question, answer it directly
    - If the task produced content (text, code, etc.), include the final version
    - Keep it concise — no need to list every step
    - Do NOT wrap in JSON — just write plain text
    """
    return runtime.exec(content=[
        {"type": "text", "text": f"Task: {task}\n\nSummarize the results above for the user."},
    ])
