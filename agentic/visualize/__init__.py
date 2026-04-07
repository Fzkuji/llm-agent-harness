"""
agentic.visualize — real-time web visualization for Agentic Programming.

Usage:
    from agentic.visualize import start_visualizer
    start_visualizer(port=8765)

Or from CLI:
    agentic visualize
    python -m agentic.visualize
"""

from agentic.visualize.server import start_server, stop_server


def start_visualizer(port: int = 8765, open_browser: bool = True):
    """
    Start the real-time visualization server in a background thread.

    Opens a browser window showing the execution tree. Updates in real-time
    as @agentic_function calls are made.

    Args:
        port: Port to serve on (default 8765).
        open_browser: Whether to open a browser tab automatically.

    Returns:
        The background thread running the server.
    """
    return start_server(port=port, open_browser=open_browser)


__all__ = ["start_visualizer", "start_server", "stop_server"]
