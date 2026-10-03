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

The enemy's fire (FIREIT, SHUPDT): it fires only when its heading is within 2 units of the bearing to the player, so the
shell flies straight at where the player was when it fired, and never before $20 game frames after it appeared. A player
hears the shot (the sound) wherever the enemy is and knows where it came from (the radar or the warning), so where the
shell will pass is something a player can work out; it is given whenever a shell is flying. The shell moves about 253
units an update, about 90 updates a second (measured on the two shots of the scripted recording, both of which killed:
each was fired with the enemy aimed exactly, 0 units, and each exploded where the tank stood as a life was lost), and
gives out after 127 updates (about 32,000 units, the radar's range). The enemy's own heading is a fact while it is on
screen, where its shape shows which way it faces.

Angles are 256 to a full circle, counterclockwise (turning left raises the heading); a relative bearing is positive to
the left. The bearing computed here matches the game's own (PTURN, its size) within 1 unit on 379 of 383 recorded frames.
"""
import math
from dataclasses import dataclass

IN_VIEW = 0x16  # below this (relative, either side) the enemy is on screen and no warning shows
REAR = 0x6B  # above this, "ENEMY TO REAR"
RADAR_RANGE = 0x80  # TDIST below this: on the radar, in firing range
SHELL_SPEED = 341  # world units a frame (measured on the scripted recording)
SHELL_UPDATES_PER_S = 90  # the enemy's shell (measured on the scripted recording; verify live)
AIMED = 2  # the enemy fires only when its heading is within this of the bearing to the player (FIREIT)
HOLDS_FIRE = 0x20  # game frames after appearing during which the enemy never fires (FTIMER, FIREIT)


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
    enemy_age: int  # game frames since this enemy appeared (counted by the game, stops at 255)
    enemy_holds_fire: bool  # too soon after appearing to fire (enemy_age below $20)
    enemy_aim: int | None  # angle units from the enemy's heading to the bearing to the player (+ = it must turn left);
    #                        only while it is on screen; it fires when this is within AIMED
    enemy_shell: str  # "none", "flying" or "exploding": the shot is heard
    shell_miss: int | None  # how far from the tank the flying shell's path passes (+ = on the tank's left); None once
    #                         it has passed or when there is none
    shell_arrives_s: float | None  # seconds until it is closest to the tank (None as shell_miss)


def shell_pass(state):
    """(passes by, seconds until closest) for the enemy's flying shell against the tank where it is now, or (None, None).
    Passes by is + when the shell goes by on the tank's left."""
    e = state.enemy
    if not 0 < e.fire < 0x80 or e.shell_step == (0, 0):
        return None, None
    rx, ry = wrap16(state.tank.x - e.shell[0]), wrap16(state.tank.y - e.shell[1])  # shell -> tank
    sx, sy = e.shell_step
    step2 = sx * sx + sy * sy
    updates = (rx * sx + ry * sy) / step2  # until closest approach
    if updates < 0 or updates > e.fire:
        return None, None  # passed, or gives out first
    px, py = sx * updates - rx, sy * updates - ry  # tank -> the closest point of the shell's path
    h = state.tank.angle * math.pi / 128
    return round(py * math.cos(h) - px * math.sin(h)), round(updates / SHELL_UPDATES_PER_S, 2)


def derive(state):
    rel = relative(state.tank, (state.enemy.x, state.enemy.y))
    size = abs(rel)
    side = "ahead" if size < IN_VIEW else "rear" if size > REAR else ("left" if rel >= 0 else "right")
    on_radar = state.enemy_distance < RADAR_RANGE
    known = on_radar or side == "ahead"
    distance = round(math.hypot(wrap16(state.enemy.x - state.tank.x), wrap16(state.enemy.y - state.tank.y)))
    side_miss, ahead = miss_distance(state, state.angle9)
    radius = hit_radius(state.tank.angle, state.enemy.angle)
    miss, arrives = shell_pass(state)
    return Facts(heading_deg=round(degrees(state.tank.angle), 1), enemy_side=side, enemy_on_radar=on_radar,
                 enemy_bearing=rel if known else None, enemy_bearing_deg=round(degrees(rel), 1) if known else None,
                 enemy_distance=distance if on_radar else None,
                 miss_by=round(side_miss) if on_radar else None, hit_radius=radius if on_radar else None,
                 on_target=(abs(side_miss) <= radius and ahead > 0) if on_radar else None,
                 dying=bool(state.dying), enemy_age=state.enemy_timer, enemy_holds_fire=state.enemy_timer < HOLDS_FIRE,
                 enemy_aim=(relative(state.enemy, (state.tank.x, state.tank.y)) if side == "ahead" else None),
                 enemy_shell="none" if not state.enemy.fire else "flying" if state.enemy.fire < 0x80 else "exploding",
                 shell_miss=miss, shell_arrives_s=arrives)
