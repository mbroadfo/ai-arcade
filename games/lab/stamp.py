"""Which weights a later round is allowed to keep training.

A zip written by an older button list or an older score is not a parent.
Loading it would either crash or teach the new seats the old 1-1 habit.
"""
from __future__ import annotations

import json
from pathlib import Path


def stamp_path(zip_path: Path) -> Path:
    return zip_path.with_suffix(".stamp.json")


def write_stamp(zip_path: Path, stamp: dict) -> None:
    from games.lab.worker import atomic_json
    atomic_json(stamp_path(zip_path), stamp)


def read_stamp(zip_path: Path) -> dict | None:
    path = stamp_path(zip_path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def matches(zip_path: Path, expected: dict | None) -> bool:
    """No expected stamp accepts any zip. An expected stamp requires an exact sidecar."""
    if expected is None:
        return True
    return read_stamp(zip_path) == expected
