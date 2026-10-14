"""A grid adapter proves the engine can run without a game import.

The grid is a test double. It is not a cabinet game and it is not registered
for the lab page. Run this file as a module to show a fresh interpreter never
loads the Mario adapter.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from games.lab.challenge import catalog, load_challenge, same_start, save_challenge
from games.lab.contract import open_experiment
from games.lab.eval import (
    accept_eval,
    checkpoint_sha256,
    compare_independent,
    evaluate_attempts,
    play_unassisted,
    write_eval,
)
from games.lab.lineage import promoted_parent
from games.lab.ranking import generation_rank, winner
from games.lab.registry import get, isolated
from games.lab.search import beam_search
from games.lab.skill import new_skill, record_mastery, verify_demonstration
from games.lab.worker import atomic_json

GOAL = 3
ROM = "grid-runtime"
CORE = "grid-core"


def _metrics(info: dict) -> dict:
    def num(key: str) -> int:
        try:
            return int(info.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    return {"score": num("score"), "time": num("time"), "position": num("position")}


def _observe(reached: dict, info: dict) -> dict:
    updated = dict(reached)
    try:
        updated["goal"] = int(info.get("position") or 0) >= GOAL
    except (TypeError, ValueError):
        updated["goal"] = False
    return updated


def _supports(episode: dict, benchmark: str) -> bool:
    if benchmark != "goal":
        return False
    try:
        return int(episode.get("position") or 0) >= GOAL
    except (TypeError, ValueError):
        return False


def _protocol(sense: str) -> dict:
    if sense == "minimize":
        return {
            "name": "grid-time-v1",
            "attempts": 2,
            "limit": 8,
            "frame_skip": 1,
            "n_actions": 2,
            "seed": 0,
            "default_benchmark": "goal",
            "game": "grid",
            "objective": "time",
            "sense": "minimize",
            "metric": "time",
            "start": "origin",
            "benchmarks": {"goal": "The marker reaches the goal. A shorter time is better."},
            "observe": _observe,
            "supports": _supports,
            "metrics": _metrics,
        }
    return {
        "name": "grid-progress-v1",
        "attempts": 2,
        "limit": 8,
        "frame_skip": 1,
        "n_actions": 2,
        "seed": 0,
        "default_benchmark": "goal",
        "game": "grid",
        "objective": "progress",
        "sense": "maximize",
        "metric": "score",
        "start": "origin",
        "benchmarks": {"goal": "The marker stands on the goal cell."},
        "observe": _observe,
        "supports": _supports,
        "metrics": _metrics,
    }


class GridEnv:
    """One cell at a time. Forward advances. Wait spends a step."""

    def __init__(self):
        self.position = 0
        self.time = 0

    def reset(self, seed=0):
        self.position = 0
        self.time = 0
        self.seed = int(seed or 0)
        return {"position": 0}, self.facts()

    def step(self, action):
        self.time += 1
        if int(action) == 1:
            self.position += 1
        done = self.position >= GOAL
        return {"position": self.position}, float(self.position), done, False, self.facts()

    def facts(self) -> dict:
        return {
            "score": self.position,
            "time": self.time,
            "position": self.position,
            "dead": False,
            "dying": False,
            "forced": False,
            "assisted": False,
            "demonstration_steps": 0,
        }

    def snapshot(self) -> bytes:
        return json.dumps({"position": self.position, "time": self.time}, separators=(",", ":")).encode()

    def restore(self, blob: bytes) -> None:
        data = json.loads(bytes(blob))
        self.position = int(data["position"])
        self.time = int(data["time"])


class GridProbe:
    def __init__(self, env: GridEnv, state: bytes):
        self.env = env
        self.state = bytes(state)

    def replay(self, trajectory) -> dict:
        self.env.restore(self.state)
        facts = self.env.facts()
        for step in trajectory:
            buttons = set(step.get("buttons") or [])
            action = 1 if "forward" in buttons else 0
            for _ in range(max(int(step.get("frames") or 1), 0)):
                _obs, _reward, _terminated, _truncated, facts = self.env.step(action)
        return facts


class GridAdapter:
    id = "grid"
    system = "synthetic"
    objective = "progress"
    sense = "maximize"
    actions = [(), ("forward",)]
    capabilities = {
        "contract": 1,
        "pixels": False,
        "ram": False,
        "savestate": True,
        "frame_accurate": True,
        "structured": True,
    }

    def open_env(self):
        return GridEnv()

    def evaluation_protocol(self):
        return _protocol("maximize")

    def owns(self, record: dict) -> bool:
        return isinstance(record, dict) and record.get("integration") == self.id


def _forward(_observation):
    return 1


class _Slow:
    def __init__(self):
        self.calls = 0

    def __call__(self, _observation):
        self.calls += 1
        return 0 if self.calls == 1 else 1


def _measure(env: GridEnv, policy_for_attempt, protocol: dict, weights: Path) -> dict:
    identity = {
        "model": "stub",
        "seed": 0,
        "rom_sha1": ROM,
        "core_sha1": CORE,
        "checkpoint_sha256": checkpoint_sha256(weights),
    }

    def run_one(seed):
        return play_unassisted(env, policy_for_attempt(), seed=seed, protocol=protocol)

    result = evaluate_attempts(run_one, protocol["attempts"], identity, protocol)
    write_eval(weights.with_suffix(".eval.json"), result)
    return result


def exercise(root: Path) -> dict:
    adapter = GridAdapter()
    with isolated(adapter):
        assert get("grid").id == "grid"
        with pytest.raises(KeyError):
            get("smb_1_1")
        experiment = open_experiment(adapter)
    env = experiment["env"]
    assert experiment["adapter"] == "grid"
    assert experiment["protocol"]["name"] == "grid-progress-v1"
    assert experiment["protocol"]["sense"] == "maximize"
    assert experiment["capabilities"]["savestate"] is True
    assert experiment["capabilities"]["ram"] is False
    _observation, info = env.reset(seed=0)
    assert info["position"] == 0 and info["assisted"] is False
    _observation, _reward, done, _truncated, info = env.step(1)
    assert info["position"] == 1 and done is False

    env.reset(seed=0)
    state = env.snapshot()
    document = {
        "id": "grid-goal",
        "objective": "Reach the goal cell.",
        "game": "grid",
        "integration": "grid",
        "rom_sha1": ROM,
        "core_sha1": CORE,
        "core_name": "synthetic",
        "state_format": "snapshot",
        "success": "goal",
        "start": {"position": 0, "time": 0},
    }
    folder = save_challenge(root, document, state)
    loaded, blob = load_challenge(folder, rom_sha1=ROM, core_sha1=CORE)
    assert loaded["state_format"] == "snapshot"
    assert loaded["identity_keys"] == ["position", "time"]
    env.step(1)
    env.restore(blob)
    assert same_start(loaded["start"], env.facts())

    probe = GridProbe(env, blob)

    def success(facts: dict) -> bool:
        return int(facts["position"]) >= GOAL and not facts["dead"]

    found = beam_search(
        probe,
        [(), ("forward",)],
        success,
        lambda facts: int(facts["position"]),
        width=2,
        depth=4,
        hold=1,
        max_attempts=40,
    )
    assert found["solved"] is True
    repeats = [success(probe.replay(found["trajectory"])) for _ in range(2)]
    skill = verify_demonstration(
        new_skill(
            "walk to the goal",
            document["objective"],
            document["id"],
            found["trajectory"],
            start=loaded["start"],
            benchmark="goal",
            context={"cell": 0},
            integration="grid",
        ),
        repeats,
    )
    assert skill["stage"] == "verified_demonstration"
    assert "world" not in skill
    assert skill["integration"] == "grid"
    atomic_json(folder / "search.json", {
        "solved": found["solved"],
        "trajectory": found["trajectory"],
        "attempts": found["attempts"],
        "frames": found["frames"],
        "decisions": found["decisions"],
    })
    atomic_json(folder / "skill.json", skill)
    listed = catalog(root)
    assert listed[0]["id"] == "grid-goal"
    assert listed[0]["skill"]["standing"] == "verified_demonstration"

    progress = _protocol("maximize")
    weights = root / "progress" / "seats" / "0" / "best.zip"
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"grid-forward")
    progressed = _measure(GridEnv(), lambda: _forward, progress, weights)
    assert progressed["failed"] is False and progressed["success_rate"] == 1.0
    assert accept_eval(progressed, weights, protocol=progress, model="stub") is True
    fixed = record_mastery(skill, "stub", progressed)
    assert fixed["agents"]["stub"] == "verified_fixed_state"
    assert fixed["standing"] == "verified_fixed_state"
    assert fixed["stage"] == "verified_demonstration"
    varied = record_mastery(fixed, "stub", {
        **progressed,
        "generalized": True,
        "starts": [{"position": 0}, {"position": 1}],
    })
    assert varied["agents"]["stub"] == "generalized"
    atomic_json(folder / "skill.json", fixed)
    assert catalog(root)[0]["skill"]["standing"] == "verified_fixed_state"

    timed = _protocol("minimize")
    fast_weights = root / "fast" / "seats" / "1" / "best.zip"
    slow_weights = root / "slow" / "seats" / "0" / "best.zip"
    fast_weights.parent.mkdir(parents=True)
    slow_weights.parent.mkdir(parents=True)
    fast_weights.write_bytes(b"grid-fast")
    slow_weights.write_bytes(b"grid-slow")
    fast = _measure(GridEnv(), lambda: _forward, timed, fast_weights)
    slow = _measure(GridEnv(), _Slow, timed, slow_weights)
    assert fast["furthest"]["time"] < slow["furthest"]["time"]
    assert compare_independent(slow, fast)["improved"] is True
    assert compare_independent(fast, slow)["improved"] is False
    for run, seat, score in (("fast", 1, fast["furthest"]["time"]), ("slow", 0, slow["furthest"]["time"])):
        (root / run / "results.json").write_text(json.dumps({
            "winner": seat,
            "sense": "minimize",
            "integration": "grid",
            "seats": [{
                "seat": seat,
                "name": run,
                "model": "stub",
                "score": score,
                "steps": 200000,
                "deaths": 1,
            }],
        }), encoding="utf-8")
    parent = promoted_parent(root, "stub", protocol=timed)
    assert parent["seat"] == 1 and parent["score"] == fast["furthest"]["time"]
    ranked = generation_rank(
        [
            {"seat": 0, "name": "slow", "model": "stub", "score": slow["furthest"]["time"]},
            {"seat": 1, "name": "fast", "model": "stub", "score": fast["furthest"]["time"]},
        ],
        slow["furthest"]["time"],
        sense="minimize",
    )
    progress_winner = winner(
        [{"seat": 0, "score": 1}, {"seat": 1, "score": 3}],
        sense="maximize",
    )
    time_winner = winner(
        [
            {"seat": 0, "score": slow["furthest"]["time"]},
            {"seat": 1, "score": fast["furthest"]["time"]},
        ],
        sense="minimize",
    )
    return {
        "searched": True,
        "restored": True,
        "progress_winner": progress_winner["seat"],
        "time_winner": time_winner["seat"],
        "time_rank": ranked[0]["name"],
        "time_delta": ranked[0]["delta"],
        "parent_seat": parent["seat"],
        "fixed": fixed["standing"],
        "general": varied["standing"],
    }


def test_grid_adapter_uses_the_generic_engine(tmp_path):
    report = exercise(tmp_path)
    assert report["searched"] is True and report["restored"] is True
    assert report["progress_winner"] == 1
    assert report["time_winner"] == 1
    assert report["time_rank"] == "fast" and report["time_delta"] == 1
    assert report["parent_seat"] == 1
    assert report["fixed"] == "verified_fixed_state"
    assert report["general"] == "generalized"


def test_grid_adapter_does_not_import_mario():
    root = Path(__file__).resolve().parents[3]
    completed = subprocess.run(
        [sys.executable, "-m", "games.lab.tests.test_synthetic"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
    assert "synthetic-ok" in completed.stdout


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        exercise(Path(tmp))
    forbidden = [
        name for name in sys.modules
        if name == "games.lab.mario"
        or name.startswith("games.lab.mario.")
        or name == "games.lab.integrations.smb_1_1"
        or name.endswith(".smb_1_1")
    ]
    if forbidden:
        raise SystemExit("game modules loaded: " + ", ".join(sorted(forbidden)))
    print("synthetic-ok")
