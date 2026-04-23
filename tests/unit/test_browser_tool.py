"""Tests for the browser tool.

No real Playwright launch — we inject a fake ``sync_playwright`` into
the module under test so every verb round-trips through the session
table and the page API without touching the network or a browser.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from openprogram.tools.browser import browser as tool


@pytest.fixture(autouse=True)
def _clean_sessions():
    tool._sessions.clear()
    yield
    tool._sessions.clear()


class _FakePage:
    def __init__(self):
        self.url = ""
        self.calls: list[tuple[str, tuple]] = []
        self._title = "Fake Page"
        self._body_text = "Hello from fake browser."

    def set_default_timeout(self, ms): self.calls.append(("set_timeout", (ms,)))
    def goto(self, url):
        self.url = url
        self.calls.append(("goto", (url,)))
    def title(self): return self._title
    def click(self, selector): self.calls.append(("click", (selector,)))
    def fill(self, selector, text): self.calls.append(("fill", (selector, text)))
    def press(self, selector, key): self.calls.append(("press", (selector, key)))
    def screenshot(self, *, path, full_page):
        self.calls.append(("screenshot", (path, full_page)))
        # Touch the file so the assertion can verify it.
        with open(path, "wb") as f:
            f.write(b"\x89PNG fake\n")
    def inner_text(self, selector): return self._body_text
    def locator(self, selector):
        loc = MagicMock()
        loc.count.return_value = 2
        items = [MagicMock(), MagicMock()]
        items[0].inner_text.return_value = "match-0"
        items[1].inner_text.return_value = "match-1"
        loc.nth.side_effect = lambda i: items[i]
        return loc


class _FakeContext:
    def __init__(self): self.page = _FakePage()
    def new_page(self): return self.page
    def close(self): self.closed = True


class _FakeBrowser:
    def __init__(self): self.ctx = _FakeContext()
    def new_context(self): return self.ctx
    def close(self): self.closed = True


class _FakeChromium:
    def __init__(self): self.browser = _FakeBrowser()
    def launch(self, *, headless): return self.browser


class _FakePlaywright:
    def __init__(self): self.chromium = _FakeChromium()
    def stop(self): self.stopped = True


class _FakeSyncPlaywrightCM:
    def __init__(self): self.pw = _FakePlaywright()
    def start(self): return self.pw


@pytest.fixture
def fake_playwright(monkeypatch):
    """Inject a fake ``sync_playwright`` for the tool to use, and pretend
    Playwright is importable so ``check_playwright`` returns True."""
    monkeypatch.setattr(tool, "check_playwright", lambda: True)

    # browser.py imports sync_playwright lazily inside _open. Patch the
    # symbol at the stdlib module location since there's no static
    # attribute to replace on the tool module itself.
    import sys
    fake_module = MagicMock()
    fake_module.sync_playwright = _FakeSyncPlaywrightCM
    sys.modules.setdefault("playwright", MagicMock())
    sys.modules["playwright.sync_api"] = fake_module
    yield
    sys.modules.pop("playwright.sync_api", None)


def test_open_creates_session(fake_playwright):
    out = tool.execute(action="open")
    assert out.startswith("Opened browser session `br_")
    # Extract the id so the next test step can use it.
    sid = out.split("`")[1]
    assert sid in tool._sessions


def test_navigate_goto(fake_playwright):
    sid = tool.execute(action="open").split("`")[1]
    out = tool.execute(action="navigate", session_id=sid, url="https://example.com")
    assert "Navigated" in out
    assert tool._sessions[sid]["page"].url == "https://example.com"


def test_navigate_requires_url(fake_playwright):
    sid = tool.execute(action="open").split("`")[1]
    out = tool.execute(action="navigate", session_id=sid)
    assert "Error" in out and "url" in out


def test_click_and_type(fake_playwright):
    sid = tool.execute(action="open").split("`")[1]
    assert "Clicked" in tool.execute(action="click", session_id=sid, selector="button.go")
    out = tool.execute(action="type", session_id=sid, selector="#q", text="hello", submit=True)
    assert "Typed 5 char" in out and "submitted" in out
    calls = tool._sessions[sid]["page"].calls
    assert ("click", ("button.go",)) in calls
    assert ("fill", ("#q", "hello")) in calls
    assert ("press", ("#q", "Enter")) in calls


def test_extract_whole_body(fake_playwright):
    sid = tool.execute(action="open").split("`")[1]
    out = tool.execute(action="extract", session_id=sid)
    assert out == "Hello from fake browser."


def test_extract_with_selector(fake_playwright):
    sid = tool.execute(action="open").split("`")[1]
    out = tool.execute(action="extract", session_id=sid, selector=".item")
    assert "2 match(es)" in out
    assert "match-0" in out and "match-1" in out


def test_screenshot_writes_file(tmp_path, fake_playwright):
    sid = tool.execute(action="open").split("`")[1]
    target = tmp_path / "shot.png"
    out = tool.execute(action="screenshot", session_id=sid, path=str(target))
    assert "Saved screenshot" in out
    assert target.exists()


def test_close_removes_session(fake_playwright):
    sid = tool.execute(action="open").split("`")[1]
    out = tool.execute(action="close", session_id=sid)
    assert "Closed" in out
    assert sid not in tool._sessions


def test_list_reports_empty():
    out = tool.execute(action="list")
    assert "no open browser sessions" in out.lower()


def test_list_reports_open_sessions(fake_playwright):
    sid = tool.execute(action="open").split("`")[1]
    tool.execute(action="navigate", session_id=sid, url="https://example.org")
    out = tool.execute(action="list")
    assert sid in out and "example.org" in out


def test_unknown_session_id(fake_playwright):
    out = tool.execute(action="navigate", session_id="br_bogus", url="https://x")
    assert "no browser session" in out


def test_missing_action():
    assert "action" in tool.execute().lower()


def test_install_hint_when_playwright_missing(monkeypatch):
    # Simulate environment without playwright installed.
    monkeypatch.setattr(tool, "check_playwright", lambda: False)
    out = tool.execute(action="open")
    assert "pip install playwright" in out
