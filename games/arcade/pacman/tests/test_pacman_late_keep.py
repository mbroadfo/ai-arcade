"""late="keep": with no answer on arrival nothing changes; he carries on or waits, and a late answer is still the model's."""
import io
import json

import pytest

from games.arcade.pacman import goals, player
from games.arcade.pacman.deciders import Decision
from games.arcade.pacman.maze import OPPOSITE, Maze, step
from games.arcade.pacman.tests.test_pacman_chain import IMAGE, Steer, Stream, at, junction_starts

MAZE = Maze(IMAGE)


class SlowWorker:
    """Takes questions and never answers by itself; a test hands answers in."""

    def __init__(self):
        self.keys, self.finished = set(), []

    def submit(self, key, goal, facts, urgent=False):
        self.keys.add(key)
        return True

    def pending(self, key):
        return key in self.keys

    def take_all(self):
        out, self.finished = self.finished, []
        for item in out:
            self.keys.discard(item[0])
        return out

    def clear_queued(self):
        pass


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now


def arrival(blocked):
    """A junction and arriving direction where going straight on is blocked (a T) or open."""
    for junction, came_from in junction_starts():
        arriving = OPPOSITE[came_from]  # moving this way, he entered from the `came_from` side
        if MAZE.passable(step(junction, arriving)) != blocked:
            return junction, arriving
    raise AssertionError("no such junction")


def make(states):
    clock, steer, log = Clock(), Steer(), io.StringIO()
    p = player.Player(Stream([(i, s, IMAGE) for i, s in enumerate(states, start=1)]), steer, SlowWorker(),
                      goals.GoalManager("clear_dots", clock=clock), log, clock=clock, late="keep")
    p.was_playing = True  # a new game would clear the book
    return p, steer, log, clock


def moves(log):
    return [e for e in map(json.loads, log.getvalue().splitlines()) if e["event"] == "move"]


def test_the_late_default_must_be_a_known_one():
    with pytest.raises(ValueError):
        player.Player(None, None, SlowWorker(), goals.GoalManager("clear_dots"), io.StringIO(), late="guess")


def test_with_the_way_open_he_carries_on_and_that_move_is_booked_to_code_when_he_leaves():
    junction, arriving = arrival(blocked=False)
    far = next(t for t, _ in junction_starts() if abs(t[0] - junction[0]) + abs(t[1] - junction[1]) > 12)
    p, steer, log, clock = make([at(junction, arriving.lower()), at(far, arriving.lower())])
    p.tick()
    assert steer.sent[-1] == arriving and moves(log) == [] and p.stats["late_keep"] == 1
    clock.now += 0.2
    p.tick()  # he is gone, and no answer came
    (move,) = moves(log)
    assert (move["by"], move["via"], move["executed"], move["waited_s"]) == ("code-late", "keep", arriving, 0.2)


def test_against_a_wall_he_waits_and_the_answer_when_it_comes_is_the_models_move():
    junction, arriving = arrival(blocked=True)
    p, steer, log, clock = make([at(junction, arriving.lower())] * 3)
    p.tick()
    assert steer.sent[-1] == arriving and moves(log) == []  # pushing into the wall: stopped
    clock.now += 0.1
    p.tick()
    assert moves(log) == [] and p.stats["late_keep"] == 1  # still waiting, counted once
    choice = next(d for d in MAZE.exits(junction) if d != arriving)
    clock.now += 0.15
    p.worker.finished.append(((junction, arriving), "clear_dots", {}, Decision(choice, "model", 0.8, 240.0), clock.now))
    p.tick()
    (move,) = moves(log)
    assert (move["by"], move["via"], move["executed"], move["waited_s"]) == ("model", "junction", choice, 0.25)
    assert steer.sent[-1] == choice
