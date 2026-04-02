"""
Context — the execution record for one Agentic Function call.

Architecture:
    All function calls form a single tree. Each node is a Context.
    The tree is a COMPLETE RECORD of everything that happened.
    When feeding context to an LLM, summarize() QUERIES the tree selectively.
    
    Record and query are fully separated:
    - What gets recorded is NOT affected by queries
    - What gets queried does NOT affect the record

Tree structure example:
    root
    ├── navigate("login")
    │   ├── observe("find login")       → root/navigate_0/observe_0
    │   │   ├── run_ocr(img)            → root/navigate_0/observe_0/run_ocr_0
    │   │   └── detect_all(img)         → root/navigate_0/observe_0/detect_all_0
    │   ├── observe("find password")    → root/navigate_0/observe_1
    │   └── act("login", [347, 291])    → root/navigate_0/act_0
    └── navigate("settings")
        └── ...

Key design decisions (lessons learned):
    1. We use contextvars.ContextVar for implicit call-stack tracking.
       Users never pass ctx manually — the decorator handles everything.
       We tried explicit ctx passing first, but it was error-prone.
    
    2. summarize() is a flexible tree query, NOT a fixed format.
       It supports depth, siblings, include/exclude paths, branch selection.
       Earlier versions had a rigid sibling_summaries() that only looked
       at immediate siblings — too limiting for complex call trees.
    
    3. Each node has an auto-computed path (e.g. "root/navigate_0/observe_1").
       Paths use {name}_{index} where index counts same-name siblings.
       This enables precise addressing in complex trees with repeated calls.
    
    4. expose is a RENDERING HINT, not a security policy.
       summarize(level=...) can override any node's expose setting.
       If you need real isolation, use @agentic_function(context="none").
    
    5. input/media/raw_reply are currently single fields (one LLM call per node).
       TODO: Change to llm_calls: list[LLMCall] to support multiple
       runtime.exec() calls within one function. This is a known limitation.

See also:
    - function.py: @agentic_function decorator
    - runtime.py: runtime.exec() — LLM call with auto recording
    - docs/context/README.md: visual diagrams of all query scenarios
"""

from __future__ import annotations

import time
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from contextvars import ContextVar

# The single global variable that tracks which Context node is "current".
# @agentic_function sets this on entry and resets on exit.
# This is what makes implicit call-stack tracking work without passing ctx.
_current_ctx: ContextVar[Optional["Context"]] = ContextVar("_current_ctx", default=None)


@dataclass
class Context:
    """
    Execution record for one Agentic Function call.
    
    All fields are managed automatically by @agentic_function and runtime.exec().
    Users write normal Python — they don't need to know this class exists.
    
    The tree structure:
        - parent: who called me
        - children: who I called
        - path: auto-computed address like "root/navigate_0/observe_1"
    """

    # === Auto-managed by @agentic_function ===
    name: str = ""                              # Function name (from __name__)
    prompt: str = ""                            # Docstring = LLM prompt (from __doc__)
    params: dict = field(default_factory=dict)  # Call arguments (from *args/**kwargs)
    output: Any = None                          # Return value
    error: str = ""                             # Error message if failed
    status: str = "running"                     # "running" → "success" or "error"
    children: list = field(default_factory=list) # Child Context nodes (sub-calls)
    parent: Optional["Context"] = field(default=None, repr=False)  # Parent node
    start_time: float = 0.0
    end_time: float = 0.0
    expose: str = "summary"                     # Rendering hint for summarize()
    #   trace:   prompt + full I/O + raw LLM reply
    #   detail:  full input and output
    #   summary: one-line summary (default)
    #   result:  return value only
    #   silent:  don't appear in summaries

    # === Auto-managed by runtime.exec() ===
    # NOTE: Currently single fields — only records the LAST runtime.exec() call.
    # TODO: Replace with llm_calls: list[LLMCall] for multiple calls per function.
    input: Optional[dict] = None                # Data sent to LLM
    media: Optional[list] = None                # Media file paths (screenshots etc.)
    raw_reply: str = ""                         # LLM's raw response text

    # === Optional user override ===
    summary_fn: Optional[Callable] = field(default=None, repr=False)
    # Custom function to render this node's summary. Bypasses expose levels.

    # ------------------------------------------------------------------
    # Path — auto-computed address for precise node selection
    # ------------------------------------------------------------------
    # Format: "root/navigate_0/observe_1/run_ocr_0"
    # The index counts same-name siblings (0-based).
    # Not stored — computed on access from parent/children relationships.

    @property
    def path(self) -> str:
        """Auto-computed path like 'root/navigate_0/observe_1'. Not stored."""
        if not self.parent:
            return self.name
        # Count how many siblings with my name appear before me
        idx = 0
        for c in self.parent.children:
            if c is self:
                break
            if c.name == self.name:
                idx += 1
        return f"{self.parent.path}/{self.name}_{idx}"

    # ------------------------------------------------------------------
    # summarize() — flexible tree query for LLM context injection
    # ------------------------------------------------------------------
    # The core idea: the tree records EVERYTHING. This method lets each
    # function choose exactly what slice of the tree to feed to its LLM.
    #
    # Design evolution:
    #   v1: sibling_summaries() — only showed immediate siblings. Too rigid.
    #   v2: renamed to summarize() — added parent info. Better but still limited.
    #   v3: added depth, siblings, include/exclude/branch — full tree query.
    #
    # The name "summarize" was chosen because the original "sibling_summaries"
    # was too abstract and didn't convey what it actually does.

    def summarize(
        self,
        level: Optional[str] = None,
        max_tokens: Optional[int] = None,
        max_siblings: Optional[int] = None,
        depth: int = -1,
        siblings: int = -1,
        include: Optional[list] = None,
        exclude: Optional[list] = None,
        branch: Optional[list] = None,
    ) -> str:
        """
        Query the Context tree and generate a text summary for LLM input.
        
        The tree is complete. This method selects what to show.
        
        Args:
            level:        Override all nodes' expose levels (e.g. "trace" to see everything)
            max_tokens:   Approximate token budget. Drops oldest siblings first.
            max_siblings: Shorthand for siblings=N (legacy compat)
            depth:        Ancestor visibility. -1=all, 0=none, 1=parent only, 2=grandparent...
            siblings:     Sibling visibility. -1=all, 0=none, N=last N siblings
            include:      Path whitelist. Only show matching nodes. Supports * wildcard.
                          e.g. ["root/navigate_0/observe_1", "root/navigate_0/observe_1/*"]
            exclude:      Path blacklist. Hide matching nodes. Supports * wildcard.
                          e.g. ["root/navigate_0/observe_0"]
            branch:       Show entire subtree under nodes with these names.
                          e.g. ["observe"] shows observe + all its children (run_ocr, detect_all)
        
        Returns:
            Multi-line string ready to inject into LLM prompt.
        
        Examples:
            ctx.summarize()                              # default: all ancestors + all siblings
            ctx.summarize(depth=1)                       # only parent + siblings
            ctx.summarize(depth=0, siblings=0)           # isolated: nothing
            ctx.summarize(include=["root/nav_0/obs_1"])  # only one specific node
            ctx.summarize(branch=["observe"])             # observe + its children
            ctx.summarize(siblings=1)                    # only the most recent sibling
        """
        # Resolve effective sibling count
        effective_siblings = max_siblings if max_siblings is not None else (
            None if siblings == -1 else siblings
        )

        parts = []

        # --- Ancestor chain ---
        if depth != 0 and self.parent and self.parent.name:
            ancestors = []
            node = self.parent
            while node and node.name:
                ancestors.append(node)
                node = node.parent
                if depth > 0 and len(ancestors) >= depth:
                    break
            # Show ancestors from root → parent order
            for a in reversed(ancestors):
                if not self._path_allowed(a, include, exclude):
                    continue
                parts.append(f"[Ancestor: {a.name}({_fmt_params(a.params)})]")

        # --- Previous siblings ---
        if self.parent and (effective_siblings is None or effective_siblings > 0):
            sibling_parts = []
            for c in self.parent.children:
                if c is self:
                    break  # Only look at siblings BEFORE me
                if c.status == "running":
                    continue
                if not self._path_allowed(c, include, exclude):
                    continue
                expose = level or c.expose
                if expose == "silent":
                    continue
                rendered = c._render(expose)
                # Branch mode: also show children of matching siblings
                if branch and c.name in branch:
                    rendered += "\n" + c._render_branch(level)
                sibling_parts.append(rendered)

            # Apply sibling limit (keep most recent)
            if effective_siblings is not None:
                sibling_parts = sibling_parts[-effective_siblings:]

            # Apply token budget (drop oldest first)
            if max_tokens is not None:
                total = sum(len(s) for s in sibling_parts)
                while sibling_parts and total > max_tokens * 4:  # rough chars→tokens
                    removed = sibling_parts.pop(0)
                    total -= len(removed)

            parts.extend(sibling_parts)

        # --- Path-based inclusion from anywhere in the tree ---
        if branch and include:
            root = self
            while root.parent:
                root = root.parent
            for path_pattern in include:
                for node in self._find_by_path(root, path_pattern):
                    if node is not self and node not in (self.parent.children if self.parent else []):
                        parts.append(node._render(level or node.expose))

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Internal: path filtering and rendering helpers
    # ------------------------------------------------------------------

    def _path_allowed(self, node: "Context", include: Optional[list], exclude: Optional[list]) -> bool:
        """Check if a node passes the include/exclude path filters."""
        if include is not None:
            return any(_path_matches(node.path, pattern) for pattern in include)
        if exclude is not None:
            return not any(_path_matches(node.path, pattern) for pattern in exclude)
        return True

    def _render_branch(self, level: Optional[str], indent: int = 1) -> str:
        """Recursively render all children of this node."""
        lines = []
        for c in self.children:
            expose = level or c.expose
            if expose != "silent":
                prefix = "  " * indent
                lines.append(f"{prefix}{c._render(expose)}")
                if c.children:
                    lines.append(c._render_branch(level, indent + 1))
        return "\n".join(lines)

    @staticmethod
    def _find_by_path(root: "Context", pattern: str) -> list:
        """Find all nodes in the tree matching a path pattern."""
        results = []
        stack = [root]
        while stack:
            node = stack.pop()
            if _path_matches(node.path, pattern):
                results.append(node)
            stack.extend(node.children)
        return results

    def _render(self, level: str) -> str:
        """
        Render this single node at the given expose level.
        
        Levels (from most verbose to least):
            trace:   prompt + input + media + raw_reply + output + error
            detail:  name(params) → status | input | output
            summary: name: output (one line)
            result:  just the output value
            silent:  empty string (shouldn't be called)
        """
        if self.summary_fn:
            return self.summary_fn(self)

        if level == "trace":
            lines = [f"{self.name}({_fmt_params(self.params)})"]
            if self.prompt:
                lines.append(f"  prompt: {self.prompt[:200]}")
            if self.input:
                lines.append(f"  input: {json.dumps(self.input, ensure_ascii=False, default=str)[:500]}")
            if self.media:
                lines.append(f"  media: {self.media}")
            if self.raw_reply:
                lines.append(f"  raw_reply: {self.raw_reply[:500]}")
            if self.output is not None:
                lines.append(f"  output: {json.dumps(self.output, ensure_ascii=False, default=str)[:500]}")
            if self.error:
                lines.append(f"  error: {self.error}")
            dur = f" ({self.duration_ms:.0f}ms)" if self.end_time else ""
            lines[0] += f" → {self.status}{dur}"
            return "\n".join(lines)

        elif level == "detail":
            dur = f" {self.duration_ms:.0f}ms" if self.end_time else ""
            inp = json.dumps(self.input, ensure_ascii=False, default=str)[:200] if self.input else ""
            out = json.dumps(self.output, ensure_ascii=False, default=str)[:200] if self.output is not None else ""
            return f"{self.name}({_fmt_params(self.params)}) → {self.status}{dur} | input: {inp} | output: {out}"

        elif level == "summary":
            dur = f" {self.duration_ms:.0f}ms" if self.end_time else ""
            out = json.dumps(self.output, ensure_ascii=False, default=str)[:100] if self.output is not None else ""
            err = f" error: {self.error}" if self.error else ""
            return f"{self.name}: {out}{err}{dur}"

        elif level == "result":
            return json.dumps(self.output, ensure_ascii=False, default=str) if self.output is not None else ""

        return ""

    # ------------------------------------------------------------------
    # Tree visualization
    # ------------------------------------------------------------------

    @property
    def duration_ms(self) -> float:
        """Execution duration in milliseconds."""
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0

    def tree(self, indent: int = 0) -> str:
        """
        Human-readable tree view of the entire execution.
        
        Example output:
            root …
              navigate ✓ 3200ms → {success: True}
                observe ✓ 1200ms → {found: True}
                  run_ocr ✓ 50ms → {texts: [...]}
                act ✓ 820ms → {clicked: True}
        """
        prefix = "  " * indent
        dur = f" {self.duration_ms:.0f}ms" if self.end_time else ""
        icon = "✓" if self.status == "success" else "✗" if self.status == "error" else "…"
        out = f" → {self.output}" if self.output is not None else ""
        err = f" ERROR: {self.error}" if self.error else ""
        line = f"{prefix}{self.name} {icon}{dur}{out}{err}"
        lines = [line]
        for c in self.children:
            lines.append(c.tree(indent + 1))
        return "\n".join(lines)

    def traceback(self) -> str:
        """
        Agentic Traceback — like Python's traceback but for agentic calls.
        
        Example output:
            Agentic Traceback:
              navigate(target="login") → error, 4523ms
                observe(task="find login") → success, 1200ms
                act(target="login") → error, 820ms
                  error: element not interactable
        """
        lines = ["Agentic Traceback:"]
        self._traceback_lines(lines, indent=1)
        return "\n".join(lines)

    def _traceback_lines(self, lines: list, indent: int):
        prefix = "  " * indent
        dur = f", {self.duration_ms:.0f}ms" if self.end_time else ""
        params_str = _fmt_params(self.params)
        lines.append(f"{prefix}{self.name}({params_str}) → {self.status}{dur}")
        if self.error:
            lines.append(f"{prefix}  error: {self.error}")
        for c in self.children:
            c._traceback_lines(lines, indent + 1)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str):
        """
        Save the Context tree to a file.
        
        .md  → human-readable tree view
        .jsonl → machine-readable (one JSON record per node)
        """
        if path.endswith(".md"):
            with open(path, "w") as f:
                f.write(self.tree())
        else:
            with open(path, "w") as f:
                for record in self._to_records():
                    f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def _to_records(self, depth: int = 0) -> list[dict]:
        """Flatten the tree into a list of records for JSONL serialization."""
        records = [{
            "depth": depth,
            "path": self.path,
            "name": self.name,
            "prompt": self.prompt,
            "params": self.params,
            "input": self.input,
            "media": self.media,
            "output": self.output,
            "raw_reply": self.raw_reply,
            "error": self.error,
            "status": self.status,
            "expose": self.expose,
            "duration_ms": self.duration_ms,
        }]
        for c in self.children:
            records.extend(c._to_records(depth + 1))
        return records


# ======================================================================
# Module-level functions
# ======================================================================

def get_context() -> Optional[Context]:
    """Get the current Context node (inside an @agentic_function).
    
    Returns None if called outside any @agentic_function.
    Most users don't need this — runtime.exec() uses it internally.
    """
    return _current_ctx.get(None)


def get_root_context() -> Optional[Context]:
    """Get the root of the Context tree.
    
    Walks up from the current node to find the root.
    Returns None if no Context exists.
    """
    ctx = _current_ctx.get(None)
    if ctx is None:
        return None
    while ctx.parent is not None:
        ctx = ctx.parent
    return ctx


def init_root(name: str = "root") -> Context:
    """Manually initialize a root Context.
    
    Usually not needed — @agentic_function(context="auto") creates one automatically.
    Use this if you want to control the root explicitly.
    """
    root = Context(name=name, start_time=time.time(), status="running")
    _current_ctx.set(root)
    return root


# ======================================================================
# Internal helpers
# ======================================================================

def _path_matches(path: str, pattern: str) -> bool:
    """
    Match a context path against a pattern.
    
    Supports:
        "root/navigate_0/observe_1"      — exact match
        "root/navigate_0/*"              — everything under navigate_0
        "root/*/observe_*"               — fnmatch wildcards
    """
    if pattern.endswith("/*"):
        prefix = pattern[:-2]
        return path.startswith(prefix + "/") or path == prefix
    if "*" in pattern:
        import fnmatch
        return fnmatch.fnmatch(path, pattern)
    return path == pattern


def _fmt_params(params: dict) -> str:
    """Format function params for display. Truncates long values."""
    if not params:
        return ""
    parts = []
    for k, v in params.items():
        v_str = json.dumps(v, ensure_ascii=False, default=str) if not isinstance(v, str) else f'"{v}"'
        if len(v_str) > 50:
            v_str = v_str[:47] + "..."
        parts.append(f"{k}={v_str}")
    return ", ".join(parts)
