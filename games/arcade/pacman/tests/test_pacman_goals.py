from dataclasses import replace
from pathlib import Path

import pytest

from games.arcade.pacman import events, features, goals, survival
from games.arcade.pacman.maze import Maze
from games.arcade.pacman.state import decode, pixel_to_tile

IMAGE = (Path(__file__).parent / 'fixtures' / 'pacman_play_ram.bin').read_bytes()
STATE = decode(IMAGE)


def opt(**kw):
    base = {"food_steps": None, "threat_steps": None, "edible_steps": None, "fruit_steps": None,
            "energizer_steps": None, "room": 10, "reverse": False}
    base.update(kw)
    return base


def test_every_goal_has_text_and_weights():
    assert set(goals.GOALS) == set(goals.WEIGHTS)
    assert "auto" in goals.MISSIONS


def test_pacifist_avoids_a_blue_ghost_that_clear_dots_ignores():
    near_blue = opt(food_steps=2, edible_steps=1)
    far = opt(food_steps=2)
    assert features.score_option("pacifist", near_blue) < features.score_option("pacifist", far)
    assert features.score_option("hunt_ghosts", near_blue) > features.score_option("hunt_ghosts", far)


def test_eat_fruit_prefers_the_fruit_exit_only_for_that_goal():
    fruit, dots = opt(fruit_steps=3), opt(food_steps=1)
    assert features.score_option("eat_fruit", fruit) > features.score_option("eat_fruit", dots)
    assert features.score_option("clear_dots", fruit) < features.score_option("clear_dots", dots)


def test_fruit_tile_decodes_from_the_observed_spawn_position():
    img = bytearray(IMAGE)
    img[0x4DD2 - 0x4000], img[0x4DD3 - 0x4000], img[0x4DD4 - 0x4000] = 0x94, 0x80, 6
    st = decode(bytes(img))
    assert st.fruit_tile == pixel_to_tile((0x94, 0x80)) == (50, 46)
    assert Maze(IMAGE).passable(st.fruit_tile)
    assert decode(IMAGE).fruit_tile is None


def test_survival_overrides_a_deadly_choice_only_when_a_safer_way_exists():
    facts = {"options": {"UP": opt(threat_steps=2), "DOWN": opt(threat_steps=None, room=8)}}
    assert survival.reflex(facts, "UP") == "DOWN"
    assert survival.reflex(facts, "DOWN") is None  # already safe
    far = {"options": {"UP": opt(threat_steps=9), "DOWN": opt(threat_steps=None)}}
    assert survival.reflex(far, "UP") is None  # not close enough to override a goal
    trapped = {"options": {"UP": opt(threat_steps=2), "DOWN": opt(threat_steps=3)}}
    assert survival.reflex(trapped, "UP") is None  # no clearly safer way


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def state_with(**changes):
    return replace(STATE, **changes)


def blue(st, names=("red",)):
    return replace(st, frightened={**st.frightened, **{n: True for n in names}})


def test_pinned_mission_never_changes():
    mgr = goals.GoalManager("pacifist")
    assert mgr.choose(blue(STATE), IMAGE) == "pacifist"


def ghosts_at(st, steps_by_name, frightened=()):
    """Place ghosts at maze tiles the given number of steps from Pac-Man; the rest sit out of reach."""
    here = Maze(IMAGE).bfs(tuple(st.pacman.tile))
    ghosts = {}
    for name, g in st.ghosts.items():
        if name in steps_by_name:
            tile = next(t for t, d in sorted(here.items()) if d == steps_by_name[name])
        else:
            tile = (0, 0)
        ghosts[name] = replace(g, tile=tile, next_tile=tile)
    frightened_flags = {n: n in frightened for n in st.ghosts}
    return replace(st, ghosts=ghosts, frightened=frightened_flags)


def fruit_at(st, steps):
    here = Maze(IMAGE).bfs(tuple(st.pacman.tile))
    return replace(st, fruit_tile=next(t for t, d in sorted(here.items()) if d == steps), fruit_value=6)


def test_feast_takes_over_at_once_when_blue_ghosts_are_reachable_in_time():
    mgr = goals.GoalManager("auto", clock=Clock())
    assert mgr.choose(ghosts_at(STATE, {}), IMAGE, frame=1000) == "clear_dots"
    blue = ghosts_at(STATE, {"red": 6, "pink": 9}, frightened=("red", "pink"))
    assert mgr.choose(blue, IMAGE, frame=1010) == "hunt_ghosts"  # no dwell wait: a better goal preempts
    # the same ghosts 300 frames into a 360-frame window can no longer be caught: back to dots
    assert mgr.choose(blue, IMAGE, frame=1010 + 330) == "clear_dots"


def test_blue_ghosts_that_are_too_far_for_the_window_are_ignored():
    mgr = goals.GoalManager("auto", clock=Clock())
    far = ghosts_at(STATE, {"red": 40}, frightened=("red",))
    assert mgr.choose(far, IMAGE, frame=100) == "clear_dots"


def test_fruit_pulls_the_goal_and_a_feast_outranks_it():
    clock = Clock()
    mgr = goals.GoalManager("auto", clock=clock)
    st = fruit_at(ghosts_at(STATE, {}), 12)
    assert mgr.choose(st, IMAGE, frame=0) == "eat_fruit"
    blue = ghosts_at(st, {"red": 5}, frightened=("red",))
    assert mgr.choose(blue, IMAGE, frame=10) == "hunt_ghosts"
    clock.t = 1.0
    assert mgr.choose(ghosts_at(STATE, {}), IMAGE, frame=20) == "clear_dots"  # nothing left to chase: no dwell


def test_ambush_needs_chasers_and_an_energizer_and_gives_up_after_its_time_box():
    clock = Clock()
    mgr = goals.GoalManager("auto", clock=clock)
    assert Maze(IMAGE).energizers_left() > 0
    quiet = ghosts_at(STATE, {})
    chased = ghosts_at(STATE, {"red": 5, "pink": 8})
    assert mgr.choose(quiet, IMAGE, frame=0) == "clear_dots"
    clock.t = 5.0
    assert mgr.choose(chased, IMAGE, frame=0) == "ambush"
    clock.t = 5.0 + goals.AMBUSH_MAX_SECONDS + 1
    assert mgr.choose(chased, IMAGE, frame=0) == "clear_dots"  # lured long enough: stop for a while
    clock.t += 1
    assert mgr.choose(chased, IMAGE, frame=0) == "clear_dots"  # still cooling down
    clock.t += goals.AMBUSH_COOLDOWN
    assert mgr.choose(chased, IMAGE, frame=0) == "ambush"


def test_ambush_waits_for_the_ghosts_then_goes_for_the_energizer():
    here = {"food_steps": 9, "edible_steps": None, "fruit_steps": None, "room": 10, "reverse": False,
            "threat_steps": None, "energizer_steps": 2}
    waiting = dict(here, ghosts_close=0, pressure=12)
    ready = dict(here, ghosts_close=2, pressure=6)
    far = dict(waiting, energizer_steps=9)
    assert features.score_option("ambush", waiting) < features.score_option("ambush", far)  # hold back, do not eat yet
    assert features.score_option("ambush", ready) > features.score_option("ambush", dict(ready, energizer_steps=6))
    assert features.score_option("ambush", ready) > features.score_option("ambush", waiting)
    panic = dict(waiting, pressure=3)  # one ghost about to catch us: the energizer is the way out
    assert features.score_option("ambush", panic) > features.score_option("ambush", waiting)


def test_events_count_ghosts_fruit_energizers_and_deaths():
    stats = events.GameStats()
    a = blue(STATE, ("red", "pink"))
    stats.update(a, IMAGE, "hunt_ghosts", 0.0)
    b = replace(a, eyes={**a.eyes, "red": True})
    stats.update(b, IMAGE, "hunt_ghosts", 1.0)
    stats.update(b, IMAGE, "hunt_ghosts", 2.0)  # still eyes: not counted again
    near = replace(b, fruit_tile=(STATE.pacman.tile[0], STATE.pacman.tile[1] + 1))
    stats.update(near, IMAGE, "eat_fruit", 3.0)
    stats.update(replace(near, fruit_tile=None), IMAGE, "eat_fruit", 4.0)
    far_fruit = replace(b, fruit_tile=(1, 1))
    stats.update(far_fruit, IMAGE, "clear_dots", 5.0)
    stats.update(replace(far_fruit, fruit_tile=None), IMAGE, "clear_dots", 6.0)
    stats.update(replace(b, lives=b.lives - 1), IMAGE, "clear_dots", 7.0)
    s = stats.summary()
    assert (s["ghosts_eaten"], s["fruit_eaten"], s["fruit_missed"], s["deaths"], s["fruit_shown"]) == (1, 1, 1, 1, 2)
    assert s["feasts"] == []  # no energizer was eaten in this sequence
    assert s["goal_seconds"]["hunt_ghosts"] == 2


def test_unknown_mission_is_rejected():
    with pytest.raises(ValueError):
        goals.GoalManager("conquer")


def test_player_reports_the_game_in_progress_when_stopped():
    from games.arcade.pacman.player import Player
    player = Player(None, None, None, goals.GoalManager("pacifist"), None)
    assert player.partial_result() is None  # nothing playing yet
    player.was_playing, player.last_state, player.game_started = True, STATE, 0.0
    result = player.partial_result()
    assert result["partial"] and result["goal"] == "pacifist" and result["score"] == STATE.score
    assert "ghosts_eaten" in result


def test_feasts_count_ghosts_eaten_per_energizer():
    maze = Maze(IMAGE)
    energizers = [(l, h) for l in range(0x20, 0x40) for h in range(0x1E, 0x3E) if maze.code((l, h)) == 0x14]

    def without(n):
        img = bytearray(IMAGE)
        for tile in energizers[:n]:
            img[maze._addr(*tile) - 0x4000] = 0x40
        return bytes(img)

    stats = events.GameStats()
    st = STATE
    stats.update(st, without(0), "ambush", 0.0)
    st = replace(st, dots_eaten=st.dots_eaten + 1)
    stats.update(st, without(1), "ambush", 1.0)  # first energizer eaten
    for k, name in enumerate(("red", "pink", "blue"), start=1):  # three ghosts eaten during it
        st = replace(st, eyes={**st.eyes, name: True})
        stats.update(st, without(1), "hunt_ghosts", 1.0 + k)
    st = replace(st, dots_eaten=st.dots_eaten + 1, eyes={n: False for n in st.eyes})
    stats.update(st, without(2), "ambush", 9.0)  # second energizer: closes the first feast of 3
    assert stats.summary()["feasts"] == [3, 0]
    assert stats.summary()["energizers"] == 2


def test_ambush_does_not_flap_when_the_chasers_hover_at_the_threshold():
    clock = Clock()
    mgr = goals.GoalManager("auto", clock=clock)
    clock.t = 5.0
    assert mgr.choose(ghosts_at(STATE, {"red": 12, "pink": 13}), IMAGE, frame=0) == "ambush"
    clock.t = 5.6
    # one ghost now beyond the 14-step entry line (and only one left): the active goal holds
    assert mgr.choose(ghosts_at(STATE, {"red": 12, "pink": 16}), IMAGE, frame=0) == "ambush"
    clock.t = 6.2
    assert mgr.choose(ghosts_at(STATE, {"red": 17}), IMAGE, frame=0) == "ambush"
    clock.t = 6.8
    assert mgr.choose(ghosts_at(STATE, {"red": 30}), IMAGE, frame=0) == "clear_dots"  # truly gone


def test_a_hunt_finishes_a_ghost_two_steps_away_even_as_the_window_closes():
    mgr = goals.GoalManager("auto", clock=Clock())
    close = ghosts_at(STATE, {"red": 2}, frightened=("red",))
    assert mgr.choose(close, IMAGE, frame=1000) == "hunt_ghosts"
    assert mgr.choose(close, IMAGE, frame=1000 + 330) == "hunt_ghosts"  # 30 frames left, ghost 2 steps away


def test_a_turn_back_is_logged_with_its_reason_and_what_was_around():
    import io
    import json

    class Broker:
        held = "LEFT"
        steered = None

        def steer(self, direction):
            self.steered = direction

    from games.arcade.pacman.player import Player
    log, broker = io.StringIO(), Broker()
    player = Player(None, broker, None, goals.GoalManager("hunt_ghosts"), log)
    player.goal = "hunt_ghosts"
    heading = STATE.pacman.direction.upper()
    opposite = {"LEFT": "RIGHT", "RIGHT": "LEFT", "UP": "DOWN", "DOWN": "UP"}[heading]
    st = ghosts_at(STATE, {"red": 3}, frightened=("red",))
    player._go(st, IMAGE, st.pacman.tile, heading, opposite, "junction", "late-rule")
    record = json.loads(log.getvalue())
    assert record["event"] == "reverse" and record["why"] == "late-rule" and record["goal"] == "hunt_ghosts"
    assert record["blue_steps"] == [3] and broker.steered == opposite
    broker.held = opposite
    log.truncate(0), log.seek(0)
    player._go(st, IMAGE, st.pacman.tile, heading, opposite, "junction", "late-rule")
    assert log.getvalue() == ""  # already going that way: not a reversal
