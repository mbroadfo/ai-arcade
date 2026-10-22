"""Who plays Space Cadet: the S1M model, and two labelled code controls for comparison.

The model decides the flippers (and the plunger pull) every window of game time while the game waits. The code only
describes the table in words and numbers (where the ball is and where it is heading, whether a flip would reach it) and
presses what was chosen. Nothing here picks a move for the model: `IdleControl` and `ReflexControl` are CONTROLS, booked as
code moves in the run log, never as the model playing.

Table, from the bridge: x runs to the screen's LEFT (the left flipper's pivot is at x +2.49) and y runs DOWN (top about -12,
the flippers at about +12, the drain below +13.8). We describe it in screen terms: sx = -x, so left is negative.
"""
import math
import random

FLIPPER_Y = 12.3  # about where the flippers' ends sit; a ball below it is past them
REACH = 2.1  # a flipper is about 1.9 long: a ball farther than this from its pivot cannot be hit
PLUNGER_LANE_SX = 6.0  # the launch lane is at the screen's far right (sx about +7)
# The ball is ready to launch only once it has rolled down to rest (y about 11.67): a pull before that jams the plunger.

HOLDS = {"neither": (False, False), "left": (True, False), "right": (False, True), "both": (True, True)}
NUDGES = {"nudge_left": "nudge_left", "nudge_right": "nudge_right", "nudge_up": "nudge_up"}  # choice: the bridge's input
NEAR = 4.5  # a flipper is "near" the ball within this of its pivot
SOON_S, LANE_HALF = 0.7, 2.5  # ... or when the ball will pass flipper height within SOON_S, within LANE_HALF of its pivot


def near(ff, side):
    """Is the ball a matter for this flipper now: close to it, or about to arrive over it? (When the model is asked.)"""
    f, a = ff[side], ff.get("arrives")
    return f["dist"] <= NEAR or bool(a and a["s"] <= SOON_S and abs(a["sx"] - f["pivot"][0]) <= LANE_HALF)


def nudge_matters(ff):
    """Is a nudge worth asking about: the ball has stayed put, or it is heading for the gap between the flippers?"""
    a = ff.get("arrives")
    return ff["ball"].get("still_s", 0) >= 1.5 or bool(a and abs(a["sx"]) < 0.9 and a["s"] <= 1.0)


PULLS = {"soft": 50, "medium": 100, "full": 150}  # frames of 10 ms the plunger is held


def screen(ball):
    """The ball in screen terms: sx (left negative), y (down positive), velocity in units a second."""
    return {"sx": -ball["x"], "y": ball["y"], "vx": -ball["dx"] * ball["speed"], "vy": ball["dy"] * ball["speed"],
            "speed": ball["speed"]}


def where(sx):
    return "far left" if sx < -3.5 else "left" if sx < -0.6 else "middle" if sx <= 0.6 else "right" if sx <= 3.5 else "far right"


def flipper_facts(state, ball):
    """For one ball: where it is, where it is going, which flipper could hit it. Plain geometry, no advice."""
    b = screen(ball)
    left, right = state["flippers"]["left"], state["flippers"]["right"]
    out = {"ball": b, "in_lane": b["sx"] > PLUNGER_LANE_SX and b["y"] > 11.5 and b["speed"] < 0.6}
    for name, f in (("left", left), ("right", right)):
        px, py = -f["pivot"][0], f["pivot"][1]
        dist = math.hypot(b["sx"] - px, b["y"] - py)
        out[name] = {"dist": dist, "reach": dist <= REACH and b["y"] <= FLIPPER_Y + 0.8, "up": abs(f["angle"]) > 0.3,
                     "pivot": (px, py), "tip": (-f["tip"][0], f["tip"][1])}
    if b["vy"] > 0.5 and b["y"] < FLIPPER_Y:
        t = (FLIPPER_Y - b["y"]) / b["vy"]
        out["arrives"] = {"s": t, "sx": b["sx"] + b["vx"] * t}
    return out


def situation(state, ff):
    """What the model is told: what a player sees."""
    if not state["balls"]:
        return (f"Score {state['score']}. Ball {4 - state['ball_number']} of 3. No ball on the table right now. "
                f"{state.get('message') or ''}").strip()
    b = ff["ball"]
    lines = [f"Score {state['score']}. Ball {4 - state['ball_number']} of 3."]
    vert = "falling toward the flippers" if b["vy"] > 1 else "rising" if b["vy"] < -1 else "moving sideways"
    lines.append(f"Ball in the {where(b['sx'])} of the table, {'low' if b['y'] > 9 else 'in the middle' if b['y'] > 0 else 'high'}"
                 f" (x {b['sx']:.1f}, y {b['y']:.1f}), {vert} at {b['speed']:.1f}.")
    if "arrives" in ff:
        a = ff["arrives"]
        side = ("over the LEFT flipper" if -2.6 <= a["sx"] <= -0.9 else "over the RIGHT flipper" if 0.9 <= a["sx"] <= 2.6 else
                "in the GAP between the flippers: it drains" if abs(a["sx"]) < 0.9 else "outside the flippers (a lane)")
        lines.append(f"Going straight it reaches flipper height in {a['s']:.2f} s at x {a['sx']:.1f}: {side}.")
    for name in ("left", "right"):
        f = ff[name]
        state_word = f"UP (held {f.get('up_s', 0):.1f} s)" if f["up"] else "down"
        lines.append(f"{name.capitalize()} flipper is {state_word}; the ball is {f['dist']:.1f} from its pivot: "
                     + ("in reach." if f["reach"] else "out of reach."))
    count = state.get("nudge_count", 0)
    lines.append(f"Tilt meter {count:.1f} (the table tilts and the flippers die above 1.0; each nudge adds about 1.6, "
                 "and it drains 1.0 a second).")
    if ff["ball"].get("still_s", 0) >= 1.5:
        lines.append(f"The ball has stayed within 0.6 of the same spot for {ff['ball']['still_s']:.1f} s.")
    if b["speed"] < 1.5 and b["y"] > 10 and (ff["left"]["up"] or ff["right"]["up"]):
        lines.append("The ball is almost still: a ball resting on a raised flipper stays there until the flipper is lowered.")
    return " ".join(lines)


def flipper_questions(ff):
    """The questions for one window: one for each flipper (raise or lower) and one for a nudge (none, or which way). Each
    option says what it would do now, as a fact. Asked apart, the model answered each flipper on its own state: asked "which
    flippers", with "both" among the answers, nimble:latest chose it 250 times in 284, with the ball far out of reach."""
    ball = ff["ball"]
    resting = ball["speed"] < 1.5 and ball["y"] > 10
    questions = {}
    for side in ("left", "right"):
        f = ff[side]
        if f["up"]:
            held = f"it has been up {f.get('up_s', 0):.1f} s"
            raise_ = (f"Keep the {side} flipper up: " + ("the ball is resting on it and will not move" if f["reach"] and resting
                                                         else "it can hit the ball" if f["reach"] else "the ball is out of its reach"))
            lower = (f"Lower the {side} flipper: " + ("the ball rolls off it" if f["reach"] and resting else "it is ready to flip again"))
        else:
            held = "it is down"
            raise_ = (f"Raise the {side} flipper: " + ("it hits the ball up the table" if f["reach"]
                                                       else "the ball is out of its reach, nothing happens"))
            lower = f"Keep the {side} flipper down: it stays ready"
        questions[side] = {"instructions": f"You play pinball. The {side} flipper: {held}. Raise it or lower it?",
                           "criteria": {"raise": raise_, "lower": lower}}
    tilt = f"adds about 1.6 to the tilt meter (now {ff['tilt']:.1f}, the table tilts above 1.0)" if "tilt" in ff else "adds to the tilt meter"
    jammed = " A jammed ball may be knocked loose." if ball.get("still_s", 0) >= 1.5 else ""
    questions["nudge"] = {"instructions": "You play pinball. Nudge the table?",
                          "criteria": {"none": "No nudge.",
                                       "nudge_left": f"Nudge left: pushes the ball left; {tilt}.{jammed}",
                                       "nudge_right": f"Nudge right: pushes the ball right; {tilt}.{jammed}",
                                       "nudge_up": f"Nudge up: pushes the ball up the table; {tilt}.{jammed}"}}
    return questions


class ModelPlayer:
    """The S1M model plays: one choice question a window for the flippers, one for the plunger pull. Anything it fails
    to answer is booked as a fallback (nothing pressed), so the share of model moves is known."""

    kind = "model"

    def __init__(self, client, ask_when="near"):
        """ask_when [timing]: "near" asks about a flipper only when the ball is near it (and about a nudge only when it matters);
        "always" asks every window. A window with nothing to ask is booked as "skipped": the flippers rest, and it is not a model move."""
        self.client = client
        self.ask_when = ask_when
        self.moves = {"model": 0, "fallback": 0, "skipped": 0}

    def ask(self, text, name, instructions, criteria):
        items = list(criteria.items())
        random.shuffle(items)  # a small model favours the first option listed
        reply = self.client.ask(text, {name: {"type": "choice", "instructions": instructions, "criteria": dict(items)}})
        answer = reply["answers"][name]
        if answer["choice"] not in criteria:
            raise ValueError(f"answered {answer['choice']!r}, not offered")
        return answer["choice"], answer.get("confidence"), reply["latency_ms"]

    def flippers(self, state, ff, held):
        ff["tilt"] = state.get("nudge_count", 0)
        text = situation(state, ff)
        questions = flipper_questions(ff)
        if self.ask_when == "near":
            questions = {n: q for n, q in questions.items()
                         if (near(ff, n) if n in ("left", "right") else nudge_matters(ff))}
            if not questions:
                self.moves["skipped"] += 1
                return {"choice": "neither", "nudge": None, "source": "skipped", "state_text": text}
        body = {}
        for name, q in questions.items():  # a small model favours the first option listed: shuffled
            items = list(q["criteria"].items())
            random.shuffle(items)
            body[name] = {"type": "choice", "instructions": q["instructions"], "criteria": dict(items)}
        try:
            reply = self.client.ask(text, body)
            picked = {}
            for name, q in questions.items():
                answer = reply["answers"][name]
                if answer["choice"] not in q["criteria"]:
                    raise ValueError(f"{name}: answered {answer['choice']!r}, not offered")
                picked[name] = answer
            up = tuple(s in picked and picked[s]["choice"] == "raise" for s in ("left", "right"))
            choice = {(False, False): "neither", (True, False): "left", (False, True): "right", (True, True): "both"}[up]
            nudge = None if picked.get("nudge", {"choice": "none"})["choice"] == "none" else picked["nudge"]["choice"]
            self.moves["model"] += 1
            return {"choice": choice, "nudge": nudge, "source": "model",
                    "confidence": {n: a.get("confidence") for n, a in picked.items()},
                    "latency_ms": reply["latency_ms"], "state_text": text, "options": questions}
        except Exception as exc:
            self.moves["fallback"] += 1
            return {"choice": "neither", "nudge": None, "source": "fallback", "note": f"model error: {exc}",
                    "state_text": text, "options": questions}

    def launch(self, state):
        text = (f"Score {state['score']}. Ball {4 - state['ball_number']} of 3. The ball is in the plunger lane. "
                "The longer you pull the plunger back, the harder it launches the ball.")
        options = {"soft": "Pull 0.5 s: a soft launch.", "medium": "Pull 1.0 s: a medium launch.",
                   "full": "Pull 1.5 s: a full launch."}
        try:
            choice, conf, ms = self.ask(text, "pull", "You play pinball: launch the ball. How hard?", options)
            self.moves["model"] += 1
            return {"choice": choice, "source": "model", "confidence": conf, "latency_ms": ms, "state_text": text}
        except Exception as exc:
            self.moves["fallback"] += 1
            return {"choice": "full", "source": "fallback", "note": f"model error: {exc}", "state_text": text}


class IdleControl:
    """CONTROL: never touches a flipper; launches full. The floor every player must beat."""

    kind = "control:idle"

    def flippers(self, state, ff, held):
        return {"choice": "neither", "source": "code"}

    def launch(self, state):
        return {"choice": "full", "source": "code"}


class ReflexControl:
    """CONTROL: raises a flipper while the ball is in its reach, but lets it down after 3 windows so a ball cannot rest on a
    raised flipper. Plain code, no model."""

    kind = "control:reflex"

    def __init__(self):
        self.up = {"left": 0, "right": 0}

    def flippers(self, state, ff, held):
        want = {}
        for side in ("left", "right"):
            self.up[side] = self.up[side] + 1 if ff[side]["reach"] else 0
            want[side] = 0 < self.up[side] <= 3
        choice = "both" if want["left"] and want["right"] else "left" if want["left"] else "right" if want["right"] else "neither"
        return {"choice": choice, "source": "code"}

    def launch(self, state):
        return {"choice": "full", "source": "code"}
