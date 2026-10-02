"""Waiting, without a wait button. Two separate ideas that both use it.

Pac-Man stops only when his heading runs into a wall; holding that heading keeps him there. So "parking" is
"arrive at a tile with a wall straight ahead and keep pushing the same way".

1. Parking near an energizer (`--park`, ambush only). Waiting for the ghosts to gather, he used to pace back and forth
   near the pellet, losing time and nearness. Instead he goes to a wall-stop tile a few steps from the pellet and holds
   there, then goes and eats it once ghosts have gathered (the usual ambush rule).

2. The refuge (`--refuge`, any goal), for a game whose spec names a safe spot (Pac-Man: the top of the stub to the
   right of the block above his start, tile (53, 44), pushing UP into the wall). With all four ghosts out of the house it
   is a quick hideaway when ghosts are close; it earns nothing. He runs there if he can get there first, waits until the
   ghosts have gone away, and leaves. The tile was named by the player; the refuge counters say whether it holds up.

The survival reflex does not steer while he is parked: the point of both is to stay put. The log says what happened.
"""
from .maze import ENERGIZER, MOVES, OPPOSITE, step

# --- parking near an energizer
HOVER_MIN, HOVER_MAX = 3, 8  # a stop this many steps from the pellet (near enough to dash, far enough not to be trapped)
HOVER_SECONDS = 10.0  # give up waiting for the ghosts after this long

# --- the refuge
REFUGE_TRIGGER = 8  # a normal ghost this close (steps) sends him there ...
REFUGE_RANGE = 12  # ... if the spot is no further than this
REFUGE_MARGIN = 2  # ... and no ghost can be on his route or at the spot within this many steps of when he is
REFUGE_CLEAR = 12  # he leaves when no normal ghost is within this many steps of the spot
REFUGE_SECONDS = 15.0  # ... or after this long


def normal_ghosts(state):
    return [g for name, g in state.ghosts.items() if not state.frightened[name] and not state.eyes[name]]


def all_out(state, here):
    """Every ghost is in the maze and alive: none in the ghost house (not reachable from here), none as eyes."""
    return all(not state.eyes[name] and g.tile in here for name, g in state.ghosts.items())


def gathered(state, here, radius):
    """Normal (dangerous) ghosts within `radius` steps."""
    return sum(1 for g in normal_ghosts(state) if here.get(g.tile, 99) <= radius)


def nearest_normal(state, here):
    steps = [here[g.tile] for g in normal_ghosts(state) if g.tile in here]
    return min(steps) if steps else None


def is_stop(maze, tile, heading):
    """Heading `heading` at `tile` runs into a wall, he can have arrived that way, and the tile is not a dead end."""
    return (maze.passable(tile) and not maze.passable(step(tile, heading))
            and maze.passable(step(tile, OPPOSITE[heading])) and len(maze.exits(tile)) >= 2)


def nearest_energizer(maze, here):
    found = [(d, t) for t, d in here.items() if maze.code(t) == ENERGIZER]
    return min(found)[1] if found else None


def hover_stop(maze, energizer):
    """The wall-stop tile to wait at for this energizer: (tile, heading into the wall), nearest in range, or None."""
    from_pellet = maze.bfs(energizer)
    best = None
    for tile, d in from_pellet.items():
        if HOVER_MIN <= d <= HOVER_MAX:
            for heading in MOVES:
                if is_stop(maze, tile, heading) and (best is None or (d, tile, heading) < best):
                    best = (d, tile, heading)
    return None if best is None else (best[1], best[2])


def refuge_move(state, maze, me, safe_spot):
    """The direction to take toward the refuge at `safe_spot`, or None (not needed, too far, or a ghost would get
    there first)."""
    me = tuple(me)
    if me == safe_spot:
        return None
    here = maze.bfs(me)
    if not all_out(state, here):
        return None
    near = nearest_normal(state, here)
    if near is None or near > REFUGE_TRIGGER:
        return None
    to_spot = maze.bfs(safe_spot)
    if to_spot.get(me, 99) > REFUGE_RANGE:
        return None
    route, tile = [], me  # walk downhill to the spot: the shortest way
    while tile != safe_spot:
        tile = min((step(tile, d) for d in MOVES if maze.passable(step(tile, d))), key=lambda t: to_spot.get(t, 99))
        route.append(tile)
    for ghost in normal_ghosts(state):  # nobody may be on the route, or at the spot, when he gets there
        reach = maze.bfs(ghost.tile)
        if any(reach.get(t, 99) < k + REFUGE_MARGIN for k, t in enumerate(route, start=1)):
            return None
    return next(d for d in MOVES if step(me, d) == route[0])
