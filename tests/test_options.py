import argparse
import sys

import pytest

from arcadekit.options import Option, add_arguments, describe, label_parts, values
from arcadekit.outcome import OutcomeStats
from games.arcade.pacman import experiment


def parse(*argv):
    parser = argparse.ArgumentParser()
    add_arguments(parser, experiment.OPTIONS, "pacman")
    return values(parser.parse_args(list(argv)), experiment.OPTIONS)


def test_every_switch_has_a_kind_and_override_and_skill_switches_can_be_turned_off():
    with pytest.raises(ValueError):
        Option("x", "magic", "?")
    with pytest.raises(ValueError):
        Option("x", "override", "an override with no off position", default=None, parse=int)
    for o in experiment.OPTIONS:
        assert o.kind in ("facts", "timing", "override", "skill")


def test_the_pacman_flags_and_run_labels_are_the_ones_used_before_phase_2():
    vals = parse()
    assert vals["reflex"] is True and vals["late"] == "rule" and vals["park"] is False and vals["chain_depth"] is None
    assert label_parts(vals, experiment.OPTIONS) == []
    vals = parse("--park", "--refuge", "--danger-query", "--revise", "--no-reflex", "--late", "keep", "--chain", "0")
    assert label_parts(vals, experiment.OPTIONS) == ["park", "refuge", "danger", "revise", "noreflex", "late-keep", "chain0"]
    assert describe(vals, experiment.OPTIONS)["reflex"] == {"value": False, "kind": "override"}


def test_option_values_become_player_keywords_and_a_named_model_becomes_a_worker():
    kwargs = experiment.player_kwargs(parse("--danger-query", "--danger-model", "tev1:0.8b", "--lookahead", "10"),
                                      lambda model: f"worker for {model}")
    assert kwargs["danger_worker"] == "worker for tev1:0.8b" and kwargs["lookahead"] == 10
    assert "danger_model" not in kwargs and "chain_depth" not in kwargs  # unset: the player's own default
    assert "danger_worker" not in experiment.player_kwargs(parse("--danger-model", "x"), lambda m: m)


def test_play_offers_the_games_switches_and_names_no_game_of_its_own():
    sys.path.insert(0, "tools")
    import play
    source = open(play.__file__).read().lower()
    for word in ("park", "refuge", "danger", "ghost", "feast", "reflex", "energizer"):
        assert word not in source, word


def test_outcome_records_each_life_with_the_games_own_progress_counts():
    o = OutcomeStats()
    o.update(0, 3, 1, 10.0, {"dots": 0})
    o.update(500, 3, 1, 40.0, {"dots": 50})
    o.update(520, 2, 1, 41.0, {"dots": 52})  # a life lost
    o.update(900, 2, 2, 70.0, {"dots": 80})  # next board
    o.update(950, 1, 2, 80.0, {"dots": 90})
    assert o.summary() == {"deaths": 2, "boards_cleared": 1, "lives": [
        {"life": 1, "seconds": 31, "score": 520, "dots": 52, "score_at_end": 520},
        {"life": 2, "seconds": 39, "score": 430, "dots": 38, "score_at_end": 950}]}
