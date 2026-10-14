"""Real FCEUmm checks. Skipped when the ROM or the core is not on this machine."""
import hashlib
from pathlib import Path

import pytest

from games.lab.challenge import challenges_root, load_challenge, reached_warp, same_start
from games.lab.roms import SMB_SHA1, pinned_smb


def _ready():
    pytest.importorskip("numpy")
    rom = pinned_smb()
    if rom is None:
        pytest.skip("pinned ROM is missing")
    from games.lab.cores import ensure_core
    core = ensure_core("nes")
    if not core.is_file():
        pytest.skip("fceumm core is missing")
    return rom, core, hashlib.sha1(core.read_bytes()).hexdigest()


def test_saved_states_restore_and_the_jump_repeats():
    rom, core, core_sha1 = _ready()
    from games.lab.actions import BUTTON_ID
    from games.lab.integrations.smb_1_1 import diagnose
    from games.lab.libretro import LibretroRunner
    from games.lab.probe import EmulatorProbe
    root = challenges_root()
    opening_dir = root / "smb-1-1-opening-jump"
    warp_dir = root / "smb-1-2-ceiling-warp"
    if not (opening_dir / "state.bin").is_file() or not (warp_dir / "state.bin").is_file():
        pytest.skip("challenge states are not captured")
    opening, opening_state = load_challenge(opening_dir, rom_sha1=SMB_SHA1, core_sha1=core_sha1)
    warp, warp_state = load_challenge(warp_dir, rom_sha1=SMB_SHA1, core_sha1=core_sha1)
    with pytest.raises(Exception):
        load_challenge(warp_dir, rom_sha1=SMB_SHA1, core_sha1="0" * 40)
    runner = LibretroRunner(core, rom, BUTTON_ID)
    try:
        probe = EmulatorProbe(runner, opening_state, empty_frame=False)
        start = probe.restore()
        assert same_start(opening["start"], start)
        assert start["player_state"] == 8 and start["world"] == 1 and start["stage"] == 1
        import json
        trajectory = json.loads((opening_dir / "search.json").read_text(encoding="utf-8"))["trajectory"]
        first = probe.replay(trajectory)
        second = probe.replay(trajectory)
        goal = int(opening["x_goal"])
        assert first["saw_jump"] and first["x_pos"] >= goal and not first["dead"]
        assert same_start(
            {key: first[key] for key in ("world", "stage", "x_pos", "y_pos", "time", "player_state")},
            second,
        )
        assert first["x_pos"] == second["x_pos"] and first["saw_jump"] == second["saw_jump"]
        warp_probe = EmulatorProbe(runner, warp_state, empty_frame=False)
        landed = warp_probe.restore()
        assert same_start(warp["start"], landed)
        assert landed["world"] == 1 and landed["stage"] == 2 and landed["player_state"] == 8
        assert diagnose(runner.ram_bytes())["physics"] == "ground"
        assert reached_warp(warp["start"], landed) is False
        held = [{"buttons": ["RIGHT"], "frames": 1}]
        one = warp_probe.replay(held)
        two = warp_probe.replay(held)
        assert one["world"] == two["world"] == 1
        assert one["x_pos"] == two["x_pos"]
        assert one["stage"] == two["stage"] == 2
    finally:
        runner.close()
