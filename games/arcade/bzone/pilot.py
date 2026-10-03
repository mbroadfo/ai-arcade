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
# Aimed turns: the model chooses a turn with a size ("pivot onto the enemy: 6 deg right"); code stops turning when the
# tank has turned that much, measured from its heading when the question was asked. A turn held until the next answer
# (~0.7 s) swung ~15 degrees and overshot every time (3 October 2026: "the AI consistently oversteers").
AIMED = {  # name: (controls while turning, controls once there, words)
    "aim_pivot": (None, frozenset(), "pivot onto the enemy"),
    "aim_arc": (None, DRIVE, "arc onto the enemy while moving"),
    "enemy_off_left": (None, DRIVE, "veer so the enemy is 15 deg left of the nose, moving"),
    "enemy_off_right": (None, DRIVE, "veer so the enemy is 15 deg right of the nose, moving"),
}
VEER_DEG = 15
UNIT9 = 360 / 512  # degrees per unit of the 9-bit heading
RELOAD_S = 1.4  # a shell flies up to 127 updates before the gun is ready again (sooner if it hits something)
# Tested offline on 40 logged situations (3 October 2026): "keep it off your nose until you can shoot" made the model
# turn toward the enemy 1-11 times in 35; this plain aim-and-fire wording, 32 in 35 (nimble).
INSTRUCTIONS = ("You drive a tank. Always keep moving. Bring the enemy into your sights (0 deg). Never drive into an "
                "obstacle. Follow the advice. Which tread command?")

# The doctrine, as advice for the moment: the points that apply now are put in front of the model with the state.
# From the player (3 October 2026): always be moving unless hiding behind an obstacle; an enemy in sight and facing
# away: turn quickly onto it and get a shot off; after every shot change heading and move; an enemy behind may be
# facing you: back up on one tread, which keeps you moving and turns you toward it (mind obstacles behind).
# From arcade players (forums.arcade-museum.com, "Battlezone - anybody got some scoring tips"; search summaries of
# primetimeamusements.com and strategywiki.org): keep moving, in arcs; approach a tank at a slight angle (it shoots
# where you are and misses); back up a lot; hear a missile, back up, let it weave left-right-left, shoot when it is
# in front; make every shot count (one shell at a time); pyramids are cover. Each matches the game's code (README).
FACING_AWAY = 20  # angle units (28 degrees): its gun points well away from the tank
# Fire is its own question (asked only when the gun is ready and the enemy in range): offered among the tread commands,
# the model never chose it, even at 20 moments when the shot would hit; asked on its own, tev1 fired at 12 of 20 hits
# and 0 of 20 misses (nimble 7 and 10).
FIRE_INSTRUCTIONS = "Fire only if the shot hits. Fire now?"


def short(deg):
    if deg is None:
        return "?"
    return "ahead" if abs(deg) < 1 else f"{abs(deg):.0f} deg {'L' if deg > 0 else 'R'}"


def advice(state, facts, moving):
    """The doctrine points that apply now, in a few words each."""
    f, out = facts, []
    if f.enemy_side == "none":
        return ["No enemy: drive on and keep clear of obstacles."]
    if f.enemy_kind == "missile":
        out.append("Missile: back up, keep it in front of you, and shoot when it is low and dead ahead.")
    elif f.enemy_shell == "flying":
        out.append("It fired at where you are: keep moving, across its line, not straight at it or away.")
    elif f.enemy_side == "rear" or (f.enemy_side in ("left", "right") and abs(f.enemy_bearing or 64) > 60):
        out.append("It is behind you and may be facing you: back up on one tread toward its side, so you keep moving "
                   "and bring it into view.")
    elif f.enemy_side == "ahead" and f.enemy_aim is not None and abs(f.enemy_aim) > FACING_AWAY and not state.tank.fire:
        out.append("It is facing away from you: turn quickly onto it and shoot before it turns.")
    elif f.enemy_side == "ahead" and f.enemy_aim is not None and abs(f.enemy_aim) < 2:
        out.append("It is aimed at you: approach at a slight angle, never straight, so its shot misses.")
    if state.tank.fire:
        out.append("You just fired: change heading and keep moving.")
    if not moving and not f.cover and not f.blocked:
        out.append("You are standing still: a still tank is easy to hit.")
    if f.blocked:
        out.append("You are against an obstacle: back off or turn away from it.")
    return out


def describe(state, facts, lookahead=LOOKAHEAD_S, moving=True):
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
    tips = advice(state, f, moving)
    if tips:
        lines.append("Advice: " + " ".join(tips))

    options, aims = {}, {}
    known = f.enemy_bearing_deg is not None and f.enemy_side != "none"
    if known:  # aimed turns replace the held turns: the size is chosen, code stops at it
        b = f.enemy_bearing_deg
        if abs(b) >= 0.7:
            way = "left" if b > 0 else "right"
            secs = abs(b) / PIVOT_DEG_S
            aims["aim_pivot"] = (b, "pivot", f"pivot onto the enemy: turn {abs(b):.1f} deg {way} ({secs:.1f} s), standing")
            aims["aim_arc"] = (b, "arc", f"arc onto the enemy: turn {abs(b):.1f} deg {way} while moving "
                                         f"({abs(b) / ARC_DEG_S:.1f} s), then straight on")
        for key, sign in (("enemy_off_left", 1), ("enemy_off_right", -1)):  # the enemy 15 deg off the nose
            delta = b - sign * VEER_DEG  # + left: the turn that leaves the enemy VEER_DEG to that side
            if abs(delta) >= 2:
                aims[key] = (delta, "arc", f"veer {abs(delta):.0f} deg {'left' if delta > 0 else 'right'} while "
                                           f"moving: the enemy ends up {VEER_DEG} deg {'left' if sign > 0 else 'right'} "
                                           "of your nose (a slight angle: its shot misses)")
        options.update({k: v[2] for k, v in aims.items()})
    for name, (_, swing, speed) in COMMANDS.items():
        if known and (name.startswith(("pivot", "arc", "nudge"))):
            continue  # replaced by the aimed turns
        if name == "stop":
            options[name] = "stand still: easy to hit" if not f.cover else "stand still behind cover"
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
        elif swing and f.enemy_side in ("left", "right", "rear"):
            toward = (swing > 0) == (f.enemy_side == "left") if f.enemy_side != "rear" else None
            parts.append("turns toward the enemy behind you" if f.enemy_side == "rear" else
                         f"turns {'toward' if toward else 'away from'} the enemy ({f.enemy_side})")
        parts.append("moving" if move else "standing still")
        if hits_obstacle:
            parts.append("BLOCKED: an obstacle stops it, goes nowhere")
        options[name] = ", ".join(parts)
    fire = None
    if ready and f.enemy_side != "none" and f.miss_by is not None:  # the gun is ready and the enemy in range
        fire = {"fire": "fire now: the shot HITS the enemy" if f.on_target else
                "fire after your turn: HITS only if you pivot or arc onto the enemy; otherwise it MISSES by "
                f"{abs(f.miss_by)} and the gun reloads for {RELOAD_S} s",
                "hold": "hold fire: keep the shell for a shot that hits"}
    return " ".join(lines), options, fire, aims


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
        text, options, fire, aims = describe(state, f, self.lookahead, facts.get("moving", True))
        start9 = state.angle9  # the heading the turn sizes were measured from
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
            target9 = None
            if answer["choice"] in aims:
                delta, _, _ = aims[answer["choice"]]
                target9 = (start9 + round(delta / UNIT9)) % 512
            return {"command": answer["choice"], "fire": fired, "source": "model", "confidence": answer["confidence"],
                    "target9": target9, "style": aims[answer["choice"]][1] if answer["choice"] in aims else None,
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
        self.last_pos = None  # the tank's position on the last tick: is it moving?

    def __call__(self, state, facts, t, last):
        for _, _, _, decision, _ in self.worker.take_all():
            self.current = decision
            self.asked.append({"t": round(t, 3), "event": "answer", "decision": decision})
        moving = self.last_pos is not None and (state.tank.x, state.tank.y) != self.last_pos
        self.last_pos = (state.tank.x, state.tank.y)
        if not self.worker.busy():  # one question always in flight: the freshest state each time
            self.n += 1
            self.worker.submit((self.n, "pilot"), None, {"facts": facts, "state": state, "moving": moving},
                               urgent=True)
        if facts.dying:
            return frozenset(), "dying: nothing to steer"
        if self.current is None:
            self.ticks_by_source["waiting"] = self.ticks_by_source.get("waiting", 0) + 1
            return frozenset(), "[waiting] no answer yet: treads still"
        d = self.current
        turning = False
        if d.get("target9") is not None:  # an aimed turn: turn until the chosen heading, then hold the after-controls
            err = (d["target9"] - state.angle9 + 256) % 512 - 256  # + : still to turn left
            if d.get("done") or abs(err) <= 1 or (d.get("last_err") is not None and (err > 0) != (d["last_err"] > 0)):
                d["done"] = True
                names = AIMED[d["command"]][1]
            else:
                turning = True
                if d["style"] == "pivot":
                    names = TURN_LEFT if err > 0 else TURN_RIGHT
                else:
                    names = ARC_LEFT if err > 0 else ARC_RIGHT
                d["last_err"] = err
        else:
            names = COMMANDS[d["command"]][0]
            if d["command"].startswith("nudge"):  # one tick of pivot, then still until the next answer
                if self.nudged is d:
                    names = frozenset()
                self.nudged = d
        if d["fire"] and self.fired_with is not d and not turning:  # once the turn is done; one press per answer
            names, self.fired_with = names | {"FIRE"}, d
        self.ticks_by_source[d["source"]] = self.ticks_by_source.get(d["source"], 0) + 1
        conf = f" {d['confidence']:.2f}" if "confidence" in d else ""
        shot = "; FIRE" if d["fire"] else ""
        phase = " (turning)" if turning else " (there)" if d.get("done") else ""
        return names, (f"[{d['source']}] {d['command']}{phase}{conf}{shot}: "
                       f"{d['options'].get(d['command'], d.get('note', ''))}")

    def model_share(self):
        total = sum(self.ticks_by_source.values()) or 1
        return {k: round(v / total, 3) for k, v in self.ticks_by_source.items()}
