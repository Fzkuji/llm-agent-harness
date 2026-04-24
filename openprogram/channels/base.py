"""Channel abstraction. Subclasses implement the per-platform bot loop."""
from __future__ import annotations

import abc
import threading


class Channel(abc.ABC):
    platform_id: str = ""

    @abc.abstractmethod
    def run(self, stop: threading.Event) -> None:
        """Run until ``stop`` is set.

        Implementations should:
          * fetch incoming messages from their platform (long poll / WS / ...)
          * for each message, invoke the shared chat runtime
          * send the reply back on the same channel
          * check ``stop.is_set()`` between iterations so ``channels.runner``
            can shut things down cleanly on Ctrl+C
        """
