"""With few dots left and no ghost anywhere, the decider must walk to the dots, not bounce between open areas."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import endgame_sim as sim  # noqa: E402

from games.arcade.pacman import features  # noqa: E402


def test_clears_the_last_dots_without_oscillating():
    for dots in (1, 3, 8):
        for image, start, heading in sim.random_scenarios(25, dots=dots, seed=dots):
            taken, left, trail = sim.simulate(image, start, heading, max_steps=500)
            assert left == 0, f"{dots} dots left, stuck after {taken} steps over {len(set(trail))} tiles"


def test_open_room_only_counts_when_a_ghost_is_near():
    roomy = {"food_steps": 20, "threat_steps": None, "edible_steps": None, "room": 30, "reverse": False}
    cramped = dict(roomy, room=5)
    assert features.score_option("clear_dots", dict(roomy, pressure=None)) == \
        features.score_option("clear_dots", dict(cramped, pressure=None))
    assert features.score_option("clear_dots", dict(roomy, pressure=8)) > \
        features.score_option("clear_dots", dict(cramped, pressure=8))


def test_nearer_food_always_scores_higher():
    scores = [features.score_option("clear_dots", {"food_steps": d, "threat_steps": None, "edible_steps": None,
                                                   "room": 10, "reverse": False, "pressure": None})
              for d in range(1, 60)]
    assert all(a > b for a, b in zip(scores, scores[1:]) if a != b) and scores[0] > scores[30]
