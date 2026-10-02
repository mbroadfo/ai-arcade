"""Ms. Pac-Man (Midway, MAME romset "mspacman"). Workshop stages 0-2 so far: feasibility, controls, state.

It runs Pac-Man's program with its own additions on an auxiliary board, so the work-RAM variables and the maze layout in
video RAM are Pac-Man's (RAM_MAP.md): the decoder is the shared one in arcadekit.kits.pacman_board. There is no player,
decider or knowledge of its own yet; README.md says what is checked and what comes next.
"""
from arcadekit.kits.pacman_board.state import AGENT_REGIONS, IMAGE, REGIONS, decode  # noqa: F401
