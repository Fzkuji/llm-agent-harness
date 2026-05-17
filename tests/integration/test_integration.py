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
        from openprogram.programs.functions.third_party.word_count import word_count
        assert word_count(text="hello world") == 2

    def test_empty(self):
        from openprogram.programs.functions.third_party.word_count import word_count
        assert word_count(text="") == 0

    def test_multiline(self):
        from openprogram.programs.functions.third_party.word_count import word_count
        assert word_count(text="one\ntwo\nthree") == 3

    def test_extra_spaces(self):
        from openprogram.programs.functions.third_party.word_count import word_count
        assert word_count(text="  hello   world  ") == 2

    def test_unicode(self):
        from openprogram.programs.functions.third_party.word_count import word_count
        assert word_count(text="你好 世界") == 2

    def test_has_input_meta(self):
        from openprogram.programs.functions.third_party.word_count import word_count
        assert word_count.input_meta["text"]["description"] == "Text to count words in"


# ---------------------------------------------------------------------------
# init_research — pure Python, creates directories
# ---------------------------------------------------------------------------

class TestInitResearch:

    def test_basic(self, tmp_path):
        from openprogram.programs.functions.buildin.init_research import init_research
        result = init_research(name="my-project", base_dir=str(tmp_path))
        assert os.path.isdir(result)
        assert os.path.isdir(os.path.join(result, "notes"))
        assert os.path.isdir(os.path.join(result, "sources"))
        assert os.path.isdir(os.path.join(result, "drafts"))

    def test_with_venue(self, tmp_path):
        from openprogram.programs.functions.buildin.init_research import init_research
        result = init_research(name="ctx-mgmt", venue="ICML", base_dir=str(tmp_path))
        assert "ctx-mgmt-ICML" in result
        assert os.path.isdir(result)

    def test_no_venue(self, tmp_path):
        from openprogram.programs.functions.buildin.init_research import init_research
        result = init_research(name="survey", base_dir=str(tmp_path))
        assert result.endswith("survey")

    def test_idempotent(self, tmp_path):
        from openprogram.programs.functions.buildin.init_research import init_research
        r1 = init_research(name="proj", base_dir=str(tmp_path))
        r2 = init_research(name="proj", base_dir=str(tmp_path))
        assert r1 == r2


# ---------------------------------------------------------------------------
# parse_json — extracts JSON from LLM-style text
# ---------------------------------------------------------------------------

class TestParseJson:

    def test_direct_json(self):
        from openprogram.programs.functions.buildin._utils import parse_json
        assert parse_json('{"key": "value"}') == {"key": "value"}

    def test_markdown_fence(self):
        from openprogram.programs.functions.buildin._utils import parse_json
        text = 'Here is the result:\n```json\n{"score": 8}\n```\nDone.'
        assert parse_json(text) == {"score": 8}

    def test_bare_json_in_text(self):
        from openprogram.programs.functions.buildin._utils import parse_json
        text = 'The output is {"status": "ok", "count": 3} as expected.'
        result = parse_json(text)
        assert result["status"] == "ok"
        assert result["count"] == 3

    def test_nested_json(self):
        from openprogram.programs.functions.buildin._utils import parse_json
        text = 'Result: {"data": {"nested": true}, "list": [1, 2]}'
        result = parse_json(text)
        assert result["data"]["nested"] is True
        assert result["list"] == [1, 2]

    def test_no_json_raises(self):
        from openprogram.programs.functions.buildin._utils import parse_json
        with pytest.raises(ValueError, match="No valid JSON"):
            parse_json("no json here at all")

    def test_multiple_json_returns_first(self):
        from openprogram.programs.functions.buildin._utils import parse_json
        text = '{"first": 1} and then {"second": 2}'
        assert parse_json(text) == {"first": 1}
