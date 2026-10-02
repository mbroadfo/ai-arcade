"""Pac-Man's own facts for the shared player (arcadekit.kits.pacman_board.spec.Spec). Everything else is shared."""
from arcadekit.kits.pacman_board.spec import Spec

RULES_L1 = """\
PAC-MAN RULES
You steer Pac-Man through a maze. You hold one of four directions (UP, DOWN, LEFT, RIGHT); Pac-Man keeps moving that way until a wall stops him. He may turn or reverse at any time.
- Pac-Man eats dots (10 points) by passing over them. Eating every dot clears the level. Energizers (4 big dots, 50 points) turn the ghosts blue for a short time.
- A bonus fruit appears in the middle of the maze, below the ghost house, after 70 and again after 170 dots are eaten. It vanishes after a few seconds. Eating it scores bonus points (100 on level 1).
- Four ghosts roam the maze: Red, Pink, Blue, Orange. A normal ghost touching Pac-Man costs a life. Ghosts move at about Pac-Man's speed, so a ghost behind you stays behind you but one ahead of you must be avoided.
- While blue (frightened), ghosts are harmless and can be eaten: 200, then 400, 800, 1600 points for each in a row. An eaten ghost shows only eyes and hurries home, harmless. Blue ghosts wander randomly and are slower.
- Ghosts never reverse on their own; at a junction they pick among the other exits. They all reverse when the mode changes (scatter to chase, or an energizer being eaten).
- The wrap-around tunnel in the middle row leads from one side of the maze to the other; ghosts are slow in it.
- A dead end is a trap. A junction with a ghost near on every side is a trap. Prefer exits with open room behind them.
- Goal: score as much as possible without losing lives. Survival beats dots. Eat blue ghosts only when it is safe.
"""

GHOST_BEHAVIOUR_L3A = """\
HOW THE GHOSTS CHOOSE (they are not random while normal)
Every ghost, at each tile, looks at the exits it may take (never straight back) and picks the one whose next tile is closest in a straight line to its TARGET tile. It does not plan ahead.
- Red chases Pac-Man's own tile.
- Pink aims 4 tiles in front of Pac-Man (a quirk: when Pac-Man faces UP she aims 4 up and 4 left).
- Blue aims at the point opposite Red: take the tile 2 in front of Pac-Man and mirror Red's position through it.
- Orange chases like Red until he is within 8 tiles of Pac-Man, then heads for his own corner (bottom left) instead.
- In scatter phases (which alternate with chase phases) ghosts ignore Pac-Man and head for their own corner of the maze. Red chases anyway once most dots are gone.
So a ghost's route follows from where Pac-Man is and which way he faces: a ghost that is far away can still be steered into a loop by where you go.
"""


def in_tunnel(maze, tile):
    """The wrap-around tunnel row (l = 47) toward either edge: ghosts make no choices here."""
    return tile[0] == 47 and (tile[1] >= 0x3B or tile[1] <= 0x20)


SPEC = Spec(
    name="Pac-Man",
    pronoun="he",
    ghost_labels={"red": "Red (Blinky)", "pink": "Pink (Pinky)", "blue": "Blue (Inky)", "orange": "Orange (Clyde)"},
    rules_l1=RULES_L1,
    ghost_behaviour_l3a=GHOST_BEHAVIOUR_L3A,
    scatter_targets={"red": (0x1D, 0x22), "pink": (0x1D, 0x39), "blue": (0x40, 0x20), "orange": (0x40, 0x3B)},
    door_target=(0x2C, 0x2E),
    in_tunnel=in_tunnel,
    # ghosts in chase/scatter mode may not turn up here: two tiles above the house, two above Pac-Man's start
    no_up_tiles=frozenset({(44, 44), (44, 47), (56, 44), (56, 47)}),
    # the refuge (--refuge): the top of the stub right of the block above the start; push UP into the wall to stay
    safe_spot=(53, 44),
)
