"""
Shared helpers for fix() tests.

The new fix() flow:
  round 0: clarify() → always returns follow_up (forced)
  user answers via ask_user
  round 1: clarify() → ready → generate_code() → verify_fix() → conclude_fix()

So a successful fix needs at least 5 LLM calls:
  1. clarify (round 0) — result ignored, forced follow_up
  2. clarify (round 1) — should return {"ready": true}
  3. generate_code — should return fixed code
  4. verify_fix — should return {"approved": true, ...}
  5. conclude_fix — returns summary string
"""

from agentic.context import set_ask_user


def make_fix_mock(fixed_code, *, answer="Proceed with the fix.", check_prompts=None):
    """Create a mock_call that handles the full fix() flow.

    Args:
        fixed_code: The Python code string to return from generate_code.
        answer: The answer to give when ask_user is called (round 0 follow-up).
        check_prompts: Optional list to append all received prompts to.

    Returns:
        (mock_call, cleanup) — call cleanup() after test to reset ask_user.
    """
    call_count = [0]
    prompts = check_prompts if check_prompts is not None else []

    def mock_call(content, model="test", response_format=None):
        call_count[0] += 1
        text = content[-1]["text"] if content else ""
        prompts.append(text)

        # Call 1: clarify (round 0) — result doesn't matter, forced follow_up
        if call_count[0] == 1:
            return '{"ready": false, "question": "Can you confirm what needs fixing?"}'

        # Call 2: clarify (round 1) — ready
        if call_count[0] == 2:
            return '{"ready": true}'

        # Call 3: generate_code — return the fixed code
        if call_count[0] == 3:
            return fixed_code

        # Call 4: verify_fix — approve
        if call_count[0] == 4:
            return '{"approved": true, "reasoning": "Fix looks correct."}'

        # Call 5+: conclude_fix or anything else
        return "Fix completed successfully."

    set_ask_user(lambda question: answer)

    def cleanup():
        set_ask_user(None)

    return mock_call, cleanup


def make_simple_fix_mock(fixed_code):
    """Even simpler: returns a mock_call and context manager.

    Usage:
        mock_call, cleanup = make_simple_fix_mock(code)
        try:
            result = fix(fn=..., runtime=Runtime(call=mock_call))
        finally:
            cleanup()
    """
    return make_fix_mock(fixed_code)
