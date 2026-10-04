"""Vanguard's work RAM -> named game state. First pass: addresses are candidates from discovery and the controlled
probe (scripts/probe.py), not yet validated; RAM_MAP.md says what is known."""
from dataclasses import dataclass

BASE = 0x0000
IMAGE = (BASE, 0x0400)

CREDITS = 0x2B
SHIP = 0x42  # 16 bits: moves 1 a step with UP/DOWN, $20 a step with RIGHT
BUTTONS = 0x40  # the fire buttons held: button 1 = 08, 2 = 04, 3 = 01, 4 = 02 (MAME's port masks)
LIVES = 0xBE  # spare ships: the HUD shows this + 1; $FF once the game is over (checked against video, 4 October 2026)
GAME_OVER_TIMER = 0x50  # counts 14, 4, 3, 2, 1, 0 while THE END is shown, then $FF
HISCORE = 0x25  # 3 bytes BCD: 00 10 00 = the 10000 on the screen (not the player's score)


@dataclass(frozen=True)
class VanguardState:
    credits: int
    ship: int
    buttons: int
    lives: int  # spare ships, $FF (255) when the game is over
    hiscore: int
    raw: bytes


def decode(image):
    image = bytes(image)
    return VanguardState(credits=image[CREDITS], ship=image[SHIP] | image[SHIP + 1] << 8, buttons=image[BUTTONS],
                         lives=image[LIVES], hiscore=int(image[HISCORE:HISCORE + 3].hex()), raw=image)
