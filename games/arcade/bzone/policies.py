"""Diagnostic policies: instrumentation tests of the real-time loop, not attempts to play well.

Each is a function (state, seconds_into_run) -> (control names to hold, why), using only the decoded state, so a log
can show that a given state led to a given command. They are code choosing, so they are controls (the rule tier in
docs/GAME_WORKSHOP.md), never reported as AI play.
"""
from .controls import DRIVE, TURN_LEFT, TURN_RIGHT


def idle(state, t):
    return frozenset(), "hold nothing"


def rotate_left(state, t):
    return TURN_LEFT, "always turn left"


def rotate_right(state, t):
    return TURN_RIGHT, "always turn right"


def drive(state, t):
    return DRIVE, "always drive forward"


def pattern(state, t, turn_s=2.0, drive_s=2.0):
    phase = t % (turn_s + drive_s)
    if phase < turn_s:
        return TURN_LEFT, f"pattern: turning ({phase:.1f} s of {turn_s:.0f})"
    return DRIVE, f"pattern: driving ({phase - turn_s:.1f} s of {drive_s:.0f})"


def fire_pulse(state, t, every_s=1.0, held_s=0.2):
    """Fire is a button the game reads on a press: hold it briefly, then let go, every `every_s` seconds."""
    if t % every_s < held_s:
        return frozenset({"FIRE"}), f"fire pulse ({t % every_s:.1f} s into a {every_s:.0f} s cycle)"
    return frozenset(), "between fire pulses"


POLICIES = {"idle": idle, "rotate_left": rotate_left, "rotate_right": rotate_right, "drive": drive,
            "pattern": pattern, "fire_pulse": fire_pulse}
