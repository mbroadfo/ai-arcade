"""The S1M player for Battlezone: the model chooses the tactic; labelled code skills carry it out.

    on a game event -> ask S1M (in the background): the tactic, and what to do if fired on (a standing order)
    every tick (10 Hz) -> the current order, carried out by the skills (skills.py), kept clear of obstacles

The model is asked two choice questions in one request, with only the options that are possible now:
- tactic: flank left / flank right (approach beside the enemy, keeping it off the nose), attack (turn in and fire),
  missile defense (back up, shoot it when low), patrol (no enemy);
- if fired on: drive across the shell's line, pivot a few degrees and reverse, or arc away. Carried out the instant a
  shot is heard, without asking again: the decision was the model's, made before.
It is asked when something happens (a new enemy or missile, the enemy coming on screen or into range, a shot heard,
its shell spent, the missile low enough to shoot, close range, blocked, a life lost), and at least every
HEARTBEAT_S. Until its first answer, and whenever it fails, `fallback_order` (code, labelled "fallback") stands in.
Every tick says whose order it carried out.

What the model is told is the doctrine (KNOWLEDGE): what the lab measured about Battlezone, 3 October 2026.
"""
import time

from arcadekit.decisions import DecisionWorker
from .controls import ARC_LEFT, ARC_RIGHT, DRIVE, REVERSE, TURN_LEFT, TURN_RIGHT
from .facts import SHELL_UPDATES_PER_S
from .skills import DODGE_TURN_S, UNIT, broadside, flank, missile_defense, steer_clear, turn_to

HEARTBEAT_S = 3.0
CLOSE = 10000  # world units: an event when the enemy comes this close
DODGE_S = 0.6  # after a shot is heard, the standing order is carried out this long

TACTICS = {
    "patrol": "No enemy to fight: drive on, keeping clear of obstacles.",
    "flank_left": "Head for a point beside the enemy, to the left of the line to it, keeping it about 30 degrees off "
                  "the nose. It aims where the tank is, so crossing its line makes its shots miss.",
    "flank_right": "The same, to the right of the line to it.",
    "attack": "Turn in now and fire: pivot onto the enemy and shoot when lined up. Fast, but it puts the enemy on the "
              "nose, where its shots are hardest to dodge.",
    "missile_defense": "Back up, keep the missile on the nose, and fire when it is low enough to hit (it lands in front "
                       "of the tank, then weaves until close).",
}
IF_FIRED = {
    "drive_across": "Drive straight forward. Gets off the shell's line at once when the enemy is well off the nose; "
                    "useless when it is dead ahead.",
    "pivot_reverse": "Pivot away for a third of a second, then reverse along the new heading. The best measured answer "
                     "to a shot from near the nose.",
    "arc_away": "Turn away while moving forward. Survived few shots from near the nose in the lab.",
}
KNOWLEDGE = (
    "Battlezone doctrine, measured in this lab. The enemy has one shell: it cannot fire again while that shell flies "
    "or explodes, and a new enemy holds its fire for its first 32 frames (under a second) - those are the safe moments "
    "to turn in and shoot. It fires only when aimed straight at the tank, with no lead, so a tank crossing its line is "
    "missed; a shell takes about 1.2 s from the radar's edge. Shots from well off the nose were survived 10 times in "
    "11 by driving across; shots from near the nose are the dangerous ones. Tall boxes and pyramids stop shells; "
    "short boxes do not. A missile lands in front of the tank and can only be hit low.")


def render(facts, state):
    """The state as the model is told it: what a player sees and hears."""
    f = facts
    parts = [f"Lives {state.lives}, score {state.score}."]
    if f.enemy_side == "none":
        parts.append("No enemy: the last one is exploding.")
    else:
        kind = "A MISSILE" if f.enemy_kind == "missile" else "An enemy tank"
        where = {"ahead": "on screen", "left": "to the left", "right": "to the right", "rear": "behind"}[f.enemy_side]
        parts.append(f"{kind} is {where}" + (f", {f.enemy_bearing_deg:+.0f} degrees off the nose (+ left)"
                                             if f.enemy_bearing_deg is not None else "")
                     + (f", {f.enemy_distance} units away" if f.enemy_distance else ", beyond the radar") + ".")
        if f.enemy_kind == "missile":
            parts.append(f"Missile height {f.missile_height}: " + ("low enough to hit" if f.missile_low else
                                                                  "too high to hit") + (", weaving" if f.missile_weaving
                                                                                        else "") + ".")
        else:
            if f.enemy_holds_fire:
                parts.append("It has just appeared and cannot fire yet.")
            if f.enemy_aim is not None:
                parts.append("It is aimed straight at the tank." if abs(f.enemy_aim) < 2 else
                             f"Its aim is {f.enemy_aim * UNIT:+.0f} degrees off the tank.")
            if f.enemy_shell == "flying":
                parts.append("Its shell is in the air (heard): it cannot fire again until it lands.")
            elif f.enemy_shell == "exploding":
                parts.append("Its shell is exploding: it cannot fire for a moment.")
        if f.on_target:
            parts.append("A shot fired now would hit.")
    parts.append("Blocked by an obstacle." if f.blocked else f"Obstacle in the path {f.obstacle_ahead} units ahead."
                 if f.obstacle_ahead is not None else "The path ahead is clear.")
    parts.append(f"Covered from its fire by a {f.cover}." if f.cover else "No cover between it and the tank.")
    return " ".join(parts)


def tactics_now(facts):
    """The tactics that are possible now."""
    if facts.enemy_side == "none":
        return ["patrol"]
    if facts.enemy_kind == "missile":
        return ["missile_defense", "attack", "flank_left", "flank_right"]
    return ["flank_left", "flank_right", "attack"]


def fallback_order(facts):
    """Code's choice when the model has not answered or failed (labelled "fallback"): Flank & Fire's rules."""
    tactics = tactics_now(facts)
    if tactics == ["patrol"]:
        tactic = "patrol"
    elif facts.enemy_kind == "missile":
        tactic = "missile_defense"
    elif facts.enemy_holds_fire or facts.enemy_shell != "none" or (facts.enemy_distance or 1e9) < CLOSE:
        tactic = "attack"
    else:
        left = flank_side(facts)
        tactic = "flank_left" if left else "flank_right"
    near_nose = facts.enemy_bearing is None or abs(facts.enemy_bearing) < 0x10
    return {"tactic": tactic, "if_fired": "pivot_reverse" if near_nose else "drive_across"}


def flank_side(facts):
    """True for the left flank point when it needs the smaller turn."""
    from .skills import flank_point
    left, right = flank_point(facts, 1), flank_point(facts, -1)
    if not left or not right:
        return (facts.enemy_bearing or 0) >= 0
    return abs(left[0]) <= abs(right[0])


class S1MDecider:
    """Asks the model both questions in one request; falls back to code per question when it fails."""

    def __init__(self, client, min_confidence=0.0):
        self.client, self.min_confidence = client, min_confidence

    def decide(self, facts, goal):
        f, state = facts["facts"], facts["state"]
        tactics = tactics_now(f)
        fallback = fallback_order(f)
        questions = {"tactic": {"type": "choice", "instructions": KNOWLEDGE + " Which tactic now?",
                                "criteria": {t: TACTICS[t] for t in tactics}},
                     "if_fired": {"type": "choice", "instructions": "If the enemy fires at the tank before you are "
                                  "asked again, what should it do at once?", "criteria": dict(IF_FIRED)}}
        if len(tactics) == 1:
            questions.pop("tactic")  # nothing to choose
        t0 = time.time()
        try:
            reply = self.client.ask(render(f, state), questions, hint={"facts": f})
        except Exception as exc:  # the model down or slow: the player is never left without an order
            return {**fallback, "source": {"tactic": "fallback", "if_fired": "fallback"}, "note": f"model error: {exc}",
                    "latency_ms": (time.time() - t0) * 1000, "asked": list(questions)}
        order, source, probs = dict(fallback), {"tactic": "fallback", "if_fired": "fallback"}, {}
        for name, answer in reply["answers"].items():
            if answer["confidence"] >= self.min_confidence and answer["choice"] in questions[name]["criteria"]:
                order[name], source[name] = answer["choice"], "model"
                probs[name] = answer.get("probabilities", {})
        if len(tactics) == 1:
            order["tactic"], source["tactic"] = tactics[0], "no choice"
        return {**order, "source": source, "probabilities": probs, "latency_ms": reply["latency_ms"],
                "asked": list(questions), "state_text": render(f, state)}


class S1MPlayer:
    """A lab policy (state, facts, t, last) -> (names, why) that carries out the model's current order and asks it
    again on events. `asked` collects (t, event, decision) for the log and the Observatory."""

    def __init__(self, client, min_confidence=0.0):
        self.worker = DecisionWorker(S1MDecider(client, min_confidence), threads=1, max_queue=1)
        self.order, self.order_at, self.asked_at = None, 0.0, -1e9
        self.previous = None
        self.asked, self.n = [], 0
        self.ticks_by_source = {}

    def events(self, state, facts):
        """What happened since the last tick that the model should hear about."""
        p, f = self.previous, facts
        if p is None:
            return ["start"]
        out = []
        if f.enemy_side != "none" and (p.enemy_side == "none" or f.enemy_age < p.enemy_age):
            out.append("new enemy" if f.enemy_kind == "tank" else "missile launched")
        if f.enemy_kind != p.enemy_kind:
            out.append(f"enemy is now a {f.enemy_kind}")
        if (f.enemy_side == "ahead") != (p.enemy_side == "ahead") and f.enemy_side != "none":
            out.append("enemy on screen" if f.enemy_side == "ahead" else "enemy left the screen")
        if f.enemy_on_radar and not p.enemy_on_radar:
            out.append("enemy in range")
        if f.enemy_shell == "flying" and p.enemy_shell != "flying":
            out.append("shot heard")
        if f.enemy_shell == "none" and p.enemy_shell != "none":
            out.append("its shell is spent")
        if f.missile_low and not p.missile_low:
            out.append("missile low enough to hit")
        if (f.enemy_distance or 1e9) < CLOSE <= (p.enemy_distance or 1e9):
            out.append("enemy close")
        if f.blocked and not p.blocked:
            out.append("blocked")
        if f.enemy_side == "none" and p.enemy_side != "none":
            out.append("enemy destroyed")
        if state.lives < getattr(self, "lives", state.lives):
            out.append("life lost")
        return out

    def __call__(self, state, facts, t, last):
        for key, _, _, decision, done_at in self.worker.take_all():
            self.order, self.order_at = decision, t
            self.asked.append({"t": round(t, 3), "event": key[1], "decision": decision})
        happened = [] if facts.dying else self.events(state, facts)
        if happened or (not facts.dying and t - self.asked_at >= HEARTBEAT_S):
            self.n += 1
            self.worker.clear_queued()  # only the newest question matters
            if self.worker.submit((self.n, ", ".join(happened) or "heartbeat"), None,
                                  {"facts": facts, "state": state}, urgent=True):
                self.asked_at = t
        self.previous, self.lives = facts, state.lives
        if facts.dying:
            return frozenset(), "dying: nothing to steer"
        order = self.order or {**fallback_order(facts), "source": {"tactic": "fallback", "if_fired": "fallback"}}
        if order["tactic"] not in tactics_now(facts):  # the order no longer fits (the enemy died, a missile came)
            order = {**fallback_order(facts), "source": {"tactic": "fallback", "if_fired": "fallback"}}
        names, why, whose = self.carry_out(state, facts, order, last)
        self.ticks_by_source[whose] = self.ticks_by_source.get(whose, 0) + 1
        return names, f"[{whose}] {why}"

    def carry_out(self, state, facts, order, last):
        """The order, by the skills. Returns (names, why, whose order it was)."""
        src = order["source"]
        if facts.enemy_shell == "flying" and facts.enemy_kind == "tank" and facts.enemy_side != "none":
            since = (0x7F - state.enemy.fire) / SHELL_UPDATES_PER_S
            if since < DODGE_S:
                style = order["if_fired"]
                left = (facts.enemy_bearing or 0) >= 0 if facts.enemy_bearing is not None else facts.enemy_side == "left"
                if style == "drive_across":
                    names, why = DRIVE, "fired on: drive straight across its line"
                elif style == "pivot_reverse":
                    names, why = ((TURN_RIGHT if left else TURN_LEFT), "fired on: pivot away") if since < DODGE_TURN_S \
                        else (REVERSE, "fired on: reverse off the line")
                else:
                    names, why = (ARC_RIGHT if left else ARC_LEFT), "fired on: arc away"
                return (*steer_clear(facts, names, why + f" ({since:.2f} s; standing order {style})"),
                        src["if_fired"])
        tactic = order["tactic"]
        if tactic == "patrol":
            names, why = DRIVE, "patrol: drive on"
        elif tactic == "missile_defense":
            names, why = missile_defense(facts, last)
        elif tactic == "attack":
            if facts.enemy_bearing is None:
                names, why = turn_to(32 if facts.enemy_side == "left" else -32, True, "attack: turn toward it")
            else:
                names, why = broadside(facts, last)
                why = why.replace("broadside", "attack")
        else:
            side = 1 if tactic == "flank_left" else -1
            steer = flank(facts, may_pivot=facts.enemy_holds_fire, side=side)
            if steer is None:  # not on the radar: head its way, moving
                names, why = turn_to(32 if facts.enemy_side == "left" else -32 if facts.enemy_side == "right" else 0,
                                     False, f"{tactic}: toward it")
            else:
                names, why = steer
            if facts.on_target:
                names, why = names | ({"FIRE"} if "FIRE" not in last else frozenset()), why + "; on target: fire"
        return (*steer_clear(facts, names, f"{tactic}: {why}" if not why.startswith(tactic) else why), src["tactic"])

    def model_share(self):
        total = sum(self.ticks_by_source.values()) or 1
        return {k: round(v / total, 3) for k, v in self.ticks_by_source.items()}
