"""Milestone 3: each pixel model can take a few updates. RAM is included on Mario."""
from __future__ import annotations

import json

from games.lab.env import make_env
from games.lab.integrations import get
from games.lab.models import registry
from games.lab.paths import runs_root
from games.lab.roms import store_smb
from games.lab.worker import train
import time


def main() -> int:
    rom = store_smb()
    integration = get("smb_1_1")
    reports = []
    for model_id in registry.ids():
        env = make_env("nes", rom, integration)
        seat = runs_root() / "model-smoke" / model_id
        started = time.time()
        info = train(env, model_id, 1, 512, seat, {
            "seat": 0, "name": model_id, "color": "#888", "model": model_id,
            "seed": 1, "objective": "x_pos",
        }, resume=False)
        reports.append({"model": model_id, "steps": info["steps"], "seconds": round(time.time() - started, 1)})
        print(json.dumps(reports[-1]), flush=True)
    missing = [row for row in reports if row["steps"] < 512]
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
