"""
Scope — defines what a Function can see when it executes.

Scope is an *intent declaration*. It tells the Runtime what context a Function
wants, but the Session decides how to fulfill that intent based on its own
capabilities.

    API Sessions (no memory):   read depth/detail/peer → inject context manually
    CLI Sessions (have memory): read compact → compress after execution

All parameters are Optional. None means "I don't care, use default behavior."
Each Session type reads the parameters it understands and ignores the rest.

Parameters for API Sessions (context injection):
    depth   How many layers up the call stack are visible.
    detail  How much of each stack layer is shown ("io" or "full").
    peer    Sibling visibility ("none", "io", "full").

Parameters for CLI Sessions (context management):
    compact Whether to compress the conversation after execution.

Parameters for all Sessions:
    (future parameters can be added here)

Common presets:
    Scope.isolated()  — pure function, no context
    Scope.chained()   — sees sibling I/O
    Scope.aware()     — sees caller + sibling I/O
    Scope.full()      — sees everything, shared session
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Scope:
    """
    Defines what a Function can see when it executes.

    All parameters are Optional. None = "no opinion, use Session default."
    Each Session type reads the parameters it understands.

    API Session parameters:
        depth:   Call stack visibility.
                 0 = only own input. 1 = caller. -1 = unlimited. None = don't inject.
        detail:  Per-layer detail. "io" or "full". None = default to "io".
        peer:    Sibling visibility. "none", "io", "full". None = default to "none".

    CLI Session parameters:
        compact: Compress conversation after execution.
                 True = summarize, False = keep full, None = Session decides.
    """
    # --- API Session parameters (context injection) ---
    depth: Optional[int] = None
    detail: Optional[str] = None
    peer: Optional[str] = None

    # --- CLI Session parameters (context management) ---
    compact: Optional[bool] = None

    def __post_init__(self):
        if self.detail is not None and self.detail not in ("io", "full"):
            raise ValueError(f"detail must be 'io', 'full', or None, got '{self.detail}'")
        if self.peer is not None and self.peer not in ("none", "io", "full"):
            raise ValueError(f"peer must be 'none', 'io', 'full', or None, got '{self.peer}'")

    # --- Presets ---

    @classmethod
    def isolated(cls) -> "Scope":
        """Pure function. No context injection, no session sharing."""
        return cls(depth=0, detail="io", peer="none", compact=None)

    @classmethod
    def chained(cls) -> "Scope":
        """Sees sibling Functions' I/O summaries."""
        return cls(depth=0, detail="io", peer="io", compact=None)

    @classmethod
    def aware(cls) -> "Scope":
        """Sees caller info + sibling I/O."""
        return cls(depth=1, detail="io", peer="io", compact=None)

    @classmethod
    def full(cls) -> "Scope":
        """Sees everything. Shared session, full reasoning visible."""
        return cls(depth=-1, detail="full", peer="full", compact=None)

    # --- Convenience properties ---

    @property
    def needs_call_stack(self) -> bool:
        """Whether this scope requests call stack information."""
        return self.depth is not None and self.depth != 0

    @property
    def needs_peers(self) -> bool:
        """Whether this scope requests information from sibling Functions."""
        return self.peer is not None and self.peer != "none"

    @property
    def shares_session(self) -> bool:
        """
        Whether Functions with this scope should share a Session.
        peer="full" means siblings share a Session for full conversation visibility.
        """
        return self.peer == "full"

    @property
    def needs_compact(self) -> bool:
        """Whether this scope requests post-execution compaction."""
        return self.compact is True

    def __str__(self):
        parts = []
        if self.depth is not None:
            parts.append(f"depth={self.depth}")
        if self.detail is not None:
            parts.append(f"detail={self.detail}")
        if self.peer is not None:
            parts.append(f"peer={self.peer}")
        if self.compact is not None:
            parts.append(f"compact={self.compact}")
        return f"Scope({', '.join(parts)})"


# Convenient constants
ISOLATED = Scope.isolated()
CHAINED = Scope.chained()
AWARE = Scope.aware()
FULL = Scope.full()
