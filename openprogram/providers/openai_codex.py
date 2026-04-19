"""
OpenAICodexRuntime — HTTP-direct provider for OpenAI Codex.

Two modes, both routed through the same Runtime class:

  auth_mode == "chatgpt"  (ChatGPT subscription)
      URL:  https://chatgpt.com/backend-api/codex/responses
      Auth: Bearer <OAuth access_token>  + chatgpt-account-id header
      Creds: read from ~/.codex/auth.json, refreshed against
             https://auth.openai.com/oauth/token when expired.

  auth_mode == "apikey"  (standard OpenAI API billing)
      URL:  https://api.openai.com/v1/responses
      Auth: Bearer <OPENAI_API_KEY>
      Creds: auth.json's OPENAI_API_KEY field, or the env var.

No codex CLI subprocess is involved at call time. The codex CLI is only
needed once, for `codex login --device-auth`, to create auth.json.

Protocol + OAuth parameters translated from @mariozechner/pi-ai
(packages/ai/src/providers/openai-codex-responses.ts and
packages/ai/src/utils/oauth/openai-codex.ts, MIT license).

Usage:
    from openprogram.providers.openai_codex import OpenAICodexRuntime

    rt = OpenAICodexRuntime(model="gpt-5.4-mini")
    reply = rt.exec(content=[{"type": "text", "text": "hi"}])
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from openprogram.agentic_programming.runtime import Runtime


# ----------------------------------------------------------------------------
# Protocol constants (from pi-ai)
# ----------------------------------------------------------------------------

CHATGPT_BACKEND_URL = "https://chatgpt.com/backend-api/codex/responses"
OPENAI_API_URL = "https://api.openai.com/v1/responses"
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
JWT_CLAIM_PATH = "https://api.openai.com/auth"

ORIGINATOR = "openprogram"

# Known Codex-route model ids as of 2026-04. Curated from OpenClaw's catalog
# (augmentModelCatalog + resolveCodexForwardCompatModel). The actual set
# available to a specific ChatGPT account depends on subscription tier.
_KNOWN_CODEX_MODELS = [
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.4-pro",
    "gpt-5.3-codex",
    "gpt-5.3-codex-spark",
    "gpt-5.2-codex",
    "gpt-5.1-codex",
    "gpt-5.1-codex-mini",
]


# ----------------------------------------------------------------------------
# auth.json reading + JWT decoding
# ----------------------------------------------------------------------------

def _codex_home() -> Path:
    """Honor $CODEX_HOME, default ~/.codex (matches Codex CLI)."""
    configured = os.environ.get("CODEX_HOME", "").strip()
    if not configured:
        return Path.home() / ".codex"
    if configured == "~":
        return Path.home()
    if configured.startswith("~/"):
        return Path.home() / configured[2:]
    return Path(configured).resolve()


def _auth_path() -> Path:
    return _codex_home() / "auth.json"


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode JWT payload section (second segment)."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT: not 3 segments")
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def _extract_account_id(access_token: str) -> str:
    """JWT.auth.chatgpt_account_id — required for chatgpt-account-id header."""
    payload = _decode_jwt_payload(access_token)
    auth = payload.get(JWT_CLAIM_PATH) or {}
    account_id = auth.get("chatgpt_account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        raise RuntimeError("JWT has no chatgpt_account_id — re-run `codex login --device-auth`")
    return account_id.strip()


def _jwt_expiry_epoch(access_token: str) -> Optional[int]:
    try:
        exp = _decode_jwt_payload(access_token).get("exp")
        return int(exp) if isinstance(exp, (int, float)) else None
    except Exception:
        return None


# ----------------------------------------------------------------------------
# OAuth token refresh (when access_token is close to expiring)
# ----------------------------------------------------------------------------

def _refresh_oauth_token(refresh_token: str, timeout: float = 30.0) -> dict[str, Any]:
    """POST to auth.openai.com/oauth/token, return new {access_token, refresh_token, expires_in}."""
    r = httpx.post(
        OAUTH_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": OAUTH_CLIENT_ID,
        },
        timeout=timeout,
    )
    if r.status_code != 200:
        raise RuntimeError(f"OAuth refresh failed {r.status_code}: {r.text[:200]}")
    data = r.json()
    for k in ("access_token", "refresh_token", "expires_in"):
        if k not in data:
            raise RuntimeError(f"OAuth refresh response missing {k!r}")
    return data


def _write_auth_json_atomic(data: dict[str, Any]) -> None:
    """Rewrite ~/.codex/auth.json atomically (same dir rename)."""
    path = _auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ----------------------------------------------------------------------------
# Credential resolution (what token do we use, and against which endpoint)
# ----------------------------------------------------------------------------

class _Credentials:
    """Resolved auth state for one call.

    mode == "chatgpt":  uses OAuth token + chatgpt backend endpoint
    mode == "apikey":   uses API key + api.openai.com endpoint
    """

    def __init__(self, mode: str, token: str, account_id: Optional[str], url: str):
        self.mode = mode
        self.token = token
        self.account_id = account_id
        self.url = url


class _AuthState:
    """Cached auth.json + refresh logic.

    Shared across calls from the same runtime. Thread-safe.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._auth: Optional[dict[str, Any]] = None

    def _load(self) -> dict[str, Any]:
        if self._auth is not None:
            return self._auth
        path = _auth_path()
        if not path.exists():
            raise RuntimeError(
                f"{path} not found. Run `codex login --device-auth` "
                "(ChatGPT subscription) or `codex login --with-api-key`."
            )
        self._auth = json.loads(path.read_text(encoding="utf-8"))
        return self._auth

    def resolve(self) -> _Credentials:
        """Return the current credentials, refreshing the OAuth token if needed."""
        with self._lock:
            # Prefer OPENAI_API_KEY env var if set — lets users override auth.json
            env_key = os.environ.get("OPENAI_API_KEY", "").strip()
            if env_key:
                return _Credentials("apikey", env_key, None, OPENAI_API_URL)

            auth = self._load()
            mode = auth.get("auth_mode")

            if mode == "apikey":
                tokens = auth.get("tokens") or {}
                api_key = (
                    tokens.get("api_key")
                    or auth.get("OPENAI_API_KEY")
                    or tokens.get("access_token")
                )
                if not api_key:
                    raise RuntimeError("auth_mode=apikey but no key in auth.json")
                return _Credentials("apikey", api_key, None, OPENAI_API_URL)

            if mode == "chatgpt":
                tokens = auth.get("tokens") or {}
                access = tokens.get("access_token")
                refresh = tokens.get("refresh_token")
                if not access or not refresh:
                    raise RuntimeError("auth_mode=chatgpt but tokens missing")

                exp = _jwt_expiry_epoch(access)
                if exp is not None and exp - 60 < time.time():
                    # Refresh: access token expires in <60s
                    new_tokens = _refresh_oauth_token(refresh)
                    access = new_tokens["access_token"]
                    auth["tokens"]["access_token"] = access
                    auth["tokens"]["refresh_token"] = new_tokens["refresh_token"]
                    if "id_token" in new_tokens:
                        auth["tokens"]["id_token"] = new_tokens["id_token"]
                    _write_auth_json_atomic(auth)
                    self._auth = auth

                account_id = tokens.get("account_id") or _extract_account_id(access)
                return _Credentials("chatgpt", access, account_id, CHATGPT_BACKEND_URL)

            raise RuntimeError(f"Unsupported auth_mode {mode!r} in {_auth_path()}")


# ----------------------------------------------------------------------------
# Request construction
# ----------------------------------------------------------------------------

def _convert_content_to_input(content: list[dict]) -> list[dict]:
    """OpenProgram content blocks → Responses API `input` (single user message).

    Supported block types:
      {"type": "text", "text": "..."}
      {"type": "image", "path": "..."}                (read + base64-encode)
      {"type": "image", "data": "...", "media_type": "image/png"}  (pre-encoded)
    """
    parts: list[dict] = []
    for block in content:
        btype = block.get("type", "text")
        if btype == "text":
            parts.append({"type": "input_text", "text": block.get("text", "")})
        elif btype == "image":
            if "data" in block:
                mt = block.get("media_type", "image/png")
                parts.append({
                    "type": "input_image",
                    "detail": "auto",
                    "image_url": f"data:{mt};base64,{block['data']}",
                })
            elif "path" in block:
                path = block["path"]
                mt = mimetypes.guess_type(path)[0] or "image/png"
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                parts.append({
                    "type": "input_image",
                    "detail": "auto",
                    "image_url": f"data:{mt};base64,{b64}",
                })
        # Silently skip unknown block types for now (audio/video/file)
    return [{"role": "user", "content": parts}]


def _build_headers(creds: _Credentials) -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {creds.token}",
        "User-Agent": f"openprogram ({sys.platform})",
        "content-type": "application/json",
        "accept": "text/event-stream",
        "OpenAI-Beta": "responses=experimental",
    }
    if creds.mode == "chatgpt":
        h["chatgpt-account-id"] = creds.account_id
        h["originator"] = ORIGINATOR
    return h


def _build_body(
    model: str,
    content: list[dict],
    instructions: Optional[str],
    reasoning_effort: Optional[str],
    response_format: Optional[dict],
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "store": False,
        "stream": True,
        # ChatGPT backend rejects bodies without `instructions` (HTTP 400
        # "Instructions are required"). Send a minimal placeholder when the
        # caller didn't supply a system prompt so the request still validates.
        "instructions": instructions or "You are a helpful assistant.",
        "input": _convert_content_to_input(content),
        "tool_choice": "auto",
        "parallel_tool_calls": True,
    }
    if reasoning_effort:
        body["reasoning"] = {"effort": reasoning_effort, "summary": "auto"}
    if response_format:
        # Nudge model toward a JSON schema reply — approximation of what
        # OpenAI's "structured outputs" does. Actual schema enforcement
        # happens in the Responses API via text.format for strict mode.
        body.setdefault("text", {})["format"] = {
            "type": "json_schema",
            "name": response_format.get("name", "response"),
            "schema": response_format.get("schema", response_format),
            "strict": True,
        }
    return body


# ----------------------------------------------------------------------------
# SSE parsing — accumulate response.output_text.delta, stop at completed/failed
# ----------------------------------------------------------------------------

def _parse_sse_response(response: httpx.Response) -> tuple[str, dict[str, Any]]:
    """Consume the SSE stream. Return (final_text, usage_dict)."""
    text_parts: list[str] = []
    usage: dict[str, Any] = {}
    for raw_line in response.iter_lines():
        if not raw_line:
            continue
        if raw_line.startswith("data: "):
            payload = raw_line[6:]
        elif raw_line.startswith("data:"):
            payload = raw_line[5:]
        else:
            continue  # skip "event:", comments, etc.

        if payload == "[DONE]":
            break
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue

        etype = event.get("type", "")

        if etype == "response.output_text.delta":
            delta = event.get("delta", "")
            if delta:
                text_parts.append(delta)

        elif etype == "response.output_text.done":
            # Final assembled text for one output block — prefer it over
            # accumulated deltas when present (avoids split tokens).
            full = event.get("text")
            if isinstance(full, str) and full:
                text_parts = [full]

        elif etype in ("response.completed", "response.done", "response.incomplete"):
            resp = event.get("response") or {}
            usage = resp.get("usage") or usage
            # Also grab final assembled text from response.output when available
            output_items = resp.get("output") or []
            collected: list[str] = []
            for item in output_items:
                if item.get("type") != "message":
                    continue
                for block in item.get("content") or []:
                    if block.get("type") == "output_text":
                        t = block.get("text")
                        if isinstance(t, str):
                            collected.append(t)
            if collected:
                text_parts = collected
            break

        elif etype == "response.failed":
            err = (event.get("response") or {}).get("error") or {}
            raise RuntimeError(f"Codex failed: {err.get('message') or err.get('code') or event}")

        elif etype == "error":
            raise RuntimeError(f"Codex error: {event.get('message') or event.get('code') or event}")

    return "".join(text_parts), usage


# ----------------------------------------------------------------------------
# Runtime
# ----------------------------------------------------------------------------

class OpenAICodexRuntime(Runtime):
    """
    Args:
        model:     Default model id (e.g. "gpt-5.4-mini", "gpt-5.4").
        timeout:   HTTP request timeout in seconds (default: 300).
        system:    Optional system prompt, sent as `instructions`.

    Other kwargs are accepted-and-ignored for backward compatibility with
    the pre-HTTP subprocess version (sandbox, full_auto, session_id, ...).
    They don't apply when talking directly to the HTTP API.
    """

    def __init__(
        self,
        model: str = "gpt-5.4-mini",
        timeout: int = 300,
        system: Optional[str] = None,
        **ignored_legacy_kwargs: Any,
    ):
        super().__init__(model=model)
        self.timeout = timeout
        self.system = system
        self._auth = _AuthState()
        self._client: Optional[httpx.Client] = None
        self._reasoning_effort: Optional[str] = None  # set externally by webui
        self.last_usage: Optional[dict[str, Any]] = None
        self.has_session = False  # we don't manage a server-side session

    # ----- lifecycle ---------------------------------------------------------

    def list_models(self) -> list[str]:
        """Curated Codex-route model ids. Actual access depends on your tier."""
        return list(_KNOWN_CODEX_MODELS)

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=httpx.Timeout(self.timeout, connect=30.0))
        return self._client

    def close(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        super().close()

    # ----- the call ----------------------------------------------------------

    def _call(
        self,
        content: list[dict],
        model: str = None,
        response_format: Optional[dict] = None,
    ) -> str:
        creds = self._auth.resolve()
        chosen_model = model or self.model
        body = _build_body(
            model=chosen_model,
            content=content,
            instructions=self.system,
            reasoning_effort=self._reasoning_effort,
            response_format=response_format,
        )
        headers = _build_headers(creds)

        client = self._get_client()
        with client.stream("POST", creds.url, headers=headers, json=body) as r:
            if r.status_code != 200:
                err_body = r.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Codex HTTP {r.status_code} ({creds.mode} mode, {creds.url}): "
                    f"{err_body[:500]}"
                )
            text, usage = _parse_sse_response(r)

        # Normalize usage to the shape the rest of OpenProgram expects
        if usage:
            self.last_usage = {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_read": (usage.get("input_tokens_details") or {}).get("cached_tokens", 0),
                "cache_create": 0,
            }
        return text
