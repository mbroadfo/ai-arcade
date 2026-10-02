"""Find and load a game package. Games live in games/<system>/<name>/, where <system> is the
EmulationStation system folder name (arcade, nes, atari2600, ...).

    game = load_game("arcade/pacman")

Importing this module also puts the repository root on sys.path so `games.*` can be imported.
A game package must provide: AGENT_REGIONS, IMAGE, decode(image), score_option (for the mock model),
and the submodules player, deciders, knowledge. See games/README.md.
"""
import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_GAME = "arcade/pacman"
# The cabinet Pi (Raspberry Pi 5 since 2026-10-02; the Pi 3 at 192.168.10.155 is the spare). Override with ARCADE_PI_HOST.
DEFAULT_PI_HOST = os.environ.get("ARCADE_PI_HOST", "192.168.10.122")


def split_spec(spec):
    system, _, name = spec.partition("/")
    if not system or not name or "/" in name:
        raise ValueError(f"game must look like <system>/<name>, e.g. {DEFAULT_GAME}; got {spec!r}")
    return system, name


def game_dir(spec):
    system, name = split_spec(spec)
    return ROOT / "games" / system / name


def load_game(spec=DEFAULT_GAME):
    system, name = split_spec(spec)
    return importlib.import_module(f"games.{system}.{name}")


def load_profile(spec=DEFAULT_GAME):
    """The game's profile.json (ROM set, controls); the ROM set is what MAME is launched with."""
    return json.loads((game_dir(spec) / "profile.json").read_text())
