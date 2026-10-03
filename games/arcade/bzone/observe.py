"""What the Observatory shows of Battlezone: the status line, with facts, series and screen marks. Display only.

The marks put where the decoded state says the enemy is onto the game's own picture (640 x 480, MAME's rendered
snapshot), so a person can see whether the RAM map is right:
- on the radar: the game draws its blip from the same enemy position (TPOSX+2/TPOSY+2). Calibrated 3 October 2026
  from 56 recorded frames: the blip sat a median 1.0 px from this prediction (centre (317.8, 50.0), 38.4 px for 32,768
  world units, the radar's range).
- in the window: where the enemy tank should be drawn while it is on screen (within $16 of the heading). The
  horizontal scale is an estimate from the screen's width, not yet calibrated.
"""
import math

from .facts import IN_VIEW, wrap16

SIZE = (640, 480)
RADAR_CENTRE, RADAR_PX = (317.8, 50.0), 38.4 / 32768  # pixels per world unit
SIGHT = (318, 240)  # the gun sight's centre
VIEW_PX = 280 / math.tan(IN_VIEW * math.pi / 128)  # estimate: the edge of view at the edge of the window (verify)


def enemy_offsets(state):
    """(ahead, left) world units from the tank to the enemy, in the tank's own frame."""
    dx, dy = wrap16(state.enemy.x - state.tank.x), wrap16(state.enemy.y - state.tank.y)
    h = state.tank.angle * math.pi / 128
    return dx * math.cos(h) + dy * math.sin(h), dy * math.cos(h) - dx * math.sin(h)


def marks(state, facts):
    ahead, left = enemy_offsets(state)
    out = [{"label": "your tank", "kind": "player", "x": SIGHT[0], "y": SIGHT[1], "colour": "#ffe600"}]
    if facts.enemy_on_radar:
        out.append({"label": "enemy (radar, predicted)", "kind": "threat", "line": False,
                    "x": round(RADAR_CENTRE[0] - left * RADAR_PX, 1), "y": round(RADAR_CENTRE[1] - ahead * RADAR_PX, 1),
                    "note": f"{facts.enemy_distance} units, {facts.enemy_bearing_deg:+.0f} deg",
                    "colour": "#ff4040", "alert": bool(facts.on_target)})
    if facts.enemy_side == "ahead" and ahead > 0:
        out.append({"label": "enemy (window, predicted)", "kind": "target", "line": False,
                    "x": round(SIGHT[0] - VIEW_PX * left / ahead, 1), "y": SIGHT[1],
                    "note": "on target" if facts.on_target else "in view", "colour": "#40ff80",
                    "alert": bool(facts.on_target)})
    return out


def status(state, facts, frame, held, why, kills):
    """The Observatory's status record for one tick (`event: status`)."""
    record = {"event": "status", "frame": frame, "title": "Battlezone", "game": 1, "playing": state.playing,
              "held": held, "why": why, "screen": {"size": list(SIZE)}, "score": state.hits, "lives": state.lives}
    if not state.playing:
        return record
    record["marks"] = marks(state, facts)
    record["facts"] = [
        {"label": "enemy", "value": facts.enemy_side, "tone": "warn" if facts.enemy_side == "rear" else None},
        {"label": "on radar", "value": "yes" if facts.enemy_on_radar else "no", "tone": None},
        {"label": "bearing", "value": "-" if facts.enemy_bearing_deg is None else f"{facts.enemy_bearing_deg:+.0f} deg",
         "tone": None},
        {"label": "distance", "value": facts.enemy_distance if facts.enemy_distance is not None else "-", "tone": None},
        {"label": "shot would pass", "value": "-" if facts.miss_by is None else f"{facts.miss_by:+d} (hits within "
         f"{facts.hit_radius})", "tone": "good" if facts.on_target else None},
        {"label": "kills", "value": kills, "tone": None},
    ]
    record["series"] = [
        {"key": "distance", "label": "enemy distance", "value": facts.enemy_distance, "unit": "units", "worse": None,
         "colour": "#ff8aa8"},
        {"key": "bearing", "label": "enemy bearing", "value": facts.enemy_bearing_deg, "unit": "deg", "worse": None,
         "colour": "#5b7bff"},
        {"key": "kills", "label": "kills", "value": kills, "unit": "", "worse": None},
    ]
    return record
