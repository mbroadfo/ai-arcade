"""Pac-Man maze queries over a 4096-byte RAM image (0x4000-0x4FFF). Pure functions, no I/O.

Tiles are (l, h) pairs as in docs/PACMAN_RAM_MAP.md: `l` rises downward, `h` rises leftward.
Maze tile codes come from video RAM: 0x10 dot, 0x14 energizer, 0x40 blank, wall = (code & 0xC0) == 0xC0.
"""
from collections import deque

BASE = 0x4000
DOT, ENERGIZER, BLANK = 0x10, 0x14, 0x40
# Direction -> (delta_l, delta_h); vector table $32FF: right h-1, down l+1, left h+1, up l-1.
MOVES = {"RIGHT": (0, -1), "DOWN": (1, 0), "LEFT": (0, 1), "UP": (-1, 0)}
OPPOSITE = {"RIGHT": "LEFT", "LEFT": "RIGHT", "UP": "DOWN", "DOWN": "UP"}
LOWER_TO_UPPER = {"right": "RIGHT", "down": "DOWN", "left": "LEFT", "up": "UP"}


def step(tile, direction):
    dl, dh = MOVES[direction]
    return (tile[0] + dl, tile[1] + dh)


class Maze:
    def __init__(self, image):
        if len(image) < 0x1000:
            raise ValueError("expected a 4096-byte RAM image")
        self.image = image

    @staticmethod
    def _addr(l, h):
        return (0x4040 + (h - 0x20) * 32 + (l - 0x20)) & 0xFFFF

    def code(self, tile):
        return self.image[self._addr(*tile) - BASE]

    def passable(self, tile):
        l, h = tile
        return 0x20 <= l <= 0x3F and 0x1E <= h <= 0x3D and self.code(tile) in (DOT, ENERGIZER, BLANK)

    def has_food(self, tile):
        return self.passable(tile) and self.code(tile) in (DOT, ENERGIZER)

    def exits(self, tile):
        """Directions that lead to a passable neighbour tile."""
        return [d for d in MOVES if self.passable(step(tile, d))]

    def bfs(self, start, blocked=frozenset()):
        """Steps from `start` to every reachable tile, not entering `blocked` tiles."""
        dist = {start: 0}
        queue = deque([start])
        while queue:
            tile = queue.popleft()
            for d in MOVES:
                nxt = step(tile, d)
                if nxt not in dist and nxt not in blocked and self.passable(nxt):
                    dist[nxt] = dist[tile] + 1
                    queue.append(nxt)
        return dist

    def food_left(self):
        return sum(1 for l in range(0x20, 0x40) for h in range(0x1E, 0x3E) if self.has_food((l, h)))

    def walk_to_decision(self, tile, heading, limit=60):
        """Follow the corridor from `tile` going `heading` until a real choice is needed.

        Corners with a single way on are followed automatically (forced moves need no model).
        Returns (decision_tile, steps_away, directions) where directions[i] is the move to make
        on step i. decision_tile is None if the corridor runs out within `limit` steps (dead end).
        A tile where Pac-Man can go two or more ways other than back is a decision tile.
        """
        directions, current, arrived = [], tile, heading
        for steps in range(limit):
            options = [d for d in self.exits(current) if d != OPPOSITE.get(arrived)]
            if len(options) >= 2:
                return current, steps, directions
            if not options:
                return None, steps, directions
            move = arrived if arrived in options else options[0]
            directions.append(move)
            current, arrived = step(current, move), move
        return None, limit, directions
