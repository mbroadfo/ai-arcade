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
# MAME (SDL) started for an AI run must see only the AI Arcade pads: they are then joysticks 1 and 2, which is where the
# aiarcade controller file (tools/configure_mame_controller.py) puts coin, start and the sticks. Without it the panel's
# encoders and any gamepad come first and the AI's presses reach nobody. Every tool that starts MAME for the broker uses it.
AI_PADS_ENV = "SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT=0x1209/0xa101,0x1209/0xa102"
# The cabinet Pi (Raspberry Pi 5 since 2026-10-02; the Pi 3 at 192.168.10.155 is the spare). Override with ARCADE_PI_HOST.
DEFAULT_PI_HOST = os.environ.get("ARCADE_PI_HOST", "192.168.10.122")


def pi_rompath(system):
    """MAME's -rompath on the Pi, quoted for the shell: sets made for MAME 0.251 first (rebuilt, or built with files
    from newer sets by tools/add_rom_files.py), then the cabinet's own folder for the system."""
    return f"'/home/pi/RetroPie/mame-0251/roms;/home/pi/RetroPie/roms/{system}'"


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
