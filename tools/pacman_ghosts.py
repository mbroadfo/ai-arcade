"""Ghost movement forecast, following the original ROM's rules.

Source: ablackett82/pacman actors.js (differential-tested against the ROM), cross-checked
against the Pac-Man Dossier. At each tile a ghost picks the exit whose neighbouring tile is
nearest (squared distance) to its target tile. It never reverses or enters a wall; ties go to the
later of right, down, left, up. Tiles are (l, h) pairs (docs/PACMAN_RAM_MAP.md).

Simplifications, all listed so nobody mistakes this for a full simulator:
- Pac-Man is held at his current tile and heading while forecasting (targets stay fixed).
- Frightened ghosts move pseudo-randomly in the ROM; they are not forecast.
- Ghosts inside the house are not forecast.
- Ghost-house exit and re-entry (around the door tile) are not modelled; paths through there are unreliable.

Special tiles (found by comparing this module with ~3,000 recorded ghost decisions, then matching the
ROM's behaviour): ghosts may not turn UP on four tiles near the house and Pac-Man's start, and make no
choice in the tunnel row (they go straight).
"""
from pacman_maze import MOVES, step

ORDER = ("RIGHT", "DOWN", "LEFT", "UP")  # ROM direction numbers 0..3; ties go to the LATER one
# Direction vectors as the ROM's 16-bit (h << 8 | l) words: right (0,-1), down (1,0), left (0,1), up (-1,0)
VECTOR_WORD = {"RIGHT": 0xFF00, "DOWN": 0x0001, "LEFT": 0x0100, "UP": 0x00FF}
SCATTER_TARGETS = {"red": (0x1D, 0x22), "pink": (0x1D, 0x39), "blue": (0x40, 0x20), "orange": (0x40, 0x3B)}
DOOR_TARGET = (0x2C, 0x2E)  # where eaten ghosts (eyes) head
GHOST_NAMES = ("red", "pink", "blue", "orange")
OPPOSITE = {"RIGHT": "LEFT", "LEFT": "RIGHT", "UP": "DOWN", "DOWN": "UP"}
LOWER = {"right": "RIGHT", "down": "DOWN", "left": "LEFT", "up": "UP"}


def to_word(tile):
    return ((tile[1] & 0xFF) << 8) | (tile[0] & 0xFF)


def from_word(word):
    return (word & 0xFF, (word >> 8) & 0xFF)


def sq_dist(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def pacman_heading(state):
    return LOWER.get(state.pacman.direction, "LEFT")


def is_scatter(state):
    """The ROM's scatter test: phase counter even and normal play."""
    return state.phase % 2 == 0 and state.substate == 3


def targets(state):
    """Each ghost's target tile under the ROM's rules, from the current state."""
    pac = state.pacman.tile
    heading = pacman_heading(state)
    scatter = is_scatter(state)

    pinky_word = (VECTOR_WORD[heading] * 4 + to_word(pac)) & 0xFFFF
    ahead2 = (VECTOR_WORD[heading] * 2 + to_word(pac)) & 0xFFFF
    blinky_next = to_word(state.ghosts["red"].next_tile)
    inky = (
        (2 * (ahead2 & 0xFF) - (blinky_next & 0xFF)) & 0xFF,
        (2 * (ahead2 >> 8) - (blinky_next >> 8)) & 0xFF,
    )
    clyde_near = sq_dist(pac, state.ghosts["orange"].next_tile) < 0x40  # within 8 tiles

    return {
        "red": SCATTER_TARGETS["red"] if scatter and not state.elroy else pac,
        "pink": SCATTER_TARGETS["pink"] if scatter else from_word(pinky_word),
        "blue": SCATTER_TARGETS["blue"] if scatter else inky,
        "orange": SCATTER_TARGETS["orange"] if scatter or clyde_near else pac,
    }


# Ghosts in chase/scatter mode may not turn up here: two tiles above the house, two above Pac-Man's start.
NO_UP_TILES = {(44, 44), (44, 47), (56, 44), (56, 47)}


def in_tunnel(tile):
    """The wrap-around tunnel row (l = 47) toward either edge: ghosts make no choices here."""
    return tile[0] == 47 and (tile[1] >= 0x3B or tile[1] <= 0x20)


def choose_exit(maze, tile, arriving, target):
    """The ROM's direction choice at `tile` for a ghost that arrived heading `arriving`."""
    if in_tunnel(tile) and arriving:
        return arriving
    best, best_dist = None, None
    for direction in ORDER:
        if direction == OPPOSITE.get(arriving):
            continue
        if direction == "UP" and tile in NO_UP_TILES:
            continue
        neighbour = step(tile, direction)
        if not maze.passable(neighbour):
            continue
        d = sq_dist(neighbour, target)
        if best_dist is None or d <= best_dist:  # <=: later of the four wins ties
            best, best_dist = direction, d
    return best


def direction_between(a, b):
    for name, (dl, dh) in MOVES.items():
        if (a[0] + dl, a[1] + dh) == tuple(b):
            return name
    return None


def forecast(state, maze, steps=12):
    """Predicted tile sequence for each ghost, starting with the tile it enters next.

    Returns {name: [tiles] or None}. None for ghosts that are frightened (random) or that sit in the house.
    """
    aim = targets(state)
    paths = {}
    for name in GHOST_NAMES:
        ghost = state.ghosts[name]
        if state.frightened[name]:
            paths[name] = None
            continue
        target = DOOR_TARGET if state.eyes[name] else aim[name]
        here, nxt = tuple(ghost.tile), tuple(ghost.next_tile)
        if not maze.passable(here) or not maze.passable(nxt):
            paths[name] = None
            continue
        arriving = direction_between(here, nxt) or LOWER.get(ghost.direction)
        tiles, tile = [nxt], nxt
        for _ in range(steps - 1):
            exit_dir = choose_exit(maze, tile, arriving, target)
            if exit_dir is None:
                break
            tile = step(tile, exit_dir)
            if not (0x20 <= tile[0] <= 0x3F and 0x1E <= tile[1] <= 0x3D):
                break  # left the maze through the tunnel; the wrap-around is not forecast
            tiles.append(tile)
            arriving = exit_dir
        paths[name] = tiles
    return paths


def collision_step(own_path, ghost_paths, tolerance=1):
    """Earliest step at which a ghost is on (or crosses) Pac-Man's own path, else None.

    own_path[i] is where Pac-Man would be after i+1 steps. A ghost forecast hit counts if it occupies
    the same tile within `tolerance` steps of the same time (they move at similar speeds).
    """
    best = None
    for path in ghost_paths.values():
        if not path:
            continue
        for i, tile in enumerate(own_path):
            for j in range(max(0, i - tolerance), min(len(path), i + tolerance + 1)):
                if path[j] == tile:
                    best = i + 1 if best is None else min(best, i + 1)
    return best
