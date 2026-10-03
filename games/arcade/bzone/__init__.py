"""Battlezone (Atari 1980, MAME romset "bzonea", rev 1; built for MAME 0.251 with tools/add_rom_files.py).

Rev 1 is the cabinet's own copy (human mode) and the revision Atari's source reassembles to byte for byte; rev 2
(`bzone`) differs only in its high-score table display, which drew slanted. The RAM map is the same for both.

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
# The video for the Observatory is MAME's rendered snapshot (a vector screen draws nothing into the screen bitmap):
# rendered at this size and scaled smoothly on the page. 640 x 480 looked jagged scaled up.
VIDEO_SIZE = (960, 720)
VIDEO_FPS = 20  # every other frame of the screen's 41 a second

# No model plays Battlezone yet: the Observatory offers its real-time lab instead (tools/ai_setup.py), runs of code
# policies on a fixed-rate clock, labelled as code (scripts/lab.py, policies.py).
LAB = {"default_policy": "track_and_fire", "default_hz": 10, "hz_range": (1, 40)}


def lab_policies():
    """The policies for the setup panel, grouped, each with what it does and (for baselines) what it is for."""
    from .policies import POLICIES, POLICY_INFO
    out = []
    for name, f in POLICIES.items():
        info = POLICY_INFO.get(name, {})
        out.append({"value": name, "label": info.get("label", name.replace("_", " ")),
                    "group": info.get("group", "Other"), "tag": info.get("tag"),
                    "help": (f.__doc__ or name).strip().splitlines()[0],
                    "purpose": info.get("purpose"), "limitation": info.get("limitation")})
    return out


# The setup panel shows the baselines a player is measured against first, then the diagnostics
LAB_GROUPS = ("Targeting baselines", "Movement", "Observation / weapons")
# What a lab run reports when it ends (scripts/summarize.py), shown in the setup panel
LAB_MEASURES = ["Score", "Kills", "Lives lost", "Survival time", "Shots fired", "Distance moved",
                "Time stationary while the enemy may fire", "Enemy shots survived"]


def lab_main(argv):
    """Run the lab with these arguments (tools/run_lab.py)."""
    from .scripts.lab import main
    return main(argv)
