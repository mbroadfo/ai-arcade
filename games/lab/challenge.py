"""A reusable challenge backed by one libretro savestate.

The state file and the description are a pair. A different ROM, a different
core, a different hash, or a different version is refused. Nothing here loads
a mismatched state and hopes the game looks right.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


class ChallengeError(ValueError):
    """The challenge cannot be loaded. The state was not applied."""


def challenges_root() -> Path:
    return Path(__file__).resolve().parent / "challenges"


def check_id(challenge_id: str) -> str:
    if not isinstance(challenge_id, str) or not challenge_id:
        raise ChallengeError("challenge id is missing")
    if (
        challenge_id in {".", ".."}
        or challenge_id.startswith(".")
        or "/" in challenge_id
        or "\\" in challenge_id
        or ".." in challenge_id
    ):
        raise ChallengeError("challenge id is not a single folder name")
    return challenge_id


def reached_warp(start: dict, now: dict) -> bool:
    """World 1-2 became world 4 inside the emulator. A score is not this check."""
    return (
        start.get("world") == 1
        and start.get("stage") == 2
        and now.get("world") == 4
        and now.get("stage") == 1
        and not now.get("dead")
        and not now.get("dying")
    )


def same_start(expected: dict, now: dict) -> bool:
    """The restored emulator matches the facts stored with the state."""
    for key in ("world", "stage", "x_pos", "y_pos", "time", "player_state"):
        try:
            if int(expected.get(key)) != int(now.get(key)):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _atomic_bytes(path: Path, blob: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, path)


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_challenge(root: Path, document: dict, state: bytes) -> Path:
    """Write the state, then the description. A reader sees a match or a refusal."""
    from games.lab.worker import atomic_json
    document = dict(document)
    check_id(str(document.get("id") or ""))
    missing = [
        key for key in ("objective", "game", "rom_sha1", "core_sha1", "core_name", "start")
        if not document.get(key)
    ]
    if missing:
        raise ChallengeError("missing " + ", ".join(missing))
    start = document["start"]
    if not isinstance(start, dict):
        raise ChallengeError("start facts are missing")
    for key in ("world", "stage", "x_pos", "y_pos", "time", "player_state"):
        if start.get(key) is None:
            raise ChallengeError(f"start is missing {key}")
    blob = bytes(state)
    document["version"] = 1
    document["state_format"] = "libretro-serialize"
    document["state_sha256"] = hashlib.sha256(blob).hexdigest()
    document["state_bytes"] = len(blob)
    folder = Path(root) / document["id"]
    folder.mkdir(parents=True, exist_ok=True)
    _atomic_bytes(folder / "state.bin", blob)
    atomic_json(folder / "challenge.json", document)
    return folder


def load_challenge(folder: Path, *, rom_sha1: str, core_sha1: str) -> tuple[dict, bytes]:
    """Return the document and the state bytes, or raise. Never a partial load."""
    folder = Path(folder)
    document = _read_json(folder / "challenge.json")
    state_path = folder / "state.bin"
    if document is None or not state_path.is_file():
        raise ChallengeError("challenge files are missing")
    try:
        state = state_path.read_bytes()
    except OSError as exc:
        raise ChallengeError("state could not be read") from exc
    if int(document.get("version") or 0) != 1:
        raise ChallengeError("unsupported challenge version")
    if document.get("state_format") != "libretro-serialize":
        raise ChallengeError("unsupported state format")
    if document.get("rom_sha1") != rom_sha1:
        raise ChallengeError("ROM does not match this challenge")
    if document.get("core_sha1") != core_sha1:
        raise ChallengeError("core does not match this challenge")
    digest = hashlib.sha256(state).hexdigest()
    if digest != document.get("state_sha256") or len(state) != int(document.get("state_bytes") or -1):
        raise ChallengeError("state hash does not match")
    start = document.get("start")
    if not isinstance(start, dict):
        raise ChallengeError("start facts are missing")
    return document, state


def catalog(root: Path | None = None) -> list[dict]:
    """Descriptions for the challenge page. The savestate blob stays on disk."""
    root = Path(root) if root is not None else challenges_root()
    rows = []
    if not root.is_dir():
        return rows
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        document = _read_json(folder / "challenge.json")
        if document is None:
            continue
        search = _read_json(folder / "search.json") or {}
        skill = _read_json(folder / "skill.json") or {}
        curriculum = _read_json(folder / "curriculum.json")
        trajectory = search.get("trajectory") if isinstance(search.get("trajectory"), list) else []
        rows.append({
            "id": document.get("id") or folder.name,
            "objective": document.get("objective"),
            "game": document.get("game"),
            "rom_sha1": document.get("rom_sha1"),
            "core_sha1": document.get("core_sha1"),
            "core_name": document.get("core_name"),
            "version": document.get("version"),
            "start": document.get("start"),
            "max_frames": document.get("max_frames"),
            "success": document.get("success"),
            "state_present": (folder / "state.bin").is_file(),
            "state_bytes": document.get("state_bytes"),
            "watch": document.get("watch"),
            "comparisons": document.get("comparisons") or [],
            "search": {
                "solved": bool(search.get("solved")),
                "attempts": search.get("attempts"),
                "frames": search.get("frames"),
                "trajectory_frames": search.get("trajectory_frames"),
                "budget_exhausted": bool(search.get("budget_exhausted")),
                "trajectory": trajectory[:80],
                "presses": len(trajectory),
                "best_facts": search.get("best_facts"),
                "frame_accounting": search.get("frame_accounting"),
                "subgoals": search.get("subgoals") or [],
            },
            "skill": {
                "stage": skill.get("stage"),
                "agents": skill.get("agents") or {},
                "provenance": skill.get("provenance"),
            },
            "curriculum": curriculum.get("stages") if isinstance(curriculum, dict) else curriculum,
            "records": {
                "assisted": None,
                "searched": {
                    "attempts": search.get("attempts"),
                    "solved": bool(search.get("solved")) if search else None,
                    "frames": search.get("frames"),
                } if search else None,
                "independent": None,
            },
        })
    return rows
