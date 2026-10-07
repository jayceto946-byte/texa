"""Small defensive TTL cache keyed by dependency file snapshots."""
from __future__ import annotations

import copy
import threading
import time
from pathlib import Path
from typing import Any, Callable, Hashable, Iterable


def dependency_signature(path: Path) -> tuple[str, int, int] | tuple[str, None, None]:
    resolved = str(path.resolve())
    try:
        stat = path.stat()
        return resolved, stat.st_mtime_ns, stat.st_size
    except OSError:
        return resolved, None, None


class DependencyTTLCache:
    def __init__(
        self,
        ttl_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._clock = clock
        self._lock = threading.RLock()
        self._entries: dict[
            Hashable,
            tuple[float, tuple[tuple[str, int | None, int | None], ...], Any],
        ] = {}

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def get_or_compute(
        self,
        key: Hashable,
        dependencies: Iterable[Path],
        factory: Callable[[], Any],
        *,
        should_cache: Callable[[Any], bool] | None = None,
    ) -> Any:
        signatures = tuple(dependency_signature(path) for path in dependencies)
        now = self._clock()
        with self._lock:
            cached = self._entries.get(key)
            if cached and cached[0] > now and cached[1] == signatures:
                return copy.deepcopy(cached[2])

        value = factory()
        if should_cache is None or should_cache(value):
            with self._lock:
                self._entries[key] = (
                    now + self.ttl_seconds,
                    signatures,
                    copy.deepcopy(value),
                )
        return copy.deepcopy(value)
