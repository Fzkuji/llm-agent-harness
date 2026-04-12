"""Tests for dispatch helper utilities used by meta functions."""

from agentic.functions.build_catalog import build_catalog
from agentic.functions.prepare_args import prepare_args


def test_build_catalog_includes_llm_inputs_and_output_types():
    def summarize_text(text, style, runtime):
        return f"{style}:{text}"

    catalog = build_catalog(
        {
            "summarize_text": {
                "function": summarize_text,
                "description": "Summarize text.",
                "input": {
                    "text": {"source": "context"},
                    "style": {
                        "source": "llm",
                        "type": str,
                        "options": ["bullet", "short"],
                        "description": "Summary style",
                    },
                },
                "output": {"summary": str},
            }
        }
    )

    assert "summarize_text" in catalog
    assert "style" in catalog
    assert "bullet, short" in catalog
    assert "summary: str" in catalog
    assert "- text:" not in catalog  # context-only args stay hidden from the LLM


def test_prepare_args_merges_context_llm_and_runtime():
    def summarize_text(text, style, runtime):
        return f"{style}:{text}"

    args = prepare_args(
        action={"call": "summarize_text", "args": {"style": "bullet", "ignored": 1}},
        available={
            "summarize_text": {
                "function": summarize_text,
                "input": {
                    "text": {"source": "context"},
                    "style": {"source": "llm", "type": str},
                },
            }
        },
        runtime="runtime-sentinel",
        context={"text": "hello"},
    )

    assert args == {
        "text": "hello",
        "style": "bullet",
        "runtime": "runtime-sentinel",
    }
