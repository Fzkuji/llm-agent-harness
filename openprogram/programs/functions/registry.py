"""Explicit registry of agentic functions.

The functions directory used to be auto-scanned. That is gone: only
modules listed here are discovered, loaded, and shown in the UI.

To expose a new agentic function, add its module path below. To hide
one, remove its line — the file can stay on disk. Each entry is a
module path relative to ``openprogram.programs.functions`` (dotted,
matching the folder layout). A module may define more than one
``@agentic_function``; all of them are exposed.
"""

FUNCTION_MODULES: list[str] = [
    # buildin/
    "buildin.agent_loop",
    "buildin.ask_user",
    "buildin.deep_work",
    "buildin.general_action",
    "buildin.init_research",
    "buildin.wait",
    # third_party/
    "third_party.analyze_sentiment",
    "third_party.extract_action_items",
    "third_party.llm_call_example",
    "third_party.sentiment_v2",
    "third_party.test_framework",
    "third_party.test_resume",
    "third_party.word_count",
    # third_party/pdf/
    "third_party.pdf.extract_pdf_tables",
    "third_party.pdf.extract_pdf_figures",
]
