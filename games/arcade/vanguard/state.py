"""Vanguard's work RAM -> named game state. First pass: addresses are candidates from discovery and the controlled
probe (scripts/probe.py), not yet validated; RAM_MAP.md says what is known."""
from dataclasses import dataclass

BASE = 0x0000
IMAGE = (BASE, 0x0400)

CREDITS = 0x2B
SHIP = 0x42  # 16 bits: moves 1 a step with UP/DOWN, $20 a step with RIGHT
BUTTONS = 0x40  # the fire buttons held: button 1 = 08, 2 = 04, 3 = 01, 4 = 02 (MAME's port masks)
LIVES_CANDIDATES = (0xA9, 0xC4)


@dataclass(frozen=True)
class VanguardState:
    credits: int
    ship: int
    buttons: int
    candidates: tuple  # LIVES_CANDIDATES, raw
    raw: bytes


def decode(image):
    image = bytes(image)
    return VanguardState(credits=image[CREDITS], ship=image[SHIP] | image[SHIP + 1] << 8, buttons=image[BUTTONS],
                         candidates=tuple(image[a] for a in LIVES_CANDIDATES), raw=image)
