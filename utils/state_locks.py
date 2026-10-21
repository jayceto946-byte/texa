"""Process-local locks for read/modify/write state files.

The desktop backend is a single process, but it serves requests and background
feedback jobs on multiple threads. Locks therefore need to be shared by path,
not stored only on individual persistence objects.
"""
from __future__ import annotations

import threading
from pathlib import Path
from utils.path_safety import canonical_path_key


_locks_guard = threading.Lock()
_path_locks: dict[str, threading.RLock] = {}


def get_state_lock(path: str | Path) -> threading.RLock:
    """Return the shared re-entrant lock for a state file."""
    key = canonical_path_key(path)
    with _locks_guard:
        lock = _path_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _path_locks[key] = lock
        return lock
