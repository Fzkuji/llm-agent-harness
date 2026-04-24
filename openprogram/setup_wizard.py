"""First-run setup wizard + per-section config commands.

Four sections, each runnable standalone:

    openprogram setup                 # full walk-through
    openprogram providers setup       # section 1 alone
    openprogram config model          # section 2 alone
    openprogram config tools          # section 3 alone
    openprogram config agent          # section 4 alone

UI layer: uses ``questionary`` for arrow-key navigation when the
dep is present, falls back to plain ``input()`` otherwise so a
minimal install still gets a usable wizard.

Storage lives under ``~/.agentic/config.json`` alongside the
existing provider / api_keys config. Keys written here:
    default_provider   str
    default_model      str
    tools.disabled     list[str]
    agent.thinking_effort  str  (low/medium/high/xhigh)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from openprogram.paths import get_config_path


# Back-compat export — many readers used to import CONFIG_PATH directly.
# Kept as a property-like getter: evaluating it returns the current
# profile's config path rather than a value frozen at import time.
class _ConfigPathProxy:
    def __fspath__(self) -> str:
        return str(get_config_path())
    def __str__(self) -> str:
        return str(get_config_path())
    def __repr__(self) -> str:
        return f"ConfigPath({get_config_path()!s})"
    @property
    def parent(self) -> Path:
        return get_config_path().parent
    def read_text(self, *a, **kw):
        return get_config_path().read_text(*a, **kw)
    def write_text(self, *a, **kw):
        return get_config_path().write_text(*a, **kw)


CONFIG_PATH: Any = _ConfigPathProxy()


# --- storage helpers --------------------------------------------------------

def _read_config() -> dict[str, Any]:
    try:
        return json.loads(get_config_path().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_config(cfg: dict[str, Any]) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2) + "\n")


def read_disabled_tools() -> set[str]:
    """Public helper consumed by openprogram.tools to filter list_available.

    Kept in this module so the tools package doesn't import config from
    deeper webui modules and drag in FastAPI at tool-registry import time.

    Also honours ``memory.backend == "none"`` by hiding the ``memory``
    tool, since it has no backing store in that mode.
    """
    cfg = _read_config()
    disabled = set(cfg.get("tools", {}).get("disabled", []) or [])
    if (cfg.get("memory", {}) or {}).get("backend") == "none":
        disabled.add("memory")
    return disabled


def read_disabled_skills() -> set[str]:
    """Skills the user opted out of in `openprogram config skills`."""
    cfg = _read_config()
    return set(cfg.get("skills", {}).get("disabled", []) or [])


def read_ui_prefs() -> dict[str, Any]:
    cfg = _read_config()
    ui = cfg.get("ui", {}) or {}
    return {
        "port": int(ui.get("port") or 8765),
        "open_browser": bool(ui.get("open_browser", True)),
    }


def read_agent_prefs() -> dict[str, Any]:
    cfg = _read_config()
    agent = cfg.get("agent", {}) or {}
    return {
        "thinking_effort": agent.get("thinking_effort") or "medium",
    }


# --- UI primitives (questionary w/ input() fallback) ------------------------

def _have_questionary() -> bool:
    try:
        import questionary  # noqa: F401
        return True
    except ImportError:
        return False


def _confirm(prompt: str, default: bool = True) -> bool:
    if _have_questionary():
        import questionary
        ans = questionary.confirm(prompt, default=default).ask()
        return bool(ans) if ans is not None else False
    hint = "Y/n" if default else "y/N"
    try:
        s = input(f"{prompt} [{hint}] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not s:
        return default
    return s in ("y", "yes")


def _choose_one(prompt: str, choices: list[str],
                default: str | None = None) -> str | None:
    if not choices:
        return None
    if _have_questionary():
        import questionary
        ans = questionary.select(prompt, choices=choices,
                                 default=default or choices[0]).ask()
        return ans  # None on Ctrl-C
    print(prompt)
    for i, c in enumerate(choices, 1):
        marker = "*" if c == default else " "
        print(f"  {marker} {i:>2}) {c}")
    try:
        raw = input(f"? [{(choices.index(default) + 1) if default in choices else 1}] ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not raw:
        return default if default in choices else choices[0]
    try:
        idx = int(raw) - 1
    except ValueError:
        print(f"Invalid: {raw!r}")
        return None
    if 0 <= idx < len(choices):
        return choices[idx]
    return None


def _checkbox(prompt: str, items: list[tuple[str, bool]]) -> list[str] | None:
    """Multi-select. Returns list of selected names, or None if cancelled.

    ``items`` = [(name, initial_checked), ...] preserving caller order.
    """
    if not items:
        return []
    if _have_questionary():
        import questionary
        choices = [
            questionary.Choice(name, value=name, checked=enabled)
            for name, enabled in items
        ]
        ans = questionary.checkbox(prompt, choices=choices).ask()
        return ans  # None on Ctrl-C
    # input() fallback: toggle by number, 'all' / 'none' / blank to commit.
    names = [n for n, _ in items]
    selected: set[str] = {n for n, e in items if e}
    while True:
        print(prompt)
        for i, (n, _) in enumerate(items, 1):
            mark = "[x]" if n in selected else "[ ]"
            print(f"  {mark} {i:>2}) {n}")
        print("Enter numbers (1,3,5) to toggle, 'all' / 'none', or blank to finish.")
        try:
            raw = input("? ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        if raw == "":
            return sorted(selected)
        if raw == "all":
            selected = set(names); continue
        if raw == "none":
            selected = set(); continue
        try:
            for tok in raw.split(","):
                idx = int(tok.strip()) - 1
                if 0 <= idx < len(names):
                    n = names[idx]
                    if n in selected:
                        selected.remove(n)
                    else:
                        selected.add(n)
                else:
                    print(f"  out of range: {idx + 1}")
        except ValueError:
            print(f"  invalid: {raw!r}")


def _text(prompt: str, default: str = "") -> str | None:
    if _have_questionary():
        import questionary
        ans = questionary.text(prompt, default=default).ask()
        return ans
    hint = f" [{default}]" if default else ""
    try:
        s = input(f"{prompt}{hint} ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return s or default


def _password(prompt: str) -> str | None:
    """Secret entry — masks input when questionary is available."""
    if _have_questionary():
        import questionary
        ans = questionary.password(prompt).ask()
        return ans
    try:
        import getpass
        return getpass.getpass(f"{prompt} ")
    except (EOFError, KeyboardInterrupt):
        return None


# --- Sections ---------------------------------------------------------------

def run_providers_section() -> int:
    """Delegate to the existing credential-import wizard."""
    from openprogram.auth.cli import _cmd_setup
    return _cmd_setup()


def run_model_section() -> int:
    """Pick the default chat model across enabled providers."""
    from openprogram.webui import _model_catalog as mc
    enabled = mc.list_enabled_models()
    if not enabled:
        print("No enabled models yet. After you enable a provider in "
              "`openprogram providers setup`, come back and run "
              "`openprogram config model`.")
        return 1

    labels = [f"{m['provider']}/{m['id']}  ({m.get('name', m['id'])})"
              for m in enabled]
    values = [f"{m['provider']}/{m['id']}" for m in enabled]
    label_to_value = dict(zip(labels, values))

    cfg = _read_config()
    cur_prov = cfg.get("default_provider")
    cur_model = cfg.get("default_model")
    current_label = None
    if cur_prov and cur_model:
        for lbl, val in label_to_value.items():
            if val == f"{cur_prov}/{cur_model}":
                current_label = lbl
                break

    picked = _choose_one("Default chat model:", labels, current_label)
    if picked is None:
        print("Cancelled.")
        return 1
    provider, model = label_to_value[picked].split("/", 1)
    cfg["default_provider"] = provider
    cfg["default_model"] = model
    _write_config(cfg)
    print(f"Default set: {provider}/{model}")
    return 0


def run_tools_section() -> int:
    """Pick which tools are enabled by default."""
    from openprogram.tools import ALL_TOOLS
    cfg = _read_config()
    disabled = set(cfg.get("tools", {}).get("disabled", []) or [])
    names = sorted(ALL_TOOLS.keys())
    items = [(n, n not in disabled) for n in names]

    picked = _checkbox("Enable these tools:", items)
    if picked is None:
        print("Cancelled.")
        return 1
    new_disabled = sorted(set(names) - set(picked))
    cfg.setdefault("tools", {})["disabled"] = new_disabled
    _write_config(cfg)
    print(f"Enabled: {len(picked)} / {len(names)} tools")
    if new_disabled:
        print(f"Disabled: {', '.join(new_disabled)}")
    return 0


def run_agent_section() -> int:
    """Default thinking effort and other agent-level defaults."""
    cfg = _read_config()
    current = (cfg.get("agent", {}) or {}).get("thinking_effort") or "medium"

    levels = ["low", "medium", "high", "xhigh"]
    picked = _choose_one("Default thinking effort:", levels, current)
    if picked is None:
        print("Cancelled.")
        return 1
    cfg.setdefault("agent", {})["thinking_effort"] = picked
    _write_config(cfg)
    print(f"Default thinking effort: {picked}")
    return 0


# --- Phase 2 sections: skills, ui, memory -----------------------------------

def run_skills_section() -> int:
    """Pick which skills (SKILL.md entries) are enabled."""
    try:
        from openprogram.agentic_programming import (
            default_skill_dirs, load_skills,
        )
        skills = load_skills(default_skill_dirs())
    except Exception as e:
        print(f"Failed to scan skills: {e}")
        return 1
    if not skills:
        print("No skills discovered. Nothing to configure.")
        return 0

    cfg = _read_config()
    disabled = set(cfg.get("skills", {}).get("disabled", []) or [])
    names = sorted(s.name for s in skills)
    items = [(n, n not in disabled) for n in names]

    picked = _checkbox("Enable these skills:", items)
    if picked is None:
        print("Cancelled.")
        return 1
    new_disabled = sorted(set(names) - set(picked))
    cfg.setdefault("skills", {})["disabled"] = new_disabled
    _write_config(cfg)
    print(f"Enabled: {len(picked)} / {len(names)} skills")
    if new_disabled:
        print(f"Disabled: {', '.join(new_disabled)}")
    return 0


def run_ui_section() -> int:
    """Web UI preferences: port + auto-open browser."""
    cfg = _read_config()
    ui = cfg.get("ui", {}) or {}
    cur_port = str(ui.get("port") or 8765)
    cur_open = bool(ui.get("open_browser", True))

    port_raw = _text("Web UI port:", default=cur_port)
    if port_raw is None:
        print("Cancelled.")
        return 1
    try:
        port = int(port_raw)
    except ValueError:
        print(f"Invalid port: {port_raw!r}")
        return 1

    open_browser = _confirm("Open browser automatically on `openprogram web`?",
                            default=cur_open)
    cfg.setdefault("ui", {}).update({
        "port": port,
        "open_browser": open_browser,
    })
    _write_config(cfg)
    print(f"UI: port={port}, open_browser={open_browser}")
    return 0


def run_memory_section() -> int:
    """Memory backend for the ``memory`` tool.

    OpenProgram currently has one native backend: ``local`` (JSON files
    under ~/.agentic/memory). Leaving the option in so hermes-style
    plugin backends (mem0 / honcho / ...) can slot in later without
    re-architecting this section.
    """
    cfg = _read_config()
    cur = (cfg.get("memory", {}) or {}).get("backend") or "local"
    choices = ["local", "none"]
    picked = _choose_one("Memory backend:", choices, cur)
    if picked is None:
        print("Cancelled.")
        return 1
    cfg.setdefault("memory", {})["backend"] = picked
    _write_config(cfg)
    print(f"Memory backend: {picked}")
    if picked == "none":
        print("(The `memory` tool will no-op until a backend is selected.)")
    return 0


# --- Phase 3 sections: profile, tts, channels, backend ----------------------

def run_profile_section() -> int:
    """Named profile (active config slot).

    For now only records the active profile name. Routing per-profile
    config-path / state dirs is a follow-up — but storing the name
    lets external tooling (and future runtime) honour it.
    """
    cfg = _read_config()
    cur = cfg.get("profile", "default") or "default"
    name = _text("Active profile name:", default=cur)
    if not name:
        print("Cancelled.")
        return 1
    cfg["profile"] = name
    _write_config(cfg)
    print(f"Active profile: {name}")
    print("[info] Per-profile config isolation is not wired yet — only "
          "the active-profile name is persisted.")
    return 0


def run_tts_section() -> int:
    """Text-to-speech backend + credentials.

    Wizard writes config; runtime hookup (spoken replies) is a separate
    follow-up. Providers mirror hermes' common set.
    """
    cfg = _read_config()
    tts = cfg.get("tts", {}) or {}
    cur_prov = tts.get("provider") or "none"

    providers = [
        "none",
        "openai",          # OPENAI_API_KEY
        "elevenlabs",      # ELEVENLABS_API_KEY
        "edge-tts",        # no key, uses Microsoft Edge free tier
        "playht",          # PLAYHT_USER_ID + PLAYHT_API_KEY
    ]
    picked = _choose_one("TTS provider:", providers, cur_prov)
    if picked is None:
        print("Cancelled.")
        return 1

    entry: dict[str, Any] = {"provider": picked}
    if picked in ("openai", "elevenlabs", "playht"):
        env_map = {
            "openai": "OPENAI_API_KEY",
            "elevenlabs": "ELEVENLABS_API_KEY",
            "playht": "PLAYHT_API_KEY",
        }
        entry["api_key_env"] = env_map[picked]
        if not os.environ.get(entry["api_key_env"]):
            key = _password(f"{entry['api_key_env']} (leave blank to set later):")
            if key:
                cfg.setdefault("api_keys", {})[entry["api_key_env"]] = key
    cfg["tts"] = entry
    _write_config(cfg)
    print(f"TTS: {picked}")
    if picked != "none":
        print("[info] Runtime hookup for spoken replies is not wired yet; "
              "the choice is stored for when it lands.")
    return 0


def run_channels_section() -> int:
    """Chat-channel bot integrations (Telegram / Discord / Slack).

    Each platform has an 'enabled' flag + minimal credential slot. The
    actual gateway / bot loop is separate infrastructure work — this
    section just captures intent + credentials.
    """
    cfg = _read_config()
    ch = cfg.get("channels", {}) or {}

    # Platform → list of (env_var, label) pairs for token auth, or
    # special value "qr" for QR-scan login (WeChat).
    PLATFORMS: list[tuple[str, Any]] = [
        ("telegram", [("TELEGRAM_BOT_TOKEN", "Telegram bot token")]),
        ("discord",  [("DISCORD_BOT_TOKEN",  "Discord bot token")]),
        ("slack",    [("SLACK_BOT_TOKEN",    "Slack bot (xoxb-)"),
                      ("SLACK_APP_TOKEN",    "Slack app-level (xapp-, Socket Mode)")]),
        ("wechat",   "qr"),
    ]
    items = [
        (p[0], bool((ch.get(p[0]) or {}).get("enabled", False)))
        for p in PLATFORMS
    ]
    picked = _checkbox("Enable channels:", items)
    if picked is None:
        print("Cancelled.")
        return 1

    new_ch: dict[str, Any] = {}
    for pid, cfg_info in PLATFORMS:
        prev = ch.get(pid, {}) or {}
        enabled = pid in picked
        entry: dict[str, Any]
        if cfg_info == "qr":
            # WeChat: no env-var token. Credentials come from a QR scan
            # during `channels start`. We capture intent here + optionally
            # drive the login right now for a fully-configured install.
            entry = {"enabled": enabled, "auth": "qr"}
            if enabled:
                try:
                    from openprogram.channels.wechat import _find_saved_creds
                    already = _find_saved_creds() is not None
                except Exception:
                    already = False
                if already:
                    print("[wechat] already logged in — skipping QR scan.")
                elif _confirm("Scan WeChat QR now? (needs your phone)",
                              default=True):
                    from openprogram.channels.wechat import _qr_login
                    _qr_login()
                else:
                    print("[wechat] skipped. You'll be prompted on "
                          "`openprogram channels start`.")
            new_ch[pid] = entry
            continue

        envs: list[tuple[str, str]] = cfg_info  # type: ignore[assignment]
        first_env = envs[0][0]
        entry = {"enabled": enabled, "api_key_env": first_env}
        if pid == "slack":
            entry["app_token_env"] = envs[1][0]
        if enabled:
            for env_var, label in envs:
                have = (
                    prev.get("token")
                    or cfg.get("api_keys", {}).get(env_var)
                    or os.environ.get(env_var)
                )
                if not have:
                    tok = _password(f"{label} (${env_var}), "
                                    f"leave blank to set later:")
                    if tok:
                        cfg.setdefault("api_keys", {})[env_var] = tok
        new_ch[pid] = entry
    cfg["channels"] = new_ch
    _write_config(cfg)
    enabled_names = [p for p in picked]
    if enabled_names:
        print(f"Channels enabled: {', '.join(enabled_names)}")
    else:
        print("No channels enabled.")
    print("[info] Channel runtime (bot loops, gateway) is not wired yet; "
          "config is stored so future runtime can read it.")
    return 0


def run_backend_section() -> int:
    """Where shell-style tools (bash, execute_code, ...) actually run.

    Currently OpenProgram only has the 'local' in-process path. Wizard
    surfaces the full set so users can record intent; docker / ssh
    execution backends are separate runtime work.
    """
    cfg = _read_config()
    be = cfg.get("backend", {}) or {}
    cur_terminal = be.get("terminal") or "local"

    choices = ["local", "docker", "ssh"]
    picked = _choose_one("Terminal backend:", choices, cur_terminal)
    if picked is None:
        print("Cancelled.")
        return 1

    entry: dict[str, Any] = {"terminal": picked}
    if picked == "docker":
        image = _text("Container image:", default=be.get("docker_image", "ubuntu:24.04"))
        entry["docker_image"] = image or "ubuntu:24.04"
    elif picked == "ssh":
        host = _text("SSH host (user@host):", default=be.get("ssh_target", ""))
        entry["ssh_target"] = host or ""
    cfg["backend"] = entry
    _write_config(cfg)
    print(f"Terminal backend: {picked}")
    if picked != "local":
        print("[info] Only the 'local' backend is currently implemented at "
              "runtime. Your selection is stored for when other backends land.")
    return 0


# --- Orchestrator -----------------------------------------------------------

# Section spec:
#   (key, title, description, fn, default_run)
#   default_run = True  → auto-run (user can Ctrl+C to abort the section)
#   default_run = False → ask first, default No
_CORE_SECTIONS = [
    ("providers", "Connect LLM provider(s)",
     "Import existing CLI logins (Claude Code / Codex / Gemini / GH CLI), "
     "or add API keys. At least one provider is required.",
     run_providers_section, True),
    ("model", "Pick your default chat model",
     "Choose which enabled model starts every new conversation.",
     run_model_section, True),
    ("agent", "Default reasoning effort",
     "How hard should the model think by default? "
     "low = fastest, xhigh = deepest.",
     run_agent_section, True),
    ("tools", "Enable / disable tools",
     f"Which of the built-in tools should the agent have access to.",
     run_tools_section, False),
    ("skills", "Enable / disable skills",
     "SKILL.md instruction packs the agent can load on demand.",
     run_skills_section, False),
    ("ui", "Web UI preferences",
     "Port and auto-open-browser for `openprogram web`.",
     run_ui_section, False),
    ("tts", "Text-to-speech (optional)",
     "Spoken replies in CLI chat. Providers: openai / elevenlabs / "
     "edge-tts (free).",
     run_tts_section, False),
    ("channels", "Chat-channel bots (optional)",
     "Route messages from Telegram / Discord / Slack / WeChat through "
     "your chat agent.",
     run_channels_section, False),
    ("memory", "Memory backend (optional)",
     "Pick between the local JSON store and 'none' (disables the "
     "memory tool).",
     run_memory_section, False),
]

_EXTRA_SECTIONS = [
    ("profile", "Named profile (advanced)",
     "Stored profile name. Per-profile state-dir isolation is done via "
     "`--profile <name>` at launch.",
     run_profile_section, True),
    ("backend", "Terminal exec backend (advanced)",
     "Where the `bash` / `execute_code` / `process` tools actually "
     "run: local / ssh / docker.",
     run_backend_section, True),
]


def _section_header(idx: int, total: int, title: str, desc: str) -> None:
    """Rich-aware section header; falls back to plain text."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text
        console = Console()
        console.print()
        header = Text(f"Step {idx}/{total}  ", style="bold bright_blue")
        header.append(title, style="bold")
        body = Text(desc, style="dim")
        console.print(Panel(body, title=header, border_style="bright_blue",
                            padding=(0, 1)))
    except ImportError:
        print()
        print(f"--- Step {idx}/{total}: {title} ---")
        print(f"    {desc}")


def _run_section(name: str, fn, ask_default: bool) -> int:
    """Run a section body. ``ask_default`` controls the 'Configure X now?'
    prompt default: True = default-yes, False = default-no.
    """
    if ask_default:
        if not _confirm(f"Configure {name} now?", default=True):
            print(f"Skipped {name}.")
            return 0
    else:
        if not _confirm(f"Configure {name} now?", default=False):
            print(f"Skipped {name}.")
            return 0
    return fn()


def _print_intro() -> None:
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text
        console = Console()
        body = Text()
        body.append("Welcome to OpenProgram.\n\n", style="bold bright_blue")
        body.append(
            "Setup has three parts:\n"
            "  Required — provider + default model + reasoning effort\n"
            "  Tailored — tools / skills / UI / TTS / channels / memory\n"
            "  Advanced — profiles, terminal exec backend\n\n",
            style="dim",
        )
        body.append(
            "Each step is rerunnable with `openprogram config <name>`. "
            "Ctrl+C to exit at any point — partial progress is saved.",
            style="dim italic",
        )
        console.print()
        console.print(Panel(body, title=Text("OpenProgram setup",
                                             style="bold bright_blue"),
                            border_style="bright_blue", padding=(1, 2)))
    except ImportError:
        print()
        print("=" * 60)
        print("  OpenProgram setup")
        print("=" * 60)
        print("Required: provider + default model + reasoning effort.")
        print("Tailored: tools / skills / UI / TTS / channels / memory.")
        print("Advanced: profiles, terminal exec backend.")
        print("Rerun any step with `openprogram config <name>`.")
        print()


def _print_summary() -> None:
    """Recap the stored config at the end of the wizard."""
    cfg = _read_config()
    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        tbl = Table.grid(padding=(0, 2))
        tbl.add_column(style="bold")
        tbl.add_column()
        tbl.add_row("default model:",
                    f"{cfg.get('default_provider', '?')}/{cfg.get('default_model', '?')}")
        tbl.add_row("thinking effort:",
                    str((cfg.get("agent", {}) or {}).get("thinking_effort", "medium")))
        tools_disabled = (cfg.get("tools", {}) or {}).get("disabled", []) or []
        tbl.add_row("disabled tools:",
                    ", ".join(tools_disabled) if tools_disabled else "(none)")
        channels = cfg.get("channels", {}) or {}
        enabled_ch = [k for k, v in channels.items() if isinstance(v, dict) and v.get("enabled")]
        tbl.add_row("channels:",
                    ", ".join(enabled_ch) if enabled_ch else "(none)")
        tts = (cfg.get("tts") or {}).get("provider") or "none"
        tbl.add_row("tts:", tts)
        profile = cfg.get("profile", "default")
        tbl.add_row("profile:", profile)
        console.print()
        console.print("[bold green]Setup complete.[/]")
        console.print(tbl)
    except ImportError:
        print("\nSetup complete.")
        print(f"  default model:    {cfg.get('default_provider')}/{cfg.get('default_model')}")
        print(f"  thinking effort:  {(cfg.get('agent') or {}).get('thinking_effort', 'medium')}")


def run_full_setup() -> int:
    """Polished multi-step first-run wizard.

    Required sections default-yes; tailored/advanced sections default-no so
    users can breeze through the minimal install. End-of-wizard shows a
    config summary and offers to drop straight into CLI chat.
    """
    _print_intro()
    if not _confirm("Start?", default=True):
        return 0

    total = len(_CORE_SECTIONS)
    for i, (name, title, desc, fn, default_run) in enumerate(_CORE_SECTIONS, 1):
        _section_header(i, total, title, desc)
        if default_run:
            rc = fn()
        else:
            rc = _run_section(name, fn, ask_default=False)
        if rc != 0:
            print(f"[warn] {name} exited with status {rc}; continuing.")

    print()
    if _confirm(
        "Configure advanced sections (profile / backend)?",
        default=False,
    ):
        extra_total = len(_EXTRA_SECTIONS)
        for i, (name, title, desc, fn, default_run) in enumerate(_EXTRA_SECTIONS, 1):
            _section_header(i, extra_total, title, desc)
            rc = _run_section(name, fn, ask_default=default_run)
            if rc != 0:
                print(f"[warn] {name} exited with status {rc}; continuing.")

    _print_summary()

    # Hand off straight to chat so "first install → first message" is one
    # continuous flow, not two commands with a manual restart between.
    if _confirm("Start chatting now?", default=True):
        try:
            from openprogram.cli_chat import run_cli_chat
            run_cli_chat()
        except Exception as e:  # noqa: BLE001
            print(f"[setup] couldn't launch chat: {type(e).__name__}: {e}")
            print("Run `openprogram` manually.")
    else:
        print("\nRun `openprogram` when ready.")
    return 0
