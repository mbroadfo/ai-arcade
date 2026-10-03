"""Diagnostic policies: instrumentation tests of the real-time loop, not attempts to play well.

Each is a function (state, facts, seconds_into_run, last_action) -> (control names to hold, why), using only the
decoded state and the tactical facts (facts.py), so a log can show that a given state led to a given command. They are
code choosing, so they are controls (the rule tier in docs/GAME_WORKSHOP.md), never reported as AI play.
"""
from .controls import DRIVE, TURN_LEFT, TURN_RIGHT

NOTHING = frozenset()


def idle(state, facts, t, last):
    """Press nothing: watch, or drive yourself on the keyboard while the lab reports."""
    return NOTHING, "hold nothing"


def rotate_left(state, facts, t, last):
    """Turn left on the spot, always."""
    return TURN_LEFT, "always turn left"


def rotate_right(state, facts, t, last):
    """Turn right on the spot, always."""
    return TURN_RIGHT, "always turn right"


def drive(state, facts, t, last):
    """Drive straight ahead, always."""
    return DRIVE, "always drive forward"


def pattern(state, facts, t, last, turn_s=2.0, drive_s=2.0):
    """Turn left 2 s, drive 2 s, repeat."""
    phase = t % (turn_s + drive_s)
    if phase < turn_s:
        return TURN_LEFT, f"pattern: turning ({phase:.1f} s of {turn_s:.0f})"
    return DRIVE, f"pattern: driving ({phase - turn_s:.1f} s of {drive_s:.0f})"


def fire_pulse(state, facts, t, last, every_s=1.0, held_s=0.2):
    """Fire is a button the game reads on a press: hold it briefly, then let go, every `every_s` seconds."""
    if t % every_s < held_s:
        return frozenset({"FIRE"}), f"fire pulse ({t % every_s:.1f} s into a {every_s:.0f} s cycle)"
    return NOTHING, "between fire pulses"


def turn_toward(state, facts, t, last):
    """Turn to the side the screen names; once the bearing is known (radar or on screen), centre on it."""
    if facts.dying:
        return NOTHING, "dying: nothing to steer"
    if facts.enemy_side == "none":
        return NOTHING, "the enemy is exploding: nothing to aim at"
    if facts.on_target:
        return NOTHING, f"on target (shot would pass {facts.miss_by:+d}, radius {facts.hit_radius}): hold still"
    if facts.miss_by is not None:
        if facts.enemy_bearing is not None and abs(facts.enemy_bearing) > 2:
            pass  # far off: steer by the bearing below
        elif facts.miss_by > 0:
            return TURN_LEFT, f"shot would pass {facts.miss_by:+d} (left of it): turn left"
        else:
            return TURN_RIGHT, f"shot would pass {facts.miss_by:+d} (right of it): turn right"
    if facts.enemy_bearing is not None:
        if facts.enemy_bearing > 0:
            return TURN_LEFT, f"enemy {facts.enemy_bearing_deg:+.0f} deg (left): turn left"
        return TURN_RIGHT, f"enemy {facts.enemy_bearing_deg:+.0f} deg (right): turn right"
    if facts.enemy_side == "right":
        return TURN_RIGHT, "screen says enemy to the right: turn right"
    return TURN_LEFT, f"screen says enemy to the {facts.enemy_side}: turn left"


def track_and_fire(state, facts, t, last):
    """turn_toward, and fire when a shot would pass within the hit radius: a press on one tick, a release on the next."""
    names, why = turn_toward(state, facts, t, last)
    if facts.on_target:
        if "FIRE" in last:
            return names, why + "; release fire (it fires on a press)"
        return names | {"FIRE"}, why + "; on target: fire"
    return names, why


# For the setup panel: what each policy is for, grouped. Movement and observation policies test the loop and the
# decoder; the targeting ones are baselines a player is measured against.
POLICY_INFO = {
    "rotate_left": {"group": "Movement", "label": "Rotate left"},
    "rotate_right": {"group": "Movement", "label": "Rotate right"},
    "drive": {"group": "Movement", "label": "Drive"},
    "pattern": {"group": "Movement", "label": "Pattern"},
    "idle": {"group": "Observation / weapons", "label": "Idle"},
    "fire_pulse": {"group": "Observation / weapons", "label": "Fire pulse"},
    "turn_toward": {"group": "Targeting baselines", "label": "Turn toward",
                    "purpose": "Aiming test: turns until a shot would hit, and never fires.",
                    "limitation": "Never fires; pivots in place."},
    "track_and_fire": {"group": "Targeting baselines", "label": "Track & Fire", "tag": "baseline",
                       "purpose": "Stationary targeting baseline: turns toward the enemy and fires when a shot would "
                                  "pass within the hit radius.",
                       "limitation": "Pivots in place: never moves or evades. All three deaths of its 3 October game "
                                     "came standing still, each from a shot aimed 0-1 units off."},
}

POLICIES = {"idle": idle, "rotate_left": rotate_left, "rotate_right": rotate_right, "drive": drive,
            "pattern": pattern, "fire_pulse": fire_pulse, "turn_toward": turn_toward, "track_and_fire": track_and_fire}
