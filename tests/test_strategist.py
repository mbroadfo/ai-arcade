import threading
import time

from arcadekit.strategist import MockStrategistClient, Strategist, build_questions, parse_reply

SCHEMA = {
    "instructions": "Advise.",
    "goals": {"a": "do a", "b": "do b"},
    "modifiers": {"care": {"about": "How careful.", "levels": {"low": "x", "high": "y"}, "default": "low"}},
}


def reply(goal="a", care="high", confidence=0.9):
    return {"answers": {"goal": {"choice": goal, "confidence": confidence}, "care": {"choice": care}},
            "latency_ms": 12.0}


class Client:
    def __init__(self, result=None, error=None, gate=None):
        self.result, self.error, self.gate, self.calls = result, error, gate, []

    def ask(self, state, questions, hint=None):
        self.calls.append((state, questions, hint))
        if self.gate:
            self.gate.wait(2)
        if self.error:
            raise self.error
        return self.result


def wait_for_advice(strategist, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        advice = strategist.take()
        if advice or not strategist.busy:
            return advice
        time.sleep(0.005)


def test_one_question_per_goal_and_per_modifier_with_their_choices():
    questions = build_questions(SCHEMA)
    assert set(questions) == {"goal", "care"}
    assert set(questions["goal"]["criteria"]) == {"a", "b"} and set(questions["care"]["criteria"]) == {"low", "high"}
    assert all(q["type"] == "choice" for q in questions.values())


def test_a_valid_reply_becomes_advice():
    advice, problems = parse_reply(reply(), SCHEMA)
    assert (advice.goal, advice.mods, problems) == ("a", {"care": "high"}, [])


def test_an_unknown_goal_voids_the_advice_and_an_unknown_level_is_only_left_out():
    assert parse_reply(reply(goal="fly"), SCHEMA)[0] is None
    advice, problems = parse_reply(reply(care="sideways"), SCHEMA)
    assert advice.goal == "a" and advice.mods == {} and problems


def test_advice_is_taken_once():
    s = Strategist(Client(reply()), SCHEMA)
    assert s.request("state")
    assert wait_for_advice(s).goal == "a"
    assert s.take() is None


def test_a_second_request_is_refused_while_the_first_is_out():
    gate = threading.Event()
    s = Strategist(Client(reply(), gate=gate), SCHEMA)
    assert s.request("one")
    assert not s.request("two")
    gate.set()
    wait_for_advice(s)
    assert s.request("three")


def test_a_failing_model_leaves_nothing_and_is_counted():
    s = Strategist(Client(error=OSError("down")), SCHEMA)
    s.request("state")
    assert wait_for_advice(s) is None
    assert s.stats["errors"] == 1 and "down" in s.last_error


def test_nonsense_and_low_confidence_are_discarded():
    s = Strategist(Client(reply(goal="fly")), SCHEMA)
    s.request("state")
    assert wait_for_advice(s) is None and s.stats["invalid"] == 1
    s = Strategist(Client(reply(confidence=0.2)), SCHEMA, min_confidence=0.5)
    s.request("state")
    assert wait_for_advice(s) is None and s.stats["low_confidence"] == 1


def test_the_mock_client_answers_every_question_from_its_chooser():
    mock = MockStrategistClient(lambda hint: {"goal": "b", "care": "low"}, latency_ms=(1, 2))
    advice, _ = parse_reply(mock.ask("state", build_questions(SCHEMA), hint={}), SCHEMA)
    assert (advice.goal, advice.mods) == ("b", {"care": "low"})


def test_asking_the_goal_alone_leaves_the_stance_unanswered_without_complaint():
    from arcadekit.strategist import build_questions, parse_reply
    schema = {"instructions": "x", "goals": {"a": "A", "b": "B"},
              "modifiers": {"caution": {"about": "c", "levels": {"low": "l", "high": "h"}, "default": "low"}}}
    assert set(build_questions(schema, only=("goal",))) == {"goal"}
    advice, problems = parse_reply({"answers": {"goal": {"choice": "b", "confidence": 0.8}}}, schema, asked={"goal"})
    assert advice.goal == "b" and advice.mods == {} and problems == []


def test_only_the_goals_on_offer_are_asked_and_accepted():
    from arcadekit.strategist import build_questions, parse_reply
    schema = {"instructions": "x", "goals": {"a": "A", "b": "B", "c": "C"}, "modifiers": {}}
    assert set(build_questions(schema, goals=("a", "c"))["goal"]["criteria"]) == {"a", "c"}
    reply = {"answers": {"goal": {"choice": "b", "confidence": 0.8}}}
    assert parse_reply(reply, schema, goals=("a", "c"))[0] is None
    assert parse_reply(reply, schema)[0].goal == "b"
