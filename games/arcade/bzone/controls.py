"""Battlezone's controls by name, and what each is on the cabinet (tools/configure_mame_controller.py, `bzone`).

An action is the set of names to hold until the next decision replaces it; an empty set holds nothing.
"""
CONTROLS = {
    "LEFT_FORWARD": (1, "UP"),  # the left tread on Player 1's stick
    "LEFT_BACK": (1, "DOWN"),
    "RIGHT_FORWARD": (2, "UP"),  # the right tread on Player 2's stick
    "RIGHT_BACK": (2, "DOWN"),
    "FIRE": (1, "BUTTON_1"),
}
# the treads together, for reading a log: both forward drives, opposite ways turn on the spot
DRIVE = frozenset({"LEFT_FORWARD", "RIGHT_FORWARD"})
REVERSE = frozenset({"LEFT_BACK", "RIGHT_BACK"})
TURN_LEFT = frozenset({"LEFT_BACK", "RIGHT_FORWARD"})
TURN_RIGHT = frozenset({"LEFT_FORWARD", "RIGHT_BACK"})
# one tread forward: turning while moving (the right tread alone turns left)
ARC_LEFT = frozenset({"RIGHT_FORWARD"})
ARC_RIGHT = frozenset({"LEFT_FORWARD"})


def broker_actions(names):
    """The broker's (player, action) pairs for these control names."""
    unknown = set(names) - set(CONTROLS)
    if unknown:
        raise ValueError(f"unknown controls {sorted(unknown)}")
    return {CONTROLS[n] for n in names}


def describe(names):
    """A held set in words, for logs and explanations."""
    names = frozenset(names)
    treads = names - {"FIRE"}
    words = {DRIVE: "drive forward", REVERSE: "drive backward", TURN_LEFT: "turn left", TURN_RIGHT: "turn right",
             ARC_LEFT: "arc left", ARC_RIGHT: "arc right",
             frozenset(): "treads still"}.get(treads, " + ".join(sorted(treads)))
    return words + (" + fire" if "FIRE" in names else "")
