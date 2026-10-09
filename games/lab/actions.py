"""Discrete button combinations. The model sees a small Discrete space, not every chord."""
from __future__ import annotations

# Libretro joypad ids. The same names are used for every core.
BUTTON_ID = {
    "B": 0,
    "Y": 1,
    "SELECT": 2,
    "START": 3,
    "UP": 4,
    "DOWN": 5,
    "LEFT": 6,
    "RIGHT": 7,
    "A": 8,
    "X": 9,
    "L": 10,
    "R": 11,
}

# Bootable NES games need a pad that can move and use both buttons.
NES_ACTIONS: list[tuple[str, ...]] = [
    (),
    ("RIGHT",),
    ("LEFT",),
    ("UP",),
    ("DOWN",),
    ("A",),
    ("B",),
    ("RIGHT", "A"),
    ("RIGHT", "B"),
    ("RIGHT", "A", "B"),
    ("LEFT", "A"),
    ("LEFT", "B"),
    ("UP", "A"),
    ("DOWN", "B"),
]

# Stella maps the 2600 fire button to A or B depending on the core. Offer both.
A2600_ACTIONS: list[tuple[str, ...]] = [
    (),
    ("LEFT",),
    ("RIGHT",),
    ("UP",),
    ("DOWN",),
    ("A",),
    ("B",),
    ("LEFT", "A"),
    ("RIGHT", "A"),
    ("LEFT", "B"),
    ("RIGHT", "B"),
]


def for_system(system: str) -> list[tuple[str, ...]]:
    if system == "nes":
        return NES_ACTIONS
    if system == "atari2600":
        return A2600_ACTIONS
    raise ValueError(f"no default actions for {system}")
