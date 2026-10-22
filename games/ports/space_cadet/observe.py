"""What the Observatory shows of Space Cadet: a top-down picture drawn from the bridge's state, and the status line. Display only.

The picture is not the game's own screen (the game runs headless); it is drawn from the same numbers the player is told: the
ball, its recent path, both flippers, the plunger lane and the drain. Screen terms, as in players.py: sx = -x runs right, y runs down.
"""
import base64
import io

from PIL import Image, ImageDraw

SIZE = (300, 560)
X_RANGE, Y_RANGE = (-8.0, 7.6), (-13.0, 14.6)  # sx and y shown, in table units
BG, WALL, BALL, TRAIL = "#0b1020", "#2a3560", "#ffe600", "#7a6a00"
FLIPPER_UP, FLIPPER_DOWN = "#40ff80", "#2ef2ff"


def to_px(sx, y):
    return ((sx - X_RANGE[0]) / (X_RANGE[1] - X_RANGE[0]) * SIZE[0], (y - Y_RANGE[0]) / (Y_RANGE[1] - Y_RANGE[0]) * SIZE[1])


def frame_png(state, trail=(), score_text=None):
    """The table now, as a base64 PNG (what the Observatory's video panel takes)."""
    img = Image.new("RGB", SIZE, BG)
    d = ImageDraw.Draw(img)
    d.rectangle([to_px(-7.4, -12.4), to_px(7.2, 13.9)], outline=WALL, width=2)  # the table
    d.line([to_px(6.0, -6.0), to_px(6.0, 12.4)], fill=WALL, width=2)  # the plunger lane's wall
    d.text(to_px(5.1, 13.2), "plunger", fill=WALL)
    d.text(to_px(-0.8, 13.7), "drain", fill=WALL)
    for side in ("left", "right"):
        f = state.get("flippers", {}).get(side)
        if not f:
            continue
        up = abs(f["angle"]) > 0.3
        d.line([to_px(-f["pivot"][0], f["pivot"][1]), to_px(-f["tip"][0], f["tip"][1])],
               fill=FLIPPER_UP if up else FLIPPER_DOWN, width=8 if up else 6)
    for i, (sx, y) in enumerate(trail):  # fading path of the ball
        x, py = to_px(sx, y)
        d.ellipse([x - 2, py - 2, x + 2, py + 2], fill=TRAIL)
    for b in state.get("balls", []):
        x, y = to_px(-b["x"], b["y"])
        d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=BALL)
    d.text((8, 6), score_text or f"score {state.get('score', 0):,}", fill="#e8ecff")
    out = io.BytesIO()
    img.save(out, "PNG", compress_level=1)
    return base64.b64encode(out.getvalue()).decode()


def status(state, decision, kind, ff, balls_lost, health_trouble=False):
    """The Observatory's status record (`event: status`) for the latest decision."""
    held = [s for s in ("left", "right") if ff and ff[s]["up"]]
    record = {"event": "status", "title": "3D Space Cadet Pinball", "game": 4 - state.get("ball_number", 3),
              "playing": state.get("game_mode") == "in_game", "held": [f"{s} flipper" for s in held],
              "why": decision.get("choice", ""), "screen": {"size": list(SIZE), "smooth": True},
              "score": state.get("score", 0), "lives": state.get("ball_number")}
    facts = [{"label": "decision", "value": f"{decision.get('choice')}" + (f" + {decision['nudge']}" if decision.get("nudge") else "")
              + f" ({decision.get('source')})", "tone": None},
             {"label": "kind", "value": kind, "tone": None},
             {"label": "message", "value": state.get("message") or "-", "tone": None},
             {"label": "balls lost", "value": balls_lost, "tone": None},
             {"label": "tilt meter", "value": f"{state.get('nudge_count', 0):.1f} (tilts at 1.0)",
              "tone": "bad" if state.get("tilt_lock") else "warn" if state.get("nudge_count", 0) > 0.5 else None}]
    if ff:
        b = ff["ball"]
        facts += [{"label": "ball", "value": f"x {b['sx']:.1f}, y {b['y']:.1f}, speed {b['speed']:.1f}", "tone": None},
                  {"label": "still for", "value": f"{b.get('still_s', 0):.1f} s", "tone": "warn" if b.get("still_s", 0) >= 3 else None}]
    if health_trouble:
        facts.insert(0, {"label": "model", "value": "NOT ANSWERING IN TIME", "tone": "bad"})
    record["facts"] = facts
    record["series"] = [{"key": "score", "label": "score", "value": state.get("score", 0), "unit": "", "worse": None,
                         "colour": "#2ef2ff"}]
    if decision.get("latency_ms") is not None:
        record["series"].append({"key": "latency", "label": "model answer", "value": round(decision["latency_ms"]),
                                 "unit": "ms", "worse": None, "colour": "#ff8aa8"})
    return record
