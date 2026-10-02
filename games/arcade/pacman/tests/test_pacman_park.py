"""Waiting without a wait button: parking near an energizer (--park) and the refuge at the safe spot (--refuge)."""
import io
import json
import time
from dataclasses import replace
from pathlib import Path

from games.arcade.pacman.spec import SPEC
from games.arcade.pacman import features, goals, park, player
from games.arcade.pacman.maze import MOVES, Maze, step
from games.arcade.pacman.state import decode
from games.arcade.pacman.tests.test_pacman_chain import FakeWorker, Steer, Stream

IMAGE = (Path(__file__).parent / "fixtures" / "pacman_play_ram.bin").read_bytes()
STATE = decode(IMAGE)
MAZE = Maze(IMAGE)
PELLETS = [(36, 33), (36, 58), (56, 33), (56, 58)]
NAMES = list(STATE.ghosts)


def at_distance(ref, steps, k=0):
    """A tile `steps` steps (by the maze) from `ref`; k picks among several."""
    return [t for t, d in MAZE.bfs(ref).items() if d == steps][k]


def snapshot(me, heading, ghost_steps, ref=None):
    """Pac-Man at `me` facing `heading`; one ghost per entry of ghost_steps (steps from `ref`, default `me`),
    None = still in the ghost house."""
    ref = ref or me
    ghosts = {}
    for i, (name, steps) in enumerate(zip(NAMES, ghost_steps)):
        tile = (0, 0) if steps is None else at_distance(ref, steps, i)
        ghosts[name] = replace(STATE.ghosts[name], tile=tile, next_tile=tile)
    return replace(STATE, mode="playing", ghosts=ghosts,
                   pacman=replace(STATE.pacman, tile=me, direction=heading.lower()),
                   frightened={n: False for n in NAMES}, eyes={n: False for n in NAMES})


def make(snaps, goal="ambush", **kw):
    steer, log = Steer(), io.StringIO()
    p = player.Player(Stream([(i, s, IMAGE) for i, s in enumerate(snaps, start=1)]), steer, FakeWorker(),
                      goals.GoalManager(goal), log, **kw)
    return p, steer, log


def events(log, kind):
    return [e for e in (json.loads(line) for line in log.getvalue().splitlines()) if e["event"] == kind]


# ---------------------------------------------------------------- parking near an energizer

STOP, PUSH = park.hover_stop(MAZE, (56, 33))
FAR = (20, 21, 22, 23)


def test_every_energizer_has_a_wall_stop_tile_in_range():
    for pellet in PELLETS:
        found = park.hover_stop(MAZE, pellet)
        assert found, pellet
        tile, heading = found
        assert park.is_stop(MAZE, tile, heading) and not MAZE.passable(step(tile, heading))
        assert park.HOVER_MIN <= MAZE.bfs(pellet)[tile] <= park.HOVER_MAX


def test_a_stop_tile_needs_a_wall_ahead_a_way_in_and_a_way_out():
    for heading in MOVES:
        if MAZE.passable(step(STOP, heading)):
            assert not park.is_stop(MAZE, STOP, heading)
    dead_end = next(t for t in MAZE.bfs(STOP) if len(MAZE.exits(t)) == 1)
    assert not any(park.is_stop(MAZE, dead_end, h) for h in MOVES)  # waiting in a dead end is a trap


def opt(**kw):
    base = {"food_steps": None, "threat_steps": None, "edible_steps": None, "fruit_steps": None, "energizer_steps": 14,
            "room": 10, "reverse": False, "pressure": 12, "ghosts_close": 0, "stop_steps": 6}
    base.update(kw)
    return base


def test_ambush_pulls_toward_the_wall_stop_instead_of_hovering_by_the_energizer():
    assert features.score_option("ambush", opt(stop_steps=4)) > features.score_option("ambush", opt(stop_steps=9))
    no_stop = opt(stop_steps=None, energizer_steps=2)  # old behaviour: too close to eat it yet, hold back
    assert features.score_option("ambush", no_stop) < 0 < features.score_option("ambush", opt(stop_steps=4))


def test_once_the_ghosts_have_gathered_the_energizer_decides_not_the_stop():
    ready = dict(ghosts_close=2)
    assert features.lure_score(opt(energizer_steps=2, stop_steps=30, **ready)) > features.lure_score(
        opt(energizer_steps=9, stop_steps=1, **ready))


def test_the_stop_is_only_in_the_facts_when_parking_is_switched_on():
    me = at_distance(STOP, 2)  # two steps short of the stop tile, so it is ahead of him on some exit
    st = snapshot(me, "up", FAR)
    on = features.junction_facts(st, IMAGE, tile=me, arriving="UP", park=True)
    off = features.junction_facts(st, IMAGE, tile=me, arriving="UP")
    assert any(o["stop_steps"] is not None for o in on["options"].values())
    assert all(o["stop_steps"] is None for o in off["options"].values())


def test_in_ambush_against_a_wall_near_the_energizer_with_no_one_close_he_waits_pushing_into_it():
    p, steer, log = make([snapshot(STOP, PUSH, FAR)], park=True)
    p.tick()
    assert steer.sent == [PUSH] and p.game.parks == 1 and p.hold["kind"] == "park"
    assert events(log, "park")[0]["phase"] == "start"


def test_he_does_not_wait_when_not_asked_to_nor_outside_ambush_nor_with_ghosts_already_close():
    cases = [(dict(park=False), "ambush", FAR), (dict(park=True), "clear_dots", FAR),
             (dict(park=True), "ambush", (3, 4, 20, 21))]
    for kw, goal, ghosts in cases:
        p, steer, _ = make([snapshot(STOP, PUSH, ghosts)], goal=goal, **kw)
        p.tick()
        assert p.hold is None and p.game.parks == 0, (kw, goal, ghosts)


def test_he_leaves_for_the_energizer_once_ghosts_have_gathered_and_is_not_turned_back_on_the_tile():
    p, steer, log = make([snapshot(STOP, PUSH, FAR), snapshot(STOP, PUSH, (3, 4, 20, 21)),
                          snapshot(STOP, PUSH, (3, 4, 20, 21))], park=True)
    for _ in range(3):
        p.tick()
    left = events(log, "park")[1]
    assert left["phase"] == "leave" and left["why"] == "gathered"
    assert steer.sent[1] == steer.sent[2] in MAZE.exits(STOP)  # one exit, kept while he is on the tile


def test_he_gives_up_waiting_after_the_time_limit_and_the_time_is_booked():
    p, steer, log = make([snapshot(STOP, PUSH, FAR), snapshot(STOP, PUSH, FAR)], park=True)
    p.tick()
    p.hold["since"] = time.time() - park.HOVER_SECONDS - 1
    p.tick()
    assert events(log, "park")[1]["why"] == "timeout" and p.game.parked_seconds >= park.HOVER_SECONDS


def test_a_life_lost_while_parked_is_counted():
    p, steer, log = make([snapshot(STOP, PUSH, FAR), snapshot(STOP, PUSH, FAR)], park=True)
    p.tick()
    dead = bytearray(IMAGE)
    dead[0x4E04 - 0x4000] = 0  # death animation / READY screen
    p.stream.states[0] = (2, snapshot(STOP, PUSH, FAR), bytes(dead))
    p.tick()
    assert p.game.park_deaths == 1 and p.hold is None


# ---------------------------------------------------------------- the refuge

SPOT = SPEC.safe_spot
START = (56, 44)  # three steps from the spot, in the corridor under the block above his start


def test_the_refuge_is_a_corner_with_a_wall_above():
    assert MAZE.passable(SPOT) and not MAZE.passable((SPOT[0] - 1, SPOT[1]))
    assert sorted(MAZE.exits(SPOT)) == ["DOWN", "RIGHT"] and MAZE.bfs(SPOT)[START] == 3


def test_a_close_ghost_with_every_ghost_out_sends_him_to_the_refuge_when_he_gets_there_first():
    others = [at_distance(START, 30 + i) for i in range(3)]  # the other three: out of the house, far away
    results = {}
    for tile in (t for t, d in MAZE.bfs(START).items() if 5 <= d <= 8):  # every place the close ghost could be
        ghosts = {n: replace(STATE.ghosts[n], tile=t, next_tile=t) for n, t in zip(NAMES, [tile] + others)}
        st = replace(snapshot(START, "right", (30, 31, 32, 33)), ghosts=ghosts)
        results[tile] = park.refuge_move(st, MAZE, START, SPOT)
    assert "UP" in results.values()  # some positions leave the way up the stub clear
    assert None in results.values()  # and some do not (the ghost would be there first)


def test_a_ghost_on_the_way_or_not_yet_out_or_not_close_keeps_him_from_running():
    far = (30, 31, 32)
    on_route = replace(snapshot(START, "right", (30,) + far), ghosts={
        **snapshot(START, "right", (30,) + far).ghosts,
        "red": replace(STATE.ghosts["red"], tile=(54, 44), next_tile=(54, 44))})
    assert park.refuge_move(on_route, MAZE, START, SPOT) is None  # it is already up the stub
    house = snapshot(START, "right", (6, 30, 31, None))
    assert park.refuge_move(house, MAZE, START, SPOT) is None  # a ghost is still in the house
    assert park.refuge_move(snapshot(START, "right", (20, 30, 31, 32)), MAZE, START, SPOT) is None  # nobody close
    assert park.refuge_move(snapshot(SPOT, "up", (6, 30, 31, 32)), MAZE, SPOT, SPOT) is None  # already there


def test_he_holds_at_the_refuge_while_ghosts_are_near_and_counts_it():
    p, steer, log = make([snapshot(SPOT, "up", (6, 7, 30, 31))], refuge=True, goal="clear_dots")
    p.tick()
    assert steer.sent == ["UP"] and p.game.refuges == 1 and p.hold["kind"] == "refuge"


def test_he_leaves_the_refuge_when_the_ghosts_have_gone_or_after_the_time_limit():
    p, steer, log = make([snapshot(SPOT, "up", (6, 7, 30, 31)), snapshot(SPOT, "up", (20, 21, 30, 31))],
                          refuge=True, goal="clear_dots")
    p.tick()
    p.tick()
    assert events(log, "refuge")[1]["why"] == "clear" and p.refuge_cooldown > time.time()
    p, steer, log = make([snapshot(SPOT, "up", (6, 7, 30, 31)), snapshot(SPOT, "up", (6, 7, 30, 31))],
                         refuge=True, goal="clear_dots")
    p.tick()
    p.hold["since"] = time.time() - park.REFUGE_SECONDS - 1
    p.tick()
    assert events(log, "refuge")[1]["why"] == "timeout" and p.game.refuge_seconds >= park.REFUGE_SECONDS


def test_the_refuge_is_not_used_unless_switched_on_nor_while_hunting_blue_ghosts():
    p, steer, _ = make([snapshot(SPOT, "up", (6, 7, 30, 31))], refuge=False, goal="clear_dots")
    p.tick()
    assert p.hold is None
    p, steer, _ = make([snapshot(SPOT, "up", (6, 7, 30, 31))], refuge=True, goal="hunt_ghosts")
    p.tick()
    assert p.hold is None


def test_a_life_lost_at_the_refuge_is_counted():
    p, steer, log = make([snapshot(SPOT, "up", (6, 7, 30, 31)), snapshot(SPOT, "up", (6, 7, 30, 31))],
                         refuge=True, goal="clear_dots")
    p.tick()
    dead = bytearray(IMAGE)
    dead[0x4E04 - 0x4000] = 0
    p.stream.states[0] = (2, snapshot(SPOT, "up", (6, 7, 30, 31)), bytes(dead))
    p.tick()
    assert p.game.refuge_deaths == 1 and p.hold is None
