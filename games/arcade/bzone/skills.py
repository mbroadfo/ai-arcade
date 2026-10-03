"""Battlezone's skills: how a tactical intent becomes tread commands, tick by tick. Code, so labelled as such.

A skill is what a player (a lab policy now, the model later) asks for by name: "flank left", "dodge". It reads only the
tactical facts (facts.py: what a player can see or hear) and returns (control names to hold, why). It never decides
what to do; it carries out what it was asked.

Measured on the cabinet (lab runs, 3 October 2026), per second: drive or reverse 2,900 units; pivot 21.5 degrees;
one tread forward (arc) 10.8 degrees while moving 1,440 units; one tread back the same, backing up.
"""
import math

from .controls import ARC_LEFT, ARC_RIGHT, DRIVE, REVERSE, TURN_LEFT, TURN_RIGHT
from .facts import SHELL_UPDATES_PER_S

UNIT = 360 / 256  # degrees per angle unit
FLANK_ANGLE = math.radians(30)  # aim this far off the line to the enemy: crossing its aim at half the tank's speed
FLANK_MIN = 3000  # the flank point is at least this far to the side of the enemy
STRAIGHT = 3  # within this many angle units of the goal, drive straight
DODGE_TURN_S = 0.3  # dodge: pivot this long after the shot, then reverse (about 6 degrees)


def turn_to(rel, may_pivot, why):
    """Steer to a relative bearing (angle units, + left): straight when close, else pivot (standing) or arc (moving)."""
    if abs(rel) <= STRAIGHT:
        return DRIVE, why + ": straight on"
    if may_pivot:
        return (TURN_LEFT if rel > 0 else TURN_RIGHT), why + f": pivot {'left' if rel > 0 else 'right'}"
    return (ARC_LEFT if rel > 0 else ARC_RIGHT), why + f": arc {'left' if rel > 0 else 'right'}"


def flank_point(facts, side):
    """The relative bearing (angle units, + left) and distance of a point beside the enemy, `side` +1 for the side to
    the tank's left of the line to the enemy, -1 for the right. None when the enemy's distance is not known."""
    if facts.enemy_distance is None or facts.enemy_bearing is None:
        return None
    b, d = facts.enemy_bearing / UNIT * math.pi / 180, facts.enemy_distance
    r = max(FLANK_MIN, d * math.tan(FLANK_ANGLE))
    ahead = d * math.cos(b) - side * r * math.sin(b)
    left = d * math.sin(b) + side * r * math.cos(b)
    return math.degrees(math.atan2(left, ahead)) / UNIT, math.hypot(ahead, left)


def flank(facts, may_pivot, side=None):
    """Drive toward a point beside the enemy (the nearer side to the present heading unless `side` is given), keeping
    it off the nose: its shots are aimed where the tank is, and crossing its line makes them miss."""
    sides = [side] if side else [1, -1]
    points = [(s, flank_point(facts, s)) for s in sides]
    points = [(s, p) for s, p in points if p]
    if not points:
        return None
    s, (rel, _) = min(points, key=lambda sp: abs(sp[1][0]))
    return turn_to(round(rel), may_pivot, f"flank {'left' if s > 0 else 'right'} (point {rel * UNIT:+.0f} deg)")


TOO_CLOSE = 2500  # broadside: nearer than this, back off first


def broadside(facts, last):
    """Close to the enemy: pivot onto it (the fastest turn) and fire; back straight off first if it is very close.
    (Backing up while swinging, tried first, swung at half the pivot rate and backed out of range: it never lined up.)"""
    rel = facts.enemy_bearing
    if facts.on_target:
        if "FIRE" in last:
            return frozenset(), "broadside: on target, release fire"
        return frozenset({"FIRE"}), "broadside: on target, fire"
    if facts.enemy_distance is not None and facts.enemy_distance < TOO_CLOSE and abs(rel) > 32:
        return REVERSE, f"broadside: enemy {facts.enemy_distance} units, too close: back off"
    return (TURN_LEFT if rel > 0 else TURN_RIGHT), f"broadside: enemy {rel * UNIT:+.0f} deg, pivot onto it"


def dodge(state, facts, style="turn_reverse"):
    """A shot is heard: it was aimed at where the tank is. Get off that line.
    - enemy well off the nose: drive forward (that crosses the line at once);
    - otherwise "turn_reverse": pivot away for DODGE_TURN_S, then reverse along the new heading (the suggestion of
      3 October: a few degrees of turn turns a straight reverse into a sideways move), or "arc": arc away."""
    rel = facts.enemy_bearing
    left = rel >= 0 if rel is not None else facts.enemy_side == "left"
    if rel is not None and abs(rel) >= 0x10:
        return DRIVE, f"dodge: enemy {rel * UNIT:+.0f} deg off the nose, drive forward across its line"
    if style == "arc":
        return (ARC_RIGHT if left else ARC_LEFT), "dodge: enemy near the nose, arc away"
    since = (0x7F - state.enemy.fire) / SHELL_UPDATES_PER_S  # since the shot was heard (the shell counts down from $7F)
    if since < DODGE_TURN_S:
        return (TURN_RIGHT if left else TURN_LEFT), f"dodge: enemy near the nose, pivot away ({since:.2f} s)"
    return REVERSE, f"dodge: enemy near the nose, reverse off the line ({since:.2f} s)"


AVOID = 2500  # an obstacle this close in the path: steer around it
TOUCHING = 400  # this close (or blocked): pivot away, a move forward would go nowhere
BACK_ROOM = 1500  # reversing needs this much room behind


def steer_clear(facts, names, why):
    """Keep a move from running into an obstacle (the fixed map, obstacles.py): a drive or arc toward one within
    AVOID becomes an arc away from it, a blocked tank pivots away, a reverse with no room behind drives forward.
    (In the first comparisons a quarter of the moving policies' moves went nowhere, pinned on obstacles.)"""
    treads, fire = names - {"FIRE"}, names & {"FIRE"}
    if treads in (DRIVE, ARC_LEFT, ARC_RIGHT):
        left = (facts.obstacle_ahead_left or 0) > 0  # the obstacle's centre is left of the path
        if facts.blocked or (facts.obstacle_ahead is not None and facts.obstacle_ahead < TOUCHING):
            return (TURN_RIGHT if left else TURN_LEFT) | fire, why + "; blocked: pivot away from the obstacle"
        if facts.obstacle_ahead is not None and facts.obstacle_ahead < AVOID and treads != (ARC_RIGHT if left else ARC_LEFT):
            return (ARC_RIGHT if left else ARC_LEFT) | fire, why + f"; obstacle in {facts.obstacle_ahead}: steer around it"
    if treads == REVERSE and (facts.blocked or (facts.obstacle_behind is not None and facts.obstacle_behind < BACK_ROOM)):
        return DRIVE | fire, why + "; no room behind: drive forward instead"
    return names, why
