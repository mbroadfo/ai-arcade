"""Counts what happened in one game from consecutive decoded states, so each goal can be judged.

Detection (checked against a recorded 240 s stream, 9 ghost scores = 9 events): a ghost is eaten when its eyes
flag rises (about a second after the score jump; the frightened flag is not reliable at that moment). The fruit
is eaten when it disappears with Pac-Man within 2 tiles of it.
"""
from .maze import Maze

GHOSTS = ("red", "pink", "blue", "orange")
FRUIT_REACH = 2


class GameStats:
    def __init__(self):
        self.ghosts_eaten = self.fruit_eaten = self.fruit_missed = self.fruit_shown = 0
        self.energizers = self.deaths = self.reflexes = 0
        self.parks = self.park_deaths = 0  # safe-spot waits, and deaths while parked
        self.parked_seconds = 0.0
        self.feasts, self._feast = [], None  # ghosts eaten per energizer (a full feast is 4 = 3000 points)
        self.goal_seconds = {}
        self._prev, self._energizers_left, self._last_t = None, None, None

    def update(self, state, image, goal=None, now=None):
        prev = self._prev
        if goal and now is not None:
            if self._last_t is not None:
                self.goal_seconds[goal] = self.goal_seconds.get(goal, 0.0) + (now - self._last_t)
            self._last_t = now
        if prev is None:
            self._energizers_left = Maze(image).energizers_left()  # baseline for counting energizers eaten
        else:
            for name in GHOSTS:
                if state.eyes[name] and not prev.eyes[name]:
                    self.ghosts_eaten += 1
                    if self._feast is not None:
                        self._feast += 1
            if state.lives < prev.lives:
                self.deaths += 1
            if prev.fruit_tile and not state.fruit_tile:
                near = (abs(prev.pacman.tile[0] - prev.fruit_tile[0]) + abs(prev.pacman.tile[1] - prev.fruit_tile[1])
                        <= FRUIT_REACH)
                if near:
                    self.fruit_eaten += 1
                else:
                    self.fruit_missed += 1
            if state.dots_eaten != prev.dots_eaten:
                left = Maze(image).energizers_left()
                if self._energizers_left is not None and left < self._energizers_left:
                    self.energizers += self._energizers_left - left
                    if self._feast is not None:
                        self.feasts.append(self._feast)
                    self._feast = 0
                self._energizers_left = left
        if state.fruit_tile and (prev is None or not prev.fruit_tile):
            self.fruit_shown += 1
        self._prev = state

    def summary(self):
        return {"ghosts_eaten": self.ghosts_eaten, "fruit_eaten": self.fruit_eaten,
                "fruit_shown": self.fruit_shown, "fruit_missed": self.fruit_missed,
                "energizers": self.energizers, "feasts": self.feasts + ([self._feast] if self._feast is not None else []),
                "deaths": self.deaths, "reflexes": self.reflexes,
                "parks": self.parks, "parked_seconds": round(self.parked_seconds), "park_deaths": self.park_deaths,
                "goal_seconds": {k: round(v) for k, v in self.goal_seconds.items()}}
