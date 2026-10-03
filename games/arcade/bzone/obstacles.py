"""Battlezone's battlefield: 21 obstacles at fixed places, the same in every game (Atari's source and ROM).

Positions: PTBLX1/PTBLY1 in the program ROM ($7681/$76AB). Type and orientation: PTBLO1 in the vector ROM ($3FCC,
036422-01.bc3 + 036421-01.a3), read from the cabinet's own ROM set on 3 October 2026. The world wraps at 16 bits.

How close counts as touching, by type (all world units):
- the player's tank: 1,152 ($0480) for every type (OBJOBJ, X = 0). Checked: 632 of 742 logged ticks where a drive
  went nowhere were 1,100-1,199 units from an obstacle on this map;
- the enemy tank: PROXTB, $0340 for types 00 and 01, $0400 for 0C, $03C0 for 0F;
- shells: PRXTBL, 4 x ($38, $58, $56, 0) for 00, 01, 0C, 0F (C_21S_ compares a quarter of the distance). Type 0F
  stops no shell: shots pass over it, so it is no cover.

Which shape each type is, identified on screen (3 October 2026: the tank stood still at stepped headings and each
obstacle's predicted window position landed on one shape): 00 narrow pyramid, 0C wide pyramid, 01 tall box, 0F short
box. The short box stops no shell (shots pass over it); the wide pyramid blocks the most ground for an enemy tank.
"""
import math
from dataclasses import dataclass

X = [0x2000, 0x0000, 0x0000, 0x4000, 0x8000, 0x8000, 0x8000, 0x4000, 0x3000, 0xC000, 0xF700, 0xC800, 0xD800, 0x9400,
     0x9800, 0xE800, 0x7000, 0x7800, 0x4000, 0x2400, 0x2C00]
Y = [0x2000, 0x4000, 0x8000, 0x8000, 0x8000, 0x4000, 0x0000, 0x0000, 0x5000, 0x1800, 0x4400, 0x4000, 0x8C00, 0x0C00,
     0xE800, 0xE400, 0x9C00, 0xCC00, 0xB400, 0xBC00, 0xF400]
KIND_ORIENT = [(0x0C, 0x00), (0x0F, 0x10), (0x0C, 0x20), (0x0F, 0x40), (0x0C, 0x18), (0x00, 0x28), (0x01, 0x30),
               (0x00, 0x38), (0x01, 0x40), (0x0F, 0x48), (0x0C, 0x50), (0x00, 0x58), (0x01, 0x60), (0x0F, 0x68),
               (0x0C, 0x70), (0x00, 0x78), (0x01, 0x80), (0x0F, 0x88), (0x0C, 0x90), (0x00, 0x98), (0x01, 0xA0)]

TANK_TOUCH = 0x480  # the player's tank, any type
ENEMY_TOUCH = {0x00: 0x340, 0x01: 0x340, 0x0C: 0x400, 0x0F: 0x3C0}
SHELL_TOUCH = {0x00: 4 * 0x38, 0x01: 4 * 0x58, 0x0C: 4 * 0x56, 0x0F: 0}
SHAPES = {0x00: "narrow pyramid", 0x01: "tall box", 0x0C: "wide pyramid", 0x0F: "short box"}


def wrap16(v):
    return (v + 0x8000) % 0x10000 - 0x8000


@dataclass(frozen=True)
class Obstacle:
    index: int
    x: int
    y: int
    kind: int
    orientation: int

    @property
    def shape(self):
        return SHAPES[self.kind]

    @property
    def blocks_shells(self):
        return SHELL_TOUCH[self.kind] > 0


MAP = [Obstacle(i, x - 0x10000 if x & 0x8000 else x, y - 0x10000 if y & 0x8000 else y, k, o)
       for i, (x, y, (k, o)) in enumerate(zip(X, Y, KIND_ORIENT))]


def offset(tank, ob):
    """(ahead, left) world units from the tank to the obstacle, in the tank's own frame."""
    dx, dy = wrap16(ob.x - tank.x), wrap16(ob.y - tank.y)
    h = tank.angle * math.pi / 128
    return dx * math.cos(h) + dy * math.sin(h), dy * math.cos(h) - dx * math.sin(h)


def path_clear(tank, reverse=False, look=6000):
    """How far the tank can drive straight (forward, or backward with reverse) before touching an obstacle, and which;
    (None, None) if nothing within `look` units."""
    best = (None, None)
    for ob in MAP:
        ahead, left = offset(tank, ob)
        if reverse:
            ahead = -ahead
        if ahead <= 0 or abs(left) >= TANK_TOUCH:
            continue
        run = ahead - math.sqrt(TANK_TOUCH ** 2 - left ** 2)  # where the touching circle is first reached
        if run < look and (best[0] is None or run < best[0]):
            best = (max(0, round(run)), ob)
    return best


def cover(tank, enemy):
    """The obstacle that stops a shell flying straight from the enemy to the tank, or None (no cover)."""
    ex, ey = wrap16(tank.x - enemy.x), wrap16(tank.y - enemy.y)  # enemy -> tank
    length = math.hypot(ex, ey) or 1
    for ob in MAP:
        if not ob.blocks_shells:
            continue
        ox, oy = wrap16(ob.x - enemy.x), wrap16(ob.y - enemy.y)
        along = (ox * ex + oy * ey) / length
        if 0 < along < length and abs(ox * ey - oy * ex) / length < SHELL_TOUCH[ob.kind]:
            return ob
    return None
