"""Pac-Man and Ms. Pac-Man share one player (arcadekit.kits.pacman_board) and differ only in their spec."""
import io
from pathlib import Path

import pytest

from arcadekit.kits.pacman_board import player as shared_player
from games.arcade import mspacman, pacman

IMAGE = (Path(__file__).resolve().parents[1] / "games" / "arcade" / "pacman" / "tests" / "fixtures"
         / "pacman_play_ram.bin").read_bytes()


def test_both_games_play_with_the_same_shared_player_bound_to_their_own_spec():
    for game in (pacman, mspacman):
        assert issubclass(game.player.Player, shared_player.Player)
        p = game.player.Player(None, None, None, game.goals.GoalManager("clear_dots"), io.StringIO())
        assert p.spec is game.SPEC


def test_each_game_tells_the_model_its_own_name_and_ghosts():
    pac = pacman.knowledge.show(IMAGE, "L3a")
    ms = mspacman.knowledge.show(IMAGE, "L3a")
    assert "PAC-MAN RULES" in pac and "Clyde" in pac and "Ms. Pac-Man" not in pac
    assert "MS. PAC-MAN RULES" in ms and "Sue" in ms and "Clyde" not in ms
    assert "Ms. Pac-Man is at a junction" in ms
    assert "You advise the strategy of a Ms. Pac-Man player" in mspacman.strategy.SCHEMA["instructions"]


def test_the_refuge_is_offered_only_where_the_game_has_a_safe_spot():
    assert "refuge" in {o.name for o in pacman.experiment.OPTIONS}
    assert "refuge" not in {o.name for o in mspacman.experiment.OPTIONS}
    with pytest.raises(ValueError):
        mspacman.player.Player(None, None, None, mspacman.goals.GoalManager("clear_dots"), io.StringIO(), refuge=True)


def test_the_question_names_the_player_and_uses_the_right_pronoun():
    facts = {"options": {"UP": {"food_steps": 3, "threat_steps": 4, "room": 9, "edible_steps": None, "reverse": False},
                         "DOWN": {"food_steps": 9, "threat_steps": None, "room": 20, "edible_steps": None,
                                  "reverse": True}},
             "danger": True, "state_text": "x"}
    _, instructions, _ = mspacman.deciders.question(facts, "clear_dots")
    assert instructions.startswith("Ms. Pac-Man is in a corridor and a ghost is close: she can carry on")
    _, instructions, _ = pacman.deciders.question(facts, "clear_dots")
    assert instructions.startswith("Pac-Man is in a corridor and a ghost is close: he can carry on")
