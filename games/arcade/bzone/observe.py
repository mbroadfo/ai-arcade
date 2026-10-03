"""What the Observatory shows of Battlezone: the status line, with facts, series and screen marks. Display only.

The marks put where the decoded state says the enemy is onto the game's own picture (640 x 480, MAME's rendered
snapshot), so a person can see whether the RAM map is right:
- on the radar: the game draws its blip from the same enemy position (TPOSX+2/TPOSY+2). Calibrated 3 October 2026
  from 56 recorded frames: the blip sat a median 1.0 px from this prediction (centre (317.8, 50.0), 38.4 px for 32,768
  world units, the radar's range).
- the enemy's heading, as an arrow from its radar mark while it is on screen (where its shape shows which way it
  faces; the radar shows only a blip), and its shell while on screen, with an arrow along its path on the radar. No
  mark shows more than a player can see, and none shows while the enemy explodes.
- in the window: where the enemy tank should be drawn while it is on screen (within $16 of the heading). The
  horizontal scale (VIEW_PX) was measured from obstacles on the fixed map: two of them gave 564 and 574.
"""
import math

from .facts import IN_VIEW, in_view, wrap16

SIZE = (640, 480)
RADAR_CENTRE, RADAR_PX = (317.8, 50.0), 38.4 / 32768  # pixels per world unit
SIGHT = (318, 240)  # the gun sight's centre
VIEW_PX = 570  # pixels per unit of left/ahead: measured 3 October 2026 (obstacles at known places, tank standing still)


def offsets(state, point):
    """(ahead, left) world units from the tank to a world point, in the tank's own frame."""
    dx, dy = wrap16(point[0] - state.tank.x), wrap16(point[1] - state.tank.y)
    return turn(state, dx, dy)


def turn(state, dx, dy):
    """A world direction as (ahead, left) in the tank's own frame."""
    h = state.tank.angle * math.pi / 128
    return dx * math.cos(h) + dy * math.sin(h), dy * math.cos(h) - dx * math.sin(h)


def on_radar(ahead, left):
    return round(RADAR_CENTRE[0] - left * RADAR_PX, 1), round(RADAR_CENTRE[1] - ahead * RADAR_PX, 1)


def pointing(x, y, ahead, left, px):
    """The end of a px-long line from (x, y) on the radar in the direction (ahead, left)."""
    n = math.hypot(ahead, left) or 1
    return [round(x - px * left / n, 1), round(y - px * ahead / n, 1)]


def marks(state, facts):
    ahead, left = offsets(state, (state.enemy.x, state.enemy.y))
    out = [{"label": "your tank", "kind": "player", "x": SIGHT[0], "y": SIGHT[1], "colour": "#ffe600"}]
    if facts.enemy_on_radar:
        x, y = on_radar(ahead, left)
        h = state.enemy.angle * math.pi / 128
        out.append({"label": "enemy (radar, predicted" + ("; arrow: its heading)" if facts.enemy_side == "ahead" else ")"),
                    "kind": "threat", "line": False, "x": x, "y": y,
                    "to": pointing(x, y, *turn(state, math.cos(h), math.sin(h)), 30) if facts.enemy_side == "ahead" else None,
                    "note": f"{facts.enemy_distance} units, {facts.enemy_bearing_deg:+.0f} deg",
                    "colour": "#ff4040", "alert": bool(facts.on_target)})
    if facts.enemy_side == "ahead" and ahead > 0:
        out.append({"label": "enemy (window, predicted)", "kind": "target", "line": False,
                    "x": round(SIGHT[0] - VIEW_PX * left / ahead, 1), "y": SIGHT[1],
                    "note": "on target" if facts.on_target else "in view", "colour": "#40ff80",
                    "alert": bool(facts.on_target)})
    if facts.enemy_shell == "flying" and in_view(state, state.enemy.shell):
        s_ahead, s_left = offsets(state, state.enemy.shell)
        x, y = on_radar(s_ahead, s_left)
        incoming = facts.shell_miss is not None
        note = (f"passes {abs(facts.shell_miss)} {'left' if facts.shell_miss >= 0 else 'right'} in "
                f"{facts.shell_arrives_s:.2f} s" if incoming else "going away")
        out.append({"label": "enemy shell (radar; arrow: its path)", "kind": "threat", "line": False, "x": x, "y": y,
                    "to": pointing(x, y, *turn(state, *state.enemy.shell_step), 30), "note": note,
                    "colour": "#ff9a1f", "alert": incoming})
        if True:  # in the window
            out.append({"label": "enemy shell (window)", "kind": "threat", "line": False,
                        "x": round(SIGHT[0] - VIEW_PX * s_left / s_ahead, 1), "y": SIGHT[1], "note": note,
                        "colour": "#ff9a1f", "alert": incoming})
    return out


def status(state, facts, frame, held, why, kills):
    """The Observatory's status record for one tick (`event: status`)."""
    record = {"event": "status", "frame": frame, "title": "Battlezone", "game": 1, "playing": state.playing,
              "held": held, "why": why, "screen": {"size": list(SIZE), "smooth": True},  # marks in 640 x 480 units
              "score": state.score, "lives": state.lives}
    if not state.playing:
        return record
    record["marks"] = marks(state, facts)
    record["facts"] = [
        {"label": "enemy", "value": facts.enemy_side if facts.enemy_kind == "tank" else
         f"MISSILE {facts.enemy_side}, height {facts.missile_height}" + (" (shootable)" if facts.missile_low else "")
         + (", weaving" if facts.missile_weaving else ""),
         "tone": "bad" if facts.enemy_kind == "missile" else "warn" if facts.enemy_side == "rear" else None},
        {"label": "on radar", "value": "yes" if facts.enemy_on_radar else "no", "tone": None},
        {"label": "bearing", "value": "-" if facts.enemy_bearing_deg is None else f"{facts.enemy_bearing_deg:+.0f} deg",
         "tone": None},
        {"label": "distance", "value": facts.enemy_distance if facts.enemy_distance is not None else "-", "tone": None},
        {"label": "shot would pass", "value": "-" if facts.miss_by is None else f"{facts.miss_by:+d} (hits within "
         f"{facts.hit_radius})", "tone": "good" if facts.on_target else None},
        {"label": "enemy may fire", "value": "not yet" if facts.enemy_holds_fire else "yes",
         "tone": None if facts.enemy_holds_fire else "warn"},
        {"label": "enemy aim", "value": "-" if facts.enemy_aim is None else
         ("on you" if abs(facts.enemy_aim) < 2 else f"{facts.enemy_aim:+d} units off"),
         "tone": "bad" if facts.enemy_aim is not None and abs(facts.enemy_aim) < 2 else None},
        {"label": "enemy shell", "value": (facts.enemy_shell + ("" if facts.enemy_shell == "none" else " (heard)"))
         if facts.shell_miss is None else
         f"passes {abs(facts.shell_miss)} {'left' if facts.shell_miss >= 0 else 'right'} in {facts.shell_arrives_s:.2f} s",
         "tone": "bad" if facts.shell_miss is not None else None},
        {"label": "path ahead", "value": "blocked" if facts.blocked else "clear" if facts.obstacle_ahead is None else
         f"obstacle in {facts.obstacle_ahead}", "tone": "bad" if facts.blocked else
         "warn" if facts.obstacle_ahead is not None and facts.obstacle_ahead < 2500 else None},
        {"label": "cover", "value": facts.cover or "none", "tone": "good" if facts.cover else None},
        {"label": "kills", "value": kills, "tone": None},
    ]
    record["series"] = [
        {"key": "distance", "label": "enemy distance", "value": facts.enemy_distance, "unit": "units", "worse": None,
         "colour": "#ff8aa8"},
        {"key": "bearing", "label": "enemy bearing", "value": facts.enemy_bearing_deg, "unit": "deg", "worse": None,
         "colour": "#5b7bff"},
        {"key": "kills", "label": "kills", "value": kills, "unit": "", "worse": None},
        {"key": "shell", "label": "enemy shell passes", "value": facts.shell_miss, "unit": "units", "worse": None,
         "colour": "#ff9a1f"},
    ]
    return record
