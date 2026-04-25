from __future__ import annotations

import sys
import time


class ProgressLogger:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.started_at = time.monotonic()

    def info(self, message: str) -> None:
        if not self.enabled:
            return
        elapsed = time.monotonic() - self.started_at
        print(f"[{elapsed:8.1f}s] {message}", file=sys.stderr, flush=True)
