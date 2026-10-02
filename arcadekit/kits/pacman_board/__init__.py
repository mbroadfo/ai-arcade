"""Games built on Pac-Man's program and board (MAME driver pacman.cpp): Pac-Man, Ms. Pac-Man, and their kin.

Ms. Pac-Man keeps Pac-Man's code at 0000-3FFF and adds its own on an auxiliary board at 8000-9FFF; the work-RAM
variables (4C00-4FFF) and the video-RAM maze layout are the same (games/arcade/mspacman/RAM_MAP.md). So the decoder and
the maze reader live here, and each game keeps what differs: its mazes' quirks, ghost behaviour, safe spots, knowledge.

    state   AGENT_REGIONS, REGIONS, IMAGE, decode(image) -> PacmanState
    maze    Maze (tiles, exits, BFS, the walk to the next decision point), MOVES, OPPOSITE, step
"""
