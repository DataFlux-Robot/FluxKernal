"""L2: solver plugin registry. All heavy, fallible, evolving computation lives
here — never in L1. Every plugin returns (result_fields, evidence, obligations).
"""
from __future__ import annotations

_PLUGINS: dict[str, callable] = {}


def register(name: str):
    def deco(fn):
        _PLUGINS[name] = fn
        return fn
    return deco


def get(name: str) -> callable:
    if name not in _PLUGINS:
        raise KeyError(f"no solver plugin registered for transform: {name}")
    return _PLUGINS[name]


def available() -> list:
    return sorted(_PLUGINS)
