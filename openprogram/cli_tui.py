"""Full-screen terminal chat (Textual).

Layout

    ┌─────────────────────────────────────────────────────────────┐
    │  status: agent=main · model=gpt-5.5-mini · session=local_…  │
    ├─────────────────┬───────────────────────────────────────────┤
    │ sessions        │  chat scrollback                          │
    │  · main         │                                           │
    │    …            │  you ▸ ...                                │
    │  · work         │                                           │
    │    …            │  assistant ▸ ...                          │
    │                 │                                           │
    ├─────────────────┴───────────────────────────────────────────┤
    │ > _                                                         │
    └─────────────────────────────────────────────────────────────┘

Key bindings
    Ctrl+N     new session (same agent)
    Ctrl+B     toggle the sidebar
    Ctrl+P     open the command palette (same as typing `/`)
    Ctrl+Q    quit
    Enter     send the current input
    Shift+↑/↓ scroll history

Slash commands behave exactly like in the Rich REPL (cli_chat._handle_slash)
— the handler is reused so /login /attach /detach /connections /help
keep the same semantics.

This module is the default chat surface. cli_chat.py's older Rich REPL
is still the fallback when the terminal reports no TUI support
(``openprogram --no-tui``).
"""
from __future__ import annotations

import threading
import uuid
from typing import Any, Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import (
    Footer, Header, Input, Label, ListItem, ListView, Markdown, Static,
)


class _StatusBar(Static):
    """One-line status: agent · model · session."""

    agent_id = reactive("")
    model = reactive("")
    session_id = reactive("")

    def render(self) -> str:
        sess = self.session_id[:14] if self.session_id else "—"
        return (f"[bold bright_blue]agent[/]: {self.agent_id or '—'}    "
                f"[bold bright_blue]model[/]: {self.model or '—'}    "
                f"[bold bright_blue]session[/]: {sess}")


class _ChatScroll(VerticalScroll):
    """The main scrollback. Holds a growing list of Markdown widgets,
    one per message."""
    DEFAULT_CSS = """
    _ChatScroll {
        border: none;
        padding: 1 2;
    }
    _ChatScroll Markdown.user {
        background: $boost 10%;
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
        padding: 1 2;
        margin: 0 0 1 0;
    }
    """


class _Sidebar(Vertical):
    """Sessions list. Users click / arrow-select to switch."""
    DEFAULT_CSS = """
    _Sidebar {
        width: 30;
        border-right: tall $accent 30%;
    }
    _Sidebar Label.header {
        padding: 1 2 0 2;
        color: $accent;
    }
    _Sidebar ListView {
        height: 1fr;
    }
    """


class OpenProgramTUI(App):
    """Full-screen chat client."""

    CSS = """
    Screen { layout: vertical; }
    #statusbar { height: 1; background: $boost 15%; padding: 0 2; }
    #main { height: 1fr; }
    #input_box { height: 3; border-top: tall $accent 30%; }
    Input { border: none; padding: 1 2; }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit_chat", "Quit", priority=True),
        Binding("ctrl+n", "new_session", "New session"),
        Binding("ctrl+b", "toggle_sidebar", "Toggle sidebar"),
        Binding("ctrl+l", "clear_scroll", "Clear"),
    ]

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
        self._busy = False

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        self._status = _StatusBar(id="statusbar")
        self._chat = _ChatScroll(id="chat_scroll")
        self._sidebar_list = ListView(id="session_list")
        self._sidebar = _Sidebar(
            Label("Sessions", classes="header"),
            self._sidebar_list,
            id="sidebar",
        )
        self._input = Input(placeholder="Type a message. / for commands.",
                             id="input_box")
        yield self._status
        with Horizontal(id="main"):
            yield self._sidebar
            yield self._chat
        yield self._input
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_status()
        self._load_history_into_scroll()
        self._refresh_sessions_list()
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
        self._refresh_sessions_list()

    async def action_toggle_sidebar(self) -> None:
        self._sidebar.display = not self._sidebar.display

    async def action_clear_scroll(self) -> None:
        self._chat.remove_children()
        self._append_system("(view cleared — history on disk is intact)")

    # ------------------------------------------------------------------
    # Input submission
    # ------------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = (event.value or "").strip()
        if not text:
            return
        self._input.value = ""
        if text.startswith("/"):
            self._run_slash(text)
            return
        if self._busy:
            self._append_system("[busy — wait for the current turn to finish]")
            return
        self._append_user(text)
        self._busy = True
        self._run_turn(text)

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
        except Exception as e:  # noqa: BLE001
            reply = f"[error] {type(e).__name__}: {e}"
        # Back to the UI thread to render.
        self.call_from_thread(self._append_assistant, reply)
        self.call_from_thread(self._mark_idle)

    def _mark_idle(self) -> None:
        self._busy = False
        self._refresh_sessions_list()

    # ------------------------------------------------------------------
    # Slash commands — reuse cli_chat._handle_slash but capture output
    # ------------------------------------------------------------------

    def _run_slash(self, raw: str) -> None:
        """Dispatch a slash command. cli_chat._handle_slash writes to
        a ``console`` object; we feed it a capture shim that turns
        each ``print`` into a system bubble inside the scroll.
        """
        from rich.console import Console as _Console
        from io import StringIO
        buf = StringIO()
        captured = _Console(file=buf, force_terminal=False,
                            width=100, record=True)
        # Light shim so `.print(markup)` without styles still produces
        # readable output. We feed the captured string as system msg.
        from openprogram.cli_chat import _handle_slash
        try:
            should_quit = _handle_slash(
                raw, captured, self.rt,
                agent=self.agent, conv_id=self.conv_id,
            )
        except Exception as e:  # noqa: BLE001
            should_quit = False
            self._append_system(f"[slash error] {type(e).__name__}: {e}")
            return
        output = buf.getvalue().strip()
        if output:
            self._append_system(output)
        if should_quit:
            self.exit()

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

    def _load_history_into_scroll(self) -> None:
        """If --resume brought us into an existing session, render it
        so the user sees their context, not a blank screen."""
        try:
            from openprogram.webui import persistence as _p
            data = _p.load_conversation(self.agent.id, self.conv_id)
        except Exception:
            data = None
        if not data:
            self._append_system(
                f"New session `{self.conv_id}` under agent `{self.agent.id}`. "
                f"Type to start, or `/login wechat` to wire up a channel."
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

    # ------------------------------------------------------------------
    # Sessions list
    # ------------------------------------------------------------------

    def _refresh_sessions_list(self) -> None:
        """Populate the sidebar with this agent's sessions. Clicking a
        row switches the main view to that session.
        """
        if self._sidebar_list is None or self.agent is None:
            return
        self._sidebar_list.clear()
        try:
            from openprogram.agents.manager import sessions_dir
            import json
            root = sessions_dir(self.agent.id)
            entries = []
            for d in root.iterdir() if root.exists() else []:
                if not d.is_dir():
                    continue
                meta_p = d / "meta.json"
                title = d.name
                ts = 0.0
                if meta_p.exists():
                    try:
                        meta = json.loads(meta_p.read_text(encoding="utf-8"))
                        title = meta.get("title") or d.name
                        ts = meta.get("_last_touched") or \
                             meta.get("created_at") or 0
                    except Exception:
                        pass
                entries.append((ts, d.name, title))
            entries.sort(key=lambda e: -e[0])
            for _ts, cid, title in entries[:80]:
                label = title
                if cid == self.conv_id:
                    label = "▶ " + title
                item = ListItem(Label(label), id=f"sess_{cid}")
                item.data_id = cid  # type: ignore[attr-defined]
                self._sidebar_list.append(item)
        except Exception:
            pass

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Sidebar row clicked — switch session."""
        if event.item is None:
            return
        cid = getattr(event.item, "data_id", None)
        if not cid or cid == self.conv_id:
            return
        self.conv_id = cid
        self._chat.remove_children()
        self._load_history_into_scroll()
        self._refresh_status()
        self._refresh_sessions_list()


def run_tui(agent, conv_id: str, rt) -> None:
    """Launch the Textual chat. Caller provides a default agent, a
    session id (new or --resume), and an LLM runtime object.

    Any exception from Textual startup propagates to the caller,
    which should fall back to the Rich REPL.
    """
    app = OpenProgramTUI(agent=agent, conv_id=conv_id, rt=rt)
    app.run()
