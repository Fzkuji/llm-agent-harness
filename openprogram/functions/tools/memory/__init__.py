"""Memory functions — agent bundle for the wiki-backed memory subsystem.

Functions exposed (all self-register via @function on import):

  memory_note      — record a fact in journal
  memory_recall    — search wiki + recent journal, raw snippets
  memory_reflect   — collect cross-cutting recall for LLM synthesis
  memory_get       — fetch a complete wiki page by slug
  memory_browse    — render the wiki folder tree
  memory_lint      — structural health report
  memory_ingest    — two-step agentic conversation ingest
  memory_backlinks — inbound references to a page (Obsidian-style)
  memory_rename    — move a page + cascade-rewrite all wikilinks
  memory_relink    — cascade-rewrite wikilinks only (no file move)
  memory_delete    — remove a page + optionally prune dangling refs
  memory_review    — list or resolve REVIEW-queue items
  memory_status    — vault stats (page counts, pending reviews, etc.)
"""
from ..._runtime import function
from .memory import (
    NOTE_NAME, NOTE_SPEC, note,
    RECALL_NAME, RECALL_SPEC, recall,
    REFLECT_NAME, REFLECT_SPEC, reflect,
    GET_NAME, GET_SPEC, memory_get,
    BROWSE_NAME, BROWSE_SPEC, memory_browse,
    LINT_NAME, LINT_SPEC, memory_lint,
    INGEST_NAME, INGEST_SPEC, memory_ingest,
    BACKLINKS_NAME, BACKLINKS_SPEC, memory_backlinks,
    RENAME_NAME, RENAME_SPEC, memory_rename,
    RELINK_NAME, RELINK_SPEC, memory_relink,
    DELETE_NAME, DELETE_SPEC, memory_delete,
    REVIEW_NAME, REVIEW_SPEC, memory_review,
    STATUS_NAME, STATUS_SPEC, memory_status,
)


def _register(name, spec, fn, *, max_chars=20_000):
    function(
        name=name,
        description=spec["description"],
        parameters=spec["parameters"],
        toolset=["core"],
        max_result_chars=max_chars,
    )(fn)


_register(NOTE_NAME, NOTE_SPEC, note)
_register(RECALL_NAME, RECALL_SPEC, recall)
_register(REFLECT_NAME, REFLECT_SPEC, reflect)
_register(GET_NAME, GET_SPEC, memory_get, max_chars=30_000)
_register(BROWSE_NAME, BROWSE_SPEC, memory_browse, max_chars=30_000)
_register(LINT_NAME, LINT_SPEC, memory_lint, max_chars=15_000)
_register(INGEST_NAME, INGEST_SPEC, memory_ingest, max_chars=4_000)
_register(BACKLINKS_NAME, BACKLINKS_SPEC, memory_backlinks, max_chars=20_000)
_register(RENAME_NAME, RENAME_SPEC, memory_rename, max_chars=8_000)
_register(RELINK_NAME, RELINK_SPEC, memory_relink, max_chars=8_000)
_register(DELETE_NAME, DELETE_SPEC, memory_delete, max_chars=8_000)
_register(REVIEW_NAME, REVIEW_SPEC, memory_review, max_chars=20_000)
_register(STATUS_NAME, STATUS_SPEC, memory_status, max_chars=8_000)


__all__ = [
    "NOTE_NAME", "RECALL_NAME", "REFLECT_NAME", "GET_NAME",
    "BROWSE_NAME", "LINT_NAME", "INGEST_NAME", "BACKLINKS_NAME",
    "RENAME_NAME", "RELINK_NAME", "DELETE_NAME", "REVIEW_NAME", "STATUS_NAME",
]
