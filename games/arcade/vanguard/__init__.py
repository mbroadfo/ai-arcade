"""Vanguard (SNK 1981, MAME romset "vanguard", MAME 0.251).

Workshop stages 0-2 (docs/GAME_WORKSHOP.md): what the Pi streams. Work RAM is 0x0000-0x03FF. MAME marks the driver
"imperfect", so it opens on a warning screen that holds every script until a key is pressed (start-up tools tap one).
README.md says what is checked and what comes next. S1M makes every decision; code supplies state and executes.
"""
from .state import IMAGE, decode  # noqa: F401

REGIONS = [(0x0000, 0x03FF)]
AGENT_REGIONS = REGIONS
SETTINGS = {}  # operator settings: none yet (coinage is left at the factory setting)
COINS_PER_PLAY = 1
