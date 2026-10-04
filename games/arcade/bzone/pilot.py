"""S1M drives Battlezone with command sequences: treads and fire, with timings. The code only plays them out.

A plan is chosen by the model in three small choice questions, each built on the answer before:
  1. step 1: which tread command (one of nine: each tread forward, back or still)
  2. how long to hold step 1 (0.1 to 3 s), and fire: now, at the end of step 1, or hold
  3. step 2: which tread command after that, held until the next plan arrives
The code plays the plan on a clock: hold step 1 for its time (pressing fire when chosen), then step 2. The model plans
the next sequence while this one runs; the new plan replaces whatever is left. The code computes no targets and makes
no choices: it only describes what each option would do (where the enemy would end up, how far the tank would move,
whether a shot would hit) - physics worked forward from the facts - and presses what was chosen.

Why: a model answering in ~0.3 s cannot steer tick by tick (a turn held until its next answer overshot every time);
asked for a duration as a plain number it barely varied (tev1: 1.3-1.5 s whether the enemy was 5 or 60 degrees off),
but choosing among durations described by their effect it picked the right one 4 times in 5 (3 October 2026).
"""
import dataclasses
import math
import random
import time

from arcadekit.decisions import DecisionWorker
from .controls import ARC_LEFT, ARC_RIGHT, BACK_ARC_LEFT, BACK_ARC_RIGHT, DRIVE, REVERSE, TURN_LEFT, TURN_RIGHT

PIVOT_DEG_S, ARC_DEG_S = 21.5, 10.8  # measured: degrees a second
DRIVE_U_S, ARC_U_S = 2900, 1450  # measured: world units a second

TREADS = {  # name: (controls held, words, nose swing degrees a second (+ left), forward units a second)
    "forward": (DRIVE, "both treads forward: drive straight", 0, DRIVE_U_S),
    "reverse": (REVERSE, "both treads back: back up straight", 0, -DRIVE_U_S),
    "pivot_left": (TURN_LEFT, "left tread back, right forward: turn left on the spot", PIVOT_DEG_S, 0),
    "pivot_right": (TURN_RIGHT, "left tread forward, right back: turn right on the spot", -PIVOT_DEG_S, 0),
    "arc_left": (ARC_LEFT, "right tread forward only: turn left while moving", ARC_DEG_S, ARC_U_S),
    "arc_right": (ARC_RIGHT, "left tread forward only: turn right while moving", -ARC_DEG_S, ARC_U_S),
    "back_left": (BACK_ARC_LEFT, "left tread back only: back up while turning left", ARC_DEG_S, -ARC_U_S),
    "back_right": (BACK_ARC_RIGHT, "right tread back only: back up while turning right", -ARC_DEG_S, -ARC_U_S),
    "stop": (frozenset(), "both treads still: stand still", 0, 0),
}
DURATIONS = (0.1, 0.25, 0.5, 1.0, 2.0, 3.0)
INSTRUCTIONS = "You drive a Battlezone tank and plan its next moves."
# One goal, one sentence: the model first picks the goal, then plans its moves under that goal's sentence alone. With
# all five rules in one paragraph it turned toward an off-nose enemy 1 time in 30 and chose "forward" 21 times; told
# only "ATTACK: bring the enemy into your sights and shoot", 15 times and 1 (offline, 30 logged situations, tev1).
GOALS = {
    "attack": "ATTACK: bring the enemy into your sights and shoot.",
    "approach": "APPROACH: close in at a slight angle, keeping the enemy a little off your nose, so its shots miss.",
    "evade": "EVADE: it fired at where you are: get off that line, moving across it.",
    "search": "SEARCH: the enemy is behind you or out of sight: turn toward its side while moving.",
    "missile": "MISSILE: back up, keep the missile in front of you, and shoot when it is low.",
    "patrol": "PATROL: no enemy: drive on and keep clear of obstacles.",
}


def side(deg):
    if deg is None:
        return "?"
    return "dead ahead" if abs(deg) < 1 else f"{abs(deg):.0f} deg {'left' if deg > 0 else 'right'} of the nose"


def situation(state, f):
    """What the model is told about now: what a player sees and hears."""
    lines = []
    if f.enemy_side == "none":
        lines.append("No enemy (the last one is exploding).")
    else:
        kind = "MISSILE" if f.enemy_kind == "missile" else "Enemy tank"
        lines.append(f"{kind} {side(f.enemy_bearing_deg) if f.enemy_bearing_deg is not None else 'to the ' + f.enemy_side}"
                     + (f", {f.enemy_distance} units away." if f.enemy_distance else ", beyond the radar."))
        if f.enemy_kind == "missile":
            lines.append("Low enough to hit." if f.missile_low else f"Height {f.missile_height}: too high to hit.")
        elif f.enemy_holds_fire:
            lines.append("It has just appeared and cannot fire yet.")
        elif f.enemy_shell == "flying":
            lines.append("IT FIRED: its shell is coming at where you were.")
        elif f.enemy_shell == "exploding":
            lines.append("It cannot fire for a moment.")
        elif f.enemy_aim is not None:
            lines.append("Its gun points at you." if abs(f.enemy_aim) < 2 else
                         f"Its gun points {abs(f.enemy_aim) * 360 / 256:.0f} deg away from you.")
    if f.blocked:
        lines.append("You are against an obstacle.")
    if f.cover:
        lines.append(f"A {f.cover} is between you and it.")
    lines.append("Gun ready." if state.tank.fire == 0 else "Gun reloading.")
    return " ".join(lines)


def effect(f, bearing, name, seconds, clear_ahead, clear_behind):
    """Physics worked forward: where the enemy would be and how far the tank moves, holding `name` for `seconds`."""
    _, _, swing, speed = TREADS[name]
    move = speed * seconds
    parts = []
    if bearing is not None and name != "stop":
        after = bearing - swing * seconds
        # in words as well as numbers: the model weighs words (told "closer to / farther from your sights" it turned
        # toward the enemy 32 times in 35; told only where it would end up, 1 in 35)
        # ... and the one that gets there says so: told only "closer" for every short turn, it chose 0.1 s for a
        # 21-degree turn (22 of 25 attack plans turned the right way, nearly all too little)
        if abs(after) < 1.5 and abs(bearing) >= 1.5:
            trend = "IN YOUR SIGHTS"
        elif bearing and after and (after > 0) != (bearing > 0) and abs(after) >= 1.5:
            trend = "OVERSHOOTS: past your sights"
        else:
            trend = ("CLOSER to your sights, not there yet" if abs(after) < abs(bearing) - 0.5 else
                     "FARTHER from your sights" if abs(after) > abs(bearing) + 0.5 else "aim unchanged")
        parts.append(f"enemy ends up {side(after)} ({trend})")
    elif swing:
        parts.append(f"turns {abs(swing * seconds):.0f} deg {'left' if swing > 0 else 'right'}")
    if move > 0:
        parts.append(f"moves {move:.0f} forward" + (" INTO AN OBSTACLE" if clear_ahead is not None and clear_ahead < move
                                                    else ""))
    elif move < 0:
        parts.append(f"backs {-move:.0f}" + (" INTO AN OBSTACLE" if clear_behind is not None and clear_behind < -move
                                             else ""))
    elif name == "stop":
        parts.append("stays put: easy to hit")
    else:
        parts.append("stays in place")
    return ", ".join(parts)


def shot(f, bearing):
    """Would a shot fired with the enemy at this bearing hit? (how far the shell passes it, against the hit radius)"""
    if f.enemy_distance is None or bearing is None:
        return "no target in range"
    miss = abs(f.enemy_distance * math.sin(math.radians(bearing)))
    return "HITS" if miss <= (f.hit_radius or 0) and abs(bearing) < 90 else f"MISSES by {miss:.0f}"


def goals_now(f):
    """The goals that make sense now, each with the facts that bear on it."""
    if f.enemy_side == "none":
        return {"patrol": "no enemy: drive on"}
    b = f.enemy_bearing_deg
    out = {}
    if f.enemy_kind == "missile":
        out["missile"] = "a missile is coming: " + ("low enough to hit" if f.missile_low else "too high to hit yet")
    else:
        if f.enemy_shell == "flying":
            out["evade"] = "it has fired: its shell is coming at where you are"
        if b is not None and abs(b) < 90:
            away = f.enemy_aim is not None and abs(f.enemy_aim) > 20
            out["attack"] = (f"turn {abs(b):.0f} deg {'left' if b > 0 else 'right'} onto it and shoot"
                             + ("; its gun points away from you" if away else "; it can fire back"
                                if not f.enemy_holds_fire and f.enemy_shell == "none" else "; it cannot fire back now"))
            out["approach"] = f"close in at a slight angle: it is {f.enemy_distance or '?'} units away"
    if b is None or abs(b) >= 60:
        out["search"] = f"it is {side(b) if b is not None else 'to the ' + f.enemy_side}: turn toward it while moving"
    return out


def duration_text(f, b, cmd, d):
    """A duration option: for a turn with the enemy in front, how much turn is left or overshot (benchmark D1: the best
    duration 39 times in 54 and within one step 50, against 30 and 40 for "enemy ends up ... (closer)"); otherwise the
    effect. A move into an obstacle says so either way."""
    full = effect(f, b, cmd, d, f.obstacle_ahead, f.obstacle_behind)
    swing = TREADS[cmd][2]
    if b is None or not swing or abs(b) >= 90:
        return f"{cmd} for {d:g} s: {full}"
    after = b - swing * d
    if abs(after) < 1.5:
        words = "the enemy ends IN YOUR SIGHTS"
    elif (after > 0) == (b > 0):
        words = f"{abs(after):.0f} deg still to turn"
    else:
        words = f"turns PAST it by {abs(after):.0f} deg"
    return f"{cmd} for {d:g} s: {words}" + (", INTO AN OBSTACLE" if "INTO AN OBSTACLE" in full else "")


def verdict_words(verdict):
    return "HITS" if verdict == "HITS" else f"{verdict}: it would be wasted"


def fire_question(f, b, cmd=None, seconds=None):
    """(options, words for the state) for the fire question: the verdict in the state, the options plain (benchmark
    F2: right 62 times in 62, firing at every hit and holding every miss; with the verdict in the options, 44)."""
    options = {"now": "fire now", "hold": "hold fire"}
    words = f" A shot fired now {verdict_words(shot(f, b))}."
    if cmd is not None and TREADS[cmd][2]:
        options["after"] = f"fire at the end of {cmd}"
        words += f" A shot fired at the end of {cmd} {verdict_words(shot(f, b - TREADS[cmd][2] * seconds))}."
    return options, words


def shuffled(options):
    items = list(options.items())
    random.shuffle(items)  # a small model favours the first option listed: no option is always first
    return dict(items)


class PlanDecider:
    """Asks the three questions of a plan. Returns the plan, or a fallback plan (stand still) if the model fails."""

    def __init__(self, client):
        self.client = client

    def ask(self, text, name, instructions, criteria):
        reply = self.client.ask(text, {name: {"type": "choice", "instructions": instructions,
                                              "criteria": shuffled(criteria)}})
        answer = reply["answers"][name]
        if answer["choice"] not in criteria:
            raise ValueError(f"{name}: answered {answer['choice']!r}, not offered")
        return answer["choice"], answer.get("confidence"), reply["latency_ms"]

    def decide(self, facts, goal):
        f, state = facts["facts"], facts["state"]
        # Where the enemy will be when this plan starts: a plan takes ~1.4 s to make, while the tank carries on with
        # what it holds and the enemy keeps moving (physics worked forward: the tank's own turn, and the enemy's drift
        # seen over the last half second). Live, without this, the plans aimed where the enemy had been.
        lead = facts.get("lead_s", 0.0)
        if f.enemy_bearing_deg is not None and f.enemy_side != "none" and lead:
            ahead_b = f.enemy_bearing_deg + (facts.get("drift_deg_s", 0.0) - facts.get("held_swing", 0.0)) * lead
            ahead_b = (ahead_b + 180) % 360 - 180
            f = dataclasses.replace(f, enemy_bearing_deg=round(ahead_b, 1))
        text = situation(state, f) + (f" (Where things will be in {lead:.1f} s, when these moves start.)" if lead
                                      else "")
        b = f.enemy_bearing_deg if f.enemy_side != "none" else None
        ahead, behind = f.obstacle_ahead, f.obstacle_behind
        t0, latency = time.time(), []
        try:
            # 0. the goal (only those that make sense now); its one sentence is the instruction for the plan
            options = goals_now(f)
            if len(options) == 1:
                goal = next(iter(options))
            else:
                goal, _, ms = self.ask(text, "goal", INSTRUCTIONS + " Which goal now?",
                                       {g: f"{GOALS[g]} Now: {why}" for g, why in options.items()})
                latency.append(ms)
            instruction = f"{INSTRUCTIONS} {GOALS[goal]}"
            # 1. step 1: which tread command (each described by what it does in half a second)
            cmd1, c1, ms = self.ask(text, "step1", instruction + " First, which tread command?",
                                    {n: f"{w}; in 0.5 s: {effect(f, b, n, 0.5, ahead, behind)}"
                                     for n, (_, w, _, _) in TREADS.items()})
            latency.append(ms)
            # 2. how long (each duration described by its effect), then fire: now / at the end of step 1 / hold
            swing = TREADS[cmd1][2]
            durations = {f"{d:g}s": duration_text(f, b, cmd1, d) for d in DURATIONS}
            how_long, c2, ms = self.ask(text, "duration", instruction + f" You chose {cmd1}. For how long?", durations)
            latency.append(ms)
            seconds = float(how_long[:-1])
            fire_when = "hold"
            if state.tank.fire == 0 and b is not None and f.enemy_distance is not None:
                fire_options, words = fire_question(f, b, cmd1, seconds)
                fire_when, _, ms = self.ask(text + words, "fire", "Fire only if the shot HITS. When?", fire_options)
                latency.append(ms)
            # 3. step 2: what next, from where step 1 leaves the tank
            b2 = None if b is None else b - swing * seconds
            moved = TREADS[cmd1][3] * seconds
            ahead2 = None if ahead is None else ahead - max(0.0, moved)
            behind2 = None if behind is None else behind + min(0.0, moved)
            after_text = text + (f" After {cmd1} for {seconds:g} s the enemy will be {side(b2)}." if b2 is not None
                                 else "")
            cmd2, c3, ms = self.ask(after_text, "step2", instruction + " Then, which tread command until your next "
                                    "plan?", {n: f"{w}; in 0.5 s: {effect(f, b2, n, 0.5, ahead2, behind2)}"
                                              for n, (_, w, _, _) in TREADS.items()})
            latency.append(ms)
            return {"plan": [(cmd1, seconds, fire_when), (cmd2, None, "hold")], "goal": goal, "source": "model",
                    "latency_ms": sum(latency), "steps_ms": latency, "confidence": [c1, c2, c3], "state_text": text}
        except Exception as exc:  # the model down or slow: stand still until it answers again
            return {"plan": [("stop", None, "hold")], "source": "fallback", "note": f"model error: {exc}",
                    "latency_ms": (time.time() - t0) * 1000, "state_text": text}


class S1MPilot:
    """A lab policy (state, facts, t, last) -> (names, why) that plays the model's latest plan on the clock, and keeps
    one plan being made, so the model plans again as soon as it has answered. `asked` collects plans for the log."""

    def __init__(self, client):
        self.worker = DecisionWorker(PlanDecider(client), threads=1, max_queue=1)
        self.plan, self.plan_t, self.n, self.asked = None, 0.0, 0, []
        self.fired = False  # the current plan's fire was pressed
        self.ticks_by_source = {}
        self.lead_s = 1.4  # how long a plan takes to make (updated from each plan)
        self.seen = []  # (t, enemy world bearing in degrees) over the last half second: its drift

    def __call__(self, state, facts, t, last):
        for _, _, _, decision, _ in self.worker.take_all():
            self.plan, self.plan_t, self.fired = decision, t, False
            if decision["source"] == "model":
                self.lead_s = min(2.5, decision["latency_ms"] / 1000)
            self.asked.append({"t": round(t, 3), "event": "plan", "decision": decision})
        if facts.enemy_bearing_deg is not None and facts.enemy_side != "none":
            world = state.angle9 * 360 / 512 + facts.enemy_bearing_deg  # where it is, not relative to the nose
            self.seen = [(ts, w) for ts, w in self.seen if t - ts <= 0.5] + [(t, world)]
        else:
            self.seen = []
        if not self.worker.busy():
            drift = 0.0
            if len(self.seen) >= 2 and self.seen[-1][0] - self.seen[0][0] >= 0.2:
                dw = (self.seen[-1][1] - self.seen[0][1] + 180) % 360 - 180
                drift = dw / (self.seen[-1][0] - self.seen[0][0])
            held = self.holding_name(t)
            self.n += 1
            self.worker.submit((self.n, "plan"), None, {"facts": facts, "state": state, "lead_s": self.lead_s,
                                                       "drift_deg_s": drift,
                                                       "held_swing": TREADS[held][2] if held else 0.0}, urgent=True)
        if facts.dying:
            return frozenset(), "dying: nothing to steer"
        if self.plan is None:
            self.ticks_by_source["waiting"] = self.ticks_by_source.get("waiting", 0) + 1
            return frozenset(), "[waiting] no plan yet: treads still"
        steps = self.plan["plan"]
        first_name, first_s, fire_when = steps[0]
        in_first = first_s is not None and t - self.plan_t < first_s
        name = first_name if in_first or len(steps) == 1 else steps[1][0]
        names = TREADS[name][0]
        if not self.fired and ((fire_when == "now") or (fire_when == "after" and not in_first)):
            names, self.fired = names | {"FIRE"}, True  # one press (the game fires on a press)
        src = self.plan["source"]
        self.ticks_by_source[src] = self.ticks_by_source.get(src, 0) + 1
        plan_words = " then ".join(f"{n}" + (f" {s:g}s" if s else "") + (f" (fire {w})" if w != "hold" else "")
                                   for n, s, w in steps)
        return names, (f"[{src}] {self.plan.get('goal', '').upper()} step {1 if in_first else 2}: {name}"
                       + (" + FIRE" if "FIRE" in names else "")
                       + f" | plan: {plan_words}")

    def holding_name(self, t):
        """The tread command the current plan holds from now on (its step 2, or step 1 while that lasts)."""
        if self.plan is None:
            return None
        steps = self.plan["plan"]
        return steps[-1][0] if len(steps) == 1 or t - self.plan_t >= (steps[0][1] or 0) else steps[0][0]

    def model_share(self):
        total = sum(self.ticks_by_source.values()) or 1
        return {k: round(v / total, 3) for k, v in self.ticks_by_source.items()}
