"""
Visualization server — FastAPI + WebSocket for real-time Context tree viewing.

Runs in a background thread alongside user code. Streams tree updates to
connected browsers via WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Any, Optional

from agentic.context import Context, _current_ctx, on_event, off_event

# ---------------------------------------------------------------------------
# Pause/resume machinery
# ---------------------------------------------------------------------------
_pause_event = threading.Event()
_pause_event.set()  # starts un-paused


def pause_execution():
    """Block agentic functions from proceeding (cooperative)."""
    _pause_event.clear()


def resume_execution():
    """Resume blocked agentic functions."""
    _pause_event.set()


def wait_if_paused():
    """Called by the event hook; blocks until resumed."""
    _pause_event.wait()


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
_root_contexts: list[dict] = []
_root_contexts_lock = threading.Lock()
_ws_connections: list[Any] = []
_ws_lock = threading.Lock()
_loop: Optional[asyncio.AbstractEventLoop] = None


def _find_root(ctx_data: dict) -> Optional[dict]:
    """Walk up to the root of a context path and find the stored root."""
    path = ctx_data.get("path", "")
    root_name = path.split("/")[0] if "/" in path else path
    with _root_contexts_lock:
        for r in _root_contexts:
            if r.get("name") == root_name or r.get("path") == root_name:
                return r
    return None


def _on_context_event(event_type: str, data: dict):
    """Callback registered with the Context event system."""
    # If we're paused and a node just got created, wait
    if event_type == "node_created":
        wait_if_paused()

    # Store/update root contexts
    path = data.get("path", "")
    if "/" not in path:
        # This is a root node
        with _root_contexts_lock:
            # Update existing or add new
            found = False
            for i, r in enumerate(_root_contexts):
                if r.get("path") == path:
                    _root_contexts[i] = data
                    found = True
                    break
            if not found:
                _root_contexts.append(data)

    # Broadcast to all connected WebSocket clients
    msg = json.dumps({"type": "event", "event": event_type, "data": data}, default=str)
    _broadcast(msg)


def _broadcast(msg: str):
    """Send a message to all connected WebSocket clients."""
    if not _ws_connections or _loop is None:
        return
    with _ws_lock:
        conns = list(_ws_connections)
    for ws in conns:
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(msg), _loop)
        except Exception:
            pass


def _get_full_tree() -> list[dict]:
    """Get current root-level context trees by walking active contexts."""
    # First check if there's a currently running context
    try:
        current = _current_ctx.get(None)
        if current is not None:
            # Walk up to root
            root = current
            while root.parent is not None:
                root = root.parent
            return [root._to_dict()]
    except Exception:
        pass

    with _root_contexts_lock:
        return list(_root_contexts)


def _find_node_by_path(tree: dict, path: str) -> Optional[dict]:
    """Find a node in a tree dict by its path."""
    if tree.get("path") == path:
        return tree
    for child in tree.get("children", []):
        result = _find_node_by_path(child, path)
        if result is not None:
            return result
    return None


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

def create_app():
    """Create and return the FastAPI application."""
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import HTMLResponse, JSONResponse
    except ImportError:
        raise ImportError(
            "FastAPI is required for the visualizer. "
            "Install with: pip install agentic-programming[visualize]"
        )

    app = FastAPI(title="Agentic Visualizer", docs_url=None, redoc_url=None)

    # Serve the HTML frontend
    @app.get("/", response_class=HTMLResponse)
    async def index():
        html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
        with open(html_path) as f:
            return HTMLResponse(content=f.read())

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        with _ws_lock:
            _ws_connections.append(ws)
        try:
            # Send current state on connect
            tree = _get_full_tree()
            await ws.send_text(json.dumps(
                {"type": "full_tree", "data": tree}, default=str
            ))
            # Keep alive — receive pings/messages
            while True:
                data = await ws.receive_text()
                # Handle ping
                if data == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            with _ws_lock:
                try:
                    _ws_connections.remove(ws)
                except ValueError:
                    pass

    # REST endpoints
    @app.get("/api/tree")
    async def get_tree():
        return JSONResponse(content=_get_full_tree())

    @app.post("/api/pause")
    async def api_pause():
        pause_execution()
        _broadcast(json.dumps({"type": "status", "paused": True}))
        return JSONResponse(content={"paused": True})

    @app.post("/api/resume")
    async def api_resume():
        resume_execution()
        _broadcast(json.dumps({"type": "status", "paused": False}))
        return JSONResponse(content={"paused": False})

    @app.get("/api/node/{path:path}")
    async def get_node(path: str):
        trees = _get_full_tree()
        for tree in trees:
            node = _find_node_by_path(tree, path)
            if node is not None:
                return JSONResponse(content=node)
        return JSONResponse(content={"error": "not found"}, status_code=404)

    return app


# ---------------------------------------------------------------------------
# Server runner (in background thread)
# ---------------------------------------------------------------------------

_server_thread: Optional[threading.Thread] = None


def start_server(port: int = 8765, open_browser: bool = True) -> threading.Thread:
    """
    Start the visualization server in a background daemon thread.

    Returns the thread object. The server runs until the process exits.
    """
    global _server_thread, _loop

    if _server_thread is not None and _server_thread.is_alive():
        print(f"Visualizer already running")
        return _server_thread

    # Register our event callback
    on_event(_on_context_event)

    def _run():
        global _loop
        try:
            import uvicorn
        except ImportError:
            raise ImportError(
                "uvicorn is required for the visualizer. "
                "Install with: pip install agentic-programming[visualize]"
            )

        app = create_app()
        config = uvicorn.Config(
            app, host="0.0.0.0", port=port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _loop.run_until_complete(server.serve())

    _server_thread = threading.Thread(target=_run, daemon=True, name="agentic-visualizer")
    _server_thread.start()

    url = f"http://localhost:{port}"
    print(f"Agentic Visualizer running at {url}")

    if open_browser:
        # Small delay to let the server start
        def _open():
            import time
            time.sleep(0.8)
            import webbrowser
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    return _server_thread


def stop_server():
    """Clean up event callbacks."""
    off_event(_on_context_event)
