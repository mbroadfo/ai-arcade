"""Speed-objective calibration, ranking, and explicit initialization. No ROM and no torch."""
import json
from pathlib import Path

import pytest

from games.lab.integrations.smb_1_1 import (
    BENCHMARKS,
    DEATH_PENALTY,
    FULL_CLOCK,
    INTEGRATION,
    SPEED_COMPLETION,
    SPEED_DEATH,
    SPEED_ID,
    SPEED_STALL,
    SPEED_STALL_LIMIT,
    SPEED_STEP_CAP,
    evaluation_protocol,
    note_clear,
    objective_profile,
    progress_components,
    scenario_stall_limit,
    speed_components,
    speed_protocol,
    step_reward,
)
from games.lab.objective import explicit_init_allowed, next_stall_run, rank_completion, stalled

# Gate A title trace. x after each of 37 decisions. Reset x is 40.
# Decision 1 stays at 40. Decision 37 is the goomba death at x 313.
# The timer on that trace is 399 - (decision // 6).
TITLE_X = [
    40, 41, 42, 45, 47, 51, 55, 59, 64, 70, 76, 82, 88, 94, 102, 110, 118, 128,
    138, 148, 158, 168, 178, 188, 198, 208, 218, 228, 238, 248, 258, 268, 278,
    288, 298, 308, 313,
]
PIPE_X = 434
FLAG_X = 3161


def _time_at(decision: int) -> int:
    return 399 - (decision // 6)


def _facts(x: int, time: int, *, dead: bool = False, flag: bool = False) -> dict:
    return {
        "world": 1,
        "stage": 1,
        "x_pos": x,
        "time": time,
        "dead": dead,
        "dying": False,
        "game_over": False,
        "flag_get": flag,
        "player_state": 0x06 if dead else 0x08,
    }


def _fold(rows: list[tuple[dict, bool]]) -> dict:
    previous = 40
    paid = False
    seen = False
    clear = {"cleared": False, "at": None}
    totals = {key: 0.0 for key in ("progress", "completion", "stall", "death", "time", "total")}
    reason = "open"
    for facts, latch in rows:
        if int(facts.get("time") or 0) > 0:
            seen = True
        if latch:
            clear = note_clear(clear, facts)
        bundle = speed_components(
            previous,
            facts,
            seen,
            bool(clear.get("cleared")),
            clear.get("at") if clear.get("cleared") else None,
            frame_skip=4,
            paid=paid,
        )
        assert bundle["progress"] <= SPEED_STEP_CAP
        assert bundle["completion"] in (0.0, SPEED_COMPLETION)
        assert bundle["stall"] in (0.0, SPEED_STALL)
        assert bundle["death"] in (0.0, SPEED_DEATH)
        assert abs(bundle["time"] - 0.004) < 1e-12
        previous = bundle["high"]
        paid = bundle["paid"]
        for key in totals:
            totals[key] += bundle[key]
        if bundle["dead"]:
            reason = "death"
            break
        if bundle["stop"]:
            reason = "complete"
            break
    totals["high"] = previous
    totals["reason"] = reason
    totals["decisions"] = len(rows) if reason == "open" else None
    return totals


def _running_until(target: int, *, flag_at: int | None = None) -> list[tuple[dict, bool]]:
    rows = []
    x = 40
    for decision, traced in enumerate(TITLE_X[:-1], start=1):
        rows.append((_facts(traced, _time_at(decision)), False))
        x = traced
    decision = len(TITLE_X) - 1
    while x < target:
        decision += 1
        x += min(10, target - x)
        flag = flag_at is not None and x >= flag_at
        rows.append((_facts(x, _time_at(decision), flag=flag), flag))
        if flag:
            break
    return rows


def _goomba():
    rows = []
    for decision, x in enumerate(TITLE_X, start=1):
        dead = decision == len(TITLE_X)
        rows.append((_facts(x, _time_at(decision), dead=dead), False))
    return rows


def _pipe_stall():
    rows = _running_until(PIPE_X)
    decision = len(rows)
    x = rows[-1][0]["x_pos"]
    for _ in range(SPEED_STALL_LIMIT):
        decision += 1
        rows.append((_facts(x, _time_at(decision)), False))
    return rows


def _past_pipe():
    rows = _running_until(PIPE_X)
    decision = len(rows)
    x = rows[-1][0]["x_pos"]
    for _ in range(30):
        decision += 1
        x += 10
        rows.append((_facts(x, _time_at(decision)), False))
    return rows


def _slow_clear():
    gains = []
    previous = 40
    for x in TITLE_X[:-1]:
        gains.append(x - previous)
        previous = x
    while previous < FLAG_X:
        step = min(10, FLAG_X - previous)
        gains.append(step)
        previous += step
    halved = []
    for gain in gains:
        if gain >= 2:
            left = gain // 2
            halved.extend((left, gain - left))
        else:
            halved.append(gain)
    rows = []
    x = 40
    for decision, gain in enumerate(halved, start=1):
        x += gain
        flag = x >= FLAG_X
        rows.append((_facts(x, _time_at(decision), flag=flag), flag))
        if flag:
            break
    return rows


def _near_flag_death():
    rows = _running_until(FLAG_X - 3)
    decision = len(rows)
    x = rows[-1][0]["x_pos"]
    rows.append((_facts(x, _time_at(decision + 1), dead=True), False))
    return rows


def representative_returns() -> dict:
    """Four Gate A episodes plus a slow clear and a near-flag death.

    The goomba death uses the traced x positions. The pipe, the further run,
    and the clears continue at the traced 10-pixel running pace. The clears
    are constructed: no saved policy has finished World 1-1 unassisted.
    """
    episodes = {
        "goomba_death": _fold(_goomba()),
        "pipe_stall": _fold(_pipe_stall()),
        "past_pipe": _fold(_past_pipe()),
        "brisk_clear": _fold(_running_until(FLAG_X, flag_at=FLAG_X)),
        "slow_clear": _fold(_slow_clear()),
        "near_flag_death": _fold(_near_flag_death()),
    }
    return episodes


def test_the_traced_clock_matches_gate_a():
    assert _time_at(1) == 399
    assert _time_at(6) == 398
    assert _time_at(36) == 393
    assert _time_at(37) == 393
    assert TITLE_X[0] == 40 and TITLE_X[-1] == 313 and len(TITLE_X) == 37


def test_progress_components_match_the_existing_reward():
    moving = {
        "world": 1,
        "stage": 1,
        "x_pos": 100,
        "time": FULL_CLOCK,
        "flag_get": False,
        "dead": False,
        "dying": False,
        "game_over": False,
    }
    flag = {
        "world": 1,
        "stage": 1,
        "x_pos": 3161,
        "time": 400,
        "flag_get": True,
        "dead": False,
        "dying": False,
        "game_over": False,
    }
    cases = [
        (80, moving, True, False, None),
        (80, {**moving, "time": 200}, True, False, None),
        (80, {**moving, "x_pos": 80}, True, False, None),
        (200, {**flag, "time": 0, "flag_get": False, "x_pos": 200}, True, False, None),
        (3161, {**flag, "time": 0}, True, False, None),
        (3266, {**flag, "time": 0, "flag_get": False, "x_pos": 3266, "dying": True, "player_state": 0x08}, True, True, (1, 1)),
    ]
    for previous, facts, seen, cleared, place in cases:
        reward, high, dead = step_reward(previous, facts, seen, cleared, place)
        bundle = progress_components(previous, facts, seen, cleared, place)
        assert bundle["total"] == reward
        assert bundle["high"] == high
        assert bundle["dead"] is dead
        assert bundle["stop"] is False
        parts = bundle["progress"] + bundle["completion"] - bundle["stall"] - bundle["death"] - bundle["time"]
        assert abs(parts - reward) < 1e-9


def test_speed_returns_prefer_a_clear_over_the_pipe_and_an_early_death():
    returns = representative_returns()
    death = returns["goomba_death"]["total"]
    pipe = returns["pipe_stall"]["total"]
    further = returns["past_pipe"]["total"]
    brisk = returns["brisk_clear"]["total"]
    slow = returns["slow_clear"]["total"]
    near = returns["near_flag_death"]["total"]
    assert returns["goomba_death"]["reason"] == "death"
    assert returns["goomba_death"]["death"] == SPEED_DEATH
    assert returns["pipe_stall"]["reason"] == "open"
    assert returns["pipe_stall"]["death"] == 0.0
    assert returns["pipe_stall"]["stall"] == pytest.approx(SPEED_STALL_LIMIT * SPEED_STALL + SPEED_STALL)
    assert returns["past_pipe"]["high"] >= PIPE_X + 300
    assert returns["brisk_clear"]["reason"] == "complete"
    assert returns["slow_clear"]["reason"] == "complete"
    assert returns["brisk_clear"]["completion"] == SPEED_COMPLETION
    assert returns["slow_clear"]["completion"] == SPEED_COMPLETION
    assert returns["near_flag_death"]["completion"] == 0.0
    assert brisk > slow > near
    assert slow > further > pipe
    assert slow > death
    assert brisk >= 3 * max(pipe, death)
    assert slow >= 3 * max(pipe, death)
    assert SPEED_COMPLETION < 100
    assert SPEED_DEATH != DEATH_PENALTY
    locked = json.loads(
        (Path(__file__).resolve().parents[1] / "experiments" / "objective-reward" / "calibration.json").read_text(encoding="utf-8")
    )
    for name, episode in locked["episodes"].items():
        for key in ("progress", "completion", "stall", "death", "time", "total"):
            assert returns[name][key] == pytest.approx(episode[key], abs=1e-9)
        assert returns[name]["high"] == episode["high"]


def test_completion_is_paid_once_and_a_stall_is_not_a_death():
    flag = _facts(FLAG_X, 350, flag=True)
    clear = note_clear({"cleared": False, "at": None}, flag)
    first = speed_components(FLAG_X - 3, flag, True, True, clear["at"], frame_skip=4, paid=False)
    assert first["completion"] == SPEED_COMPLETION and first["stop"] is True and first["paid"] is True
    second = speed_components(first["high"], flag, True, True, clear["at"], frame_skip=4, paid=True)
    assert second["completion"] == 0.0 and second["stop"] is False
    held = speed_components(80, _facts(80, 400), True, False, None)
    assert held["stall"] == SPEED_STALL and held["death"] == 0.0
    fallen = speed_components(80, _facts(80, 390, dead=True), True, False, None)
    assert fallen["death"] == SPEED_DEATH and fallen["stall"] == 0.0
    huge = speed_components(
        0,
        {"world": 2, "stage": 1, "x_pos": 0, "time": 400, "dead": False, "dying": False, "game_over": False, "flag_get": False},
        True,
        False,
        None,
    )
    assert huge["progress"] == SPEED_STEP_CAP


def test_stall_cutoff_is_configuration():
    run = 0
    for _ in range(SPEED_STALL_LIMIT - 1):
        run = next_stall_run(run, 0)
    assert run == SPEED_STALL_LIMIT - 1
    assert stalled(run, SPEED_STALL_LIMIT) is False
    run = next_stall_run(run, 0)
    assert stalled(run, SPEED_STALL_LIMIT) is True
    assert next_stall_run(run, 4) == 0
    assert stalled(100, None) is False
    assert scenario_stall_limit("progress") is None
    assert scenario_stall_limit(SPEED_ID) == 24
    assert INTEGRATION.stall_limit("progress") is None
    assert INTEGRATION.stall_limit(SPEED_ID) == 24
    ceiling = scenario_stall_limit(SPEED_ID, "smb-1-2-ceiling-lift")
    assert ceiling == 64
    path = Path(__file__).resolve().parents[1] / "challenges" / "smb-1-2-ceiling-lift" / "challenge.json"
    assert json.loads(path.read_text(encoding="utf-8"))["stall_limit"] == ceiling


def test_speed_stamp_does_not_claim_the_progress_objective():
    progress = INTEGRATION.stamp()
    speed = INTEGRATION.stamp(SPEED_ID)
    assert INTEGRATION.objective == "progress"
    assert progress["objective"] == "progress"
    assert speed["objective"] == SPEED_ID
    assert progress["actions"] == speed["actions"]
    assert progress["ram"] == speed["ram"] == 9
    with pytest.raises(ValueError):
        INTEGRATION.stamp("smb-points")
    with pytest.raises(ValueError):
        objective_profile("smb-points")
    profile = objective_profile(SPEED_ID)
    assert profile["implemented"] is True
    assert profile["stall_limit"] == 24
    assert profile["completion"] == SPEED_COMPLETION
    protocol = speed_protocol()
    assert protocol["objective"] == SPEED_ID
    assert protocol["sense"] == "minimize"
    assert protocol["metric"] == "frames"
    assert protocol["require_success"] is True
    assert protocol["default_benchmark"] == "clear-1-1-flag"
    assert protocol["benchmarks"]["clear-1-1-flag"] == BENCHMARKS["clear-1-1-flag"]
    assert evaluation_protocol()["objective"] == "progress"
    assert "require_success" not in evaluation_protocol()


def test_a_fast_death_does_not_outrank_a_slow_clear():
    death = {"failed": False, "success": False, "score": 313, "frames": 148}
    early = {"failed": False, "success": False, "score": 80, "frames": 40}
    slow = {"failed": False, "success": True, "score": FLAG_X, "frames": 4000}
    brisk = {"failed": False, "success": True, "score": FLAG_X, "frames": 1200}
    assert rank_completion([death, early, slow, brisk]) is brisk
    assert rank_completion([death, early]) is death
    assert rank_completion([slow, death]) is slow
    from games.lab.eval import _furthest, _record_furthest
    assert _furthest([death, slow], metric="frames", sense="minimize", require_success=True) is slow
    assert _furthest([death, slow], metric="frames", sense="minimize") is death
    recorded = _record_furthest(
        {"score": 1, "world": 1, "stage": 1, "x_pos": 1, "time": 9, "dead": False, "frames": 80},
        speed_protocol(),
    )
    assert recorded["frames"] == 80
    assert recorded["time"] == 9


def test_a_failed_speed_run_is_not_a_promoted_parent(tmp_path):
    from games.lab.eval import checkpoint_sha256, write_eval
    from games.lab.lineage import promoted_parent

    protocol = speed_protocol()

    def measurement(success: bool, frames: int, score: int) -> dict:
        episodes = []
        for seed in range(5):
            episodes.append({
                "seed": seed,
                "failed": False,
                "score": score,
                "world": 1,
                "stage": 1,
                "x_pos": score,
                "time": 300,
                "dead": not success,
                "frames": frames,
                "success": success,
                "milestones": {
                    "clear-1-1-flag": success,
                    "reach-world-1-2": False,
                    "enter-world-4": False,
                },
            })
        return {
            "assisted": False,
            "failed": False,
            "record": "independent",
            "protocol": protocol["name"],
            "benchmark": "clear-1-1-flag",
            "benchmark_definition": BENCHMARKS["clear-1-1-flag"],
            "game": "smb_1_1",
            "objective": SPEED_ID,
            "frame_skip": 4,
            "deterministic": True,
            "limit": 2000,
            "n_actions": 12,
            "start": "game",
            "model": "ppo_cnn",
            "rom_sha1": "abc",
            "core_sha1": "def",
            "seed": 0,
            "seeds": list(range(5)),
            "attempts": 5,
            "successes": 5 if success else 0,
            "success_rate": 1.0 if success else 0.0,
            "furthest": {
                "score": score,
                "world": 1,
                "stage": 1,
                "x_pos": score,
                "time": 300,
                "dead": not success,
                "frames": frames,
            },
            "episodes": episodes,
        }

    def write(run: str, seat: int, payload: bytes, evaluation: dict) -> None:
        folder = tmp_path / run / "seats" / str(seat)
        folder.mkdir(parents=True)
        zip_path = folder / "best.zip"
        zip_path.write_bytes(payload)
        (tmp_path / run / "results.json").write_text(json.dumps({
            "winner": seat,
            "seats": [{
                "seat": seat,
                "name": "Red",
                "model": "ppo_cnn",
                "score": 100,
                "steps": 200000,
                "deaths": 1,
            }],
        }), encoding="utf-8")
        evaluation = {**evaluation, "checkpoint_sha256": checkpoint_sha256(zip_path)}
        write_eval(folder / "best.eval.json", evaluation)

    write("failed", 0, b"failed-speed", measurement(False, 148, 313))
    assert promoted_parent(tmp_path, "ppo_cnn", protocol=protocol) is None
    write("slow", 0, b"slow-clear", measurement(True, 4000, FLAG_X))
    write("brisk", 1, b"brisk-clear", measurement(True, 1200, FLAG_X))
    parent = promoted_parent(tmp_path, "ppo_cnn", protocol=protocol)
    assert parent["success_rate"] == 1.0
    assert parent["score"] == 1200
    assert parent["seat"] == 1
    assert promoted_parent(tmp_path, "ppo_cnn", protocol=evaluation_protocol()) is None


def test_explicit_init_allows_a_different_objective_only(tmp_path):
    from games.lab.stamp import write_stamp
    from games.lab.worker import train

    source = {"actions": [["RIGHT"]], "objective": "progress", "ram": 9}
    expected = {"actions": [["RIGHT"]], "objective": SPEED_ID, "ram": 9}
    assert explicit_init_allowed(source, expected) is True
    assert explicit_init_allowed(source, {**expected, "objective": "progress"}) is True
    assert explicit_init_allowed({**source, "ram": 8}, expected) is False
    assert explicit_init_allowed({**source, "actions": [[]]}, expected) is False
    assert explicit_init_allowed(None, expected) is False
    assert explicit_init_allowed({"actions": [["RIGHT"]], "ram": 9}, expected) is False
    zip_path = tmp_path / "seed.zip"
    zip_path.write_bytes(b"not-weights")
    write_stamp(zip_path, {"actions": [["LEFT"]], "objective": "progress", "ram": 9})
    with pytest.raises(ValueError):
        train(None, "ppo_cnn", 0, 8, tmp_path / "seat", {"stamp": expected}, False, init_from=zip_path)
    bare = tmp_path / "unstamped.zip"
    bare.write_bytes(b"not-weights")
    with pytest.raises(ValueError):
        train(None, "ppo_cnn", 0, 8, tmp_path / "seat", {"stamp": expected}, False, init_from=bare)
