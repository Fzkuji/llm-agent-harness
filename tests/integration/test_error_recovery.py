"""
End-to-end tests for error recovery: create → fail → edit → succeed.
"""

import pytest
from openprogram import agentic_function, Runtime
from openprogram.programs.functions.meta import create, edit


class TestCreateFailFixSucceed:
    """Full create → fail → edit → succeed cycle."""

    def test_basic_recovery_flow(self):
        """create() → call fails → edit(fn=...) → call succeeds."""
        from openprogram.programs.functions.buildin.ask_user import set_ask_user

        fix_code = '''@agentic_function
def divide(a, b):
    """Divide a by b safely."""
    a_num = float(a)
    b_num = float(b)
    if b_num == 0:
        return "Error: division by zero"
    return str(a_num / b_num)'''

        create_call_count = [0]
        fix_call_count = [0]
        phase = ["create"]

        def mock_call(content, model="test", response_format=None):
            prompt_text = "".join(b.get("text", "") for b in content if b["type"] == "text")

            if phase[0] == "create":
                create_call_count[0] += 1
                return '''@agentic_function
def divide(a, b):
    """Divide a by b."""
    return str(a / b)'''

            # edit phase — handle multi-call flow
            fix_call_count[0] += 1
            if fix_call_count[0] == 1:  # clarify round 0
                return '{"ready": false, "question": "Confirm edit?"}'
            if fix_call_count[0] == 2:  # clarify round 1
                return '{"ready": true}'
            if fix_call_count[0] == 3:  # generate
                return fix_code
            if fix_call_count[0] == 4:  # verify
                return '{"approved": true, "reasoning": "ok"}'
            return "Fix done."  # conclude

        runtime = Runtime(call=mock_call)

        # Create
        divide = create(description="Divide two numbers", runtime=runtime)
        result = divide(a=10, b=2)
        assert "5" in result

        # Fails for zero
        with pytest.raises(Exception):
            divide(a=10, b=0)

        # Edit
        phase[0] = "edit"
        set_ask_user(lambda q: "Yes, fix the division by zero.")
        try:
            edited_divide = edit(fn=divide, runtime=runtime)
        finally:
            set_ask_user(None)

        result = edited_divide(a=10, b=0)
        assert "Error" in result or "zero" in result.lower()

    def test_edit_preserves_context_tree(self):
        """Fixed function creates proper Context trees."""
        from openprogram.programs.functions.buildin.ask_user import set_ask_user

        create_call_count = [0]
        fix_call_count = [0]
        phase = ["create"]

        def mock_call(content, model="test", response_format=None):
            prompt_text = "".join(b.get("text", "") for b in content if b["type"] == "text")

            if phase[0] == "create":
                create_call_count[0] += 1
                return '''@agentic_function
def process(data):
    """Process data."""
    return runtime.exec(content=[
        {"type": "text", "text": "Process: " + str(data)},
    ])'''

            if phase[0] == "edit":
                fix_call_count[0] += 1
                if fix_call_count[0] == 1:
                    return '{"ready": false, "question": "Confirm?"}'
                if fix_call_count[0] == 2:
                    return '{"ready": true}'
                if fix_call_count[0] == 3:
                    return '''@agentic_function
def process(data):
    """Process data with validation."""
    if not data:
        return "empty"
    return runtime.exec(content=[
        {"type": "text", "text": "Process: " + str(data)},
    ])'''
                if fix_call_count[0] == 4:
                    return '{"approved": true, "reasoning": "ok"}'
                return "Fix done."

            return f"processed: {prompt_text}"

        runtime = Runtime(call=mock_call)

        original = create(description="Process data", runtime=runtime)

        phase[0] = "edit"
        set_ask_user(lambda q: "Yes, proceed.")
        try:
            fixed = edit(fn=original, runtime=runtime)
        finally:
            set_ask_user(None)

        phase[0] = "run"

        @agentic_function
        def pipeline(items):
            """Pipeline."""
            results = []
            for item in items:
                results.append(fixed(data=item))
            return results

        pipeline(items=["a", "b"])
        root = pipeline.context
        assert root.status == "success"
        assert len(root.children) == 2


class TestRetryMechanics:
    """Detailed tests for exec() retry behavior."""

    def test_retry_count_matches_max_retries(self):
        call_count = [0]

        def counting_call(content, model="test", response_format=None):
            call_count[0] += 1
            raise Exception("fail")

        for max_retries in [1, 2, 3]:
            call_count[0] = 0
            runtime = Runtime(call=counting_call, max_retries=max_retries)

            @agentic_function
            def func():
                return runtime.exec(content=[{"type": "text", "text": "test"}])

            with pytest.raises(RuntimeError):
                func()

            assert call_count[0] == max_retries

    def test_no_retry_on_type_error(self):
        call_count = [0]

        def type_error_call(content, model="test", response_format=None):
            call_count[0] += 1
            raise TypeError("wrong type")

        runtime = Runtime(call=type_error_call, max_retries=3)

        @agentic_function
        def func():
            return runtime.exec(content=[{"type": "text", "text": "test"}])

        with pytest.raises(TypeError):
            func()

        assert call_count[0] == 1

    def test_successful_retry_records_reply(self):
        attempt = [0]

        def flaky(content, model="test", response_format=None):
            attempt[0] += 1
            if attempt[0] == 1:
                raise ConnectionError("transient")
            return "recovered"

        runtime = Runtime(call=flaky, max_retries=2)

        @agentic_function
        def func():
            return runtime.exec(content=[{"type": "text", "text": "test"}])

        result = func()
        assert result == "recovered"
        assert func.context.raw_reply == "recovered"
