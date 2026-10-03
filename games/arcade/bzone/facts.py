"""Battlezone's tactical facts: what a player can see, derived from the decoded state (never a recommendation).

What the screen shows, from Atari's source (RAM_MAP.md):
- the warning "ENEMY TO LEFT / RIGHT / REAR", or no warning while the enemy is on screen. MAIN picks it from the
  enemy's bearing relative to the tank's heading: on screen below $16 (about 31 degrees), rear above $6B (about 150),
  otherwise left or right by its sign. Shown whatever the distance.
- the radar, which draws the enemy's blip only within firing range (DRADAR: the distance's high byte below $80), at
  its bearing and distance; "ENEMY IN RANGE" flashes then.
So the exact bearing and the distance are facts only while the enemy is on the radar or on screen; beyond the radar a
player knows the side alone.

Whether a shot fired now would hit (the sight on the tank, as a player sees it): a shell flies along the tank's heading
and hits the enemy if it passes within its hit radius, which SHRTCK computes from how the two tanks face each other:
(1.5 * (|2 * angle difference| / 8) + $38) * 4 world units, about 224 head-on to 320 side-on (TEMP3 is the distance / 4).
At 25,000 units that is about +-0.6 degrees, finer than the heading's 9-bit step (0.7 degrees): long shots hardly ever
hit. The miss distance assumes the enemy stays put while the shell flies (341 units a frame, 127 frames).

Angles are 256 to a full circle, counterclockwise (turning left raises the heading); a relative bearing is positive to
the left. The bearing computed here matches the game's own (PTURN, its size) within 1 unit on 379 of 383 recorded frames.
"""
import math
from dataclasses import dataclass

IN_VIEW = 0x16  # below this (relative, either side) the enemy is on screen and no warning shows
REAR = 0x6B  # above this, "ENEMY TO REAR"
RADAR_RANGE = 0x80  # TDIST below this: on the radar, in firing range
SHELL_SPEED = 341  # world units a frame (measured on the scripted recording)


def degrees(units):
    return units * 360 / 256


def wrap16(v):
    return (v + 0x8000) % 0x10000 - 0x8000


def bearing(tank, other):
    """Angle units (0-255) from the tank to the other position, in the tank's own convention."""
    return round(math.atan2(wrap16(other[1] - tank.y), wrap16(other[0] - tank.x)) * 128 / math.pi) % 256


def relative(tank, other):
    """Signed angle units from the tank's heading to the other position: positive = to the left."""
    return (bearing(tank, other) - tank.angle + 128) % 256 - 128


def hit_radius(tank_angle, enemy_angle):
    """World units within which the player's shell hits the enemy tank (SHRTCK, for a tank; not the missile)."""
    a = ((tank_angle - enemy_angle) << 1) & 0xFF
    if a & 0x80:
        a = (-a) & 0xFF
    a >>= 3
    return (a + (a >> 1) + 0x38) * 4


def miss_distance(state, angle9):
    """How far to the side (world units, + left) a shell fired now along the 9-bit heading passes the enemy, and the
    distance along the line to it (negative: behind)."""
    dx, dy = wrap16(state.enemy.x - state.tank.x), wrap16(state.enemy.y - state.tank.y)
    h = angle9 * math.pi / 256
    return dy * math.cos(h) - dx * math.sin(h), dx * math.cos(h) + dy * math.sin(h)


@dataclass(frozen=True)
class Facts:
    heading_deg: float
    enemy_side: str  # "ahead" (on screen), "left", "right", "rear": what the screen says
    enemy_on_radar: bool  # in firing range: the radar shows its blip and "ENEMY IN RANGE" flashes
    enemy_bearing: int | None  # relative, angle units, + left; only when on the radar or on screen
    enemy_bearing_deg: float | None
    enemy_distance: int | None  # world units; only when on the radar
    miss_by: int | None  # how far to the side a shot fired now passes it (+ left); only when on the radar
    hit_radius: int | None  # how close a shot must pass to hit, from how the two tanks face; only on the radar
    on_target: bool | None  # a shot fired now would pass within the hit radius (ignoring obstacles and movement)
    dying: bool


def derive(state):
    rel = relative(state.tank, (state.enemy.x, state.enemy.y))
    size = abs(rel)
    side = "ahead" if size < IN_VIEW else "rear" if size > REAR else ("left" if rel >= 0 else "right")
    on_radar = state.enemy_distance < RADAR_RANGE
    known = on_radar or side == "ahead"
    distance = round(math.hypot(wrap16(state.enemy.x - state.tank.x), wrap16(state.enemy.y - state.tank.y)))
    side_miss, ahead = miss_distance(state, state.angle9)
    radius = hit_radius(state.tank.angle, state.enemy.angle)
    return Facts(heading_deg=round(degrees(state.tank.angle), 1), enemy_side=side, enemy_on_radar=on_radar,
                 enemy_bearing=rel if known else None, enemy_bearing_deg=round(degrees(rel), 1) if known else None,
                 enemy_distance=distance if on_radar else None,
                 miss_by=round(side_miss) if on_radar else None, hit_radius=radius if on_radar else None,
                 on_target=(abs(side_miss) <= radius and ahead > 0) if on_radar else None,
                 dying=bool(state.dying))
