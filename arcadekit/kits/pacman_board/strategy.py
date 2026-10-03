"""The slow layer for games on Pac-Man's board: a model picks the goal and the stance; code still picks every direction.

The schema, the situation summary and the legality gates are this family's (the player's name comes from the game). The asking, validating and
never-blocking is general (tools/strategist.py). Survival (survival.py) overrides whatever is chosen.

Labelling for the ablation: when this layer is a model, the model sets *parameters* (goal and stance) and
the scoring code turns them into directions. That is a different rung from a model choosing directions.
"""
import time

from .features import ghost_modes
from .goals import FRAMES_PER_TILE, GAME_FPS, GOALS, STANCE
from .maze import ENERGIZER, Maze

MODEL_GOALS = ("clear_dots", "hunt_ghosts", "ambush", "eat_fruit")  # pacifist stays a pinned mission only
ADVICE_TTL = 8.0  # seconds a piece of advice is trusted; after that the code's own goal takes over
DWELL = 3.0  # a model-chosen goal is held at least this long (a goal whose precondition has vanished is dropped)
# timing "events" (the default for runs): the slow layer shares the model server with the junction questions, which
# answers one question at a time, so it asks only when it is worth it. Measured 2026-10-02 on nimble, idle server:
# goal alone 95 ms, goal and the three stance questions 665 ms.
TIMINGS = ("events", "always")
HEARTBEAT = 5.0  # seconds: the goal is asked at least this often (and at once on a game event)
STANCE_EVERY = 15.0  # seconds: the stance is asked this often, only when no junction question is waiting


def schema(name):
    """The slow layer's questions for a game whose player is called `name`."""
    return {
        "instructions": f"You advise the strategy of a {name} player. A fast layer steers and a reflex "
                        f"keeps {name} away from danger; you only set the aim and the temperament.",
        "goals": {g: GOALS[g] for g in MODEL_GOALS},
        "modifiers": {key: {"about": m["about"], "levels": dict(m["levels"]), "default": m["default"]}
                      for key, m in STANCE.items()},
    }


def situation(state, image):
    """Steps from Pac-Man to what matters, for the summary and for the legality gates."""
    maze = Maze(image)
    here = maze.bfs(tuple(state.pacman.tile))
    modes = ghost_modes(state)
    steps = lambda g: here.get(g.tile)  # noqa: E731
    return {
        "blue": sorted(d for n, g in state.ghosts.items() if modes[n] == "frightened" and (d := steps(g)) is not None),
        "normal": sorted(d for n, g in state.ghosts.items() if modes[n] == "normal" and (d := steps(g)) is not None),
        "energizers": sorted(d for t, d in here.items() if maze.code(t) == ENERGIZER),
        "fruit": here.get(tuple(state.fruit_tile)) if state.fruit_tile else None,
        "food_left": maze.food_left(),
        "ghosts": [(n, modes[n], steps(g)) for n, g in state.ghosts.items()],
    }


def legal(goal, sit):
    """A goal needs something to aim at. Saying 'hunt' with no blue ghost, or 'fruit' with none on screen, is
    not a judgment call, it is empty: the code falls back instead of pretending."""
    if goal == "hunt_ghosts":
        return bool(sit["blue"])
    if goal == "eat_fruit":
        return sit["fruit"] is not None
    if goal == "ambush":
        return bool(sit["energizers"])
    return True


def arrangement(blue, seconds_left):
    """How the edible ghosts are laid out and whether they can be caught: the sums a small model gets wrong."""
    seconds_to_nearest = blue[0] * FRAMES_PER_TILE / GAME_FPS  # a tile takes about 8 frames
    spread = blue[-1] - blue[0]
    text = (f"{len(blue)} edible ghost{'s' if len(blue) > 1 else ''} out of the ghost house, the nearest {blue[0]} steps "
            f"away (about {seconds_to_nearest:.0f} s to reach)")
    if len(blue) > 1:
        text += f", {'close together' if spread <= 8 else 'spread out'} (the farthest {blue[-1]} steps)"
    if seconds_left is not None:
        text += f". They stay blue for about {max(seconds_left, 0):.0f} more seconds"
        text += (": time enough to catch the nearest." if seconds_to_nearest * 1.3 < seconds_left
                 else ": barely enough time to catch even the nearest.")
    return text + ("" if text.endswith(".") else ".")


def describe(state, sit, goal, mods, seconds_blue_left=None, name="the player"):
    lines = [f"{name}, level {state.level}, {state.lives} lives, {sit['food_left']} dots left."]
    for name, mode, steps in sit["ghosts"]:
        where = "in the ghost house" if steps is None else f"{steps} steps away"
        lines.append(f"Ghost {name} is {'blue and edible' if mode == 'frightened' else mode}, {where}.")
    if sit["blue"]:
        lines.append(arrangement(sit["blue"], seconds_blue_left))
    lines.append(f"Energizer pills left: {len(sit['energizers'])}"
                 + (f", nearest {sit['energizers'][0]} steps away." if sit["energizers"] else "."))
    lines.append(f"Bonus fruit: {sit['fruit']} steps away." if sit["fruit"] is not None else "No bonus fruit on screen.")
    lines.append(f"Current goal: {goal}. Current stance: " + ", ".join(f"{k} {v}" for k, v in mods.items()) + ".")
    return "\n".join(lines)


class ModelGoalManager:
    """Drop-in for GoalManager: the same choose(state, image, frame), plus .mods (the stance).

    The code's own GoalManager keeps running underneath: it is the fallback before the first answer, after
    an answer expires, and when the model's goal has nothing to aim at; every answer is logged beside what
    the code would have chosen, so the two can be compared.
    """

    mission = "model"

    def __init__(self, strategist, code_manager, interval=1.0, dwell=DWELL, ttl=ADVICE_TTL, clock=time.time,
                 name="the player", timing="always", quiet=lambda: True):
        self.name = name  # the player's name, for the situation summary
        self.strategist, self.code, self.interval, self.dwell, self.ttl, self.clock = (
            strategist, code_manager, interval, dwell, ttl, clock)
        self.default_mods = {name: m["default"] for name, m in STANCE.items()}
        self.mods = dict(self.default_mods)
        self.goal, self.since, self.asked_at, self.advice_at = code_manager.goal, clock(), -1e9, None
        self.events = []
        self.stats = {"advice": 0, "agreed_with_code": 0, "gated": 0, "held": 0, "expired": 0}
        self.configure(timing, quiet)
        self.stance_at, self.signature, self.why = -1e9, None, None

    def configure(self, timing=None, quiet=None):
        """timing: "always" asks goal and stance as often as answers come (every `interval`); "events" asks the
        goal on game events and every HEARTBEAT seconds, the stance every STANCE_EVERY seconds when quiet().
        quiet: the player's "no junction question is waiting" (a timing switch: when to ask, never what to choose)."""
        if timing is not None:
            if timing not in TIMINGS:
                raise ValueError(f"timing must be one of {TIMINGS}")
            self.timing = timing
        if quiet is not None:
            self.quiet = quiet

    @staticmethod
    def _signature(state, sit):
        """What, when it changes, is worth a new goal: energizers, blue ghosts, fruit, lives, level."""
        return (len(sit["energizers"]), bool(sit["blue"]), sit["fruit"] is not None, state.lives, state.level)

    def _due(self, state, sit, now):
        """(ask now?, only these questions or None for all, why)."""
        if self.timing == "always":
            return now - self.asked_at >= self.interval, None, "interval"
        signature, before = self._signature(state, sit), self.signature
        self.signature = signature
        if before is not None and signature != before:
            changed = [n for n, a, b in zip(("energizers", "blue", "fruit", "lives", "level"), before, signature) if a != b]
            return True, ("goal",), "event: " + ", ".join(changed)
        if now - self.stance_at >= STANCE_EVERY and self.quiet():
            return True, None, "stance heartbeat"
        if now - self.asked_at >= HEARTBEAT and self.quiet():
            return True, ("goal",), "heartbeat"
        return False, None, None

    def drain(self):
        out, self.events = self.events, []
        return out

    def _apply(self, advice, code_goal, sit, now):
        self.stats["advice"] += 1
        self.stats["agreed_with_code"] += advice.goal == code_goal
        self.advice_at = now
        record = {"event": "advice", "goal": advice.goal, "code_goal": code_goal, "mods": advice.mods,
                  "confidence": round(advice.confidence, 2), "latency_ms": round(advice.latency_ms), "why": self.why}
        if advice.orders is not None:
            record["orders"] = advice.orders
        self.mods.update(advice.mods)
        if advice.mods:
            self.stance_until = now + (2 * STANCE_EVERY if self.timing == "events" else self.ttl)
        if not legal(advice.goal, sit):
            self.stats["gated"] += 1
            record["result"] = "gated: nothing to aim at"
        elif advice.goal != self.goal and now - self.since < self.dwell and legal(self.goal, sit):
            self.stats["held"] += 1
            record["result"] = "held: goal changed too recently"
        else:
            if advice.goal != self.goal:
                self.since = now
            self.goal = advice.goal
            record["result"] = "taken"
        self.events.append(record)

    def choose(self, state, image, frame=None):
        now = self.clock()
        code_goal = self.code.choose(state, image, frame)
        sit = situation(state, image)
        due, only, why = self._due(state, sit, now)
        if due:
            left = None
            if sit["blue"] and self.code.fright_left:
                left = self.code.fright_left / GAME_FPS  # frames of blue left, in game seconds
            asked = self.strategist.request(describe(state, sit, self.goal, self.mods, left, self.name),
                                            hint={"code_goal": code_goal, "mods": dict(self.mods)},
                                            **({"only": only} if only else {}))
            if asked:
                self.asked_at, self.why = now, why
                if only is None:
                    self.stance_at = now
            elif why and why.startswith("event"):
                self.signature = None  # the previous question was still out: try the event again next time
        advice = self.strategist.take()
        if advice:
            self._apply(advice, code_goal, sit, now)
        if self.advice_at is None or now - self.advice_at > self.ttl:
            if self.advice_at is not None:
                self.stats["expired"] += 1
                self.advice_at = None
            self.goal = code_goal
        if self.mods != self.default_mods and now > getattr(self, "stance_until", 0):
            self.mods = dict(self.default_mods)  # a stance not renewed in time lapses
        elif not legal(self.goal, sit):
            self.goal, self.since = code_goal, now  # what it aimed at has gone
        return self.goal


def code_chooser(hint):
    """The mock strategist's answer: what the code's own manager chose, with the stance left alone."""
    return {"goal": hint["code_goal"], **hint["mods"]}
