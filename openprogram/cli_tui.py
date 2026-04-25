"""Full-screen terminal chat (Textual).

Layout

    ┌─ agent: main  ▾    model: openai-codex/gpt-5.5-mini    session: local_ab… ─┐
    ├──────────────┬───────────────────────────────────────────────────────────┤
    │ ▶ Sessions   │  ┌─ you ────────────────────────────────────────────────┐ │
    │ ▾ main       │  │ hello                                                │ │
    │   📱 alice   │  └──────────────────────────────────────────────────────┘ │
    │   • local…   │                                                           │
    │              │  ┌─ main ───────────────────────────────────────────────┐ │
    │ ▾ work       │  │ Hi! How can I help?                                  │ │
    │   …          │  └──────────────────────────────────────────────────────┘ │
    ├──────────────┴───────────────────────────────────────────────────────────┤
    │ ❯ /login wechat                                            [thinking ⠦] │
    └──────────────────────────────────────────────────────────────────────────┘

Key bindings (also visible in the Footer):
    Tab         move focus between sidebar and input
    Ctrl+N      new session in the active agent
    Ctrl+A      switch agent (cycles through agents)
    Ctrl+B      toggle the sidebar
    Ctrl+L      clear scroll (disk history unchanged)
    Ctrl+Q      quit
    Up/Down     in input: scroll command history; in sidebar: pick session

Slash commands:
    Type ``/`` to bring up a command palette right above the input.
    Up/Down to highlight a candidate, Enter to accept (the rest of the
    command line is keepable). Same handler as the Rich REPL.

Cross-platform notes:
    Textual uses standard ANSI control sequences. Tested on macOS
    Terminal / iTerm2; works on every modern Linux terminal (GNOME
    Terminal, Konsole, Alacritty, kitty, tmux+st, ...) and Windows
    Terminal / WSL without changes. ``--no-tui`` opts back into the
    Rich REPL on the rare terminal without alt-screen support.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import (
    Footer, Input, Label, ListItem, ListView, LoadingIndicator,
    Markdown, Static,
)


_SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help",        "show every slash command"),
    ("/session",     "show current session id + agent"),
    ("/new",         "start a new session under the current agent"),
    ("/agent",       "switch agent (or list agents with no arg)"),
    ("/model",       "switch chat model (or list with no arg)"),
    ("/login",       "log in to a channel (wechat: QR; others: token)"),
    ("/attach",      "route a channel peer into THIS session"),
    ("/detach",      "remove a channel peer alias"),
    ("/connections", "list channel peers wired to this session"),
    ("/copy",        "copy the last assistant reply to clipboard"),
    ("/web",         "open the Web UI"),
    ("/tools",       "list tools"),
    ("/skills",      "list skills"),
    ("/functions",   "list agentic functions"),
    ("/apps",        "list applications"),
    ("/clear",       "clear the scroll (disk history kept)"),
    ("/profile",     "show or switch the active profile"),
    ("/quit",        "exit"),
]

_PLATFORM_ICON = {
    "wechat":   "💬",
    "telegram": "✈",
    "discord":  "🎮",
    "slack":    "💼",
}


class _StatusBar(Static):
    """One-line status: agent · model · session · channels worker."""

    agent_id = reactive("")
    model = reactive("")
    session_id = reactive("")
    worker_state = reactive("")

    def render(self) -> str:
        sess = self.session_id[:14] if self.session_id else "—"
        worker = (f"  [bold bright_blue]channels[/]: {self.worker_state}"
                  if self.worker_state else "")
        return (f"[bold bright_blue]agent[/]: {self.agent_id or '—'}    "
                f"[bold bright_blue]model[/]: {self.model or '—'}    "
                f"[bold bright_blue]session[/]: {sess}{worker}")


class _ChatScroll(VerticalScroll):
    """Main scrollback. Each turn is a Markdown widget."""
    DEFAULT_CSS = """
    _ChatScroll { padding: 1 2; }
    _ChatScroll Markdown.user {
        background: $boost 8%;
        border-left: tall $accent;
        padding: 1 2;
        margin: 0 0 1 0;
    }
    _ChatScroll Markdown.assistant {
        padding: 1 2;
        margin: 0 0 1 0;
    }
    _ChatScroll Markdown.system {
        color: $text-muted;
        padding: 0 2;
        margin: 0 0 1 0;
    }
    _ChatScroll Markdown.error {
        background: $error 12%;
        border-left: tall $error;
        color: $error;
        padding: 1 2;
        margin: 0 0 1 0;
    }
    _ChatScroll Markdown.thinking {
        color: $text-muted;
        padding: 0 2 1 2;
        margin: 0 0 1 0;
    }
    """


class _Sidebar(Vertical):
    """Sessions grouped by agent. Header row per agent acts as the
    active-agent toggle when clicked."""
    DEFAULT_CSS = """
    #sidebar {
        width: 32;
        border-right: tall $accent 30%;
    }
    #sidebar ListView { height: 1fr; }
    /* Same one-row-per-item rule as the palette — without it
       ListItem.Horizontal expands to fill and only one row shows. */
    #sidebar ListItem { height: 1; padding: 0 1; }
    #sidebar ListItem.agent_header { color: $accent; }
    #sidebar ListItem.agent_header.active {
        background: $accent 15%;
    }
    #sidebar ListItem.session { padding-left: 2; }
    #sidebar ListItem.session.active {
        background: $accent 25%;
        text-style: bold;
    }
    #sidebar ListItem.action_row {
        color: $warning;
    }
    #sidebar ListItem.separator_row {
        color: $text-muted;
    }
    """


class _SlashPalette(ListView):
    """Floating-ish palette that appears above the input when the
    user starts a slash command. Filters by prefix as they type.

    NOTE: the CSS uses the ``#slash_palette`` id selector instead of
    the class name. Textual's parser doesn't reliably match component
    classes whose names start with an underscore (``_SlashPalette``);
    sticking to id avoids that footgun and makes max-height land.
    """
    DEFAULT_CSS = """
    #slash_palette {
        height: 14;
        min-height: 4;
        border: tall $accent 30%;
        background: $surface;
    }
    /* ListItem must be height 1 — without it, the Horizontal child
       expands to fill, each row eats the whole palette and only one
       command shows. */
    #slash_palette ListItem { height: 1; padding: 0 1; }
    #slash_palette ListItem Horizontal { height: 1; }
    #slash_palette ListItem Label.cmd { color: $accent; width: 24; }
    #slash_palette ListItem Label.desc { color: $text-muted; padding-left: 1; }
    """


class OpenProgramTUI(App):
    """Full-screen chat client."""

    CSS = """
    Screen { layout: vertical; }
    #brand { height: 1; padding: 0 2; color: $accent; text-style: bold; }
    #statusbar { height: 1; background: $boost 12%; padding: 0 2; }
    #main { height: 1fr; }
    #input_box { height: 3; border: round $accent 30%; }
    Input { padding: 0 1; }
    #thinking { height: auto; padding: 0 2; color: $text-muted; }
    #thinking_row { height: auto; padding: 0 2; }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit_chat", "Quit", priority=True),
        Binding("ctrl+n", "new_session", "New session"),
        Binding("ctrl+a", "next_agent", "Next agent"),
        Binding("ctrl+m", "pick_model", "Switch model"),
        Binding("ctrl+y", "copy_last", "Copy reply"),
        Binding("ctrl+b", "toggle_sidebar", "Toggle sidebar"),
        Binding("ctrl+l", "clear_scroll", "Clear"),
        Binding("tab", "switch_focus", "Switch focus"),
        Binding("escape", "close_palette", show=False),
    ]

    show_palette = reactive(False)
    busy = reactive(False)

    def __init__(self, agent, conv_id: str, rt) -> None:
        super().__init__()
        self.agent = agent
        self.conv_id = conv_id
        self.rt = rt
        self._chat: Optional[_ChatScroll] = None
        self._status: Optional[_StatusBar] = None
        self._sidebar: Optional[_Sidebar] = None
        self._sidebar_list: Optional[ListView] = None
        self._input: Optional[Input] = None
        self._palette: Optional[_SlashPalette] = None
        self._thinking_row: Optional[Static] = None
        self._thinking_indicator: Optional[LoadingIndicator] = None
        self._sidebar_index: list[dict] = []  # parsed entries for nav
        self._input_history: list[str] = []
        self._history_idx = 0
        # When non-None the slash palette is in modal picker mode and
        # input typing should NOT re-filter it.
        self._picker_callback = None

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static("  OpenProgram", id="brand")
        self._status = _StatusBar(id="statusbar")
        yield self._status

        self._chat = _ChatScroll(id="chat_scroll")
        self._sidebar_list = ListView(id="session_list")
        self._sidebar = _Sidebar(
            self._sidebar_list,
            id="sidebar",
        )
        with Horizontal(id="main"):
            yield self._sidebar
            yield self._chat

        # Slash palette (initially hidden) sits between scroll and input.
        self._palette = _SlashPalette(id="slash_palette")
        self._palette.display = False
        yield self._palette

        # Thinking row (between chat and input) — text + spinner.
        self._thinking_indicator = LoadingIndicator()
        self._thinking_indicator.display = False
        thinking_text = Static("", id="thinking")
        thinking_text.display = False
        with Horizontal(id="thinking_row"):
            yield self._thinking_indicator
            yield thinking_text

        self._input = Input(placeholder="Type a message  ·  / for commands",
                             id="input_box")
        yield self._input
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_status()
        self._load_history_into_scroll()
        self._refresh_sidebar()
        self.set_focus(self._input)

    # ------------------------------------------------------------------
    # Actions (key bindings)
    # ------------------------------------------------------------------

    async def action_quit_chat(self) -> None:
        self.exit()

    async def action_new_session(self) -> None:
        self.conv_id = "local_" + uuid.uuid4().hex[:10]
        self._chat.remove_children()
        self._append_system(
            f"New session `{self.conv_id}` under agent `{self.agent.id}`."
        )
        self._refresh_status()
        self._refresh_sidebar()

    async def action_next_agent(self) -> None:
        from openprogram.agents import manager as _A
        agents = _A.list_all()
        if len(agents) <= 1:
            self._append_system(
                "Only one agent. Add more with `openprogram agents add <id>`."
            )
            return
        ids = [a.id for a in agents]
        try:
            idx = ids.index(self.agent.id)
        except ValueError:
            idx = -1
        next_id = ids[(idx + 1) % len(ids)]
        if next_id == self.agent.id:
            return
        self._switch_agent_threaded(next_id, None)

    async def action_toggle_sidebar(self) -> None:
        self._sidebar.display = not self._sidebar.display

    async def action_clear_scroll(self) -> None:
        self._chat.remove_children()
        self._append_system("(view cleared — history on disk is intact)")

    async def action_switch_focus(self) -> None:
        if self.focused is self._input:
            self.set_focus(self._sidebar_list)
        else:
            self.set_focus(self._input)

    async def action_close_palette(self) -> None:
        if self.show_palette:
            self.show_palette = False

    async def action_pick_model(self) -> None:
        self._action_pick_model()

    async def action_copy_last(self) -> None:
        self._action_copy_last()

    # Sidebar action-row callbacks. Names match the strings in
    # _refresh_sidebar's action tuples; ListView routes a click on
    # the row to the corresponding bound method.

    def _action_new_session(self) -> None:
        self.run_worker(self.action_new_session(), exclusive=True)

    def _action_pick_model(self) -> None:
        """Open a slash-palette-style model picker. Each row is one
        enabled model from the registry; selecting it switches the
        active agent's model."""
        try:
            from openprogram.webui import _model_catalog as mc
            enabled = mc.list_enabled_models()
        except Exception as e:  # noqa: BLE001
            self._append_error(f"model list failed: {e}")
            return
        if not enabled:
            self._append_system(
                "No enabled models. Run `openprogram providers setup` "
                "first to import a credential."
            )
            return
        self._open_picker(
            title="Pick a model",
            options=[
                (f"{m['provider']}/{m['id']}",
                 m.get("name") or m["id"])
                for m in enabled
            ],
            on_select=self._set_model,
        )

    def _set_model(self, full_id: str) -> None:
        from openprogram.agents import manager as _A
        from openprogram.agents import runtime_registry as _R
        provider, _, model_id = full_id.partition("/")
        if not provider or not model_id:
            self._append_error(f"unparseable model id: {full_id!r}")
            return
        _A.update(self.agent.id,
                  {"model": {"provider": provider, "id": model_id}})
        _R.invalidate(self.agent.id)
        # Re-pull the spec so reactives see the new model.
        self.agent = _A.get(self.agent.id) or self.agent
        # Also drop our local rt so the next turn rebuilds.
        self.rt = None
        self._append_system(
            f"Switched model to **{provider}/{model_id}**."
        )
        self._refresh_status()
        self._refresh_sidebar()

    def _open_picker(self, *, title: str,
                     options: list[tuple[str, str]],
                     on_select) -> None:
        """Show a modal picker with two-column rows (id, description).

        ``options`` = ``[(value, label), ...]``. Up/Down to highlight,
        Enter to confirm, Esc to cancel. The selected value is fed
        into ``on_select``.

        Implementation note: we reuse the slash palette widget so the
        user gets the same look and feel as / commands. While the
        picker is up, the input doesn't drive palette filtering — we
        use a transient mode flag.
        """
        if not options:
            self._append_system(f"Nothing to pick for: {title}")
            return
        self._palette.clear()
        for value, label in options:
            self._palette.append(
                self._make_palette_row(value, label, picker=True),
            )
        self._picker_callback = on_select
        self.show_palette = True
        self.set_focus(self._palette)
        self._append_system(f"**{title}** — Up/Down + Enter, Esc to cancel.")

    def _action_show_add_agent_hint(self) -> None:
        self._append_system(
            "Add a new agent from your shell:\n\n"
            "  `openprogram agents add <id> --provider <name> "
            "--model <id>`\n\n"
            "Then come back here and use Ctrl+A or `/agent <id>` to "
            "switch into it."
        )

    def _action_copy_last(self) -> None:
        """Copy the last assistant message to the system clipboard
        via Textual's built-in OSC-52 path. Works in iTerm2, kitty,
        WezTerm, recent VS Code terminals, GNOME Terminal 3.50+,
        Windows Terminal, tmux with set-clipboard on."""
        try:
            from openprogram.webui import persistence as _persist
            data = _persist.load_conversation(self.agent.id, self.conv_id)
        except Exception:
            data = None
        if not data:
            self._append_system("No messages yet to copy.")
            return
        last = next(
            (m for m in reversed(data.get("messages") or [])
             if m.get("role") == "assistant"),
            None,
        )
        if last is None:
            self._append_system("No assistant reply to copy yet.")
            return
        text = last.get("content") or ""
        try:
            self.copy_to_clipboard(text)
            self._append_system(f"Copied {len(text)} chars to clipboard.")
        except Exception as e:  # noqa: BLE001
            self._append_error(f"copy failed: {e}")

    # ------------------------------------------------------------------
    # Input + slash palette
    # ------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        # Don't fight the picker — once a modal picker (model / agent
        # / etc.) is showing, ignore user keystrokes in the input.
        if self._picker_callback is not None:
            return
        v = event.value or ""
        if v.startswith("/"):
            self._update_palette(v)
        else:
            if self.show_palette:
                self.show_palette = False

    def watch_show_palette(self, value: bool) -> None:
        if self._palette is not None:
            self._palette.display = value

    def _update_palette(self, text: str) -> None:
        """Two-tier filter:

          * empty query → list every command
          * otherwise → first try prefix on the command name (so
            typing ``/m`` shows ``/model`` first); if no prefix
            matches, fall back to substring across cmd + description
            (so typing ``/wec`` finds ``/login`` because the desc
            mentions wechat).

        Always shows SOME results when a query is non-empty so the
        user gets feedback instead of an empty popup.
        """
        query = text.lstrip("/").strip().lower()
        if not query:
            candidates = list(_SLASH_COMMANDS)
        else:
            prefix_hits = [
                (cmd, desc) for cmd, desc in _SLASH_COMMANDS
                if cmd[1:].lower().startswith(query)
            ]
            if prefix_hits:
                candidates = prefix_hits
            else:
                candidates = [
                    (cmd, desc) for cmd, desc in _SLASH_COMMANDS
                    if query in cmd.lower() or query in desc.lower()
                ]
        self._palette.clear()
        for cmd, desc in candidates:
            self._palette.append(self._make_palette_row(cmd, desc))
        self.show_palette = bool(candidates)

    def _make_palette_row(self, cmd: str, desc: str,
                          picker: bool = False) -> ListItem:
        """Build a one-line palette row. We force height: 1 inline
        because Textual's ListView CSS otherwise lets the inner
        Horizontal stretch and crowd the rest of the rows out."""
        cmd_lbl = Label(cmd, classes="cmd")
        desc_lbl = Label(desc, classes="desc")
        body = Horizontal(cmd_lbl, desc_lbl)
        body.styles.height = 1
        cmd_lbl.styles.width = 24
        cmd_lbl.styles.height = 1
        desc_lbl.styles.height = 1
        row = ListItem(body)
        row.styles.height = 1
        row.data_cmd = cmd  # type: ignore[attr-defined]
        if picker:
            row.data_picker = True  # type: ignore[attr-defined]
        return row

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = (event.value or "").strip()
        if not text:
            return
        self._input_history.append(text)
        self._history_idx = len(self._input_history)
        self._input.value = ""
        self.show_palette = False
        if text.startswith("/"):
            self._run_slash(text)
            return
        if self.busy:
            self._append_system(
                "[busy — wait for the current turn to finish]"
            )
            return
        self._append_user(text)
        self._set_busy(True)
        self._run_turn(text)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Either palette pick or sidebar entry pick.

        Important: ListView fires Selected when the list is rebuilt
        (the previously-active row is auto-selected). We have to
        ignore "selecting the agent / session you're already on" or
        every refresh causes a runtime rebuild + agent switch loop.
        """
        if event.list_view is self._palette:
            cmd = getattr(event.item, "data_cmd", None)
            picker = getattr(event.item, "data_picker", False)
            if not cmd:
                return
            if picker:
                cb = getattr(self, "_picker_callback", None)
                self.show_palette = False
                self._picker_callback = None
                self.set_focus(self._input)
                if cb:
                    cb(cmd)
            else:
                self._input.value = cmd + " "
                self._input.cursor_position = len(self._input.value)
                self.set_focus(self._input)
                self.show_palette = False
            return

        sb_data = getattr(event.item, "data", None)
        if not sb_data:
            return
        if sb_data["kind"] == "separator":
            return
        if sb_data["kind"] == "action":
            cb = sb_data.get("callback")
            handler = getattr(self, cb, None) if cb else None
            if handler:
                handler()
            return
        if sb_data["kind"] == "agent":
            target = sb_data["agent_id"]
            if target == self.agent.id:
                return
            self._switch_agent_threaded(target, None)
        elif sb_data["kind"] == "session":
            cid = sb_data["conv_id"]
            agent_id = sb_data["agent_id"]
            if agent_id == self.agent.id and cid == self.conv_id:
                return
            if agent_id != self.agent.id:
                self._switch_agent_threaded(agent_id, cid)
            else:
                self.conv_id = cid
                self._chat.remove_children()
                self._load_history_into_scroll()
                self._refresh_status()
                self._refresh_sidebar()

    # ------------------------------------------------------------------
    # Turn execution (off the event loop)
    # ------------------------------------------------------------------

    @work(exclusive=True, thread=True)
    def _run_turn(self, user_text: str) -> None:
        try:
            from openprogram.cli_chat import _run_turn_with_history
            reply = _run_turn_with_history(
                self.agent, self.conv_id, user_text,
            )
            error = False
        except Exception as e:  # noqa: BLE001
            reply = f"{type(e).__name__}: {e}"
            error = True
        self.call_from_thread(self._render_reply, reply, error)

    def _render_reply(self, reply: str, error: bool) -> None:
        if error:
            self._append_error(reply)
        else:
            self._append_assistant(reply)
        self._set_busy(False)
        self._refresh_sidebar()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        if self._thinking_indicator is None:
            return
        self._thinking_indicator.display = busy
        thinking_text = self.query_one("#thinking", Static)
        thinking_text.display = busy
        if busy:
            thinking_text.update(
                f"[dim]{self.agent.id} is thinking…[/]"
            )

    # ------------------------------------------------------------------
    # Slash commands — reuse cli_chat._handle_slash; capture output
    # ------------------------------------------------------------------

    def _run_slash(self, raw: str) -> None:
        from rich.console import Console as _Console
        from io import StringIO
        buf = StringIO()
        captured = _Console(file=buf, force_terminal=False, width=100)
        from openprogram.cli_chat import _handle_slash
        try:
            should_quit = _handle_slash(
                raw, captured, self.rt,
                agent=self.agent, conv_id=self.conv_id,
            )
        except Exception as e:  # noqa: BLE001
            should_quit = False
            self._append_error(f"slash error: {type(e).__name__}: {e}")
            return
        output = buf.getvalue().strip()
        if output:
            self._append_system(output)
        if should_quit:
            self.exit()
        # Slash commands can mutate state we display; refresh.
        self._refresh_status()
        self._refresh_sidebar()

    # ------------------------------------------------------------------
    # Agent switching
    # ------------------------------------------------------------------

    @work(exclusive=True, thread=True, group="switch")
    def _switch_agent_threaded(self, agent_id: str,
                               then_conv_id: Optional[str]) -> None:
        """Build the new runtime in a worker thread (so any auth
        refresh can spin its own loop), then bounce back to the UI
        thread to apply the change."""
        from openprogram.agents import manager as _A
        from openprogram.agents import runtime_registry as _R
        spec = _A.get(agent_id)
        if spec is None:
            self.call_from_thread(self._append_error,
                                  f"no agent {agent_id!r}")
            return
        try:
            rt = _R.get_runtime_for(spec)
        except Exception as e:  # noqa: BLE001
            self.call_from_thread(
                self._append_error, f"runtime build failed: {e}",
            )
            return
        self.call_from_thread(self._apply_switch, spec, rt, then_conv_id)

    def _apply_switch(self, spec, rt, then_conv_id: Optional[str]) -> None:
        self.agent = spec
        self.rt = rt
        self.conv_id = then_conv_id or ("local_" + uuid.uuid4().hex[:10])
        self._chat.remove_children()
        self._load_history_into_scroll()
        self._append_system(
            f"Switched to agent `{spec.id}` "
            f"(model={spec.model.provider}/{spec.model.id or '?'})."
        )
        self._refresh_status()
        self._refresh_sidebar()

    # ------------------------------------------------------------------
    # Scroll helpers
    # ------------------------------------------------------------------

    def _append_user(self, text: str) -> None:
        w = Markdown(f"**you**\n\n{text}", classes="user")
        self._chat.mount(w)
        self._chat.scroll_end(animate=False)

    def _append_assistant(self, text: str) -> None:
        w = Markdown(f"**{self.agent.id}**\n\n{text}", classes="assistant")
        self._chat.mount(w)
        self._chat.scroll_end(animate=False)

    def _append_system(self, text: str) -> None:
        w = Markdown(f"`system`\n\n{text}", classes="system")
        self._chat.mount(w)
        self._chat.scroll_end(animate=False)

    def _append_error(self, text: str) -> None:
        w = Markdown(f"**error**\n\n{text}", classes="error")
        self._chat.mount(w)
        self._chat.scroll_end(animate=False)

    def _load_history_into_scroll(self) -> None:
        """Render this session's persisted history into the scroll
        on agent / session switch."""
        try:
            from openprogram.webui import persistence as _p
            data = _p.load_conversation(self.agent.id, self.conv_id)
        except Exception:
            data = None
        if not data:
            self._append_system(
                f"New session `{self.conv_id}` under agent `{self.agent.id}`. "
                f"Type to start or `/login wechat` to wire a channel in."
            )
            return
        msgs = data.get("messages") or []
        for m in msgs:
            role = m.get("role")
            content = (m.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                self._append_user(content)
            elif role == "assistant":
                self._append_assistant(content)

    def _refresh_status(self) -> None:
        if not self._status:
            return
        self._status.agent_id = self.agent.id if self.agent else ""
        model = ""
        if self.agent and self.agent.model.id:
            model = f"{self.agent.model.provider}/{self.agent.model.id}"
        elif self.rt is not None:
            model = getattr(self.rt, "model", "") or ""
        self._status.model = model
        self._status.session_id = self.conv_id or ""
        # Channels worker liveness — best-effort, no exception leaks.
        try:
            from openprogram.channels.worker import current_worker_pid
            pid = current_worker_pid()
            self._status.worker_state = (f"running (PID {pid})"
                                          if pid else "off")
        except Exception:
            self._status.worker_state = ""

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def _refresh_sidebar(self) -> None:
        """Group sessions by agent. Each agent gets a header row;
        sessions hang underneath. Active agent + active session get
        highlighted classes."""
        if self._sidebar_list is None:
            return
        self._sidebar_list.clear()
        self._sidebar_index = []
        try:
            from openprogram.agents import manager as _A
            from openprogram.agents.manager import sessions_dir
            agents = _A.list_all()
        except Exception:
            return

        # Top row: actionable shortcuts. Click → fires the same code
        # path as the matching slash command.
        for action in (
            ("+ New session", "_action_new_session", "action"),
            ("⌥ Switch model…", "_action_pick_model", "action"),
            ("+ Add agent (CLI)", "_action_show_add_agent_hint", "action"),
        ):
            label, callback, kind = action
            row = ListItem(Label(label, classes="action_row"),
                           classes="action_row")
            row.data = {"kind": kind, "callback": callback}
            self._sidebar_list.append(row)
            self._sidebar_index.append(row.data)

        # Spacer divider so actions don't blend into the agent list.
        sep = ListItem(Label("─ Agents ─", classes="agent_header"),
                       classes="separator_row")
        sep.data = {"kind": "separator"}
        self._sidebar_list.append(sep)
        self._sidebar_index.append(sep.data)

        for spec in agents:
            head_classes = "agent_header"
            if spec.id == self.agent.id:
                head_classes += " active"
            head_label = Label(f"{'▾' if spec.id == self.agent.id else '▸'} "
                                f"{spec.name or spec.id}",
                                classes=head_classes)
            head_item = ListItem(head_label, classes=head_classes)
            head_item.data = {"kind": "agent", "agent_id": spec.id}
            self._sidebar_list.append(head_item)
            self._sidebar_index.append(head_item.data)
            # Sessions for this agent (only when expanded — we expand
            # the active agent only to keep the list tight).
            if spec.id != self.agent.id:
                continue
            entries = []
            root = sessions_dir(spec.id)
            for d in sorted(root.iterdir()) if root.exists() else []:
                if not d.is_dir():
                    continue
                meta_p = d / "meta.json"
                title = d.name
                source = ""
                ts = 0.0
                if meta_p.exists():
                    try:
                        meta = json.loads(meta_p.read_text(encoding="utf-8"))
                        title = meta.get("title") or d.name
                        source = (meta.get("channel") or
                                  meta.get("source") or "")
                        ts = (meta.get("_last_touched")
                              or meta.get("created_at") or 0)
                    except Exception:
                        pass
                entries.append((ts, d.name, title, source))
            entries.sort(key=lambda e: -e[0])
            for _ts, cid, title, source in entries[:80]:
                icon = _PLATFORM_ICON.get(source, "•")
                disp = title if len(title) <= 24 else title[:22] + "…"
                line = f"  {icon} {disp}"
                cls = "session"
                if cid == self.conv_id:
                    cls += " active"
                lbl = Label(line)
                row = ListItem(lbl, classes=cls)
                row.data = {"kind": "session", "agent_id": spec.id,
                             "conv_id": cid}
                self._sidebar_list.append(row)
                self._sidebar_index.append(row.data)


def run_tui(agent, conv_id: str, rt) -> None:
    """Launch the Textual chat. Caller provides a default agent, a
    session id (new or --resume), and an LLM runtime object.
    Falls through with an exception if Textual can't start (caller
    falls back to the Rich REPL).
    """
    app = OpenProgramTUI(agent=agent, conv_id=conv_id, rt=rt)
    app.run()
