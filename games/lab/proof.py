"""Milestone 2: one PPO / Nature CNN seat against always-Right, same world, bounded steps."""
from __future__ import annotations

import json
import time
from pathlib import Path

from games.lab.env import make_env
from games.lab.integrations import get
from games.lab.paths import runs_root
from games.lab.roms import store_smb
from games.lab.seats import SEATS
from games.lab.worker import atomic_json, train


def always_right(env, steps: int) -> int:
    index = env.unwrapped.actions.index(("RIGHT",))
    best = 0
    _obs, info = env.reset()
    best = max(best, info.get("x_pos") or 0)
    for _ in range(steps):
        _obs, _reward, terminated, truncated, info = env.step(index)
        best = max(best, info.get("score") or 0)
        if terminated or truncated:
            _obs, info = env.reset()
    return best


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=100_000)
    parser.add_argument("--baseline-steps", type=int, default=2_000)
    parser.add_argument("--seat-dir", default="", help="Resume this seat directory instead of starting a new one")
    args = parser.parse_args()

    rom = store_smb()
    integration = get("smb_1_1")
    baseline_env = make_env("nes", rom, integration)
    try:
        baseline = always_right(baseline_env, args.baseline_steps)
    finally:
        baseline_env.close()

    started = time.time()
    train_env = make_env("nes", rom, integration)
    resume = bool(args.seat_dir)
    seat_dir = Path(args.seat_dir) if resume else runs_root() / time.strftime("proof-%Y%m%dT%H%M%SZ", time.gmtime())
    info = train(train_env, "ppo_cnn", 1, args.steps, seat_dir, {
        "seat": 0, "name": SEATS[0]["name"], "color": SEATS[0]["color"],
        "model": "ppo_cnn", "seed": 1, "objective": "x_pos",
    }, resume=resume)
    report = {
        "model": "ppo_cnn",
        "steps": args.steps,
        "wall_seconds": round(time.time() - started, 1),
        "baseline_x": baseline,
        "best_x": info["score"],
        "flag": info["flag"],
        "rom": str(rom),
        "seat_dir": str(seat_dir),
    }
    atomic_json(Path(seat_dir) / "proof.json", report)
    print(json.dumps(report))
    return 0 if info["score"] > baseline else 1


if __name__ == "__main__":
    raise SystemExit(main())
