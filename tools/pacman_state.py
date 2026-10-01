"""Decode Pac-Man work RAM (0x4000-0x4FFF) into game state. Map: docs/PACMAN_RAM_MAP.md."""
from dataclasses import dataclass

BASE = 0x4000
REGIONS = [(0x4000, 0x4FFF)]

GHOSTS = ("red", "pink", "blue", "orange")
DIRECTIONS = {0: "right", 1: "down", 2: "left", 3: "up"}  # on-screen, per vector table $32FF
MODES = {0: "init", 1: "attract", 2: "coin", 3: "playing"}


def bcd(data):
    """Little-endian BCD bytes (least-significant pair first) to int."""
    value = 0
    for byte in reversed(data):
        value = value * 100 + (byte >> 4) * 10 + (byte & 0x0F)
    return value


@dataclass
class Actor:
    pos: tuple  # raw (l, h) position bytes
    tile: tuple  # raw (l, h) tile bytes
    direction: str


@dataclass
class PacmanState:
    mode: str
    credits: int
    lives: int
    score: int
    high_score: int
    dots_eaten: int
    level: int
    pacman: Actor
    pacman_wanted: str  # direction held on the joystick, even if a wall blocks it
    ghosts: dict
    frightened: dict
    eyes: dict
    fruit_pos: tuple


def decode(buf):
    """buf: the 4096 bytes starting at 0x4000 (frame-counter header already stripped)."""
    def b(addr):
        return buf[addr - BASE]

    def span(addr, n):
        return buf[addr - BASE: addr - BASE + n]

    ghosts = {
        name: Actor(
            pos=(b(0x4D00 + 2 * i), b(0x4D01 + 2 * i)),
            tile=(b(0x4D31 + 2 * i), b(0x4D32 + 2 * i)),
            direction=DIRECTIONS.get(b(0x4D28 + i), "?"),
        )
        for i, name in enumerate(GHOSTS)
    }
    return PacmanState(
        mode=MODES.get(b(0x4E00), f"unknown({b(0x4E00)})"),
        credits=bcd([b(0x4E6E)]),
        lives=b(0x4E14),
        score=bcd(span(0x4E80, 3)),  # 6 digits; 4E83 is a flag that becomes 1 past 10,000
        high_score=bcd(span(0x4E88, 3)),
        dots_eaten=b(0x4E0E),
        level=b(0x4E13) + 1,
        pacman=Actor(
            pos=(b(0x4D08), b(0x4D09)),
            tile=(b(0x4D39), b(0x4D3A)),
            direction=DIRECTIONS.get(b(0x4D30), "?"),
        ),
        pacman_wanted=DIRECTIONS.get(b(0x4D3C), "?"),
        ghosts=ghosts,
        frightened={n: bool(b(0x4DA6 + i)) for i, n in enumerate(GHOSTS)},
        eyes={n: bool(b(0x4DAC + i)) for i, n in enumerate(GHOSTS)},
        fruit_pos=(b(0x4DD2), b(0x4DD3)),
    )
