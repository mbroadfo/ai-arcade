"""Puck Man (bootleg set 1) (MAME set "puckmanb"): Pac-Man (Midway)'s spec with only the name changed. What differs on this game
is found by the kit's validation (tools/new_game.py) and goes here as it is found."""
from dataclasses import replace

from games.arcade.pacman.spec import SPEC as BASE

NAME = "Puck Man"

SPEC = replace(
    BASE,
    name=NAME,
    rules_l1=BASE.rules_l1.replace(BASE.name, NAME),
    ghost_behaviour_l3a=BASE.ghost_behaviour_l3a.replace(BASE.name, NAME),
    forecast_note=BASE.forecast_note.replace(BASE.name, NAME),
    orders_example=BASE.orders_example.replace(BASE.name, NAME),
)
