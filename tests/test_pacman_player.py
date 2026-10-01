from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import deciders
import pacman_features as pf
import systemone
from pacman_maze import Maze
from pacman_state import decode

IMAGE = (Path(__file__).parent / 'fixtures' / 'pacman_play_ram.bin').read_bytes()
STATE = decode(IMAGE)


def facts():
    return pf.junction_facts(STATE, IMAGE)


def test_food_count_matches_dots_eaten():
    assert Maze(IMAGE).food_left() == 244 - STATE.dots_eaten


def test_walk_to_decision_at_a_junction_is_zero_steps():
    tile, steps, path = Maze(IMAGE).walk_to_decision(STATE.pacman.tile, "LEFT")
    assert tile == STATE.pacman.tile and steps == 0 and path == []


def test_facts_cover_every_open_exit_and_flag_the_reverse():
    f = facts()
    assert set(f["options"]) == {"RIGHT", "DOWN", "UP"}
    assert f["options"]["RIGHT"]["reverse"] and not f["options"]["UP"]["reverse"]


def test_ghosts_in_the_house_have_no_path_distance():
    in_house = [g for g in facts()["ghosts"] if g["steps"] is None]
    assert {g["name"] for g in in_house} == {"blue", "orange"}


def test_rule_decider_picks_an_available_option():
    assert deciders.RuleDecider().decide(facts(), "clear_dots").direction in facts()["options"]


def test_mock_model_returns_normalised_probabilities_and_respects_latency():
    client = systemone.MockSystemOne(latency_ms=(1, 2), seed=1)
    d = deciders.SystemOneDecider(client)
    decision = d.decide(facts(), "clear_dots")
    assert decision.source == "model"
    assert abs(sum(decision.probabilities.values()) - 1) < 1e-9
    assert decision.direction in facts()["options"]


class Broken:
    def ask(self, *args, **kwargs):
        raise systemone.SystemOneError("model down")


def test_decider_falls_back_to_the_rule_when_the_model_fails():
    decision = deciders.SystemOneDecider(Broken()).decide(facts(), "clear_dots")
    assert decision.source == "fallback" and "model down" in decision.note


def test_low_confidence_triggers_the_fallback():
    client = systemone.MockSystemOne(latency_ms=(0, 0), seed=1)
    decision = deciders.SystemOneDecider(client, min_confidence=0.999).decide(facts(), "clear_dots")
    assert decision.source == "fallback" and "low confidence" in decision.note
