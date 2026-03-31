"""
Scope — defines what a Function can see when it executes.

Modeled after Python's variable scoping (LEGB rule), but for LLM context:

    Python                          Agentic Programming
    ─────                           ────────────────────
    Local variables                 Function's own params
    Enclosing scope                 Call stack (who called whom)
    Module-level / neighbors        Peer Functions at the same level

Three dimensions:

    depth   How many layers up the call stack are visible.
            0 = only own input. 1 = direct caller. -1 = unlimited.

    detail  How much of each call stack layer is visible.
            "io" = input + output only. "full" = complete reasoning.

    peer    How much of same-level (sibling) Functions is visible.
            "none" = nothing. "io" = their input + output. "full" = full reasoning.

Common presets:
    Scope.ISOLATED  depth=0, detail="io", peer="none"   — pure function, sees nothing
    Scope.CHAINED   depth=0, detail="io", peer="io"     — sees sibling I/O
    Scope.AWARE     depth=1, detail="io", peer="io"     — sees caller + sibling I/O
    Scope.FULL      depth=-1, detail="full", peer="full" — sees everything
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Scope:
    """
    Defines what a Function can see when it executes.

    Args:
        depth:   Call stack visibility.
                 0  = only own input (no caller info)
                 1  = sees direct caller
                 2  = sees caller's caller
                 -1 = unlimited (full stack)

        detail:  How much of each stack layer is shown.
                 "io"   = input params + return value only
                 "full" = complete conversation (including reasoning)

        peer:    Visibility of sibling Functions (same level, executed before this one).
                 "none" = sees nothing from siblings
                 "io"   = sees siblings' input + output
                 "full" = sees siblings' complete conversation
    """
    depth: int = 0
    detail: str = "io"
    peer: str = "none"

    def __post_init__(self):
        if self.detail not in ("io", "full"):
            raise ValueError(f"detail must be 'io' or 'full', got '{self.detail}'")
        if self.peer not in ("none", "io", "full"):
            raise ValueError(f"peer must be 'none', 'io', or 'full', got '{self.peer}'")

    # --- Presets ---

    @classmethod
    def isolated(cls) -> "Scope":
        """Pure function. Sees only its own params. No context."""
        return cls(depth=0, detail="io", peer="none")

    @classmethod
    def chained(cls) -> "Scope":
        """Sees sibling Functions' I/O. Good for sequential pipelines."""
        return cls(depth=0, detail="io", peer="io")

    @classmethod
    def aware(cls) -> "Scope":
        """Sees caller info + sibling I/O. Knows where it is in the call chain."""
        return cls(depth=1, detail="io", peer="io")

    @classmethod
    def full(cls) -> "Scope":
        """Sees everything: full call stack, full sibling reasoning."""
        return cls(depth=-1, detail="full", peer="full")

    # --- Convenience ---

    @property
    def needs_call_stack(self) -> bool:
        """Whether this scope requires call stack information."""
        return self.depth != 0

    @property
    def needs_peers(self) -> bool:
        """Whether this scope requires information from sibling Functions."""
        return self.peer != "none"

    @property
    def shares_session(self) -> bool:
        """
        Whether Functions with this scope should share a Session.

        If peer == "full", siblings need to see each other's complete
        conversation, which means they must share a Session.
        If peer == "io", they only need structured summaries (no sharing needed).
        If peer == "none", definitely no sharing.
        """
        return self.peer == "full"

    def __str__(self):
        return f"Scope(depth={self.depth}, detail={self.detail}, peer={self.peer})"


# Convenient constants
ISOLATED = Scope.isolated()
CHAINED = Scope.chained()
AWARE = Scope.aware()
FULL = Scope.full()
