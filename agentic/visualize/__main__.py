"""
Allow running the visualizer with: python -m agentic.visualize

Starts the server and keeps it alive until interrupted.
"""

import argparse
import signal
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="python -m agentic.visualize",
        description="Start the Agentic Programming real-time visualizer.",
    )
    parser.add_argument(
        "--port", "-p", type=int, default=8765,
        help="Port to serve on (default: 8765)",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Don't open a browser window automatically",
    )
    args = parser.parse_args()

    from agentic.visualize import start_visualizer

    thread = start_visualizer(port=args.port, open_browser=not args.no_browser)

    print("Press Ctrl+C to stop.")
    try:
        thread.join()
    except KeyboardInterrupt:
        print("\nStopping visualizer.")
        sys.exit(0)


if __name__ == "__main__":
    main()
