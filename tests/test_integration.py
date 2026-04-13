"""Integration tests for pure-Python functions — no LLM required.

These tests import and execute real functions (not mocked) to verify
end-to-end correctness after installation. They run in CI alongside
unit tests.
"""

import json
import os
import tempfile

import pytest


# ---------------------------------------------------------------------------
# word_count — pure Python, no runtime needed
# ---------------------------------------------------------------------------

class TestWordCount:

    def test_basic(self):
        from agentic.functions.word_count import word_count
        assert word_count(text="hello world") == 2

    def test_empty(self):
        from agentic.functions.word_count import word_count
        assert word_count(text="") == 0

    def test_multiline(self):
        from agentic.functions.word_count import word_count
        assert word_count(text="one\ntwo\nthree") == 3

    def test_extra_spaces(self):
        from agentic.functions.word_count import word_count
        assert word_count(text="  hello   world  ") == 2

    def test_unicode(self):
        from agentic.functions.word_count import word_count
        assert word_count(text="你好 世界") == 2

    def test_has_input_meta(self):
        from agentic.functions.word_count import word_count
        assert word_count.input_meta["text"]["description"] == "Text to count words in"


# ---------------------------------------------------------------------------
# init_research — pure Python, creates directories
# ---------------------------------------------------------------------------

class TestInitResearch:

    def test_basic(self, tmp_path):
        from agentic.functions.init_research import init_research
        result = init_research(name="my-project", base_dir=str(tmp_path))
        assert os.path.isdir(result)
        assert os.path.isdir(os.path.join(result, "notes"))
        assert os.path.isdir(os.path.join(result, "sources"))
        assert os.path.isdir(os.path.join(result, "drafts"))

    def test_with_venue(self, tmp_path):
        from agentic.functions.init_research import init_research
        result = init_research(name="ctx-mgmt", venue="ICML", base_dir=str(tmp_path))
        assert "ctx-mgmt-ICML" in result
        assert os.path.isdir(result)

    def test_no_venue(self, tmp_path):
        from agentic.functions.init_research import init_research
        result = init_research(name="survey", base_dir=str(tmp_path))
        assert result.endswith("survey")

    def test_idempotent(self, tmp_path):
        from agentic.functions.init_research import init_research
        r1 = init_research(name="proj", base_dir=str(tmp_path))
        r2 = init_research(name="proj", base_dir=str(tmp_path))
        assert r1 == r2


# ---------------------------------------------------------------------------
# parse_json — extracts JSON from LLM-style text
# ---------------------------------------------------------------------------

class TestParseJson:

    def test_direct_json(self):
        from agentic.functions._utils import parse_json
        assert parse_json('{"key": "value"}') == {"key": "value"}

    def test_markdown_fence(self):
        from agentic.functions._utils import parse_json
        text = 'Here is the result:\n```json\n{"score": 8}\n```\nDone.'
        assert parse_json(text) == {"score": 8}

    def test_bare_json_in_text(self):
        from agentic.functions._utils import parse_json
        text = 'The output is {"status": "ok", "count": 3} as expected.'
        result = parse_json(text)
        assert result["status"] == "ok"
        assert result["count"] == 3

    def test_nested_json(self):
        from agentic.functions._utils import parse_json
        text = 'Result: {"data": {"nested": true}, "list": [1, 2]}'
        result = parse_json(text)
        assert result["data"]["nested"] is True
        assert result["list"] == [1, 2]

    def test_no_json_raises(self):
        from agentic.functions._utils import parse_json
        with pytest.raises(ValueError, match="No valid JSON"):
            parse_json("no json here at all")

    def test_multiple_json_returns_first(self):
        from agentic.functions._utils import parse_json
        text = '{"first": 1} and then {"second": 2}'
        assert parse_json(text) == {"first": 1}


# ---------------------------------------------------------------------------
# parse_action — extracts function call from LLM output
# ---------------------------------------------------------------------------

class TestParseAction:

    def test_markdown_action(self):
        from agentic.functions.parse_action import parse_action
        text = '```json\n{"call": "summarize", "args": {"style": "brief"}}\n```'
        result = parse_action(text)
        assert result["call"] == "summarize"
        assert result["args"]["style"] == "brief"

    def test_bare_action(self):
        from agentic.functions.parse_action import parse_action
        text = 'I will call {"call": "polish", "args": {"text": "hi"}} now.'
        result = parse_action(text)
        assert result["call"] == "polish"

    def test_no_call_key_returns_none(self):
        from agentic.functions.parse_action import parse_action
        text = '{"not_a_call": "value"}'
        assert parse_action(text) is None

    def test_plain_text_returns_none(self):
        from agentic.functions.parse_action import parse_action
        assert parse_action("just some text") is None


# ---------------------------------------------------------------------------
# build_catalog — builds function catalog for LLM
# ---------------------------------------------------------------------------

class TestBuildCatalog:

    def test_basic_catalog(self):
        from agentic.functions.build_catalog import build_catalog
        catalog = build_catalog({
            "greet": {
                "function": lambda: None,
                "description": "Say hello",
                "input": {},
            }
        })
        assert "greet" in catalog
        assert "Say hello" in catalog

    def test_llm_params_shown(self):
        from agentic.functions.build_catalog import build_catalog
        catalog = build_catalog({
            "translate": {
                "function": lambda: None,
                "description": "Translate text",
                "input": {
                    "text": {"source": "context"},
                    "lang": {"source": "llm", "type": str, "options": ["en", "zh"]},
                },
            }
        })
        assert "lang: str" in catalog
        assert '"en"' in catalog
        assert '"zh"' in catalog
        # context params should NOT appear in signature
        assert "text" not in catalog.split("\n")[0]


# ---------------------------------------------------------------------------
# prepare_args — merges LLM args with context and runtime
# ---------------------------------------------------------------------------

class TestPrepareArgs:

    def test_merges_sources(self):
        from agentic.functions.prepare_args import prepare_args
        from agentic import Runtime

        def target(text, style, runtime):
            return text, style

        rt = Runtime(call=lambda c, model="t", response_format=None: "ok")
        result = prepare_args(
            action={"call": "target", "args": {"style": "brief"}},
            available={"target": {
                "function": target,
                "input": {"text": {"source": "context"}},
            }},
            runtime=rt,
            context={"text": "hello"},
        )
        assert result["text"] == "hello"
        assert result["style"] == "brief"
        assert result["runtime"] is rt


# ---------------------------------------------------------------------------
# Context roundtrip — serialization
# ---------------------------------------------------------------------------

class TestContextRoundtrip:

    def test_nested_context_to_dict_and_back(self):
        from agentic import agentic_function

        @agentic_function
        def parent():
            child()
            return "done"

        @agentic_function
        def child():
            return "child_result"

        parent()
        tree = parent.context
        d = tree._to_dict()

        # Verify structure
        assert d["name"] == "parent"
        assert len(d["children"]) == 1
        assert d["children"][0]["name"] == "child"
        assert d["children"][0]["output"] == "child_result"

    def test_save_and_load_jsonl(self, tmp_path):
        from agentic import agentic_function

        @agentic_function
        def task():
            return 42

        task()
        out = tmp_path / "test.jsonl"
        task.context.save(str(out))

        with open(out) as f:
            data = json.loads(f.readline())
        assert data["name"] == "task"
        assert data["output"] == 42
