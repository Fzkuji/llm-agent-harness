"""Command-line entry points for auth v2.

Wired into ``openprogram`` via ``openprogram auth <subcommand>``. The
goal is feature parity with ``gh auth login`` / ``codex login`` — a
single interactive wizard that handles every provider's setup without
the user needing to know which auth kind it is.

Subcommands:

  * ``openprogram auth login <provider>`` — interactive wizard. Detects
    what's possible for the provider (paste key / device-code / import
    from another CLI) and drives the right flow.
  * ``openprogram auth list`` — tabular view of pools per profile with
    masked secret previews.
  * ``openprogram auth discover`` — non-destructive scan of external
    sources. Shows what could be imported but doesn't commit.
  * ``openprogram auth adopt`` — accept a previously-discovered
    credential into the store. Usually follows ``discover``.
  * ``openprogram auth logout <provider> [--profile P]`` — remove all
    credentials for the provider in the given profile and print any
    non-executable :class:`RemovalStep` so the user knows what they
    still need to clean up manually.
  * ``openprogram auth profile {list,create,delete} [...]`` — profile
    CRUD without requiring the WebUI.
  * ``openprogram auth status <provider> [--profile P]`` — show the
    active credential for a provider and whether AuthManager would
    resolve it right now.

Design constraints:

  * no webserver or browser — this must work over SSH
  * no dependency on the WebUI routes — CLI and webui both hit
    :mod:`auth.store` + :mod:`auth.manager` directly
  * secrets are masked on display; paste flows read via
    :func:`getpass.getpass` so the key doesn't appear in shell history
    or in terminal scroll-back of a screen-sharing session
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import sys
import time
from typing import Any, Optional

from .context import auth_scope
from .manager import AuthManager, get_manager
from .profiles import (
    DEFAULT_PROFILE_NAME,
    ProfileManager,
    get_profile_manager,
)
from .store import AuthStore, get_store
from .types import (
    ApiKeyPayload,
    AuthConfigError,
    AuthError,
    CliDelegatedPayload,
    Credential,
    CredentialPool,
    DeviceCodePayload,
    ExternalProcessPayload,
    OAuthPayload,
    RemovalStep,
)


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------

def build_parser(sub: "argparse._SubParsersAction") -> None:
    """Attach the ``auth`` command tree onto an existing argparse parent.

    Expected use from :func:`openprogram.cli.main`::

        sub = parser.add_subparsers(...)
        from openprogram.auth.cli import build_parser as build_auth
        build_auth(sub)
    """
    p = sub.add_parser(
        "auth",
        help="Manage credentials (login, logout, list, discover).",
    )
    auth_sub = p.add_subparsers(dest="auth_cmd", metavar="subcommand")

    # login
    p_login = auth_sub.add_parser("login", help="Log into a provider")
    p_login.add_argument("provider", help="Provider id (e.g. openai-codex, anthropic)")
    p_login.add_argument("--profile", default=DEFAULT_PROFILE_NAME,
                         help=f"Profile (default: {DEFAULT_PROFILE_NAME})")
    p_login.add_argument("--method", default=None,
                         help="Force a login method (api_key / import_from_cli / device_code). "
                              "If omitted, the wizard auto-selects the best available.")

    # list
    p_list = auth_sub.add_parser("list", help="List pools per profile")
    p_list.add_argument("--profile", default=None,
                        help="Filter to one profile (default: all)")
    p_list.add_argument("--json", action="store_true", help="Output JSON")

    # discover
    p_disc = auth_sub.add_parser("discover", help="Scan external sources")
    p_disc.add_argument("--json", action="store_true", help="Output JSON")

    # adopt
    p_adopt = auth_sub.add_parser("adopt",
        help="Adopt a discovered credential into the store")
    p_adopt.add_argument("source_id",
        help="Source id from `discover` output (e.g. codex_cli, env:OPENAI_API_KEY)")
    p_adopt.add_argument("--profile", default=DEFAULT_PROFILE_NAME,
                         help=f"Target profile (default: {DEFAULT_PROFILE_NAME})")

    # logout
    p_logout = auth_sub.add_parser("logout", help="Remove credentials for a provider")
    p_logout.add_argument("provider")
    p_logout.add_argument("--profile", default=DEFAULT_PROFILE_NAME)
    p_logout.add_argument("--yes", action="store_true", help="Skip confirmation")

    # status
    p_status = auth_sub.add_parser("status", help="Check a provider's current credential")
    p_status.add_argument("provider")
    p_status.add_argument("--profile", default=DEFAULT_PROFILE_NAME)

    # profile
    p_profile = auth_sub.add_parser("profile", help="Profile management")
    prof_sub = p_profile.add_subparsers(dest="profile_cmd", metavar="action")
    prof_sub.add_parser("list", help="List profiles")
    pc = prof_sub.add_parser("create", help="Create a profile")
    pc.add_argument("name")
    pc.add_argument("--display-name", default="")
    pc.add_argument("--description", default="")
    pd = prof_sub.add_parser("delete", help="Delete a profile")
    pd.add_argument("name")
    pd.add_argument("--yes", action="store_true", help="Skip confirmation")


def dispatch(args: argparse.Namespace) -> int:
    """Run the selected auth subcommand.

    Returns a shell-style exit code so the outer ``main()`` can
    propagate it to ``sys.exit``."""
    cmd = args.auth_cmd
    if cmd == "login":
        return _cmd_login(args.provider, args.profile, args.method)
    if cmd == "list":
        return _cmd_list(args.profile, args.json)
    if cmd == "discover":
        return _cmd_discover(args.json)
    if cmd == "adopt":
        return _cmd_adopt(args.source_id, args.profile)
    if cmd == "logout":
        return _cmd_logout(args.provider, args.profile, skip_confirm=args.yes)
    if cmd == "status":
        return _cmd_status(args.provider, args.profile)
    if cmd == "profile":
        return _dispatch_profile(args)
    # No subcommand — print the auth help. We do it from here so the
    # caller doesn't need to carry the parser object around.
    print("Usage: openprogram auth <subcommand>\n"
          "Subcommands: login, list, discover, adopt, logout, status, profile",
          file=sys.stderr)
    return 2


def _dispatch_profile(args: argparse.Namespace) -> int:
    pc = args.profile_cmd
    if pc == "list":
        return _cmd_profile_list()
    if pc == "create":
        return _cmd_profile_create(args.name, args.display_name, args.description)
    if pc == "delete":
        return _cmd_profile_delete(args.name, args.yes)
    print("Usage: openprogram auth profile {list,create,delete}", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _mask(secret: str, keep_prefix: int = 6, keep_suffix: int = 4) -> str:
    if not secret:
        return ""
    if len(secret) <= keep_prefix + keep_suffix + 1:
        return "*" * len(secret)
    return f"{secret[:keep_prefix]}…{secret[-keep_suffix:]}"


def _payload_summary(cred: Credential) -> str:
    p = cred.payload
    if isinstance(p, ApiKeyPayload):
        return f"api_key {_mask(p.api_key)}"
    if isinstance(p, OAuthPayload):
        extra = " (+refresh)" if p.refresh_token else ""
        expiry = _fmt_expiry(p.expires_at_ms)
        return f"oauth {_mask(p.access_token)}{extra} exp={expiry}"
    if isinstance(p, DeviceCodePayload):
        return f"device_code {_mask(p.access_token)} exp={_fmt_expiry(p.expires_at_ms)}"
    if isinstance(p, CliDelegatedPayload):
        return f"cli_delegated → {p.store_path}"
    if isinstance(p, ExternalProcessPayload):
        return f"external_process {' '.join(p.command)}"
    return cred.kind


def _fmt_expiry(ms: int) -> str:
    if not ms:
        return "unknown"
    delta = ms - int(time.time() * 1000)
    if delta < 0:
        return f"{_fmt_duration(-delta)} ago (expired)"
    return f"in {_fmt_duration(delta)}"


def _fmt_duration(ms: int) -> str:
    seconds = ms // 1000
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86_400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86_400}d"


# ---------------------------------------------------------------------------
# login — interactive wizard
# ---------------------------------------------------------------------------

def _cmd_login(provider: str, profile: str, method: Optional[str]) -> int:
    store = get_store()
    choices = _available_login_methods(provider)
    if not choices:
        print(f"No login method implemented for provider {provider!r}.", file=sys.stderr)
        return 1

    if method is None:
        print(f"Login to {provider} (profile: {profile})")
        print("Available methods:")
        for i, (mid, label) in enumerate(choices, 1):
            print(f"  {i}. {mid:24s} — {label}")
        try:
            pick = input(f"Pick a method [1-{len(choices)}] (default 1): ").strip() or "1"
            chosen = choices[int(pick) - 1][0]
        except (EOFError, ValueError, IndexError):
            print("Aborted.", file=sys.stderr)
            return 1
    else:
        chosen = method
        if chosen not in {m for m, _ in choices}:
            print(f"Method {chosen!r} not available for {provider}. "
                  f"Try: {', '.join(m for m, _ in choices)}", file=sys.stderr)
            return 1

    try:
        cred = _run_login_method(provider, profile, chosen)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130
    except AuthError as e:
        print(f"Login failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Login failed: {e.__class__.__name__}: {e}", file=sys.stderr)
        return 1

    store.add_credential(cred)
    print(f"\n✓ Saved credential {cred.credential_id} for {provider}/{profile}")
    print(f"  kind: {cred.kind}")
    print(f"  preview: {_payload_summary(cred)}")
    print(f"  store: {store.root}/{provider}/{profile}.json")
    return 0


def _available_login_methods(provider: str) -> list[tuple[str, str]]:
    """Enumerate login methods the CLI can drive for ``provider``.

    The ordering matters — the first entry is what ``--method`` defaults
    to if the user just hits Enter. Provider-specific customizations
    (e.g. Codex's "import from codex CLI" helper) take precedence over
    the generic paste-an-api-key method because they almost always
    produce a better credential."""
    choices: list[tuple[str, str]] = []
    if provider == "openai-codex":
        choices.append(("import_from_cli", "Import from ~/.codex/auth.json (run `codex login` first)"))
    if provider == "anthropic":
        choices.append(("import_from_cli", "Import from Claude Code's ~/.claude/.credentials.json"))
    if provider == "google-gemini-cli":
        choices.append(("import_from_cli", "Import from ~/.gemini/oauth_creds.json"))
    if provider == "qwen":
        choices.append(("import_from_cli", "Import from ~/.qwen/oauth_creds.json"))
    # API-key paste is universal — every provider accepts one even if
    # it's not the recommended path.
    choices.append(("api_key", "Paste a static API key"))
    return choices


def _run_login_method(provider: str, profile: str, method: str) -> Credential:
    if method == "api_key":
        return _login_paste_api_key(provider, profile)
    if method == "import_from_cli":
        return _login_import_from_cli(provider, profile)
    raise AuthConfigError(f"unsupported method: {method!r}")


def _login_paste_api_key(provider: str, profile: str) -> Credential:
    key = getpass.getpass(f"Paste API key for {provider} (hidden): ").strip()
    if not key:
        raise AuthConfigError("empty API key — nothing to save")
    return Credential(
        provider_id=provider,
        profile_id=profile,
        kind="api_key",
        payload=ApiKeyPayload(api_key=key),
        source="cli_paste",
        metadata={},
    )


def _login_import_from_cli(provider: str, profile: str) -> Credential:
    """Delegate to the per-provider adapter's ``import_from_*`` helper.

    Adapters produce either writable OAuth (Codex — we rotate) or
    delegated read-only (Anthropic/Gemini/Qwen — external CLI rotates).
    The distinction is invisible here; we just hand off."""
    if provider == "openai-codex":
        from openprogram.providers.openai_codex import auth_adapter
        cred = auth_adapter.import_from_codex_file(profile_id=profile)
        if cred is None:
            raise AuthConfigError(
                f"{auth_adapter.codex_auth_path()} not found. "
                f"Run `codex login --device-auth` first, then re-run this command."
            )
        return cred
    if provider == "anthropic":
        from openprogram.providers.anthropic import auth_adapter
        cred = auth_adapter.import_from_claude_code(profile_id=profile)
        if cred is None:
            raise AuthConfigError(
                f"{auth_adapter.claude_code_credentials_path()} not found. "
                f"Run `claude login` (Claude Code CLI) first."
            )
        return cred
    if provider == "google-gemini-cli":
        from openprogram.providers.google_gemini_cli import auth_adapter
        cred = auth_adapter.import_from_gemini_cli(profile_id=profile)
        if cred is None:
            raise AuthConfigError(
                f"{auth_adapter.gemini_cli_credentials_path()} not found. "
                f"Run `gemini auth login` first."
            )
        return cred
    if provider == "qwen":
        from openprogram.auth.sources.qwen_cli import QwenCliSource
        src = QwenCliSource(profile_id=profile)
        creds = src.try_import(get_profile_manager().get_profile(profile).root)
        if not creds:
            raise AuthConfigError(
                "~/.qwen/oauth_creds.json not found. Run `qwen login` first."
            )
        return creds[0]
    raise AuthConfigError(f"no import-from-CLI adapter for {provider!r}")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def _cmd_list(profile_filter: Optional[str], as_json: bool) -> int:
    store = get_store()
    pm = get_profile_manager()
    pools = store.list_pools()
    if profile_filter:
        pools = [p for p in pools if p.profile_id == profile_filter]

    if as_json:
        out = [
            {
                "provider_id": p.provider_id,
                "profile_id": p.profile_id,
                "strategy": p.strategy,
                "credentials": [
                    {
                        "id": c.credential_id,
                        "kind": c.kind,
                        "preview": _payload_summary(c),
                        "status": c.status,
                        "read_only": c.read_only,
                    }
                    for c in p.credentials
                ],
            }
            for p in pools
        ]
        print(json.dumps(out, indent=2))
        return 0

    if not pools:
        print("No credential pools yet. Try:")
        print("  openprogram auth discover        # scan for existing credentials")
        print("  openprogram auth login <prov>    # add one manually")
        return 0

    print(f"{'provider':28s}  {'profile':16s}  credential")
    for p in pools:
        for c in p.credentials:
            ro = " [read-only]" if c.read_only else ""
            print(f"{p.provider_id:28s}  {p.profile_id:16s}  "
                  f"{c.credential_id} — {_payload_summary(c)}{ro}")
    return 0


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------

def _cmd_discover(as_json: bool) -> int:
    from openprogram.auth.sources import (
        ClaudeCodeSource,
        CodexCliSource,
        EnvApiKeySource,
        GhCliSource,
        QwenCliSource,
    )
    from openprogram.providers.env_api_keys import PROVIDER_ENV_VARS

    pm = get_profile_manager()
    default = pm.get_profile(DEFAULT_PROFILE_NAME)
    sources: list[Any] = [
        CodexCliSource(),
        ClaudeCodeSource(),
        QwenCliSource(),
        GhCliSource(),
    ]
    for provider, env_var in PROVIDER_ENV_VARS.items():
        sources.append(EnvApiKeySource(provider_id=provider, env_var=env_var))

    found: list[dict[str, Any]] = []
    for src in sources:
        try:
            creds = src.try_import(default.root)
        except Exception as e:
            found.append({"source_id": src.source_id, "error": str(e)})
            continue
        for cred in creds:
            found.append({
                "source_id": src.source_id,
                "provider": cred.provider_id,
                "profile": cred.profile_id,
                "kind": cred.kind,
                "preview": _payload_summary(cred),
                "read_only": cred.read_only,
            })

    if as_json:
        print(json.dumps(found, indent=2))
        return 0

    if not found:
        print("Nothing found. No existing CLIs or env-var keys detected on this machine.")
        return 0

    print(f"Found {len(found)} adoptable credential(s):\n")
    print(f"{'source':28s}  {'provider':24s}  preview")
    for f in found:
        if "error" in f:
            print(f"{f['source_id']:28s}  (error)                   {f['error']}")
            continue
        print(f"{f['source_id']:28s}  {f['provider']:24s}  {f['preview']}")
    print("\nAdopt one with:  openprogram auth adopt <source_id>")
    return 0


# ---------------------------------------------------------------------------
# adopt
# ---------------------------------------------------------------------------

def _cmd_adopt(source_id: str, profile: str) -> int:
    store = get_store()
    pm = get_profile_manager()
    profile_obj = pm.get_profile(profile)

    src = _source_by_id(source_id, profile)
    if src is None:
        print(f"Unknown source: {source_id!r}. "
              f"Run `openprogram auth discover` to see available ids.",
              file=sys.stderr)
        return 1

    try:
        creds = src.try_import(profile_obj.root)
    except Exception as e:
        print(f"Source failed: {e}", file=sys.stderr)
        return 1
    if not creds:
        print(f"Source {source_id!r} produced no credentials — nothing to adopt.",
              file=sys.stderr)
        return 1

    for cred in creds:
        # Force the caller's requested profile — some sources default
        # to "default" but the user may be scoping to "work".
        cred.profile_id = profile
        store.add_credential(cred)
        print(f"✓ Adopted {cred.provider_id}/{cred.profile_id}: {_payload_summary(cred)}")
    return 0


def _source_by_id(source_id: str, profile: str):
    from openprogram.auth.sources import (
        ClaudeCodeSource,
        CodexCliSource,
        EnvApiKeySource,
        GhCliSource,
        QwenCliSource,
    )
    from openprogram.providers.env_api_keys import PROVIDER_ENV_VARS

    if source_id == "codex_cli":
        return CodexCliSource(profile_id=profile)
    if source_id == "claude_code":
        return ClaudeCodeSource(profile_id=profile)
    if source_id == "qwen_cli":
        return QwenCliSource(profile_id=profile)
    if source_id == "gh_cli":
        return GhCliSource()
    if source_id.startswith("env:"):
        env_var = source_id[4:]
        provider = next(
            (p for p, v in PROVIDER_ENV_VARS.items() if v == env_var), None,
        )
        if provider is None:
            return None
        return EnvApiKeySource(provider_id=provider, env_var=env_var, profile_id=profile)
    return None


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------

def _cmd_logout(provider: str, profile: str, *, skip_confirm: bool) -> int:
    store = get_store()
    pool = store.find_pool(provider, profile)
    if pool is None or not pool.credentials:
        print(f"No credentials for {provider}/{profile} — nothing to remove.")
        return 0

    if not skip_confirm:
        print(f"About to remove {len(pool.credentials)} credential(s) for "
              f"{provider}/{profile}:")
        for c in pool.credentials:
            print(f"  - {c.credential_id} ({_payload_summary(c)})")
        confirm = input("Proceed? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Aborted.")
            return 0

    removed_steps = _collect_removal_steps(pool)
    store.delete_pool(provider, profile)
    print(f"✓ Removed {len(pool.credentials)} credential(s) from "
          f"{store.root}/{provider}/{profile}.json")

    non_exec = [s for s in removed_steps if not s.executable]
    if non_exec:
        print("\nManual cleanup still required:")
        for step in non_exec:
            print(f"  - {step.description}")
    return 0


def _collect_removal_steps(pool: CredentialPool) -> list[RemovalStep]:
    """Gather :class:`RemovalStep` entries from whichever source produced
    each credential. Returns a flat list; duplicates are OK because
    the user reads through them regardless."""
    steps: list[RemovalStep] = []
    for cred in pool.credentials:
        src = _source_by_id(cred.source, cred.profile_id) if cred.source else None
        if src is not None and hasattr(src, "removal_steps"):
            try:
                steps.extend(src.removal_steps(cred))
            except Exception:
                continue
    return steps


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def _cmd_status(provider: str, profile: str) -> int:
    manager = get_manager()
    with auth_scope(profile_id=profile):
        try:
            cred = manager.acquire_sync(provider, profile)
        except AuthConfigError as e:
            print(f"No credential configured for {provider}/{profile}.")
            print(f"  → {e}")
            print(f"Try: openprogram auth login {provider} --profile {profile}")
            return 1
        except AuthError as e:
            print(f"Credential exists but is not usable: {e}")
            return 1

    print(f"Provider: {provider}")
    print(f"Profile:  {profile}")
    print(f"Kind:     {cred.kind}")
    print(f"Status:   {cred.status}")
    print(f"Preview:  {_payload_summary(cred)}")
    if cred.metadata:
        print("Metadata:")
        for k, v in cred.metadata.items():
            print(f"  {k}: {v}")
    return 0


# ---------------------------------------------------------------------------
# profile CRUD
# ---------------------------------------------------------------------------

def _cmd_profile_list() -> int:
    pm = get_profile_manager()
    profiles = pm.list_profiles()
    print(f"{'name':16s}  {'display name':24s}  root")
    for p in profiles:
        print(f"{p.name:16s}  {p.display_name or '-':24s}  {p.root}")
    return 0


def _cmd_profile_create(name: str, display_name: str, description: str) -> int:
    pm = get_profile_manager()
    try:
        profile = pm.create_profile(
            name, display_name=display_name, description=description,
        )
    except AuthConfigError as e:
        print(f"Failed to create profile: {e}", file=sys.stderr)
        return 1
    print(f"✓ Created profile {profile.name} at {profile.root}")
    return 0


def _cmd_profile_delete(name: str, skip_confirm: bool) -> int:
    pm = get_profile_manager()
    if not skip_confirm:
        confirm = input(f"Delete profile {name!r} and all its credentials? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Aborted.")
            return 0
    try:
        pm.delete_profile(name)
    except AuthConfigError as e:
        print(f"Failed to delete profile: {e}", file=sys.stderr)
        return 1
    print(f"✓ Deleted profile {name}")
    return 0


__all__ = ["build_parser", "dispatch"]
