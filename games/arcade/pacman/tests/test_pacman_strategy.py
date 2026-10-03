"""The slow layer for Pac-Man: stance scales weights, a model picks goal and stance, code keeps the veto."""
from dataclasses import replace
from pathlib import Path

from games.arcade.pacman import features, goals, strategy
from games.arcade.pacman.state import decode

IMAGE = (Path(__file__).parent / "fixtures" / "pacman_play_ram.bin").read_bytes()
STATE = decode(IMAGE)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeStrategist:
    def __init__(self):
        self.asked, self.advice, self.stats = [], None, {}

    def request(self, text, hint=None, only=None, goals=None):
        self.asked.append((text, hint))
        self.goals = goals
        self.only = getattr(self, "only_log", [])
        self.only.append(only)
        self.only_log = self.only
        return True

    def take(self):
        out, self.advice = self.advice, None
        return out


def advice(goal, **mods):
    from arcadekit.strategist import Advice
    return Advice(goal, mods, 0.9, 20.0, 0.0)


def manager(**kw):
    clock = Clock()
    m = strategy.ModelGoalManager(FakeStrategist(), goals.GoalManager("auto", clock=clock), clock=clock, **kw)
    return m, clock


def with_blue(state, blue=True):
    return replace(state, frightened={n: blue for n in state.ghosts}, eyes={n: False for n in state.ghosts})


def test_a_normal_stance_is_the_plain_weights_and_a_stance_scales_only_what_it_names():
    assert goals.scaled_weights("hunt_ghosts") == goals.WEIGHTS["hunt_ghosts"]
    assert goals.scaled_weights("hunt_ghosts", {"caution": "normal", "chase": "normal"}) == goals.WEIGHTS["hunt_ghosts"]
    base, hard = goals.WEIGHTS["hunt_ghosts"], goals.scaled_weights("hunt_ghosts", {"chase": "hard"})
    assert hard[3] > base[3] and hard[:3] == base[:3] and hard[4:] == base[4:]
    cautious = goals.scaled_weights("clear_dots", {"caution": "high"})
    assert cautious[1] > goals.WEIGHTS["clear_dots"][1] and cautious[2] > goals.WEIGHTS["clear_dots"][2]


def test_the_stance_changes_which_way_scores_best():
    risky = {"food_steps": 2, "threat_steps": 6, "edible_steps": None, "fruit_steps": None, "energizer_steps": None,
             "room": 10, "reverse": False, "pressure": 3, "ghosts_close": 1}
    safe = dict(risky, food_steps=9, threat_steps=None)
    pick = lambda mods: max(("risky", "safe"), key=lambda k: features.score_option(  # noqa: E731
        "clear_dots", {"risky": risky, "safe": safe}[k], mods))
    assert pick({"caution": "low", "greed": "high"}) == "risky"
    assert pick({"caution": "high", "greed": "low"}) == "safe"


def test_the_prompt_mentions_only_a_stance_that_is_not_the_default():
    assert goals.stance_text({"caution": "normal", "chase": "normal"}) == ""
    assert "well clear" in goals.stance_text({"caution": "high"})


def test_before_any_answer_the_codes_own_goal_is_used():
    m, clock = manager()
    assert m.choose(STATE, IMAGE, 100) == m.code.goal
    assert m.strategist.asked  # and a question went out


def test_a_legal_goal_from_the_model_is_taken_with_its_stance():
    m, clock = manager()
    m.choose(STATE, IMAGE, 100)
    clock.now += 5
    m.strategist.advice = advice("hunt_ghosts", chase="hard")
    blue = with_blue(STATE)
    assert m.choose(blue, IMAGE, 110) == "hunt_ghosts"
    assert m.mods["chase"] == "hard"
    assert m.drain()[0]["result"] == "taken"


def test_a_goal_with_nothing_to_aim_at_is_gated_and_the_code_goal_stands():
    m, clock = manager()
    clock.now += 5
    nobody_blue = with_blue(STATE, blue=False)
    m.strategist.advice = advice("hunt_ghosts")
    goal = m.choose(nobody_blue, IMAGE, 100)
    assert goal != "hunt_ghosts" and goal == m.code.goal
    assert m.stats["gated"] == 1 and "gated" in m.drain()[0]["result"]


def test_a_goal_is_held_against_flapping_then_given_up_after_the_dwell():
    m, clock = manager(dwell=3.0)
    blue = with_blue(STATE)
    clock.now += 5
    m.strategist.advice = advice("hunt_ghosts")
    m.choose(blue, IMAGE, 100)
    clock.now += 1
    m.strategist.advice = advice("ambush")
    assert m.choose(blue, IMAGE, 120) == "hunt_ghosts" and m.stats["held"] == 1
    clock.now += 3
    m.strategist.advice = advice("ambush")
    assert m.choose(blue, IMAGE, 140) == "ambush"


def test_advice_expires_and_the_code_takes_back_over_with_a_default_stance():
    m, clock = manager(ttl=8.0)
    blue = with_blue(STATE)
    clock.now += 5
    m.strategist.advice = advice("hunt_ghosts", chase="hard")
    m.choose(blue, IMAGE, 100)
    clock.now += 9  # no new answer
    goal = m.choose(blue, IMAGE, 200)
    assert goal == m.code.goal and m.mods["chase"] == "normal" and m.stats["expired"] == 1


def test_the_models_goal_is_dropped_when_what_it_aimed_at_goes_away():
    m, clock = manager()
    clock.now += 5
    m.strategist.advice = advice("hunt_ghosts")
    m.choose(with_blue(STATE), IMAGE, 100)
    clock.now += 1
    assert m.choose(with_blue(STATE, blue=False), IMAGE, 110) == m.code.goal


def test_the_mock_strategist_repeats_the_codes_choice():
    assert strategy.code_chooser({"code_goal": "eat_fruit", "mods": {"caution": "high"}}) == {
        "goal": "eat_fruit", "caution": "high"}


def test_the_summary_says_how_the_blue_ghosts_are_laid_out_and_whether_there_is_time():
    close = strategy.arrangement([5, 7, 9], 5.0)
    assert "3 edible ghosts" in close and "close together" in close and "time enough" in close
    far = strategy.arrangement([6, 30], 1.0)
    assert "spread out" in far and "barely enough time" in far
    assert "1 edible ghost out" in strategy.arrangement([4], None)


def events_manager(quiet=True):
    m, clock = manager(timing="events", quiet=lambda: quiet)
    return m, clock


def test_events_timing_asks_the_goal_with_one_stance_setting_per_heartbeat_in_turn():
    m, clock = events_manager()
    m.choose(STATE, IMAGE, 0)
    settings = list(goals.STANCE)
    assert len(m.strategist.asked) == 1 and m.strategist.only_log[-1] == ("goal", settings[0])
    clock.now += 1.0
    m.choose(STATE, IMAGE, 60)
    assert len(m.strategist.asked) == 1  # nothing new happened, heartbeat not due
    for i in range(1, len(settings) + 1):
        clock.now += strategy.HEARTBEAT
        m.choose(STATE, IMAGE, 400)
        assert m.strategist.only_log[-1] == ("goal", settings[i % len(settings)])
    assert strategy.STANCE_EVERY == strategy.HEARTBEAT * len(settings)


def test_only_goals_with_something_to_aim_at_are_offered():
    m, clock = events_manager()
    m.choose(with_blue(STATE, blue=False), IMAGE, 0)
    assert "hunt_ghosts" not in m.strategist.goals and "clear_dots" in m.strategist.goals
    clock.now += strategy.HEARTBEAT
    m.choose(with_blue(STATE), IMAGE, 400)
    assert "hunt_ghosts" in m.strategist.goals


def test_a_game_event_asks_the_goal_at_once_even_while_junction_questions_wait():
    m, clock = events_manager(quiet=False)
    m.choose(STATE, IMAGE, 0)  # not quiet: the first full question waits
    assert m.strategist.asked == []
    clock.now += 0.5
    m.choose(with_blue(STATE), IMAGE, 30)  # ghosts turn blue
    assert len(m.strategist.asked) == 1 and m.strategist.only_log[-1] == ("goal",)
    m.strategist.advice = advice("clear_dots")
    clock.now += 0.1
    m.choose(with_blue(STATE), IMAGE, 36)
    assert m.drain()[-1]["why"] == "event: blue"


def test_heartbeats_wait_for_a_quiet_moment():
    quiet = {"now": False}
    m, clock = manager(timing="events", quiet=lambda: quiet["now"])
    for _ in range(4):
        clock.now += strategy.HEARTBEAT
        m.choose(STATE, IMAGE, 0)
    assert m.strategist.asked == []
    quiet["now"] = True
    m.choose(STATE, IMAGE, 0)
    assert len(m.strategist.asked) == 1

