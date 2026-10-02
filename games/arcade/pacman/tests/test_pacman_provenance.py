"""Who made each move: provenance per junction decision, frame numbers in the log, per-life stats and boards."""
import io
import json
import time
from dataclasses import replace

from games.arcade.pacman import goals, player
from games.arcade.pacman import deciders as _deciders
Decision = _deciders.Decision
from games.arcade.pacman import events as _events
GameStats = _events.GameStats
from games.arcade.pacman.maze import Maze
from games.arcade.pacman.tests.test_pacman_chain import (HEADON, IMAGE, STATE, FakeWorker, Steer, Stream, at,
                                                         junction_starts)
from games.arcade.pacman.state import decode


def moves(log):
    return [e for e in (json.loads(line) for line in log.getvalue().splitlines()) if e["event"] == "move"]


def make(states, **kw):
    log = io.StringIO()
    p = player.Player(Stream([(i, s, IMAGE) for i, s in enumerate(states, start=1)]), Steer(), FakeWorker(),
                      goals.GoalManager("clear_dots"), log, **kw)
    return p, log


def start():
    junction, arriving = next(junction_starts())
    return junction, arriving, arriving.lower(), Maze(IMAGE).exits(junction)


def test_a_model_answer_that_arrives_in_time_is_booked_as_the_models_move_with_its_age():
    junction, arriving, heading, exits = start()
    p, log = make([at(junction, heading)])
    p.was_playing = True  # a new game would clear the plan
    p.plan[(junction, arriving)] = (Decision(exits[0], "model", 0.9, 120.0), "clear_dots", time.time() - 0.3)
    p.tick()
    assert p.ledger.counts == {("model", "junction"): 1}
    record = moves(log)[0]
    assert (record["by"], record["via"], record["proposed"], record["executed"]) == ("model", "junction", exits[0], exits[0])
    assert record["confidence"] == 0.9 and record["latency_ms"] == 120 and 0.2 < record["age_s"] < 1.0
    assert record["late"] is None


def test_a_late_answer_is_booked_as_code_deciding_and_says_why():
    junction, arriving, heading, _ = start()
    p, log = make([at(junction, heading)])
    p.tick()  # nothing was asked before he arrived: the rule decides
    record = moves(log)[0]
    assert record["by"] == "code-late" and record["late"] == "seen_too_late"
    assert p.ledger.counts == {("code-late", "junction"): 1}


def test_the_rule_decider_run_is_booked_as_the_control_not_as_the_model():
    junction, arriving, heading, exits = start()
    p, log = make([at(junction, heading)])
    p.was_playing = True  # a new game would clear the plan
    p.plan[(junction, arriving)] = (Decision(exits[0], "rule"), "clear_dots", time.time())
    p.tick()
    assert p.ledger.counts == {("rule", "junction"): 1}


def test_a_model_failure_that_the_rule_covered_is_booked_as_code_fallback():
    junction, arriving, heading, exits = start()
    p, log = make([at(junction, heading)])
    p.was_playing = True  # a new game would clear the plan
    p.plan[(junction, arriving)] = (Decision(exits[0], "fallback", note="model error"), "clear_dots", time.time())
    p.tick()
    assert p.ledger.counts == {("code-fallback", "junction"): 1}


def test_a_move_the_reflex_changed_is_booked_as_the_reflex_not_the_model():
    st = decode(HEADON)
    log = io.StringIO()
    p = player.Player(None, Steer(), FakeWorker(), goals.GoalManager("clear_dots"), log)
    final = p._go(st, HEADON, (56, 38), "UP", "LEFT", "junction", "model")
    assert final == "DOWN" and p.last_how == "reflex"
    p._book_move(((56, 38), "UP"), Decision("LEFT", "model", 0.9), final)
    assert p.ledger.counts == {("code-override", "reflex"): 1}
    record = moves(log)[0]
    assert (record["proposed"], record["executed"], record["by"], record["via"]) == ("LEFT", "DOWN", "code-override", "reflex")


def test_every_log_line_carries_the_frame_so_it_lines_up_with_a_recording():
    junction, arriving, heading, _ = start()
    p, log = make([at(junction, heading)])
    p.tick()
    lines = [json.loads(line) for line in log.getvalue().splitlines()]
    assert lines and all("frame" in line for line in lines) and {line["frame"] for line in lines} == {1}


# ---------------------------------------------------------------- per-life stats and boards

def with_(state, **kw):
    return replace(state, **kw)


def test_each_life_lost_is_recorded_with_its_seconds_score_and_dots():
    stats = GameStats()
    s = with_(STATE, lives=3, score=0, dots_eaten=0, level=1)
    stats.update(s, IMAGE, "clear_dots", 100.0)
    stats.update(with_(s, score=900, dots_eaten=40), IMAGE, "clear_dots", 130.0)
    stats.update(with_(s, lives=2, score=950, dots_eaten=42), IMAGE, "clear_dots", 145.0)
    stats.update(with_(s, lives=2, score=1200, dots_eaten=60), IMAGE, "clear_dots", 170.0)
    stats.update(with_(s, lives=1, score=1300, dots_eaten=63), IMAGE, "clear_dots", 190.0)
    first, second = stats.summary()["lives"]
    assert first == {"life": 1, "seconds": 45, "score": 950, "dots": 42, "score_at_end": 950}
    assert (second["life"], second["seconds"], second["score"], second["dots"]) == (2, 45, 350, 21)


def test_boards_cleared_and_total_dots_survive_the_dot_counter_resetting_each_board():
    stats = GameStats()
    s = with_(STATE, lives=3, score=0, dots_eaten=0, level=1)
    stats.update(s, IMAGE, "clear_dots", 0.0)
    stats.update(with_(s, dots_eaten=240, score=2400), IMAGE, "clear_dots", 60.0)
    stats.update(with_(s, dots_eaten=0, level=2, score=2400), IMAGE, "clear_dots", 70.0)  # next board
    stats.update(with_(s, dots_eaten=30, level=2, score=2700), IMAGE, "clear_dots", 80.0)
    out = stats.summary()
    assert out["boards_cleared"] == 1 and out["dots_total"] == 270 and out["board_dots"] == 30
