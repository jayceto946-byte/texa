"""Coordinate active-index publication with complete production retrieval reads."""
from contextlib import contextmanager
from threading import Condition, RLock

_condition = Condition(RLock())
_readers = 0
_publishing = False
_waiting_publishers = 0


@contextmanager
def index_read_snapshot():
    global _readers
    with _condition:
        while _publishing or _waiting_publishers:
            _condition.wait()
        _readers += 1
    try:
        yield
    finally:
        with _condition:
            _readers -= 1
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
