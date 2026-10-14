"""Coordinate active-index publication with complete production retrieval reads."""
from contextlib import contextmanager
from functools import wraps
from threading import Condition, RLock, local

_condition = Condition(RLock())
_readers = 0
_publishing = False
_waiting_publishers = 0
_local = local()


def read_snapshot(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with index_read_snapshot():
            return function(*args, **kwargs)
    return wrapped


@contextmanager
def index_read_snapshot():
    global _readers
    if getattr(_local, "read_depth", 0):
        _local.read_depth += 1
        try:
            yield
        finally:
            _local.read_depth -= 1
        return
    with _condition:
        while _publishing or _waiting_publishers:
            _condition.wait()
        _readers += 1
        _local.read_depth = 1
    try:
        yield
    finally:
        with _condition:
            _readers -= 1
            _local.read_depth = 0
            _condition.notify_all()


@contextmanager
def index_publication():
    global _publishing, _waiting_publishers
    with _condition:
        _waiting_publishers += 1
        try:
            while _publishing or _readers:
                _condition.wait()
            _publishing = True
        finally:
            _waiting_publishers -= 1
    try:
        yield
    finally:
        with _condition:
            _publishing = False
            _condition.notify_all()
