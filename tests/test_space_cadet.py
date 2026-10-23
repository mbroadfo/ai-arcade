"""Space Cadet's player-side code: the facts, options and controls, the picture for the Observatory, and the AI setup's view of the
game. No game or Pi needed: states are written out as the bridge reports them."""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import ai_setup  # noqa: E402
from games.ports.space_cadet import observe  # noqa: E402
from games.ports.space_cadet.players import ModelPlayer, ReflexControl, flipper_facts, flipper_questions, situation  # noqa: E402


def table(ball, left_up=False, right_up=False, **extra):
    """A bridge state with one ball (table coordinates: x runs to the screen's left)."""
    flip = lambda sign, up: {"angle": 1.2 * sign if up else 0.0, "max": 1.2, "pivot": [2.489 * sign, 12.063],  # noqa: E731
                             "tip": [0.961 * sign, 13.131]}
    return {"game_mode": "in_game", "score": 1000, "ball_number": 3, "balls": [ball], "message": "", "nudge_count": 0.0,
            "flippers": {"left": flip(1, left_up), "right": flip(-1, right_up)}, **extra}


def ball(x, y, dx=0.0, dy=1.0, speed=5.0):
    return {"x": x, "y": y, "z": 0.3, "dx": dx, "dy": dy, "speed": speed}


def test_screen_terms_put_the_left_flipper_on_the_left():
    ff = flipper_facts(table(ball(2.0, 11.0)), ball(2.0, 11.0))  # x +2 is the screen's left
    assert ff["ball"]["sx"] == -2.0
    assert ff["left"]["reach"] and not ff["right"]["reach"]


def test_a_ball_in_the_plunger_lane_is_ready_only_at_rest():
    assert flipper_facts(table(ball(-7.0, 11.67, speed=0.1)), ball(-7.0, 11.67, speed=0.1))["in_lane"]
    assert not flipper_facts(table(ball(-7.0, 10.2, speed=1.9)), ball(-7.0, 10.2, speed=1.9))["in_lane"]  # still rolling in


def test_each_flipper_is_asked_apart_and_options_say_what_a_resting_ball_does():
    b = ball(-2.4, 11.3, speed=0.1)
    ff = flipper_facts(table(b, right_up=True), b)
    questions = flipper_questions(ff)
    assert set(questions) == {"left", "right", "nudge"}
    assert set(questions["right"]["criteria"]) == {"raise", "lower"}
    assert "resting on it and will not move" in questions["right"]["criteria"]["raise"]
    assert "rolls off" in questions["right"]["criteria"]["lower"]
    assert "out of its reach" in questions["left"]["criteria"]["raise"]


class FakeClient:
    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def ask(self, text, questions):
        self.asked.append(questions)
        return {"answers": {n: {"choice": self.answers[n], "confidence": 0.9} for n in questions}, "latency_ms": 100}


def test_the_model_player_turns_three_answers_into_flippers_and_a_nudge():
    b = ball(2.0, 11.0)
    state = table(b)
    ff = flipper_facts(state, b)
    d = ModelPlayer(FakeClient({"left": "raise", "right": "lower", "nudge": "nudge_up"}), "always").flippers(state, ff, None)
    assert (d["choice"], d["nudge"], d["source"]) == ("left", "nudge_up", "model")
    d = ModelPlayer(FakeClient({"left": "lower", "right": "lower", "nudge": "none"}), "always").flippers(state, ff, None)
    assert (d["choice"], d["nudge"]) == ("neither", None)


def test_a_model_that_answers_something_not_offered_is_booked_as_a_fallback():
    b = ball(2.0, 11.0)
    state = table(b)
    player = ModelPlayer(FakeClient({"left": "both", "right": "lower", "nudge": "none"}), "always")
    d = player.flippers(state, flipper_facts(state, b), None)
    assert d["source"] == "fallback" and d["choice"] == "neither" and player.moves["fallback"] == 1


def test_situation_reports_a_stuck_ball_and_the_tilt_meter():
    b = ball(-2.4, 11.3, speed=0.1)
    state = table(b, right_up=True, nudge_count=0.4)
    ff = flipper_facts(state, b)
    ff["ball"]["still_s"] = 4.0
    ff["right"]["up_s"] = 3.0
    text = situation(state, ff)
    assert "same spot for 4.0 s" in text and "held 3.0 s" in text and "Tilt meter 0.4" in text


def test_reflex_control_lets_a_flipper_down_after_three_windows():
    b = ball(2.0, 11.0, speed=0.1)
    ff = flipper_facts(table(b), b)
    reflex = ReflexControl()
    choices = [reflex.flippers({}, ff, None)["choice"] for _ in range(5)]
    assert choices == ["left", "left", "left", "neither", "neither"]


def test_the_picture_is_a_png_and_the_status_names_whose_move_it_was():
    state = table(ball(1.0, 5.0))
    png = base64.b64decode(observe.frame_png(state, [(-1.0, 4.0)]))
    assert png.startswith(b"\x89PNG")
    ff = flipper_facts(state, state["balls"][0])
    record = observe.status(state, {"choice": "left", "source": "model", "latency_ms": 230}, "flippers", ff, 0)
    assert record["event"] == "status" and record["screen"]["size"] == list(observe.SIZE)
    assert any(f["value"] == "left (model)" for f in record["facts"])


def test_the_ai_setup_lists_the_game_and_knows_it_has_no_mame():
    assert "ports/space_cadet" in ai_setup.ai_games()
    schema = ai_setup.schema("ports/space_cadet")
    assert schema["kind"] == "lab" and schema["own_screen"]
    args = ai_setup.command_line("ports/space_cadet", {"runtype": "ai", "ai_mode": "model", "hz": 12.5, "seconds": 300})
    assert args[:2] == ["--game", "ports/space_cadet"] and "--model" in args


def test_when_the_ball_is_far_from_both_flippers_the_model_is_not_asked_and_the_window_is_booked_as_skipped():
    b = ball(-1.0, -8.0, speed=9.0)  # high on the table, falling slowly toward the flippers
    state = table(b)
    client = FakeClient({})
    player = ModelPlayer(client)  # ask_when "near"
    d = player.flippers(state, flipper_facts(state, b), None)
    assert d["source"] == "skipped" and d["choice"] == "neither" and client.asked == [] and player.moves["skipped"] == 1


def test_only_the_near_flipper_is_asked_and_a_nudge_only_when_the_ball_is_stuck():
    b = ball(2.0, 11.0, speed=0.1)  # at the left flipper (x +2 is the screen's left), and not moving
    state = table(b)
    ff = flipper_facts(state, b)
    client = FakeClient({"left": "raise", "right": "lower", "nudge": "none"})
    ModelPlayer(client).flippers(state, ff, None)
    assert "left" in client.asked[0] and "nudge" not in client.asked[0]  # not yet stuck
    ff["ball"]["still_s"] = 2.0
    ModelPlayer(client).flippers(state, ff, None)
    assert "nudge" in client.asked[1]
