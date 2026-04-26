"""browser tool — automate a headless Chromium via Playwright.

Verbs:

    open       launch browser + context; returns a session id
    navigate   <session_id, url>                       load a URL
    click      <session_id, selector>                  click an element
    type       <session_id, selector, text, [submit]>  fill an input
    extract    <session_id, [selector]>                return readable text
    screenshot <session_id, path>                      save PNG, return path
    close      <session_id>                            tear down

Sessions are process-local — ``open`` returns an id the agent passes
to subsequent calls. Each session owns one Playwright browser + one
page; multi-page workflows can open multiple sessions.

Playwright is an optional dependency. Without it, ``check_playwright``
returns False so the runtime hides the tool. The first call still
emits a clear install hint if the user forces it anyway.
"""

from __future__ import annotations

import sys
import uuid
from typing import Any

from .._helpers import read_string_param


NAME = "browser"

DESCRIPTION = (
    "Automate a headless Chromium browser via Playwright. Open a session, "
    "navigate to URLs, click / type into elements by CSS selector, extract "
    "page text, or take screenshots. Sessions persist across tool calls "
    "within the same process — always ``close`` when done. Install the "
    "runtime first: `pip install playwright && playwright install chromium`."
)


SPEC: dict[str, Any] = {
    "name": NAME,
    "description": DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "open", "navigate", "click", "type",
                    "extract", "screenshot", "close", "list",
                    "upload", "wait", "eval", "html",
                ],
                "description": "What to do.",
            },
            "session_id": {
                "type": "string",
                "description": "Session id returned by ``open``. Required for every action except ``open`` / ``list``.",
            },
            "url": {
                "type": "string",
                "description": "URL to navigate to. Required for ``navigate``.",
            },
            "selector": {
                "type": "string",
                "description": "CSS selector. Required for ``click`` / ``type`` / ``upload``, optional for ``extract`` / ``html`` / ``wait``.",
            },
            "text": {
                "type": "string",
                "description": "Text to type. Required for ``type``.",
            },
            "submit": {
                "type": "boolean",
                "description": "When typing, press Enter afterwards (default false).",
            },
            "path": {
                "type": "string",
                "description": "For ``screenshot``: output PNG path. For ``upload``: file path on disk to attach to the matching <input type=file>.",
            },
            "code": {
                "type": "string",
                "description": "JavaScript expression for ``eval``. Result is JSON-stringified, capped at 2KB.",
            },
            "state": {
                "type": "string",
                "enum": ["attached", "detached", "visible", "hidden", "load", "domcontentloaded", "networkidle"],
                "description": "For ``wait``: with a selector, the element state to wait for (visible/hidden/attached/detached). Without a selector, a page load state (load/domcontentloaded/networkidle). Default 'visible' / 'networkidle'.",
            },
            "headless": {
                "type": "boolean",
                "description": "For ``open``: start browser in headless mode (default true).",
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Per-action timeout in ms (default 30000).",
            },
        },
        "required": ["action"],
    },
}


# Per-process session table. Value shape: dict with playwright, browser, page.
# Kept minimal — we don't persist across process exits.
_sessions: dict[str, dict[str, Any]] = {}


def check_playwright() -> bool:
    """Gate the tool's visibility by whether Playwright is importable."""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _install_hint() -> str:
    return (
        "Error: Playwright not installed. Run:\n"
        "  pip install playwright\n"
        "  playwright install chromium"
    )


def _require_session(session_id: str) -> dict[str, Any] | str:
    if not session_id:
        return "Error: `session_id` is required."
    sess = _sessions.get(session_id)
    if sess is None:
        return f"Error: no browser session with id {session_id!r}."
    return sess


def _open(*, headless: bool = True, timeout_ms: int = 30_000) -> str:
    if not check_playwright():
        return _install_hint()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _install_hint()
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        session_id = "br_" + uuid.uuid4().hex[:10]
        _sessions[session_id] = {
            "playwright": pw,
            "browser": browser,
            "context": context,
            "page": page,
        }
        return (
            f"Opened browser session `{session_id}` "
            f"(headless={headless}, timeout={timeout_ms}ms). "
            f"Pass this id to navigate / click / type / extract / screenshot."
        )
    except Exception as e:
        return f"Error opening browser: {type(e).__name__}: {e}"


def _navigate(session_id: str, url: str) -> str:
    sess = _require_session(session_id)
    if isinstance(sess, str):
        return sess
    if not url:
        return "Error: `url` is required for navigate."
    try:
        sess["page"].goto(url)
        return f"Navigated {session_id} → {url}\nTitle: {sess['page'].title()}"
    except Exception as e:
        return f"Error navigating: {type(e).__name__}: {e}"


def _click(session_id: str, selector: str) -> str:
    sess = _require_session(session_id)
    if isinstance(sess, str):
        return sess
    if not selector:
        return "Error: `selector` is required for click."
    try:
        sess["page"].click(selector)
        return f"Clicked `{selector}` in {session_id}."
    except Exception as e:
        return f"Error clicking: {type(e).__name__}: {e}"


def _type(session_id: str, selector: str, text: str, submit: bool = False) -> str:
    sess = _require_session(session_id)
    if isinstance(sess, str):
        return sess
    if not selector:
        return "Error: `selector` is required for type."
    if text is None:
        return "Error: `text` is required for type."
    try:
        sess["page"].fill(selector, text)
        if submit:
            sess["page"].press(selector, "Enter")
        return f"Typed {len(text)} char(s) into `{selector}`{' + submitted' if submit else ''}."
    except Exception as e:
        return f"Error typing: {type(e).__name__}: {e}"


def _extract(session_id: str, selector: str | None = None) -> str:
    sess = _require_session(session_id)
    if isinstance(sess, str):
        return sess
    try:
        page = sess["page"]
        if selector:
            el = page.locator(selector)
            count = el.count()
            if count == 0:
                return f"(no elements matched `{selector}`)"
            pieces: list[str] = []
            for i in range(min(count, 20)):
                pieces.append(el.nth(i).inner_text())
            return f"[{count} match(es) for `{selector}`, up to 20 shown]\n\n" + "\n---\n".join(pieces)
        return page.inner_text("body")
    except Exception as e:
        return f"Error extracting: {type(e).__name__}: {e}"


def _screenshot(session_id: str, path: str) -> str:
    sess = _require_session(session_id)
    if isinstance(sess, str):
        return sess
    if not path:
        return "Error: `path` is required for screenshot."
    try:
        sess["page"].screenshot(path=path, full_page=True)
        return f"Saved screenshot → {path}"
    except Exception as e:
        return f"Error taking screenshot: {type(e).__name__}: {e}"


def _upload(session_id: str, selector: str, path: str) -> str:
    sess = _require_session(session_id)
    if isinstance(sess, str):
        return sess
    if not selector:
        return "Error: `selector` is required for upload (target the <input type=file>)."
    if not path:
        return "Error: `path` is required for upload."
    import os
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    if not os.path.isfile(path):
        return f"Error: file not found: {path}"
    try:
        sess["page"].set_input_files(selector, path)
        return f"Uploaded `{path}` → `{selector}`."
    except Exception as e:
        return f"Error uploading: {type(e).__name__}: {e}"


def _wait(
    session_id: str,
    selector: str | None,
    state: str | None,
    timeout_ms: int,
) -> str:
    sess = _require_session(session_id)
    if isinstance(sess, str):
        return sess
    page = sess["page"]
    try:
        if selector:
            # Element-state wait. Default to "visible" if user didn't say.
            element_state = state or "visible"
            if element_state not in ("attached", "detached", "visible", "hidden"):
                return (
                    f"Error: with a selector, `state` must be attached / detached / "
                    f"visible / hidden (got {element_state!r})."
                )
            page.wait_for_selector(selector, state=element_state, timeout=timeout_ms)
            return f"Element `{selector}` reached state `{element_state}`."
        # Page-state wait.
        page_state = state or "networkidle"
        if page_state not in ("load", "domcontentloaded", "networkidle"):
            return (
                f"Error: without a selector, `state` must be load / domcontentloaded / "
                f"networkidle (got {page_state!r})."
            )
        page.wait_for_load_state(page_state, timeout=timeout_ms)
        return f"Page reached state `{page_state}`."
    except Exception as e:
        return f"Error waiting: {type(e).__name__}: {e}"


def _eval_js(session_id: str, code: str) -> str:
    sess = _require_session(session_id)
    if isinstance(sess, str):
        return sess
    if not code:
        return "Error: `code` is required for eval."
    try:
        result = sess["page"].evaluate(code)
        # Stringify and cap so a giant DOM dump can't flood the agent.
        if isinstance(result, (dict, list)):
            import json as _json
            text = _json.dumps(result, default=str, ensure_ascii=False)
        else:
            text = str(result)
        if len(text) > 2000:
            text = text[:2000] + f"\n\n[truncated, {len(text) - 2000} more chars]"
        return text
    except Exception as e:
        return f"Error evaluating: {type(e).__name__}: {e}"


def _html(session_id: str, selector: str | None) -> str:
    sess = _require_session(session_id)
    if isinstance(sess, str):
        return sess
    page = sess["page"]
    try:
        if selector:
            el = page.locator(selector)
            count = el.count()
            if count == 0:
                return f"(no elements matched `{selector}`)"
            html = el.first.inner_html()
        else:
            html = page.content()
        # Cap at 5KB — enough for the model to skim structure / find ids.
        if len(html) > 5000:
            html = html[:5000] + f"\n\n[truncated, {len(html) - 5000} more chars]"
        return html
    except Exception as e:
        return f"Error fetching HTML: {type(e).__name__}: {e}"


def _close(session_id: str) -> str:
    sess = _sessions.pop(session_id, None)
    if sess is None:
        return f"Error: no browser session with id {session_id!r}."
    errors: list[str] = []
    for key in ("context", "browser"):
        obj = sess.get(key)
        if obj is None:
            continue
        try:
            obj.close()
        except Exception as e:
            errors.append(f"{key}: {e}")
    pw = sess.get("playwright")
    if pw is not None:
        try:
            pw.stop()
        except Exception as e:
            errors.append(f"playwright: {e}")
    if errors:
        return f"Closed {session_id} with warnings: {'; '.join(errors)}"
    return f"Closed browser session `{session_id}`."


def _list() -> str:
    if not _sessions:
        return "(no open browser sessions)"
    lines = [f"Open browser sessions: {len(_sessions)}"]
    for sid, sess in _sessions.items():
        try:
            url = sess["page"].url
        except Exception:
            url = "?"
        lines.append(f"  {sid}  {url}")
    return "\n".join(lines)


def execute(
    action: str | None = None,
    session_id: str | None = None,
    url: str | None = None,
    selector: str | None = None,
    text: str | None = None,
    submit: bool = False,
    path: str | None = None,
    code: str | None = None,
    state: str | None = None,
    headless: bool = True,
    timeout_ms: int = 30_000,
    **kw: Any,
) -> str:
    action = action or read_string_param(kw, "action", "op")
    if not action:
        return "Error: `action` is required."
    action = action.lower()

    session_id = session_id or read_string_param(kw, "session_id", "sid")
    url = url or read_string_param(kw, "url")
    selector = selector or read_string_param(kw, "selector", "sel")
    text = text if text is not None else read_string_param(kw, "text", "value")
    path = path or read_string_param(kw, "path", "file")
    code = code if code is not None else read_string_param(kw, "code", "js", "expression")
    state = state or read_string_param(kw, "state")

    if action == "open":
        return _open(headless=headless, timeout_ms=timeout_ms)
    if action == "navigate":
        return _navigate(session_id or "", url or "")
    if action == "click":
        return _click(session_id or "", selector or "")
    if action == "type":
        return _type(session_id or "", selector or "", text or "", submit=submit)
    if action == "extract":
        return _extract(session_id or "", selector or None)
    if action == "screenshot":
        return _screenshot(session_id or "", path or "")
    if action == "upload":
        return _upload(session_id or "", selector or "", path or "")
    if action == "wait":
        return _wait(session_id or "", selector or None, state, timeout_ms)
    if action == "eval":
        return _eval_js(session_id or "", code or "")
    if action == "html":
        return _html(session_id or "", selector or None)
    if action == "close":
        return _close(session_id or "")
    if action == "list":
        return _list()
    return f"Error: unknown action {action!r}."


__all__ = ["NAME", "SPEC", "DESCRIPTION", "execute", "check_playwright"]
