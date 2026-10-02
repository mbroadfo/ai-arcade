"""Chained look-ahead: an answer for one junction triggers the question about the junction it leads to."""
import io
import json
import time
from dataclasses import replace
from pathlib import Path

from games.arcade.pacman import goals, player
from games.arcade.pacman import deciders as _deciders
RuleDecider = _deciders.RuleDecider
from games.arcade.pacman import features as _features
junction_facts = _features.junction_facts
features_score = _features.score_option
from games.arcade.pacman.maze import Maze, step
from games.arcade.pacman.state import decode

IMAGE = (Path(__file__).parent / 'fixtures' / 'pacman_play_ram.bin').read_bytes()
STATE = decode(IMAGE)


class FakeWorker:
    """Synchronous stand-in: submissions are answered by the rule decider on the next take_all()."""

    def __init__(self):
        self.submitted, self.finished, self.rule = [], [], RuleDecider()

    def submit(self, key, goal, facts, urgent=False):
        self.submitted.append(key)
        decision = self.rule.decide(facts, goal)
        self.finished.append((key, goal, facts, decision, time.time()))
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
        direction = p.plan[(tile, arriving)][0].choice
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
    facts = {"options": {"UP": option(edible_steps=1), "DOWN": option(edible_steps=None)}}
    assert p._revise(facts, "DOWN") == "UP"
    assert p._revise(facts, "UP") is None  # already the best
    near_tie = {"options": {"UP": option(edible_steps=5), "DOWN": option(edible_steps=6)}}
    assert p._revise(near_tie, "DOWN") is None  # not worth changing the plan for a small difference


def test_ablation_switches_default_to_code_not_overruling_the_decider():
    p = make_player()
    assert p.revise is False and p.reflex is True and p.chain_depth == player.CHAIN_DEPTH


def test_revise_is_skipped_unless_switched_on():
    import io

    class Broker:
        held = None
        steered = None

        def steer(self, direction):
            self.steered = direction

    junction, arriving = next(junction_starts())
    exits = Maze(IMAGE).exits(junction)
    chosen, other = exits[0], exits[1]
    for switch in (False, True):
        p = player.Player(None, Broker(), FakeWorker(), goals.GoalManager("clear_dots"), io.StringIO(), revise=switch)
        p._revise = lambda facts, was, other=other: other  # pretend fresh facts say another exit is clearly better
        p._go(STATE, IMAGE, junction, arriving, chosen, "junction", "rule")
        assert p.broker.steered == (other if switch else chosen)
        assert p.stats["revised"] == (1 if switch else 0)


def test_chain_depth_zero_turns_the_chain_off():
    p = make_player()
    p.chain_depth = 0
    start = next(junction_starts())
    p.worker.submit(start, p.goal, p._facts(STATE, IMAGE, *start))
    p.depth[start] = 0
    for _ in range(5):
        p._collect(STATE, IMAGE, frame=100)
    assert len(p.worker.submitted) == 1


def test_reflex_switch_off_lets_a_deadly_choice_stand():
    import io

    class Broker:
        held = None

        def steer(self, direction):
            self.steered = direction

    maze = Maze(IMAGE)
    tile, arriving = next(junction_starts())
    exits = maze.exits(tile)
    ahead = next(d for d in exits if d != {"LEFT": "RIGHT", "RIGHT": "LEFT", "UP": "DOWN", "DOWN": "UP"}[arriving])
    near = step(tile, ahead)
    st = replace(STATE, pacman=replace(STATE.pacman, tile=tile, direction=arriving.lower()),
                 frightened={n: False for n in STATE.ghosts}, eyes={n: False for n in STATE.ghosts},
                 ghosts={n: replace(g, tile=near, next_tile=near) if n == "red" else replace(g, tile=(0, 0), next_tile=(0, 0))
                         for n, g in STATE.ghosts.items()})
    on = player.Player(None, Broker(), FakeWorker(), goals.GoalManager("clear_dots"), io.StringIO())
    off = player.Player(None, Broker(), FakeWorker(), goals.GoalManager("clear_dots"), io.StringIO(), reflex=False)
    assert on._survive(st, IMAGE, tile, arriving, ahead, "junction") != ahead
    assert off._survive(st, IMAGE, tile, arriving, ahead, "junction") == ahead


def test_late_reasons_are_told_apart():
    p = make_player()
    key = ((40, 40), "LEFT")
    assert p.book.late_reason(key) == "not_asked"
    p.plan[((40, 40), "UP")] = (None, "g", 0.0)
    assert p.book.late_reason(key) == "other_arrival"
    p.worker.finished.append((key, "g", {}, None, 0.0))  # FakeWorker.pending: asked, answer not taken yet
    assert p.book.late_reason(key) == "in_flight"


class Stream:
    """Feeds a fixed sequence of (frame, state, image) snapshots to Player.tick()."""

    def __init__(self, states):
        self.states = list(states)

    def latest(self, newer_than=-1, timeout=2.0):
        return self.states.pop(0)


class Steer:
    held = None

    def __init__(self):
        self.sent = []

    def steer(self, direction):
        self.sent.append(direction)

    def tap(self, *a, **k):
        pass

    def release_all(self):
        pass


def at(tile, direction="left"):
    ghosts = {n: replace(g, tile=(0, 0), next_tile=(0, 0)) for n, g in STATE.ghosts.items()}
    return replace(STATE, ghosts=ghosts, mode="playing", pacman=replace(STATE.pacman, tile=tile, direction=direction))


def test_a_stored_answer_is_used_once_and_gone_when_pacman_leaves_the_junction():
    junction, arriving = next(junction_starts())
    heading = arriving.lower()
    far = next(t for t, a in junction_starts() if abs(t[0] - junction[0]) + abs(t[1] - junction[1]) > 12)
    seq = [(1, at(junction, heading), IMAGE), (2, at(junction, heading), IMAGE), (3, at(far, heading), IMAGE)]
    p = player.Player(Stream(seq), Steer(), FakeWorker(), goals.GoalManager("clear_dots"), io.StringIO())
    for _ in range(2):
        p.tick()
    key = (junction, arriving)
    assert key in p.consumed  # applied at its junction
    p.tick()  # Pac-Man is elsewhere now
    assert key not in p.plan and key not in p.consumed  # no stale reuse if he comes back to this junction later


def test_late_reason_says_when_the_junction_was_only_seen_too_late():
    p = make_player()
    key = ((40, 40), "LEFT")
    assert p.book.late_reason(key, asked_now=True) == "seen_too_late"
    assert p.book.late_reason(key) == "not_asked"


HEADON = (Path(__file__).parent / 'fixtures' / 'pacman_headon_ram.bin').read_bytes()  # recorded: a death on the right side


def test_a_ghost_reaching_the_junction_as_pacman_does_is_run_from_not_into():
    """Recorded: Pac-Man heads UP the h=38 corridor, 1 step from the junction (56,38) where his plan turns LEFT. A ghost
    comes DOWN the same corridor and reaches the junction as he does. From the junction, LEFT looks clear (the ghost is
    16 steps away by the long way round); only from his own tile is the ghost 3 steps ahead. He died here."""
    st = decode(HEADON)
    assert tuple(st.pacman.tile) == (57, 38)
    p = player.Player(None, Steer(), FakeWorker(), goals.GoalManager("clear_dots"), io.StringIO())
    assert p._survive(st, HEADON, (56, 38), "UP", "LEFT", "junction") == "DOWN"  # turn round, not on into the ghost
    assert json.loads(p.decisions_log.getvalue().splitlines()[-1])["event"] == "reflex"


def test_the_decision_at_a_junction_holds_while_pacman_is_still_on_its_tile():
    """Each heading change on the tile used to re-key the junction and decide again: UP, RIGHT, UP, RIGHT while a ghost
    closed in (recorded at (38,44), three deaths). One decision per visit now."""
    junction, arriving = next(junction_starts())
    exits = Maze(IMAGE).exits(junction)
    seq = [(i, at(junction, h), IMAGE) for i, h in enumerate(("right", "up", "right", "up", "left"), start=1)]
    steer = Steer()
    p = player.Player(Stream(seq), steer, FakeWorker(), goals.GoalManager("clear_dots"), io.StringIO())
    p.tick()
    first = steer.sent[-1]
    assert first in exits
    flip = next(d for d in exits if d != first)
    p.rule.decide = lambda facts, goal: type("D", (), {"direction": flip, "source": "rule"})()  # a new decision would flip
    for _ in range(4):
        p.tick()
    assert set(steer.sent) == {first}
    assert p.stats["late_rule"] <= 1  # decided once, not on every change of heading


def test_the_commitment_ends_when_pacman_leaves_the_junction():
    junction, arriving = next(junction_starts())
    far = next(t for t, a in junction_starts() if abs(t[0] - junction[0]) + abs(t[1] - junction[1]) > 12)
    seq = [(1, at(junction, arriving.lower()), IMAGE), (2, at(far, arriving.lower()), IMAGE)]
    p = player.Player(Stream(seq), Steer(), FakeWorker(), goals.GoalManager("clear_dots"), io.StringIO())
    p.tick()
    assert p.commit and p.commit[0] == junction
    p.tick()
    assert p.commit is None or p.commit[0] != junction


def test_observe_reports_what_is_on_screen_without_deciding():
    class Broker:
        held = "LEFT"

    p = player.Player(None, Broker(), FakeWorker(), goals.GoalManager("clear_dots"), io.StringIO())
    assert p.observe()["playing"] is False and "lines" not in p.observe()
    p.was_playing, p.last_state, p.last_image, p.last_frame = True, STATE, IMAGE, 42
    seen = p.observe()
    assert seen["event"] == "status" and seen["frame"] == 42 and seen["held"] == "LEFT"
    assert seen["score"] == STATE.score and seen["lives"] == STATE.lives and seen["goal"] == "clear_dots"
    assert seen["lines"][0][0] == "Pac-Man" and len(seen["lines"]) >= 5  # Pac-Man, then the four ghosts
    json.dumps(seen)  # it goes over the wire as JSON
    assert p.decisions_log.getvalue() == ""  # observing logs nothing
