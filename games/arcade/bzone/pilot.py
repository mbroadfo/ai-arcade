"""S1M drives: the model chooses every tread and fire command. No skills, no tactics: the controls themselves.

    ask (one choice question) -> hold the chosen command -> ask again the moment the answer arrives

The question offers the tank's commands (seven tread combinations, and fire, either driving straight or standing),
each described by what it would do over the next LOOKAHEAD_S: where the enemy would be relative to the nose, whether
it runs into an obstacle, whether a shot would hit. Those are facts (facts.py, obstacles.py) worked forward; the
choice is the model's. A command is held until the next answer (about 0.1 s with `nimble`). Fire is a button the
game reads on a press: a "fire" answer presses it, and the next command releases it.

Code chooses only when the model fails (labelled fallback: stand still) and never steers on its own.
"""
import random
import time

from arcadekit.decisions import DecisionWorker
from .controls import ARC_LEFT, ARC_RIGHT, BACK_ARC_LEFT, BACK_ARC_RIGHT, DRIVE, REVERSE, TURN_LEFT, TURN_RIGHT
from .skills import UNIT

LOOKAHEAD_S = 0.15  # describe each command by its effect over this long (about one to two answers)
PIVOT_DEG_S, ARC_DEG_S = 21.5, 10.8  # measured: degrees a second
DRIVE_U_S, ARC_U_S = 2900, 1450  # measured: world units a second

COMMANDS = {  # name: (controls held, nose swing degrees a second (+ left), forward units a second)
    "forward": (DRIVE, 0, DRIVE_U_S),
    "reverse": (REVERSE, 0, -DRIVE_U_S),
    "pivot_left": (TURN_LEFT, PIVOT_DEG_S, 0),
    "pivot_right": (TURN_RIGHT, -PIVOT_DEG_S, 0),
    "arc_left": (ARC_LEFT, ARC_DEG_S, ARC_U_S),
    "arc_right": (ARC_RIGHT, -ARC_DEG_S, ARC_U_S),
    "back_left": (BACK_ARC_LEFT, ARC_DEG_S, -ARC_U_S),
    "back_right": (BACK_ARC_RIGHT, -ARC_DEG_S, -ARC_U_S),
    "stop": (frozenset(), 0, 0),
    # one tick of pivot, then still: a ~2 degree step for fine aim (a turn held for a whole answer swings ~11 degrees,
    # more than the half degree a long shot needs; in the first tev1 game every turn near the target overshot)
    "nudge_left": (TURN_LEFT, PIVOT_DEG_S, 0),
    "nudge_right": (TURN_RIGHT, -PIVOT_DEG_S, 0),
}
NUDGE_S = 0.1  # how long a nudge holds the pivot: one tick
RELOAD_S = 1.4  # a shell flies up to 127 updates before the gun is ready again (sooner if it hits something)
# Tested offline on 40 logged situations (3 October 2026): "keep it off your nose until you can shoot" made the model
# turn toward the enemy 1-11 times in 35; this plain aim-and-fire wording, 32 in 35 (nimble).
INSTRUCTIONS = ("You drive a tank. Bring the enemy into your sights (0 deg). Never drive into an obstacle. If it has "
                "fired at you, keep moving. Which tread command?")
# Fire is its own question (asked only when the gun is ready and the enemy in range): offered among the tread commands,
# the model never chose it, even at 20 moments when the shot would hit; asked on its own, tev1 fired at 12 of 20 hits
# and 0 of 20 misses (nimble 7 and 10).
FIRE_INSTRUCTIONS = "Fire only if the shot hits. Fire now?"


def short(deg):
    if deg is None:
        return "?"
    return "ahead" if abs(deg) < 1 else f"{abs(deg):.0f} deg {'L' if deg > 0 else 'R'}"


def describe(state, facts, lookahead=LOOKAHEAD_S):
    """(state text, {command: what it would do}) for this moment: short, so the model answers fast. (The first
    version, with eleven long options, took 479 ms an answer; it also fired at 62 shots it was told would miss.)"""
    f = facts
    lines = []
    if f.enemy_side == "none":
        lines.append("No enemy (the last one is exploding).")
    else:
        kind = "MISSILE" if f.enemy_kind == "missile" else "Enemy tank"
        lines.append(f"{kind} {short(f.enemy_bearing_deg) if f.enemy_bearing_deg is not None else f.enemy_side}"
                     + (f", {f.enemy_distance} away." if f.enemy_distance else ", out of range."))
        if f.enemy_kind == "missile":
            lines.append("Low enough to hit." if f.missile_low else f"Height {f.missile_height}: too high to hit.")
        elif f.enemy_holds_fire:
            lines.append("It cannot fire yet.")
        elif f.enemy_shell == "flying":
            lines.append("IT FIRED: its shell is coming at where you were.")
        elif f.enemy_shell == "exploding":
            lines.append("It cannot fire for a moment.")
        elif f.enemy_aim is not None and abs(f.enemy_aim) < 2:
            lines.append("It is aimed at you.")
    if f.blocked:
        lines.append("BLOCKED by an obstacle.")
    ready = state.tank.fire == 0
    lines.append("Gun ready." if ready else "Gun reloading.")

    options = {}
    for name, (_, swing, speed) in COMMANDS.items():
        if name == "stop":
            options[name] = "stand still"
            continue
        window = NUDGE_S if name.startswith("nudge") else lookahead
        move = speed * window
        clear = f.obstacle_ahead if move > 0 else f.obstacle_behind if move < 0 else None
        hits_obstacle = (clear is not None and clear < abs(move)) or (f.blocked and move > 0)
        parts = []
        if f.enemy_bearing_deg is not None:  # what it does for the aim, in words (the model weighs words, not numbers)
            now, after = abs(f.enemy_bearing_deg), abs(f.enemy_bearing_deg - swing * window)
            if after < now - 0.2:
                parts.append(f"enemy CLOSER to your sights ({now:.1f} -> {after:.1f} deg)")
            elif after > now + 0.2:
                parts.append(f"enemy FARTHER from your sights ({now:.1f} -> {after:.1f} deg)")
            else:
                parts.append(f"aim unchanged ({now:.1f} deg off)")
        elif swing and f.enemy_side in ("left", "right"):
            toward = (swing > 0) == (f.enemy_side == "left")
            parts.append(f"turns {'toward' if toward else 'away from'} the enemy ({f.enemy_side})")
        parts.append("moving" if move else "standing still")
        if hits_obstacle:
            parts.append("BLOCKED: an obstacle stops it, goes nowhere")
        options[name] = ", ".join(parts)
    fire = None
    if ready and f.enemy_side != "none" and f.miss_by is not None:  # the gun is ready and the enemy in range
        fire = {"fire": "fire now: the shot HITS the enemy" if f.on_target else
                f"fire now: the shot MISSES by {abs(f.miss_by)}; the gun then reloads for {RELOAD_S} s",
                "hold": "hold fire: keep the shell for a shot that hits"}
    return " ".join(lines), options, fire


def shuffled(options):
    items = list(options.items())
    random.shuffle(items)  # a small model favours the first option listed: no option is always first
    return dict(items)


class PilotDecider:
    def __init__(self, client):
        self.client = client
        self.lookahead = LOOKAHEAD_S  # becomes the measured answer time: a command is held that long

    def decide(self, facts, goal):
        f, state = facts["facts"], facts["state"]
        text, options, fire = describe(state, f, self.lookahead)
        options = shuffled(options)
        questions = {"command": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": options}}
        if fire:
            questions["fire"] = {"type": "choice", "instructions": FIRE_INSTRUCTIONS, "criteria": shuffled(fire)}
        t0 = time.time()
        try:
            reply = self.client.ask(text, questions)
            answer = reply["answers"]["command"]
            if answer["choice"] not in options:
                raise ValueError(f"answered {answer['choice']!r}, not offered")
            fired = fire is not None and reply["answers"].get("fire", {}).get("choice") == "fire"
            self.lookahead = min(0.5, max(0.1, reply["latency_ms"] / 1000))
            return {"command": answer["choice"], "fire": fired, "source": "model", "confidence": answer["confidence"],
                    "probabilities": answer.get("probabilities", {}),
                    "fire_probabilities": reply["answers"].get("fire", {}).get("probabilities"),
                    "latency_ms": reply["latency_ms"], "state_text": text, "options": options, "fire_options": fire}
        except Exception as exc:  # the model down or slow: stand still until it answers again
            return {"command": "stop", "fire": False, "source": "fallback", "note": f"model error: {exc}",
                    "latency_ms": (time.time() - t0) * 1000, "state_text": text, "options": options,
                    "fire_options": fire}


class S1MPilot:
    """A lab policy (state, facts, t, last) -> (names, why): holds the model's latest command, and keeps one question
    in flight, so the model is asked again as soon as it answers. `asked` collects answers for the log."""

    def __init__(self, client):
        self.worker = DecisionWorker(PilotDecider(client), threads=1, max_queue=1)
        self.current, self.n, self.asked = None, 0, []
        self.ticks_by_source = {}
        self.fired_with = None  # the answer whose fire press is being held: release on the next tick
        self.nudged = None  # the nudge answer already carried out (its one tick)

    def __call__(self, state, facts, t, last):
        for _, _, _, decision, _ in self.worker.take_all():
            self.current = decision
            self.asked.append({"t": round(t, 3), "event": "answer", "decision": decision})
        if not self.worker.busy():  # one question always in flight: the freshest state each time
            self.n += 1
            self.worker.submit((self.n, "pilot"), None, {"facts": facts, "state": state}, urgent=True)
        if facts.dying:
            return frozenset(), "dying: nothing to steer"
        if self.current is None:
            self.ticks_by_source["waiting"] = self.ticks_by_source.get("waiting", 0) + 1
            return frozenset(), "[waiting] no answer yet: treads still"
        d = self.current
        names = COMMANDS[d["command"]][0]
        if d["command"].startswith("nudge"):  # one tick of pivot, then still until the next answer
            if self.nudged is d:
                names = frozenset()
            self.nudged = d
        if d["fire"] and self.fired_with is not d:  # press once per answer (the game fires on a press)
            names, self.fired_with = names | {"FIRE"}, d
        self.ticks_by_source[d["source"]] = self.ticks_by_source.get(d["source"], 0) + 1
        conf = f" {d['confidence']:.2f}" if "confidence" in d else ""
        shot = "; FIRE" if d["fire"] else ""
        return names, f"[{d['source']}] {d['command']}{conf}{shot}: {d['options'].get(d['command'], d.get('note', ''))}"

    def model_share(self):
        total = sum(self.ticks_by_source.values()) or 1
        return {k: round(v / total, 3) for k, v in self.ticks_by_source.items()}
