"""Offline registry types from the fixed reviewed V0.1 source."""
from .frozen_runtime import frozen_module


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(frozen_module("backend.tools.registry"), name)
