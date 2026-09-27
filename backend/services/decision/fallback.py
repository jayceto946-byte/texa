"""Bounded fallback for a validated capability chooser, with no tool schema."""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Callable

from backend.services.decision.contracts import DecisionContext

_FALLBACK_SLOTS = threading.BoundedSemaphore(2)


@dataclass
class BoundedFallback:
    chooser: Callable[[DecisionContext, tuple[str, ...]], str | None]
    timeout_seconds: float = 2.0

    def choose(self, context: DecisionContext, candidates: tuple[str, ...]) -> str | None:
        if not _FALLBACK_SLOTS.acquire(blocking=False):
            return None
        output: queue.Queue = queue.Queue(maxsize=1)
        def invoke():
            try:
                output.put(self.chooser(context, candidates))
            except Exception:
                output.put(None)
            finally:
                _FALLBACK_SLOTS.release()
        threading.Thread(target=invoke, name="capability-fallback", daemon=True).start()
        try:
            chosen = output.get(timeout=self.timeout_seconds)
        except queue.Empty:
            return None
        return chosen if chosen in candidates else None
