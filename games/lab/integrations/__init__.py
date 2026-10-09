"""Scored games. A bootable game has no integration: the objective is steps survived."""
from __future__ import annotations

from games.lab.integrations.smb_1_1 import INTEGRATION as SMB

BY_ID = {SMB.id: SMB}


def get(integration_id: str | None):
    if not integration_id:
        return None
    try:
        return BY_ID[integration_id]
    except KeyError:
        raise KeyError(f"unknown integration {integration_id}") from None
