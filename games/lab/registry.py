"""Adapter lookup. Production adapters load on first use. Tests can isolate one.

This module does not import a game. The installer in games.lab.integrations does.
"""
from __future__ import annotations

from contextlib import contextmanager

_adapters: dict[str, object] = {}
_autoload = True


def register(adapter) -> None:
    adapter_id = getattr(adapter, "id", None)
    if not adapter_id:
        raise ValueError("an adapter needs an id")
    _adapters[str(adapter_id)] = adapter


def _ensure() -> None:
    if _adapters or not _autoload:
        return
    from games.lab.integrations import install
    install()


def registered() -> list:
    _ensure()
    return list(_adapters.values())


def get(adapter_id: str | None):
    if not adapter_id:
        return None
    _ensure()
    try:
        return _adapters[adapter_id]
    except KeyError:
        raise KeyError(f"unknown integration {adapter_id}") from None


def find_match(system: str, stem: str):
    """The adapter that claims this catalog title, or None."""
    for adapter in registered():
        matches = getattr(adapter, "matches", None)
        if callable(matches) and matches(system, stem):
            return adapter
    return None


def owner_of(record: dict | None):
    """The adapter that owns a historical round, tape, or challenge."""
    if not isinstance(record, dict):
        return None
    named = record.get("integration")
    if named:
        try:
            return get(named)
        except KeyError:
            return None
    for adapter in registered():
        owns = getattr(adapter, "owns", None)
        if callable(owns) and owns(record):
            return adapter
    return None


@contextmanager
def isolated(*adapters):
    """Use only these adapters. The production installer stays unloaded."""
    global _autoload, _adapters
    previous = dict(_adapters)
    previous_auto = _autoload
    _adapters = {}
    _autoload = False
    for adapter in adapters:
        register(adapter)
    try:
        yield
    finally:
        _adapters = previous
        _autoload = previous_auto
