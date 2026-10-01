from dataclasses import replace
from pathlib import Path
import sys

import pytest

from games.arcade.pacman import knowledge as pk
from games.arcade.pacman.features import junction_facts
from games.arcade.pacman.state import decode

IMAGE = (Path(__file__).parent / 'fixtures' / 'pacman_play_ram.bin').read_bytes()


def build(level, **changes):
    st = replace(decode(IMAGE), **changes)
    facts = junction_facts(st, IMAGE)
    return pk.build_state_text(level, st, IMAGE, facts, st.pacman.tile, st.pacman.direction.upper())


def test_rungs_add_exactly_their_own_help():
    l0, l1, l2, l3a, l3b = (build(l, phase=1) for l in pk.LEVELS)
    assert "PAC-MAN RULES" not in l0 and "SITUATION" not in l0
    assert "PAC-MAN RULES" in l1 and "SITUATION" not in l1
    assert "SITUATION" in l2 and "HOW THE GHOSTS CHOOSE" not in l2
    assert "HOW THE GHOSTS CHOOSE" in l3a and "GHOST AIMS AND ROUTES" not in l3a
    assert "GHOST AIMS AND ROUTES" in l3b
    assert len(l0) < len(l1) < len(l2) < len(l3a) < len(l3b)


def test_l0_has_no_derived_facts():
    text = build("L0", phase=1)
    assert "steps" not in text and "DANGER" not in text


def test_chase_phase_aim_is_described_relative_to_pacman():
    text = build("L3b", phase=1)
    assert "its own corner" not in text.split("GHOST AIMS AND ROUTES")[1].split("Red")[1].split("\n")[0]
    assert "the tile on you" in text  # Red chases Pac-Man's own tile


def test_scatter_phase_names_the_corner():
    assert "its own corner (scatter)" in build("L3b", phase=0)


def test_frightened_ghost_is_edible_and_has_no_route():
    st = decode(IMAGE)
    text = build("L3b", phase=1, frightened={**st.frightened, "red": True})
    assert "BLUE, edible" in text
    assert "blue, moves at random; no route" in text


def test_ghost_facts_flag_close_ghosts_as_danger():
    st = decode(IMAGE)
    from games.arcade.pacman.maze import Maze, step
    maze = Maze(IMAGE)
    nxt = next(step(st.pacman.tile, d) for d in ("UP", "DOWN", "LEFT", "RIGHT") if maze.passable(step(st.pacman.tile, d)))
    near = replace(st, ghosts={**st.ghosts, "red": replace(st.ghosts["red"], tile=nxt, next_tile=nxt)})
    red = next(g for g in pk.ghost_facts(near, IMAGE, st.pacman.tile) if g["name"] == "red")
    assert red["steps"] == 1 and pk._band(red["steps"]) == "DANGER"


def test_unknown_level_is_rejected():
    st = decode(IMAGE)
    with pytest.raises(ValueError):
        pk.build_state_text("L9", st, IMAGE, junction_facts(st, IMAGE), st.pacman.tile, "LEFT")
