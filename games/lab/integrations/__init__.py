"""Production adapters. The engine asks games.lab.registry and does not import this itself.

install() is the composition root. Adding an adapter is a module plus one line here.
"""
from __future__ import annotations

from games.lab.integrations.smb_1_1 import INTEGRATION as SMB

_INSTALLED = (SMB,)


def install() -> None:
    from games.lab.registry import register
    for adapter in _INSTALLED:
        register(adapter)


def registered():
    from games.lab.registry import registered as live
    return live()


def get(integration_id: str | None):
    from games.lab.registry import get as lookup
    return lookup(integration_id)
