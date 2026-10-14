"""A human hint. The buttons play after the shared run, in one game-defined context.

A hint with no buttons is a note. It waits until the route is filled in.
The context is the adapter's: a world and stage, a room, or whatever that game uses.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

HINTS_NAME = "hints.json"
_HINT_SEQ = 0
MAX_HINTS = 20
MAX_ACTIONS = 4000
MAX_TITLE = 80
MAX_NOTE = 500


def labels(actions: list[tuple[str, ...]]) -> list[str]:
    return ["+".join(chord) if chord else "NONE" for chord in actions]


def parse_actions(text: str, names: list[str]) -> list[int]:
    lookup = {name.upper(): index for index, name in enumerate(names)}
    lookup.update({"NONE": 0, "WAIT": 0, "NOTHING": 0, "·": 0})
    out = []
    for token in str(text or "").replace(",", " ").split():
        key = token.strip().upper()
        if not key:
            continue
        if key.isdigit():
            index = int(key)
        elif key in lookup:
            index = lookup[key]
        else:
            raise ValueError(f"unknown button {token.strip()}")
        if index < 0 or index >= len(names):
            raise ValueError(f"unknown button {token.strip()}")
        out.append(index)
        if len(out) > MAX_ACTIONS:
            raise ValueError("hint is too long")
    return out


def _context_of(item: dict) -> dict | None:
    context = item.get("context")
    if isinstance(context, dict) and context:
        return dict(context)
    context = {}
    for key in ("world", "stage"):
        if item.get(key) is None:
            continue
        try:
            context[key] = int(item.get(key))
        except (TypeError, ValueError):
            return None
    return context or None


def _clean(item: dict, n_actions: int | None, accept=None) -> dict | None:
    if not isinstance(item, dict):
        return None
    context = _context_of(item)
    if context is None:
        return None
    if accept is not None:
        try:
            context = accept(dict(context))
        except (TypeError, ValueError):
            return None
        if not isinstance(context, dict) or not context:
            return None
    actions = item.get("actions") or []
    if not isinstance(actions, list) or len(actions) > MAX_ACTIONS:
        return None
    limit = MAX_ACTIONS if n_actions is None else int(n_actions)
    buttons = []
    for action in actions:
        if isinstance(action, bool) or not isinstance(action, int):
            return None
        if action < 0 or action >= limit:
            return None
        buttons.append(int(action))
    title = str(item.get("title") or "").strip()[:MAX_TITLE]
    if not title:
        return None
    row = {
        "id": str(item.get("id") or "")[:40],
        "title": title,
        "context": context,
        "enabled": bool(item.get("enabled", True)),
        "note": str(item.get("note") or "").strip()[:MAX_NOTE],
        "actions": buttons,
    }
    if "world" in context:
        row["world"] = context["world"]
    if "stage" in context:
        row["stage"] = context["stage"]
    return row


def read_hints(path: Path, n_actions: int | None = None) -> list[dict]:
    file = Path(path)
    if not file.is_file():
        return []
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = data.get("hints") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    cleaned = []
    for item in rows:
        hint = _clean(item, n_actions)
        if hint is not None and hint["id"]:
            cleaned.append(hint)
    return cleaned[:MAX_HINTS]


def _write(path: Path, hints: list[dict]) -> None:
    from games.lab.worker import atomic_json
    atomic_json(Path(path), {"hints": hints})


def _hint_id() -> str:
    global _HINT_SEQ
    _HINT_SEQ += 1
    return f"hint-{time.time_ns()}-{_HINT_SEQ}"


def add_hint(path: Path, spec: dict, n_actions: int | None = None, accept_context=None) -> dict:
    hints = read_hints(path, n_actions)
    if len(hints) >= MAX_HINTS:
        raise ValueError("too many hints")
    title = str(spec.get("title") or "").strip()
    if not title:
        raise ValueError("a hint needs a title")
    actions = spec.get("actions") or []
    if isinstance(actions, str):
        raise ValueError("buttons should already be indexes")
    raw = {
        "id": _hint_id(),
        "title": title,
        "enabled": True,
        "note": spec.get("note") or "",
        "actions": actions,
    }
    if isinstance(spec.get("context"), dict):
        raw["context"] = spec["context"]
    else:
        raw["world"] = spec.get("world")
        raw["stage"] = spec.get("stage")
    hint = _clean(raw, n_actions, accept_context)
    if hint is None:
        raise ValueError("hint could not be saved")
    hints.append(hint)
    _write(path, hints)
    return hint


def change_hint(
    path: Path,
    hint_id: str,
    enabled: bool | None = None,
    remove: bool = False,
    n_actions: int | None = None,
) -> list[dict]:
    hints = read_hints(path, n_actions)
    found = False
    kept = []
    for hint in hints:
        if hint["id"] != hint_id:
            kept.append(hint)
            continue
        found = True
        if remove:
            continue
        if enabled is not None:
            hint = dict(hint)
            hint["enabled"] = bool(enabled)
        kept.append(hint)
    if not found:
        raise ValueError("no such hint")
    _write(path, kept)
    return kept


def hint_button(hints: list[dict], world, stage, index: int, n_actions: int):
    """The button to play at this step of a matching hint, or None."""
    try:
        world = int(world)
        stage = int(stage)
        index = int(index)
    except (TypeError, ValueError):
        return None
    if world is None or stage is None or index < 0:
        return None
    for hint in hints:
        if not hint.get("enabled"):
            continue
        if int(hint.get("world") or 0) != world or int(hint.get("stage") or 0) != stage:
            continue
        actions = hint.get("actions") or []
        if index >= len(actions):
            continue
        button = int(actions[index])
        if 0 <= button < int(n_actions):
            return button
    return None
