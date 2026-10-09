"""Milestone 1: a thousand steps of Super Mario Bros., and no ROM in git."""
from __future__ import annotations

import json

from games.lab.env import make_env
from games.lab.integrations import get
from games.lab.paths import assert_outside_repo
from games.lab.roms import git_tracks_games, store_smb


def main() -> int:
    tracked = git_tracks_games()
    if tracked:
        print(json.dumps({"error": "git already tracks game files", "lines": tracked}))
        return 1
    rom = store_smb()
    assert_outside_repo(rom)
    env = make_env("nes", rom, get("smb_1_1"))
    try:
        _obs, info = env.reset()
        steps = 0
        for _ in range(1000):
            _obs, _reward, terminated, truncated, info = env.step(int(env.action_space.sample()))
            steps += 1
            if terminated or truncated:
                _obs, info = env.reset()
        ram = len(env.unwrapped.ram_bytes())
    finally:
        env.close()
    tracked = git_tracks_games()
    report = {"steps": steps, "x_pos": info.get("x_pos"), "ram_bytes": ram, "rom": str(rom), "git": tracked}
    print(json.dumps(report))
    if steps != 1000 or "x_pos" not in info or tracked or ram < 2048:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
