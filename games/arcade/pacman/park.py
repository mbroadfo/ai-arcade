"""The safe spot, used inside the ambush goal.

Known from play: with all four ghosts out of the house, Pac-Man can wait pushing UP into the wall at the top of the
stub to the right of the block above his start, and the ghosts gather around instead of catching him. He stops there
only because the wall stops him: the game has no wait button, and the stub's top is a corner with a wall above.
(The tile was named by the player; whether it is really safe in this build is what the park counters are for.)

Ambush with parking: head for the spot (the option scoring pulls toward it, features.lure_score), hold UP against the
wall while the ghosts come in, and when enough have gathered leave for the energizer. The survival reflex is off
while parked: that is the point of the experiment, and the log says what happened.
"""
SAFE_SPOT = (53, 44)  # tile (l, h): one stub up the right-hand side of the block above the start, corner, wall above
PUSH = "UP"  # hold this into the wall to stay put
GATHER = 3  # leave when this many normal ghosts are within LURE_RADIUS steps
MAX_SECONDS = 12.0  # ... or after waiting this long


def all_out(state, here):
    """Every ghost is in the maze and alive: none in the ghost house (not reachable from here), none as eyes."""
    return all(not state.eyes[name] and g.tile in here for name, g in state.ghosts.items())


def gathered(state, here, radius):
    """Normal (dangerous) ghosts within `radius` steps."""
    return sum(1 for name, g in state.ghosts.items()
               if not state.frightened[name] and not state.eyes[name] and here.get(g.tile, 99) <= radius)
