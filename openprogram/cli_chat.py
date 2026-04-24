"""Terminal chat for ``openprogram`` / ``openprogram --cli``.

Hermes-style welcome banner (tools + skills inventory) followed by a
REPL. The REPL is deliberately thin: each turn goes through the same
chat runtime the web UI uses, so behaviour stays aligned. Slash
commands (``/help``, ``/web``, ``/quit``, ...) are handled locally.

Multi-turn memory depends on the underlying runtime. The Claude Code
runtime keeps a persistent subprocess session so successive
``exec()`` calls share context; HTTP runtimes are stateless here —
left for a follow-up when we plumb conversation history through.
"""
from __future__ import annotations

import sys
from typing import Any


def _get_chat_runtime():
    """Return (provider_name, runtime) for the configured chat agent."""
    from openprogram.webui import _runtime_management as rm
    rm._init_providers()
    if rm._chat_runtime is None:
        return None, None
    return rm._chat_provider, rm._chat_runtime


def _tool_inventory() -> tuple[int, list[str]]:
    from openprogram.tools import ALL_TOOLS, list_available
    names = list_available()  # only tools whose check_fn currently passes
    # Prefer the gated list; if the helper returns empty (no gating), fall
    # back to the full registry so the banner isn't misleadingly blank.
    if not names:
        names = list(ALL_TOOLS.keys())
    return len(names), names


def _skill_inventory() -> tuple[int, list[tuple[str, str]]]:
    """Return (count, [(name, description), ...]) for discovered skills."""
    try:
        from openprogram.agentic_programming import (
            default_skill_dirs, load_skills,
        )
        skills = load_skills(default_skill_dirs())
    except Exception:
        return 0, []
    return len(skills), [(s.name, getattr(s, "description", "") or "") for s in skills]


def _print_banner(console, provider: str, model: str) -> None:
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box

    tool_count, tool_names = _tool_inventory()
    skill_count, skill_items = _skill_inventory()

    logo = Text("OpenProgram", style="bold bright_blue")
    subtitle = Text(f"  ·  {provider}/{model}", style="dim")
    header = logo + subtitle

    body = Table.grid(padding=(0, 2), expand=True)
    body.add_column(ratio=1)
    body.add_column(ratio=1)

    tools_txt = Text()
    tools_txt.append("Tools ", style="bold")
    tools_txt.append(f"({tool_count})\n", style="dim")
    preview = tool_names[:8]
    tools_txt.append(", ".join(preview), style="cyan")
    if tool_count > len(preview):
        tools_txt.append(f" (+{tool_count - len(preview)} more)", style="dim")

    skills_txt = Text()
    skills_txt.append("Skills ", style="bold")
    skills_txt.append(f"({skill_count})\n", style="dim")
    if skill_count == 0:
        skills_txt.append("no skills loaded", style="dim italic")
    else:
        preview = [n for n, _ in skill_items[:8]]
        skills_txt.append(", ".join(preview), style="magenta")
        if skill_count > len(preview):
            skills_txt.append(f" (+{skill_count - len(preview)} more)", style="dim")

    body.add_row(tools_txt, skills_txt)

    footer = Text()
    footer.append(f"{tool_count} tools", style="cyan")
    footer.append(" · ")
    footer.append(f"{skill_count} skills", style="magenta")
    footer.append(" · /help for commands", style="dim")

    panel_body = Table.grid(padding=(1, 0))
    panel_body.add_row(body)
    panel_body.add_row(footer)

    console.print()
    console.print(Panel(
        panel_body,
        title=header,
        border_style="bright_blue",
        box=box.ROUNDED,
        padding=(1, 2),
    ))
    console.print(
        Text("Tip: ", style="yellow bold")
        + Text("type your message, or /help to see commands.", style="dim")
    )


# --- Slash commands --------------------------------------------------------

SLASH_HELP = [
    ("/help", "show this message"),
    ("/web [port]", "launch the Web UI in your browser"),
    ("/model", "show current chat model"),
    ("/tools", "list available tools"),
    ("/skills", "list discovered skills"),
    ("/clear", "clear the screen"),
    ("/quit", "exit"),
]


def _handle_slash(cmd: str, console, rt) -> bool:
    """Handle a /slash command. Return True if the session should exit."""
    raw = cmd[1:].strip()
    parts = raw.split()
    verb = (parts[0] if parts else "").lower()
    args = parts[1:]

    if verb in ("q", "quit", "exit"):
        console.print("[dim]Goodbye.[/]")
        return True

    if verb in ("", "h", "help", "?"):
        from rich.table import Table
        tbl = Table(show_header=False, box=None, padding=(0, 2))
        tbl.add_column(style="bold cyan")
        tbl.add_column(style="dim")
        for name, desc in SLASH_HELP:
            tbl.add_row(name, desc)
        console.print(tbl)
        return False

    if verb == "web":
        port = 8765
        if args:
            try:
                port = int(args[0])
            except ValueError:
                console.print(f"[yellow]Invalid port: {args[0]!r}[/]")
                return False
        console.print(f"[dim]Starting Web UI at http://localhost:{port} ...[/]")
        from openprogram.cli import _cmd_web  # lazy to avoid cycle
        _cmd_web(port, True)
        return True

    if verb == "model":
        console.print(f"[bold]{getattr(rt, 'model', '?')}[/]")
        return False

    if verb == "tools":
        count, names = _tool_inventory()
        console.print(f"[bold]{count} tools[/]")
        for n in names:
            console.print(f"  [cyan]{n}[/]")
        return False

    if verb == "skills":
        count, items = _skill_inventory()
        console.print(f"[bold]{count} skills[/]")
        for name, desc in items:
            short = (desc[:80] + "...") if len(desc) > 80 else desc
            console.print(f"  [magenta]{name}[/]  [dim]{short}[/]")
        return False

    if verb == "clear":
        console.clear()
        return False

    console.print(f"[yellow]Unknown command: /{verb}[/]  (try /help)")
    return False


# --- Chat turn -------------------------------------------------------------

def _run_turn(rt, message: str) -> str:
    """Send one user message to the runtime; return the assistant reply."""
    try:
        reply = rt.exec(content=[{"type": "text", "text": message}])
    except Exception as e:  # noqa: BLE001
        return f"[error] {type(e).__name__}: {e}"
    if reply is None:
        return ""
    if isinstance(reply, str):
        return reply
    return str(reply)


# --- Entry point -----------------------------------------------------------

def run_cli_chat(oneshot: str | None = None) -> None:
    """Launch the terminal chat. ``oneshot`` runs one turn and exits."""
    from rich.console import Console
    console = Console()

    provider, rt = _get_chat_runtime()
    if rt is None:
        console.print(
            "[red]No LLM provider configured.[/]\n"
            "Run: [cyan]openprogram providers setup[/]"
        )
        sys.exit(1)
    model = getattr(rt, "model", "?")

    if oneshot:
        reply = _run_turn(rt, oneshot)
        print(reply)
        return

    _print_banner(console, provider, model)

    while True:
        try:
            user_input = console.input("\n[bold bright_blue]❯[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            return
        if not user_input:
            continue
        if user_input.startswith("/"):
            if _handle_slash(user_input, console, rt):
                return
            continue
        reply = _run_turn(rt, user_input)
        console.print()
        console.print(reply)
