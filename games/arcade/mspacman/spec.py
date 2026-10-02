"""Ms. Pac-Man's own facts for the shared player (arcadekit.kits.pacman_board.spec.Spec).

Sources: the commented disassembly and community descriptions (RAM_MAP.md). What is not checked on Ms. Pac-Man yet is
said so here and in the texts: the corner targets and the door are Pac-Man's (shared code); no no-up tiles are known.
"""
from arcadekit.kits.pacman_board.spec import Spec

RULES_L1 = """\
MS. PAC-MAN RULES
You steer Ms. Pac-Man through a maze. You hold one of four directions (UP, DOWN, LEFT, RIGHT); Ms. Pac-Man keeps moving that way until a wall stops her. She may turn or reverse at any time.
- Ms. Pac-Man eats dots (10 points) by passing over them. Eating every dot clears the level. Energizers (4 big dots, 50 points) turn the ghosts blue for a short time.
- There are four different mazes; the maze changes every few levels. Each maze has wrap-around tunnels at the sides that lead to the other side.
- A bonus fruit enters through a tunnel, wanders around the maze and leaves again. Eating it scores bonus points.
- Four ghosts roam the maze: Red, Pink, Blue, Orange. A normal ghost touching Ms. Pac-Man costs a life. Ghosts move at about her speed, so a ghost behind you stays behind you but one ahead of you must be avoided.
- While blue (frightened), ghosts are harmless and can be eaten: 200, then 400, 800, 1600 points for each in a row. An eaten ghost shows only eyes and hurries home, harmless. Blue ghosts wander randomly and are slower.
- A dead end is a trap. A junction with a ghost near on every side is a trap. Prefer exits with open room behind them.
- Goal: score as much as possible without losing lives. Survival beats dots. Eat blue ghosts only when it is safe.
"""

GHOST_BEHAVIOUR_L3A = """\
HOW THE GHOSTS CHOOSE
Every ghost, at each tile, looks at the exits it may take (never straight back) and picks the one whose next tile is closest in a straight line to its TARGET tile. It does not plan ahead.
- Red chases Ms. Pac-Man's own tile.
- Pink aims 4 tiles in front of Ms. Pac-Man.
- Blue aims at the point opposite Red: take the tile 2 in front of Ms. Pac-Man and mirror Red's position through it.
- Orange chases like Red until she is within 8 tiles of Ms. Pac-Man, then heads for her own corner instead.
- Unlike Pac-Man, Red and Pink move at random for the first seconds of each level, so their routes cannot be predicted then.
"""


def in_tunnel(maze, tile):
    """A wrap-around tunnel: an open tile beyond the maze's side walls (each maze has its own tunnel rows)."""
    return maze is not None and maze.passable(tile) and (tile[1] >= 0x3B or tile[1] <= 0x20)


SPEC = Spec(
    name="Ms. Pac-Man",
    pronoun="she",
    ghost_labels={"red": "Red (Blinky)", "pink": "Pink (Pinky)", "blue": "Blue (Inky)", "orange": "Orange (Sue)"},
    rules_l1=RULES_L1,
    ghost_behaviour_l3a=GHOST_BEHAVIOUR_L3A,
    scatter_targets={"red": (0x1D, 0x22), "pink": (0x1D, 0x39), "blue": (0x40, 0x20), "orange": (0x40, 0x3B)},
    door_target=(0x2C, 0x2E),
    in_tunnel=in_tunnel,
    forecast_note="(Red and Pink move at random for the first seconds of a level; their routes are unreliable then.)",
)
