"""Standing goals for the Pac-Man player, and the manager that holds one for a while.

A goal says what to try to achieve; it is chosen slowly (a pinned `--goal`, or `auto`, later a slow
LLM) and held for a minimum time. It is NOT the survival instinct: survival.py can override any goal
the instant a ghost is about to catch Pac-Man.
"""
import time

from .maze import ENERGIZER, Maze

GOALS = {
    "clear_dots": "Eat every dot to clear the level. Prefer the exit with the nearest dots. Ghosts are "
                  "hazards; touch a blue ghost only if it is in your way.",
    "hunt_ghosts": "Score from ghosts. Eat an energizer, then chase blue ghosts while they stay blue: "
                   "200, 400, 800, 1600 in a row. With none blue, head for an energizer.",
    "pacifist": "Eat dots but never eat a ghost, not even a blue one. Keep clear of every ghost.",
    "ambush": "Lure the ghosts toward you near an energizer, then eat it when they are close and chase them "
              "while blue: 200, 400, 800, then 1600 for the fourth. Never chase ghosts that are not blue.",
    "eat_fruit": "Eat the bonus fruit whenever it is on screen: take the shortest route to it. With no "
                 "fruit on screen, keep clearing dots.",
}
MISSIONS = ("auto",) + tuple(GOALS)

# Weights per goal for score_option: food, threat, room, edible, fruit, energizer, lure
WEIGHTS = {
    "clear_dots": (1.0, 1.6, 0.25, 0.0, 0.0, 0.0, 0.0),
    "hunt_ghosts": (0.3, 1.4, 0.2, 1.4, 0.0, 0.9, 0.0),
    "pacifist": (1.0, 1.8, 0.25, -1.6, 0.0, 0.0, 0.0),
    "ambush": (0.3, 1.6, 0.25, 0.0, 0.0, 0.0, 1.0),
    "eat_fruit": (0.3, 1.6, 0.25, 0.0, 4.0, 0.0, 0.0),
}

# The stance a slow layer can set: named levels, each scaling some of the weights above (indices into the
# WEIGHTS tuples). A model picks a level by name; it never sees or sets a raw number, and the scale is bounded.
STANCE = {
    "caution": {"about": "How careful to be about ghosts that can hurt Pac-Man.", "default": "normal",
                "levels": {"low": "take risks for points", "normal": "balanced",
                           "high": "keep well clear of ghosts, even at a cost in points"},
                "scale": {"low": 0.6, "normal": 1.0, "high": 1.6}, "weights": (1, 2)},
    "chase": {"about": "How hard to pursue blue (edible) ghosts.", "default": "normal",
              "levels": {"off": "ignore blue ghosts", "normal": "go for them when convenient",
                         "hard": "make eating them the priority"},
              "scale": {"off": 0.3, "normal": 1.0, "hard": 1.6}, "weights": (3,)},
    "greed": {"about": "How strongly to prefer eating dots.", "default": "normal",
              "levels": {"low": "dots can wait", "normal": "balanced", "high": "clear dots whenever possible"},
              "scale": {"low": 0.6, "normal": 1.0, "high": 1.5}, "weights": (0,)},
}


def scaled_weights(goal, mods=None):
    """The goal's weights with the stance applied. No stance (or all normal) gives the plain table entry."""
    weights = list(WEIGHTS[goal])
    for name, level in (mods or {}).items():
        spec = STANCE.get(name)
        if spec and level in spec["scale"]:
            for i in spec["weights"]:
                weights[i] *= spec["scale"][level]
    return tuple(weights)


def stance_text(mods):
    """One sentence of the non-default stance, for a prompt; empty when it is all default."""
    bits = [STANCE[n]["levels"][lv] for n, lv in (mods or {}).items()
            if n in STANCE and lv != STANCE[n]["default"] and lv in STANCE[n]["levels"]]
    return ("Stance: " + "; ".join(bits) + ".") if bits else ""


# Frames ghosts stay blue after an energizer, by level (Pac-Man Dossier; level 1 measured: 359 frames).
FRIGHT_FRAMES = {1: 360, 2: 300, 3: 240, 4: 180, 5: 120, 6: 300, 7: 120, 8: 120, 9: 60, 10: 300,
                 11: 120, 12: 60, 13: 60, 14: 180, 15: 60, 16: 60, 17: 0, 18: 60}
FRAMES_PER_TILE = 8  # Pac-Man's pace at level 1 (about 7.6 tiles per second at 60 frames per second)
HUNT_MARGIN = 0.6  # chase a blue ghost only if it is within this share of the tiles the window allows
FRUIT_RANGE = 40  # go for fruit within this many steps
AMBUSH_RANGE = 20  # head for an energizer when one is this close
AMBUSH_CHASERS = 2  # ... and this many normal ghosts are within CHASE_RADIUS steps
CHASE_RADIUS = 14
STAY = 1.4  # a goal that is already active keeps going while its trigger is within STAY x the entry threshold
AMBUSH_MAX_SECONDS, AMBUSH_COOLDOWN = 20.0, 15.0  # give up luring after this long, then not again for a while
DWELL_SECONDS = 4.0  # a goal is held at least this long unless its trigger vanishes or a better goal appears
RANK = {"clear_dots": 0, "pacifist": 0, "ambush": 1, "eat_fruit": 2, "hunt_ghosts": 3}


class GoalManager:
    """mission: "auto" picks by game state; any goal name pins that goal for the whole game.

    Auto policy, highest first: feast (blue ghosts we can still reach before they turn back), fruit,
    ambush (lure ghosts near an energizer), otherwise clear the dots. A better goal takes over at once;
    otherwise a goal is held for the dwell time. Survival (survival.py) overrides all of them.
    """

    def __init__(self, mission="auto", dwell=DWELL_SECONDS, clock=time.time):
        if mission not in MISSIONS:
            raise ValueError(f"mission must be one of {MISSIONS}, got {mission!r}")
        self.mission, self.dwell, self.clock = mission, dwell, clock
        self.goal, self.since = (mission if mission != "auto" else "clear_dots"), clock()
        self.blue_since, self.cooldown_until = None, 0.0
        self.fright_left = 0  # frames of blue left (0 when no ghost is blue)

    def _look(self, state, image, frame):
        maze = Maze(image)
        here = maze.bfs(tuple(state.pacman.tile))
        blue = [here[g.tile] for n, g in state.ghosts.items()
                if state.frightened[n] and not state.eyes[n] and g.tile in here]
        stay = lambda goal: STAY if self.goal == goal else 1.0  # noqa: E731
        chasers = sum(1 for n, g in state.ghosts.items()
                      if not state.frightened[n] and not state.eyes[n]
                      and here.get(g.tile, 99) <= CHASE_RADIUS * stay("ambush"))
        fruit = here.get(tuple(state.fruit_tile)) if state.fruit_tile else None
        energizers = [d for t, d in here.items() if maze.code(t) == ENERGIZER]
        if blue and self.blue_since is None:
            self.blue_since = frame
        elif not blue:
            self.blue_since = None
        left = FRIGHT_FRAMES.get(state.level, 0) - (frame - self.blue_since) if blue else 0
        self.fright_left = max(left, 0)
        reachable = [d for d in blue if d <= 2 or d * FRAMES_PER_TILE <= left * HUNT_MARGIN * stay("hunt_ghosts")]
        reachable = reachable if left > 0 else []  # a ghost two steps away is worth finishing while any window is left
        return {"feast": bool(reachable), "fruit": fruit is not None and fruit <= FRUIT_RANGE * stay("eat_fruit"),
                "ambush": bool(energizers) and min(energizers) <= AMBUSH_RANGE * stay("ambush")
                and chasers >= (1 if self.goal == "ambush" else AMBUSH_CHASERS)}

    def choose(self, state, image, frame=None):
        if self.mission != "auto":
            return self.mission
        now = self.clock()
        frame = frame if frame is not None else now * 50  # emulation runs near 50 frames per wall second
        look = self._look(state, image, frame)
        if self.goal == "ambush" and now - self.since > AMBUSH_MAX_SECONDS:
            self.cooldown_until = now + AMBUSH_COOLDOWN
        look["ambush"] = look["ambush"] and now >= self.cooldown_until
        if look["feast"]:
            want = "hunt_ghosts"
        elif look["fruit"]:
            want = "eat_fruit"
        elif look["ambush"]:
            want = "ambush"
        else:
            want = "clear_dots"
        active = {"hunt_ghosts": look["feast"], "eat_fruit": look["fruit"], "ambush": look["ambush"]}
        gone = self.goal in active and not active[self.goal]
        if want != self.goal and (gone or RANK[want] > RANK[self.goal] or now - self.since >= self.dwell):
            self.goal, self.since = want, now
        return self.goal
