from dataclasses import replace
from pathlib import Path
import sys

from games.arcade.pacman import ghosts as pg
from games.arcade.pacman.maze import Maze
from games.arcade.pacman.state import decode

IMAGE = (Path(__file__).parent / 'fixtures' / 'pacman_play_ram.bin').read_bytes()


def state(**changes):
    return replace(decode(IMAGE), **changes)


def with_pacman(st, tile, direction):
    return replace(st, pacman=replace(st.pacman, tile=tile, direction=direction))


def test_blinky_targets_pacmans_tile_in_chase():
    st = with_pacman(state(phase=1), (50, 40), "left")
    assert pg.targets(st)["red"] == (50, 40)


def test_scatter_targets_are_the_corners():
    st = state(phase=0)
    assert pg.targets(st) == pg.SCATTER_TARGETS


def test_elroy_blinky_chases_during_scatter():
    st = with_pacman(state(phase=0, elroy=True), (50, 40), "left")
    assert pg.targets(st)["red"] == (50, 40)


def test_pinky_aims_four_tiles_ahead():
    # left is h+1, so four ahead of (50, 40) heading left is (50, 44)
    st = with_pacman(state(phase=1), (50, 40), "left")
    assert pg.targets(st)["pink"] == (50, 44)


def test_pinky_overflow_when_pacman_faces_up():
    # the ROM adds the vector as one 16-bit word: facing up is also four to the left (h + 4)
    st = with_pacman(state(phase=1), (50, 40), "up")
    assert pg.targets(st)["pink"] == (46, 44)


def test_clyde_flees_to_his_corner_when_within_eight_tiles():
    near = with_pacman(state(phase=1), (47, 46), "left")  # orange next tile is about (47, 44)
    assert pg.targets(near)["orange"] == pg.SCATTER_TARGETS["orange"]
    far = with_pacman(state(phase=1), (34, 36), "left")
    assert pg.targets(far)["orange"] == (34, 36)


def test_choose_exit_never_reverses_and_prefers_nearest_target():
    maze = Maze(IMAGE)
    tile = (56, 53)  # an open junction: RIGHT, DOWN and UP are open, LEFT is not
    assert pg.choose_exit(maze, tile, "LEFT", target=(30, 53)) == "UP"
    # arriving heading LEFT excludes RIGHT (reverse) even if it is nearest
    assert pg.choose_exit(maze, tile, "LEFT", target=(56, 30)) != "RIGHT"


def test_ties_go_to_the_later_of_right_down_left_up():
    maze = Maze(IMAGE)
    tile = (56, 53)
    # DOWN and UP are equally near a target on the same row, UP comes later so it wins
    assert pg.choose_exit(maze, tile, "LEFT", target=(56, 53)) == "UP"


def test_forecast_skips_frightened_ghosts_and_returns_paths_for_others():
    maze = Maze(IMAGE)
    st = state(phase=1)
    st = replace(st, frightened={**st.frightened, "pink": True})
    paths = pg.forecast(st, maze, steps=6)
    assert paths["pink"] is None
    assert len(paths["red"]) == 6
    assert all(maze.passable(t) for t in paths["red"])


def test_collision_step_finds_a_shared_tile_within_tolerance():
    own = [(1, 1), (1, 2), (1, 3)]
    ghosts = {"red": [(9, 9), (1, 2)], "pink": None}
    assert pg.collision_step(own, ghosts) == 2
    assert pg.collision_step([(5, 5)], {"red": [(1, 1)]}) is None


def test_ghosts_cannot_turn_up_on_the_four_restricted_tiles():
    maze = Maze(IMAGE)
    for tile in pg.NO_UP_TILES:
        # target far above so UP would normally win; the rule forbids it
        assert pg.choose_exit(maze, tile, "LEFT", target=(0x1D, tile[1])) != "UP"


def test_ghosts_go_straight_in_the_tunnel():
    maze = Maze(IMAGE)
    tile = (47, 60)
    assert pg.in_tunnel(tile)
    assert pg.choose_exit(maze, tile, "LEFT", target=(0x1D, 60)) == "LEFT"
