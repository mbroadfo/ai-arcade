"""Where things are on the upright 224 x 288 screen, for the Observatory's overlay. Display only: nothing decides with it.

Tiles are (l, h) as in maze.py: l counts rows downward from screen row 2 (0x20), h counts columns leftward from column 27
(0x20). Video RAM holds the playfield column by column from the right, which is why h runs right to left.
"""
CELL = 8
SIZE = (224, 288)
# x = a*l + b*h + c, y = d*l + e*h + f: the centre of tile (l, h) in screen pixels
TILE_TO_PX = [[0, -CELL, (0x3B * CELL) + CELL // 2], [CELL, 0, (2 - 0x20) * CELL + CELL // 2]]
# an actor's position bytes (l, h) are pixels along the same axes; the offsets were measured against MAME's screen
POS_TO_PX = [[0, -1, 241], [1, 0, 16]]
COLOURS = {"red": "#ff2a2a", "pink": "#ffb8ff", "blue": "#2ef2ff", "orange": "#ffb852"}
FRIGHTENED = "#3b5bff"


def apply(matrix, pair):
    (a, b, c), (d, e, f) = matrix
    return (a * pair[0] + b * pair[1] + c, d * pair[0] + e * pair[1] + f)


def marks(state, steps, name, labels):
    """Screen marks for the player and each ghost. steps: tile -> path steps from the player (only reachable tiles)."""
    x, y = apply(POS_TO_PX, state.pacman.pos)
    out = [{"label": name, "kind": "player", "x": x, "y": y, "colour": "#ffe600"}]
    for key, ghost in state.ghosts.items():
        kind = "eyes" if state.eyes[key] else "prey" if state.frightened[key] else "threat"
        x, y = apply(POS_TO_PX, ghost.pos)
        out.append({"label": labels.get(key, key), "kind": kind, "x": x, "y": y, "steps": steps.get(ghost.tile),
                    "colour": FRIGHTENED if kind == "prey" else COLOURS.get(key, "#ffffff")})
    return out
