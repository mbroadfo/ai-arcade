"""Ambush with the safe spot: go there, hold UP into the wall, leave when the ghosts have gathered or time is up."""
import io
import json
import time
from dataclasses import replace
from pathlib import Path

from games.arcade.pacman import features, goals, park, player
from games.arcade.pacman.maze import Maze
from games.arcade.pacman.state import decode
from games.arcade.pacman.tests.test_pacman_chain import FakeWorker, Steer, Stream

IMAGE = (Path(__file__).parent / "fixtures" / "pacman_play_ram.bin").read_bytes()
STATE = decode(IMAGE)
SPOT = park.SAFE_SPOT
HERE = Maze(IMAGE).bfs(SPOT)


def tiles_at(distance, count):
    found = [t for t, d in HERE.items() if d == distance]
    return found[:count]


def snapshot(ghost_steps, direction="up", spot=SPOT):
    """Pac-Man at the spot; one ghost per entry of ghost_steps (steps from the spot), None = still in the house."""
    names = list(STATE.ghosts)
    ghosts = {}
    for name, steps in zip(names, ghost_steps):
        tile = (0, 0) if steps is None else tiles_at(steps, 4)[names.index(name)]
        ghosts[name] = replace(STATE.ghosts[name], tile=tile, next_tile=tile)
    return replace(STATE, mode="playing", ghosts=ghosts, pacman=replace(STATE.pacman, tile=spot, direction=direction),
                   frightened={n: False for n in names}, eyes={n: False for n in names})


def make(snaps, goal="ambush", **kw):
    steer, log = Steer(), io.StringIO()
    p = player.Player(Stream([(i, s, IMAGE) for i, s in enumerate(snaps, start=1)]), steer, FakeWorker(),
                      goals.GoalManager(goal), log, park=kw.pop("park", True), **kw)
    return p, steer, log


def events(log):
    return [json.loads(line) for line in log.getvalue().splitlines() if '"park"' in line]


FAR = (20, 21, 22, 23)


def test_the_spot_is_a_corner_with_a_wall_above():
    maze = Maze(IMAGE)
    assert maze.passable(SPOT) and not maze.passable((SPOT[0] - 1, SPOT[1]))
    assert sorted(maze.exits(SPOT)) == ["DOWN", "RIGHT"]


def test_with_every_ghost_out_and_none_near_he_waits_pushing_up():
    p, steer, log = make([snapshot(FAR)])
    p.tick()
    assert steer.sent == ["UP"] and p.game.parks == 1 and p.parked_since is not None
    assert events(log)[0]["phase"] == "start"


def test_he_does_not_wait_unless_asked_to_nor_outside_ambush_nor_with_a_ghost_still_in_the_house():
    for kw, snap in ((dict(park=False), snapshot(FAR)), (dict(goal="clear_dots"), snapshot(FAR)),
                     (dict(), snapshot((20, 21, 22, None)))):
        p, steer, _ = make([snap], **kw)
        p.tick()
        assert p.parked_since is None and p.game.parks == 0


def test_he_leaves_for_the_energizer_side_once_three_ghosts_are_within_reach():
    p, steer, log = make([snapshot(FAR), snapshot((6, 7, 8, 20))])
    p.tick()
    p.tick()
    left = [e for e in events(log) if e["phase"] == "leave"][0]
    assert left["why"] == "gathered" and left["crowd"] == 3
    assert p.parked_since is None and steer.sent[-1] in ("RIGHT", "DOWN") and p.park_exit == steer.sent[-1]


def test_he_gives_up_waiting_after_the_time_limit():
    p, steer, log = make([snapshot(FAR), snapshot(FAR)])
    p.tick()
    p.parked_since = time.time() - park.MAX_SECONDS - 1
    p.tick()
    assert [e for e in events(log) if e["phase"] == "leave"][0]["why"] == "timeout"
    assert p.game.parked_seconds >= park.MAX_SECONDS


def test_a_life_lost_while_parked_is_counted():
    p, steer, log = make([snapshot(FAR), snapshot(FAR)])
    p.tick()
    dead = bytearray(IMAGE)
    dead[0x4E04 - 0x4000] = 0  # not in normal play: the death animation / READY screen
    p.stream.states[0] = (2, snapshot(FAR), bytes(dead))
    p.tick()
    assert p.game.park_deaths == 1 and p.parked_since is None


def test_the_leaving_choice_is_kept_until_he_has_left_the_tile():
    p, steer, log = make([snapshot(FAR), snapshot((6, 7, 8, 20)), snapshot((6, 7, 8, 20))])
    for _ in range(3):
        p.tick()
    assert len(set(steer.sent[1:])) == 1  # not turned back into the corridor logic's forced RIGHT or flipped


def opt(**kw):
    base = {"food_steps": None, "threat_steps": None, "edible_steps": None, "fruit_steps": None, "energizer_steps": 14,
            "room": 10, "reverse": False, "pressure": 12, "ghosts_close": 0, "park_ok": True, "park_steps": 6}
    base.update(kw)
    return base


def test_ambush_pulls_toward_the_spot_instead_of_hovering_by_the_energizer():
    nearer, farther = opt(park_steps=4), opt(park_steps=9)
    assert features.score_option("ambush", nearer) > features.score_option("ambush", farther)
    without = dict(park_ok=False)  # spot not usable (a ghost still in the house): the old hover rule applies
    assert features.score_option("ambush", opt(energizer_steps=2, **without)) < 0 < features.score_option("ambush", nearer)


def test_the_spot_is_not_in_play_unless_switched_on():
    maze_image, st = IMAGE, snapshot(FAR)
    on = features.junction_facts(st, maze_image, tile=SPOT, arriving="UP", park=True)
    off = features.junction_facts(st, maze_image, tile=SPOT, arriving="UP")
    assert all(o["park_ok"] for o in on["options"].values()) and not any(o["park_ok"] for o in off["options"].values())


def test_enough_ghosts_gathered_sends_him_for_the_energizer_not_the_spot():
    ready = dict(ghosts_close=park.GATHER)
    near_pellet_far_spot = opt(energizer_steps=2, park_steps=30, **ready)
    far_pellet_near_spot = opt(energizer_steps=9, park_steps=1, **ready)
    assert features.lure_score(near_pellet_far_spot) > features.lure_score(far_pellet_near_spot)  # the pellet decides
    waiting = dict(ghosts_close=park.GATHER - 1)
    assert features.lure_score(opt(energizer_steps=9, park_steps=1, **waiting)) > features.lure_score(
        opt(energizer_steps=2, park_steps=30, **waiting))  # still gathering: the spot decides
