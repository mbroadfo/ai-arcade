"""Grade the cabinet catalog. A game is scored, bootable, or listed and not startable.

Empty RetroPie folders are not in the catalog, so they are not invented here.
Zip and raw copies of one title collapse to a single row. The raw image wins.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from games.lab.integrations.smb_1_1 import INTEGRATION as SMB
from games.lab.paths import REPO_ROOT

# Lower is better. A loose zip loses to the raw image the core can open directly.
_SUFFIX_RANK = {
    ".nes": 0,
    ".a26": 0,
    ".bin": 0,
    ".fds": 1,
    ".zip": 5,
    ".7z": 6,
}

_REASONS = {
    "arcade": "Arcade sets use four MAME builds and are not in the gym yet.",
    "sega32x": "32X waits on a Picodrive smoke test.",
    "ports": "Ports are native programs, not a console frame.",
    "trs-80": "TRS-80 is a keyboard and disks, not a joystick gym.",
    "zmachine": "Zork is text and has its own observatory.",
    "retropie": "The RetroPie menu is settings, not a game.",
}
_PLAYABLE = {"nes": "fceumm", "atari2600": "stella2014"}


@dataclass(frozen=True)
class Game:
    id: str
    system: str
    name: str
    path: str
    grade: str
    reason: str
    integration: str | None
    core: str | None

    @property
    def selectable(self) -> bool:
        return self.grade in ("scored", "bootable")

    def to_json(self) -> dict:
        data = asdict(self)
        data["selectable"] = self.selectable
        return data


def _stem(path: str) -> str:
    name = path.rstrip("/").rsplit("/", 1)[-1]
    dot = name.rfind(".")
    return name[:dot] if dot > 0 else name


def _slug(stem: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", stem.casefold()).strip("-")
    return slug or "game"


def _suffix_rank(path: str) -> int:
    suffix = Path(path).suffix.lower()
    return _SUFFIX_RANK.get(suffix, 3)


def _entries(document: dict):
    body = document.get("catalog", document)
    for system in body.get("systems", []):
        system_name = system.get("name") or ""
        entries = system.get("entries") or system.get("games") or []
        for entry in entries:
            if entry.get("type", "game") != "game":
                continue
            path = entry.get("path") or ""
            if not path:
                continue
            yield {
                "system": entry.get("source_system") or system_name,
                "name": entry.get("name") or _stem(path),
                "path": path,
            }


def _grade(system: str, stem: str) -> tuple[str, str, str | None, str | None]:
    if SMB.matches(system, stem):
        return "scored", "", SMB.id, _PLAYABLE["nes"]
    core = _PLAYABLE.get(system)
    if core:
        return "bootable", "", None, core
    reason = _REASONS.get(system, "No libretro core for this system yet.")
    return "unavailable", reason, None, None


def games_from(document: dict) -> list[Game]:
    """Dedupe and grade. Order is the catalog order of each title's first copy."""
    grouped: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for entry in _entries(document):
        key = (entry["system"], _stem(entry["path"]).casefold())
        if key not in grouped:
            grouped[key] = entry
            order.append(key)
            continue
        if _suffix_rank(entry["path"]) < _suffix_rank(grouped[key]["path"]):
            grouped[key] = entry

    games = []
    used: dict[str, int] = {}
    for key in order:
        entry = grouped[key]
        system, stem = key
        grade, reason, integration, core = _grade(system, stem)
        base = f"{system}/{_slug(stem)}"
        used[base] = used.get(base, 0) + 1
        game_id = base if used[base] == 1 else f"{base}-{used[base]}"
        games.append(Game(
            id=game_id,
            system=system,
            name=entry["name"],
            path=entry["path"],
            grade=grade,
            reason=reason,
            integration=integration,
            core=core,
        ))
    return games


def load_path(path: Path) -> list[Game]:
    return games_from(json.loads(path.read_text(encoding="utf-8")))


def default_catalog_path() -> Path | None:
    folder = REPO_ROOT / ".manifests" / "es-catalog"
    files = sorted(folder.glob("*.json")) if folder.is_dir() else []
    return files[-1] if files else None


def by_id(games: list[Game]) -> dict[str, Game]:
    return {game.id: game for game in games}
