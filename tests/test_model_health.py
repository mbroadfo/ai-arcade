"""arcadekit/health.py and the pilot's plan deadline: a slow model must be seen, not silently replaced by code."""
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

import pytest  # noqa: E402

from arcadekit.health import ModelHealth  # noqa: E402
from games.arcade.bzone import pilot  # noqa: E402


def test_trouble_starts_after_three_misses_in_five_and_clears_when_the_model_answers_again():
    h = ModelHealth()
    assert [h.record(ok) for ok in (True, False, False)] == [None, None, None] and not h.trouble
    assert h.record(False) == "trouble" and h.trouble
    assert "3 of the last 4 plans" in h.message() and "GPU" in h.message()
    assert h.record(False) is None  # still in trouble: no second alarm
    changes = [h.record(True) for _ in range(5)]
    assert "recovered" in changes and not h.trouble and changes.count("recovered") == 1


def test_a_healthy_model_never_raises_the_alarm():
    h = ModelHealth()
    assert all(h.record(True) is None for _ in range(20)) and not h.trouble


class FakeClient:
    def __init__(self):
        self.calls = 0

    def ask(self, text, questions):
        self.calls += 1
        name = next(iter(questions))
        return {"answers": {name: {"choice": next(iter(questions[name]["criteria"])), "confidence": 1.0}}, "latency_ms": 5}


def test_a_plan_that_is_taking_too_long_is_given_up_between_questions():
    decider = pilot.PlanDecider(FakeClient())
    decider.deadline = time.time() - 1  # the plan began long ago
    with pytest.raises(TimeoutError):
        decider.ask("text", "step1", "which?", {"a": "a", "b": "b"})
    assert decider.client.calls == 0  # not even asked
    decider.deadline = time.time() + 60
    assert decider.ask("text", "step1", "which?", {"a": "a"})[0] == "a" and decider.client.calls == 1


def test_one_slow_call_is_allowed_longer_than_the_plan_deadline_allows_for_none():
    assert pilot.CALL_TIMEOUT_S >= 3.0 and pilot.PLAN_DEADLINE_S > pilot.CALL_TIMEOUT_S
