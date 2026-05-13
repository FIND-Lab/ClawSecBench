from __future__ import annotations

import sys
import threading
import time


class ProgressLogger:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.started_at = time.monotonic()
        self._lock = threading.Lock()

    def info(self, message: str) -> None:
        if not self.enabled:
            return
        elapsed = time.monotonic() - self.started_at
        with self._lock:
            print(f"[{elapsed:8.1f}s] {message}", file=sys.stderr, flush=True)
