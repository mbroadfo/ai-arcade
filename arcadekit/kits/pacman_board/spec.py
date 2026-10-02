"""What a game on Pac-Man's board supplies to the shared player: everything that differs between Pac-Man and its kin.

The shared modules take a Spec wherever a game's own facts matter; a game builds one Spec (games/<system>/<name>/spec.py)
and binds the shared modules to it (bind.py). Anything not here is the same program and lives once, in this kit.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass(frozen=True)
class Spec:
    name: str  # the player character, in every text the model reads ("Pac-Man", "Ms. Pac-Man")
    pronoun: str  # "he" / "she", in the same texts
    ghost_labels: dict  # ghost key (red, pink, blue, orange) -> how the model is told its name
    rules_l1: str  # knowledge rung L1: the rules as static text
    ghost_behaviour_l3a: str  # knowledge rung L3a: how the ghosts choose where to go
    scatter_targets: dict  # ghost key -> its corner target tile in scatter mode (the ROM's)
    door_target: tuple  # where eaten ghosts (eyes) head
    in_tunnel: Callable  # (maze, tile) -> True where ghosts make no choice (the wrap-around tunnels)
    no_up_tiles: frozenset = field(default_factory=frozenset)  # tiles where ghosts may not turn up
    safe_spot: Optional[tuple] = None  # the refuge tile (--refuge), or None if the game has none
    forecast_note: str = ""
    orders_example: str = ""  # a standing order an operator might give, shown as the Observatory's example  # a caveat added to the L3b ghost routes (e.g. where ghosts move at random)
