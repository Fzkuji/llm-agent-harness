"""
GeminiRuntime — thin Runtime subclass for Google Gemini's Generative
Language API.

Streaming, tool loops, and exec-tree recording all happen through the
default ``Runtime`` → ``AgentSession`` → pi-ai path. This class only
resolves the API key and lets ``Runtime("google:<id>", api_key=...)``
do the rest.

Usage::

    from openprogram.providers.google import GeminiRuntime
    rt = GeminiRuntime(api_key="...", model="gemini-2.5-pro")
    rt.exec(content=[{"type": "text", "text": "hi"}])
"""

from __future__ import annotations

import os
from typing import Optional

from openprogram.agentic_programming.runtime import Runtime


class GeminiRuntime(Runtime):
    """Runtime that targets the Google Gemini API via pi-ai.

    Args:
        api_key:     Google API key. Falls back to ``GOOGLE_API_KEY``
                     or ``GOOGLE_GENERATIVE_AI_API_KEY``.
        model:       Model id under the ``google`` provider namespace.
        max_retries: Retry budget forwarded to base ``Runtime``.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash",
        max_retries: int = 2,
    ):
        api_key = (
            api_key
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY")
        )
        if not api_key:
            raise ValueError(
                "Google API key is required. Pass api_key= or set "
                "GOOGLE_API_KEY (or GOOGLE_GENERATIVE_AI_API_KEY) env var."
            )
        super().__init__(
            model=f"google:{model}",
            api_key=api_key,
            max_retries=max_retries,
        )

    def list_models(self) -> list[str]:
        """Return Gemini model ids known to the pi-ai registry."""
        from openprogram.providers.models_generated import MODELS
        return sorted(
            m.id for m in MODELS.values() if m.provider == "google"
        )
