"""Anthropic auth adapter — registers with AuthManager, adopts Claude Code state.

Three credential routes the adapter exposes:

  1. **API key** — the legacy ``ANTHROPIC_API_KEY`` env var. Handled via
     :mod:`auth.sources.env` on the ``anthropic`` provider.

  2. **OAuth token** (``sk-ant-oat`` prefix) — minted by the
     ``claude login`` flow in Claude Code. We don't own the refresh path;
     Claude Code rotates it through its own Keychain/file, and we adopt
     the result read-only so the CLI remains authoritative. Import
     via :func:`import_from_claude_code`. If the on-disk token is past
     expiry, AuthManager surfaces :class:`AuthReadOnlyError` — the user
     must rerun ``claude login`` in their terminal (we tell them how).

  3. **OAuth via our own PKCE flow** — reserved. When Anthropic publishes
     a stable public OAuth client for third-party apps, a
     :class:`PkceLoginMethod` configured against
     ``auth.anthropic.com`` slots in here. Not wired today because the
     endpoint isn't published.

The provider config registers no refresh function: we either hold an
``api_key`` (never expires) or a delegated OAuth token (we don't own
rotation). That's exactly what AuthManager needs to treat both routes
correctly without conflating them.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

from openprogram.auth.manager import (
    ProviderAuthConfig,
    register_provider_config,
)
from openprogram.auth.types import (
    ApiKeyPayload,
    CliDelegatedPayload,
    Credential,
    OAuthPayload,
)


PROVIDER_ID = "anthropic"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def claude_code_credentials_path() -> Path:
    """Return the filesystem path to Claude Code's credentials file.

    The canonical on-disk location is ``~/.claude/.credentials.json``.
    macOS users may alternatively have the payload in the Keychain under
    service ``Claude Code-credentials``; Keychain adoption is a follow-up
    (needs a ``security find-generic-password`` external-process hook).
    """
    return Path.home() / ".claude" / ".credentials.json"


# ---------------------------------------------------------------------------
# Import from Claude Code
# ---------------------------------------------------------------------------

def import_from_claude_code(
    *,
    profile_id: str = "default",
    path: Optional[Path] = None,
) -> Optional[Credential]:
    """Read Claude Code's credentials file and produce a delegated OAuth
    credential.

    Returns ``None`` if the file is missing or unusable — callers decide
    whether that's a "please log in" error or just "skip this route".

    The resulting credential is :class:`CliDelegatedPayload`, read-only.
    The Claude Code CLI owns rotation; every API call re-reads the file
    through AuthManager, so rotations propagate automatically.
    """
    target = Path(path) if path else claude_code_credentials_path()
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    oauth = data.get("claudeAiOauth") or {}
    if not oauth.get("accessToken"):
        return None

    metadata: dict[str, Any] = {
        "imported_from": "claude_code",
        "source_path": str(target),
        "platform": sys.platform,
    }
    if oauth.get("subscriptionType"):
        metadata["subscription_type"] = oauth["subscriptionType"]
    if oauth.get("scopes"):
        metadata["scopes"] = oauth["scopes"]

    return Credential(
        provider_id=PROVIDER_ID,
        profile_id=profile_id,
        kind="cli_delegated",
        payload=CliDelegatedPayload(
            store_path=str(target),
            access_key_path=["claudeAiOauth", "accessToken"],
            refresh_key_path=["claudeAiOauth", "refreshToken"],
            expires_key_path=["claudeAiOauth", "expiresAt"],
        ),
        source="claude_code_import",
        metadata=metadata,
        read_only=True,
    )


def import_api_key(
    api_key: str,
    *,
    profile_id: str = "default",
    metadata: Optional[dict[str, Any]] = None,
) -> Credential:
    """Wrap a pasted ANTHROPIC_API_KEY as a :class:`Credential`.

    Doesn't register it with the store — callers do that themselves via
    :meth:`AuthStore.add_credential`. Exists so every path that produces
    an Anthropic credential funnels through the same type construction,
    with uniform metadata.
    """
    md = {"imported_from": "paste"} | (metadata or {})
    return Credential(
        provider_id=PROVIDER_ID,
        profile_id=profile_id,
        kind="api_key",
        payload=ApiKeyPayload(api_key=api_key.strip()),
        source="anthropic_paste",
        metadata=md,
        read_only=False,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_anthropic_auth() -> None:
    """Register the Anthropic provider config with :mod:`auth.manager`.

    Called at module import. Idempotent; tests that need to swap refresh
    or failure-policy can call :func:`register_provider_config` directly
    — last registration wins.
    """
    register_provider_config(
        ProviderAuthConfig(
            provider_id=PROVIDER_ID,
            refresh_skew_seconds=60,
            # No refresh function: either we hold a static api_key (never
            # expires) or a delegated OAuth (external CLI owns refresh).
            refresh=None,
            async_refresh=None,
        )
    )


register_anthropic_auth()


__all__ = [
    "PROVIDER_ID",
    "claude_code_credentials_path",
    "import_from_claude_code",
    "import_api_key",
    "register_anthropic_auth",
]
