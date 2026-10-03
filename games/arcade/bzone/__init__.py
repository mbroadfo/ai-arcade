"""Battlezone (Atari 1980, MAME romset "bzone", rev 2; built for MAME 0.251 with tools/add_rom_files.py).

Workshop stages 0-2 (docs/GAME_WORKSHOP.md): what the Pi streams. The 6502's work RAM is 0x0000-0x03FF (MAME's
bzone driver memory map, `mame` provenance); vector RAM (0x2000-0x2FFF) and the math box are not read yet.
README.md says what is checked and what comes next.
"""
from .state import IMAGE, decode  # noqa: F401  (IMAGE: the RAM window decode() reads)

REGIONS = [(0x0000, 0x03FF)]  # all of work RAM, every frame (validation and discovery)
AGENT_REGIONS = REGIONS  # 1 KB a frame; narrowed once the RAM map is known

# Operator settings (DIP switches) AI mode applies by MAME's names (tools/mame_settings.lua); every other switch is at
# its factory default, and the run records them all. Coins are not part of the experiment: free play (the factory
# setting is 2 coins, 1 credit). Lives stay at the factory 3.
SETTINGS = {"Coinage": "Free Play"}
COINS_PER_PLAY = 0  # with SETTINGS applied: START alone begins a game

# No model plays Battlezone yet: the Observatory offers its real-time lab instead (tools/ai_setup.py), runs of code
# policies on a fixed-rate clock, labelled as code (scripts/lab.py, policies.py).
LAB = {"default_policy": "track_and_fire", "default_hz": 10, "hz_range": (1, 40)}


def lab_policies():
    """{name: what it does} for the AI setup panel."""
    from .policies import POLICIES
    return {name: (f.__doc__ or name.replace("_", " ")).strip().splitlines()[0] for name, f in POLICIES.items()}


def lab_main(argv):
    """Run the lab with these arguments (tools/run_lab.py)."""
    from .scripts.lab import main
    return main(argv)
