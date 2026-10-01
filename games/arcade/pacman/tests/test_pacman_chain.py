"""Chained look-ahead: an answer for one junction triggers the question about the junction it leads to."""
import io
import json
from dataclasses import replace
from pathlib import Path

from games.arcade.pacman import goals, player
from games.arcade.pacman.deciders import RuleDecider
from games.arcade.pacman.maze import Maze, step
from games.arcade.pacman.state import decode

IMAGE = (Path(__file__).parent / 'fixtures' / 'pacman_play_ram.bin').read_bytes()
STATE = decode(IMAGE)


class FakeWorker:
    """Synchronous stand-in: submissions are answered by the rule decider on the next take_all()."""

    def __init__(self):
        self.submitted, self.finished, self.rule = [], [], RuleDecider()

    def submit(self, key, goal, facts):
        self.submitted.append(key)
        decision = self.rule.decide(facts, goal)
        self.finished.append((key, goal, facts, decision, 0.0))
        return True

    def pending(self, key):
        return key in [k for k, *_ in self.finished]

    def take_all(self):
        out, self.finished = self.finished, []
        return out

    def clear_queued(self):
        pass


def make_player():
    return player.Player(None, None, FakeWorker(), goals.GoalManager("clear_dots"), io.StringIO())


def junction_starts():
    """Every (junction, arriving direction) pair in the maze, in a fixed order."""
    maze = Maze(IMAGE)
    for l in range(0x20, 0x40):
        for h in range(0x1E, 0x3E):
            tile = (l, h)
            exits = maze.exits(tile) if maze.passable(tile) else []
            if len(exits) >= 3:
                for arriving in exits:
                    yield tile, arriving


def run_chain(start, pause=False):
    p = make_player()
    p.worker.submit(start, p.goal, p._facts(STATE, IMAGE, *start))
    p.depth[start] = 0
    p.pause_until = 10_000 if pause else -1
    for _ in range(10):  # each pass answers what the previous pass asked
        p._collect(STATE, IMAGE, frame=100)
    return p


def long_chain_start():
    """A start whose chain is not cut short by looping back onto a junction it already answered."""
    for start in junction_starts():
        if len(run_chain(start, pause=True).worker.submitted) == 1 + player.CHAIN_DEPTH_PAUSE:
            return start
    raise AssertionError("no junction in the maze chains deep enough")


def test_each_answer_asks_about_the_junction_it_leads_to():
    start = long_chain_start()
    p = run_chain(start)
    keys = p.worker.submitted
    assert len(keys) == 1 + player.CHAIN_DEPTH  # the first question plus the chain, no more
    maze = Maze(IMAGE)
    for (tile, arriving), nxt in zip(keys, keys[1:]):
        direction = p.plan[(tile, arriving)][0].direction
        assert nxt[0] == maze.walk_to_decision(step(tile, direction), direction)[0]


def test_the_chain_goes_deeper_while_the_game_is_paused():
    start = long_chain_start()
    assert len(run_chain(start, pause=True).worker.submitted) == 1 + player.CHAIN_DEPTH_PAUSE
    assert len(run_chain(start).worker.submitted) == 1 + player.CHAIN_DEPTH


def test_chained_queries_are_counted_and_logged_with_their_depth():
    p = run_chain(long_chain_start())
    assert p.stats["chained"] == player.CHAIN_DEPTH
    depths = [json.loads(line)["chain"] for line in p.decisions_log.getvalue().splitlines()
              if json.loads(line)["event"] == "decision"]
    assert depths == list(range(player.CHAIN_DEPTH + 1))


def test_a_junction_already_answered_is_not_asked_again():
    p = run_chain(next(junction_starts()))
    assert len(set(p.worker.submitted)) == len(p.worker.submitted)


def test_a_ghost_score_jump_starts_a_pause_and_other_scores_do_not():
    p = make_player()
    p._watch_for_pause(replace(STATE, score=100), frame=500)  # first sight of the score: nothing to compare
    assert p.pause_until < 500
    p._watch_for_pause(replace(STATE, score=150), frame=510)  # an energizer (+50)
    assert p.pause_until < 510
    p._watch_for_pause(replace(STATE, score=550), frame=520)  # +400: the second ghost of a feast
    assert p.pause_until == 520 + player.PAUSE_FRAMES
    assert json.loads(p.decisions_log.getvalue().splitlines()[-1])["event"] == "pause"
    p._watch_for_pause(replace(STATE, score=560), frame=530)  # a dot: the pause is not extended
    assert p.pause_until == 520 + player.PAUSE_FRAMES
    p._watch_for_pause(replace(STATE, score=770), frame=600)  # +210: a ghost and a dot in one step
    assert p.pause_until == 600 + player.PAUSE_FRAMES


def test_a_stale_answer_is_revised_only_when_it_is_now_clearly_worse():
    p = make_player()
    p.goal = "hunt_ghosts"

    def option(**kw):
        base = {"food_steps": None, "threat_steps": None, "edible_steps": None, "fruit_steps": None,
                "energizer_steps": None, "room": 10, "reverse": False, "pressure": None, "ghosts_close": 0}
        base.update(kw)
        return base

    # the blue ghost is now toward UP; the stored answer (made when it was elsewhere) says DOWN
    facts = {"options": {"UP": option(edible_steps=2), "DOWN": option(edible_steps=None)}}
    assert p._revise(facts, "DOWN") == "UP"
    assert p._revise(facts, "UP") is None  # already the best
    near_tie = {"options": {"UP": option(edible_steps=5), "DOWN": option(edible_steps=6)}}
    assert p._revise(near_tie, "DOWN") is None  # not worth changing the plan for a small difference
