"""Objective comparison for World 1-1 speed.

Measure the jump button, then train two PPO/CNN runs that differ only by the
reward. Training starts from the title. The pipe savestate and the held-out
states are evaluation starts. This does not resume a lab generation, and it
does not write into historical run folders.

Run with the mario-lab Python 3.12 environment:

    python games/lab/experiments/objective-reward/compare.py --measure-only
    python games/lab/experiments/objective-reward/compare.py --train-only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

REPO = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
ROM = Path(r"C:\Users\Mike\mario-lab\roms\smb.nes")
CHAMPION = Path(r"C:\Users\Mike\mario-runs\20261012T011344Z\seats\0\best.zip")
CHAMPION_SHA = "0d31d9fd5ae3cdab1531f72e33938a584e93f7549061e9de49ed26b2a18cf7ec"
PIPE_STATE = HERE / "state.bin"
RUNS = Path(r"C:\Users\Mike\AppData\Local\Temp\lab-speed-ab")
ARTIFACTS = Path(r"C:\Users\Mike\mario-runs\artifacts\smb-1-1-speed-ab")
STEPS = 16384
EVAL_LIMIT = 800
HELD = ("RIGHT", "A", "B")
RELEASED = ("RIGHT", "B")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _gray(rgb):
    import numpy as np
    from PIL import Image
    image = Image.fromarray(rgb).convert("L").resize((84, 84), Image.BILINEAR)
    return np.asarray(image, dtype=np.uint8)


def _save(path: Path, rgb) -> None:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(path)


def _frame(env):
    return env.unwrapped


def _open(objective: str):
    from games.lab.registry import get
    return get("smb_1_1").open_env(ROM, objective=objective)


def _buttons(index: int) -> tuple:
    from games.lab.integrations.smb_1_1 import SMB_ACTIONS
    return tuple(SMB_ACTIONS[int(index)])


def _diff(left: bytes, right: bytes) -> list[int]:
    return [index for index, (a, b) in enumerate(zip(left, right)) if a != b]


def _snapshot(runner, blob: bytes, buttons: set, frames: int) -> dict:
    from games.lab.integrations.smb_1_1 import describe, diagnose, ram_vector
    runner.unserialize(blob)
    for _ in range(frames):
        runner.frame(set(buttons))
    ram = bytes(runner.ram_bytes())
    rgb = runner.rgb.copy()
    return {
        "ram": ram,
        "rgb": rgb,
        "gray": _gray(rgb),
        "facts": describe(ram),
        "physics": diagnose(ram),
        "vector": ram_vector(ram),
    }


def _reach_pipe(env) -> dict:
    """Hold RIGHT+A+B from the pipe-approach state until x stops at the pipe."""
    frame = _frame(env)
    frame._state = PIPE_STATE.read_bytes()
    _obs, info = env.reset()
    rows = []
    stuck = None
    still = 0
    last_x = None
    for decision in range(1, 81):
        _obs, _reward, terminated, truncated, info = env.step(4)
        x = int(info.get("x_pos") or 0)
        row = {
            "decision": decision,
            "x": x,
            "y": int(info.get("y_pos") or 0),
            "time": int(info.get("time") or 0),
            "dead": bool(info.get("dead")),
            "termination": info.get("termination") or "",
        }
        rows.append(row)
        if last_x is not None and x == last_x:
            still += 1
        else:
            still = 0
        last_x = x
        if stuck is None and x >= 430 and still >= 3 and not info.get("dead"):
            stuck = bytes(frame.runner.serialize())
            _save(HERE / "frames" / "pipe-contact.png", frame.runner.rgb)
            break
        if terminated or truncated:
            break
    if stuck is None:
        raise RuntimeError("the scripted hold did not reach the pipe")
    return {"rows": rows, "state": stuck, "info": rows[-1]}


def _cross(env, stuck: bytes) -> dict:
    """Release A, press it again, and save states that are past the pipe."""
    from games.lab.integrations.smb_1_1 import diagnose
    frame = _frame(env)
    frame._state = stuck
    _obs, info = env.reset()
    rows = []
    on_pipe_x = None
    past = None
    later = None
    for decision in range(1, 121):
        action = 3 if decision <= 3 else 4
        _obs, _reward, terminated, truncated, info = env.step(action)
        physics = diagnose(frame.ram_bytes())
        x = int(info.get("x_pos") or 0)
        y = int(info.get("y_pos") or 0)
        row = {
            "decision": decision,
            "action": list(_buttons(action)),
            "x": x,
            "y": y,
            "time": int(info.get("time") or 0),
            "physics": physics["physics"],
            "y_speed": physics["y_speed"],
            "dead": bool(info.get("dead")),
            "termination": info.get("termination") or "",
            "components": info.get("components"),
        }
        rows.append(row)
        grounded = physics["physics"] == "ground" and not info.get("dead")
        if on_pipe_x is None and grounded and y >= 100 and x >= 450:
            on_pipe_x = x
            _save(HERE / "frames" / "on-pipe.png", frame.runner.rgb)
        if past is None and on_pipe_x is not None and grounded and y <= 90 and x > on_pipe_x + 16:
            past = {
                "bytes": bytes(frame.runner.serialize()),
                "x": x,
                "y": y,
                "decision": decision,
            }
            _save(HERE / "frames" / "past-pipe.png", frame.runner.rgb)
        elif past is not None and later is None and decision >= past["decision"] + 15 and grounded:
            later = {
                "bytes": bytes(frame.runner.serialize()),
                "x": x,
                "y": y,
                "decision": decision,
            }
            _save(HERE / "frames" / "later.png", frame.runner.rgb)
            break
        if terminated or truncated:
            break
    return {"rows": rows, "on_pipe_x": on_pipe_x, "past": past, "later": later}


def _store_state(name: str, blob: bytes, facts: dict) -> dict:
    path = HERE / name
    path.write_bytes(blob)
    return {
        "path": name,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "bytes": len(blob),
        **facts,
    }


def measure() -> dict:
    import numpy as np
    if _sha(CHAMPION) != CHAMPION_SHA:
        raise SystemExit("champion bytes changed; refusing to measure against a different zip")
    if _sha(PIPE_STATE) != "72c3ea8bd337c489e2a0c1adb3253de22457c8617c8162816dfbd25ae014a97e":
        raise SystemExit("pipe-approach state.bin changed")
    env = _open("smb-1-1-speed")
    try:
        reached = _reach_pipe(env)
        stuck = reached["state"]
        runner = _frame(env).runner
        runner.unserialize(stuck)
        before = runner.rgb.copy()
        held = _snapshot(runner, stuck, HELD, 8)
        released = _snapshot(runner, stuck, RELEASED, 8)
        moving_while_held = set(_diff(
            _snapshot(runner, stuck, HELD, 4)["ram"],
            held["ram"],
        ))
        changed = _diff(held["ram"], released["ram"])
        buttonish = [index for index in changed if index not in moving_while_held]
        _save(HERE / "frames" / "edge-held.png", held["rgb"])
        _save(HERE / "frames" / "edge-released.png", released["rgb"])
        _save(HERE / "frames" / "edge-before.png", before)
        gray_mae = float(np.mean(np.abs(held["gray"].astype(np.int16) - released["gray"].astype(np.int16))))
        before_gray = _gray(before)
        edge = {
            "method": (
                "From the stuck pipe savestate, advance 8 emulator frames holding "
                "RIGHT+A+B, and 8 frames holding RIGHT+B. Bytes that also change "
                "between 4 and 8 held frames are treated as ordinary time."
            ),
            "controls_changed": False,
            "actions": 12,
            "pre_decision_image": "the savestate frame. Both choices see it before either button runs.",
            "held": _place(held),
            "released": _place(released),
            "gray_mae": round(gray_mae, 4),
            "gray_max_abs": int(np.max(np.abs(held["gray"].astype(np.int16) - released["gray"].astype(np.int16)))),
            "before_vs_held_gray_mae": round(float(np.mean(np.abs(before_gray.astype(np.int16) - held["gray"].astype(np.int16)))), 4),
            "ram_vector_equal": held["vector"] == released["vector"],
            "ram_vector_held": held["vector"],
            "ram_vector_released": released["vector"],
            "ram_bytes_differ": len(changed),
            "buttonish_addresses": [{"address": index, "held": held["ram"][index], "released": released["ram"][index]} for index in buttonish[:40]],
            "buttonish_count": len(buttonish),
        }
        crossed = _cross(env, stuck)
    finally:
        env.close()
    held_out = []
    if crossed["past"] is not None:
        held_out.append(_store_state("held-out-past-pipe.bin", crossed["past"]["bytes"], {
            "role": "held-out",
            "x": crossed["past"]["x"],
            "y": crossed["past"]["y"],
            "decision_after_release": crossed["past"]["decision"],
        }))
    if crossed["later"] is not None:
        held_out.append(_store_state("held-out-later.bin", crossed["later"]["bytes"], {
            "role": "held-out",
            "x": crossed["later"]["x"],
            "y": crossed["later"]["y"],
            "decision_after_release": crossed["later"]["decision"],
        }))
    payload = {
        "pipe_contact": reached["info"],
        "on_pipe_x": crossed["on_pipe_x"],
        "held_out": held_out,
        "cross_trace": crossed["rows"],
        "action_edge": edge,
        "training_resets": ["title"],
        "evaluation_only": ["state.bin", *[item["path"] for item in held_out]],
    }
    _write(HERE / "action-edge.json", payload)
    print(f"MEASURE on_pipe_x={crossed['on_pipe_x']} held_out={len(held_out)} gray_mae={edge['gray_mae']} buttonish={edge['buttonish_count']}", flush=True)
    return payload


def _place(snap: dict) -> dict:
    facts = snap["facts"]
    physics = snap["physics"]
    return {
        "x": facts.get("x_pos"),
        "y": facts.get("y_pos"),
        "time": facts.get("time"),
        "physics": physics.get("physics"),
        "x_speed": physics.get("x_speed"),
        "y_speed": physics.get("y_speed"),
        "dead": facts.get("dead"),
    }


def _edges(actions: list[list[str]]) -> dict:
    releases = 0
    represses = 0
    previous = False
    for buttons in actions:
        held = "A" in buttons
        if previous and not held:
            releases += 1
        if held and not previous and releases > 0:
            represses += 1
        previous = held
    opening = bool(actions) and "A" in actions[0]
    return {
        "opening_a": opening,
        "releases": releases,
        "represses_after_release": represses,
        "unique": [list(item) for item in dict.fromkeys(tuple(item) for item in actions)],
    }


def _rollout(zip_path: Path, objective: str, state: bytes | None, limit: int) -> dict:
    import numpy as np
    from games.lab.models import registry
    env = _open(objective)
    try:
        model = registry.load("ppo_cnn", str(zip_path), env)
        vec = model.get_env()
        frame = _frame(vec.envs[0])
        if state is not None:
            frame._state = state
        obs = vec.reset()
        info = dict(vec.reset_infos[0] or {})
        actions = []
        start_x = int(info.get("x_pos") or 0)
        max_x = start_x
        saw_release = False
        saw_repress = False
        previous_a = False
        termination = ""
        dead = False
        for _decision in range(limit):
            action, _state = model.predict(obs, deterministic=True)
            action = int(np.asarray(action).reshape(-1)[0])
            buttons = list(_buttons(action))
            held = "A" in buttons
            if previous_a and not held:
                saw_release = True
            if held and not previous_a and saw_release:
                saw_repress = True
            previous_a = held
            actions.append(buttons)
            obs, _rewards, dones, infos = vec.step(np.asarray([action]))
            info = dict(infos[0] or {})
            max_x = max(max_x, int(info.get("x_pos") or 0))
            dead = bool(info.get("dead")) or dead
            if bool(dones[0]):
                termination = str(info.get("termination") or "")
                break
        else:
            termination = str(info.get("termination") or "limit")
        return {
            "objective_env": objective,
            "decisions": len(actions),
            "frames": int(info.get("frames") or (len(actions) * 4)),
            "start_x": start_x,
            "max_x": max_x,
            "gained": max_x - start_x,
            "final_x": int(info.get("x_pos") or 0),
            "final_y": int(info.get("y_pos") or 0),
            "world": info.get("world"),
            "stage": info.get("stage"),
            "dead": dead,
            "termination": termination,
            "components": info.get("components"),
            "flag": bool(info.get("flag_get")),
            "released_a": saw_release,
            "repressed_a": saw_repress,
            "edges": _edges(actions),
            "actions_head": actions[:8],
            "actions_tail": actions[-8:],
        }
    finally:
        env.close()


def _starts(measured: dict) -> list[dict]:
    starts = [
        {"name": "title", "state": None, "role": "training-reset"},
        {"name": "pipe-approach", "state": PIPE_STATE.read_bytes(), "role": "evaluation"},
    ]
    for item in measured.get("held_out") or []:
        starts.append({
            "name": item["path"],
            "state": (HERE / item["path"]).read_bytes(),
            "role": "held-out",
        })
    return starts


def _evaluate(label: str, zip_path: Path, measured: dict) -> dict:
    rows = []
    pipe_x = int(measured.get("on_pipe_x") or 472)
    past_x = 505
    for item in measured.get("held_out") or []:
        if str(item.get("path", "")).endswith("past-pipe.bin"):
            past_x = int(item["x"])
    for start in _starts(measured):
        for objective in ("progress", "smb-1-1-speed"):
            episode = _rollout(zip_path, objective, start["state"], EVAL_LIMIT)
            episode["start"] = start["name"]
            episode["start_role"] = start["role"]
            episode["reached_pipe"] = episode["start_x"] < 434 and episode["max_x"] >= 434
            episode["on_or_over_pipe"] = episode["start_x"] < pipe_x and episode["max_x"] >= pipe_x
            episode["past_pipe"] = episode["start_x"] < past_x and episode["max_x"] >= past_x
            episode["further"] = episode["gained"] >= 32 and episode["max_x"] > max(episode["start_x"], past_x - 1)
            rows.append(episode)
            print(
                f"EVAL {label} {start['name']} {objective} x={episode['max_x']} "
                f"release={episode['released_a']} repress={episode['repressed_a']} "
                f"term={episode['termination']}",
                flush=True,
            )
    return {"zip": str(zip_path), "sha256": _sha(zip_path), "episodes": rows}


def _train(objective: str, seat: Path) -> dict:
    env = os.environ.copy()
    env["LAB_RUNS"] = str(RUNS)
    env["CUDA_VISIBLE_DEVICES"] = "-1"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["PYTHONPATH"] = str(REPO)
    env["OMP_NUM_THREADS"] = "1"
    seat.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "games.lab.worker",
        "--system", "nes",
        "--rom", str(ROM),
        "--integration", "smb_1_1",
        "--model", "ppo_cnn",
        "--seed", "0",
        "--steps", str(STEPS),
        "--seat-dir", str(seat),
        "--seat", "0",
        "--name", "Red",
        "--color", "red",
        "--objective", objective,
        "--bare",
        "--init-from", str(CHAMPION),
    ]
    started = time.perf_counter()
    print(f"TRAIN {objective} steps={STEPS}", flush=True)
    completed = subprocess.run(command, cwd=str(REPO), env=env, check=False)
    elapsed = time.perf_counter() - started
    status_path = seat / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
    return {
        "objective": objective,
        "exit_code": completed.returncode,
        "wall_seconds": round(elapsed, 3),
        "status": status,
        "emulator_frames": int(status.get("steps") or 0) * 4,
    }


def _copy_artifact(source: Path, name: str) -> str:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    dest = ARTIFACTS / name
    if dest.exists():
        dest = ARTIFACTS / f"{dest.stem}-{_sha(source)[:8]}{dest.suffix}"
    if not dest.exists():
        dest.write_bytes(source.read_bytes())
    stamp = source.with_suffix(".stamp.json")
    if stamp.is_file():
        sidecar = dest.with_suffix(".stamp.json")
        if not sidecar.exists():
            sidecar.write_bytes(stamp.read_bytes())
    return str(dest)


def train_and_eval(measured: dict) -> dict:
    from games.lab.integrations.smb_1_1 import INTEGRATION
    from games.lab.objective import explicit_init_allowed
    from games.lab.stamp import read_stamp
    if str(RUNS).startswith(str(Path.home() / "mario-runs")):
        raise SystemExit("refusing to train inside historical runs")
    source = read_stamp(CHAMPION)
    progress_stamp = INTEGRATION.stamp("progress")
    speed_stamp = INTEGRATION.stamp("smb-1-1-speed")
    if not explicit_init_allowed(source, progress_stamp) or not explicit_init_allowed(source, speed_stamp):
        raise SystemExit("champion stamp cannot initialize these objectives")
    if _sha(CHAMPION) != CHAMPION_SHA:
        raise SystemExit("champion bytes changed")
    os.environ["LAB_RUNS"] = str(RUNS)
    config = {
        "steps": STEPS,
        "seed": 0,
        "model": "ppo_cnn",
        "frame_skip": 4,
        "eval_limit_decisions": EVAL_LIMIT,
        "init_sha256": CHAMPION_SHA,
        "init_role": "initialization",
        "init_objective": source.get("objective"),
        "rom": str(ROM),
        "pipe_state_sha256": _sha(PIPE_STATE),
        "held_out": measured.get("held_out"),
        "on_pipe_x": measured.get("on_pipe_x"),
        "device": "cpu",
        "cuda_visible_devices": "-1",
        "bare": True,
        "tapes": False,
        "hints": False,
    }
    _write(HERE / "run-config.json", config)
    runs = {}
    evaluations = {"initialization": _evaluate("initialization", CHAMPION, measured)}
    for objective, folder in (("progress", "progress"), ("smb-1-1-speed", "speed")):
        seat = RUNS / folder / "seats" / "0"
        runs[objective] = _train(objective, seat)
        if runs[objective]["exit_code"] != 0:
            _write(HERE / "comparison.json", {"config": config, "runs": runs, "evaluations": evaluations})
            raise SystemExit(f"training failed for {objective}")
        checkpoint = seat / "checkpoint.zip"
        best = seat / "best.zip"
        evaluations[objective] = {
            "final": _evaluate(f"{objective}-final", checkpoint, measured),
        }
        evaluations[objective]["artifact"] = _copy_artifact(checkpoint, f"{folder}-final.zip")
        if best.is_file() and _sha(best) != _sha(checkpoint):
            evaluations[objective]["best_x"] = _evaluate(f"{objective}-best", best, measured)
            evaluations[objective]["best_artifact"] = _copy_artifact(best, f"{folder}-best.zip")
    payload = {"config": config, "runs": runs, "evaluations": evaluations}
    _write(HERE / "comparison.json", payload)
    print("DONE comparison", flush=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measure-only", action="store_true")
    parser.add_argument("--train-only", action="store_true")
    args = parser.parse_args()
    if not ROM.is_file():
        raise SystemExit(f"missing rom {ROM}")
    measured = None
    edge_path = HERE / "action-edge.json"
    if args.train_only:
        if not edge_path.is_file():
            raise SystemExit("measure first")
        measured = json.loads(edge_path.read_text(encoding="utf-8"))
    else:
        measured = measure()
    if args.measure_only:
        print("DONE measure", flush=True)
        return 0
    train_and_eval(measured)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"FAILED {exc}", flush=True)
        raise
