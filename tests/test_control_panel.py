import importlib.util
from pathlib import Path

import pytest

import ai_setup

CABINET = Path(__file__).resolve().parents[1] / "pi" / "cabinet" / "cabinet.py"


def load_cabinet():
    spec = importlib.util.spec_from_file_location("cabinet", CABINET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RC = "/opt/retropie/supplementary/runcommand/runcommand.sh"
PROCS = {
    1: (0, ["/sbin/init"]),
    100: (1, ["/bin/sh", "/opt/retropie/supplementary/emulationstation/emulationstation.sh"]),
    101: (100, ["/opt/retropie/supplementary/emulationstation/emulationstation"]),
    200: (101, ["sh", "-c", f"{RC} 0 _SYS_ arcade /home/pi/RetroPie/roms/arcade/missile.zip"]),
    201: (200, ["bash", RC, "0", "_SYS_", "arcade", "/home/pi/RetroPie/roms/arcade/missile.zip"]),
    202: (201, ["bash", "-c", "retroarch ..."]),
    203: (202, ["/opt/retropie/emulators/retroarch/bin/retroarch", "-L", "core.so"]),
    300: (1, ["mame", "pacman", "-autoboot_script", "/home/pi/ai-arcade/autoboot.lua"]),
}


def test_a_game_from_the_menu_is_found_with_its_system_and_rom():
    cabinet = load_cabinet()
    assert cabinet.runcommands(PROCS) == [(201, "arcade", "/home/pi/RetroPie/roms/arcade/missile.zip")]


def test_stopping_a_game_ends_its_emulator_not_the_menu():
    cabinet = load_cabinet()
    assert cabinet.descendants(PROCS, 201) == [203, 202]  # deepest first; runcommand itself returns on its own
    assert 101 not in cabinet.descendants(PROCS, 201)


def test_ai_modes_mame_is_told_apart_from_a_persons():
    cabinet = load_cabinet()
    assert cabinet.ai_mame(PROCS) == (300, "pacman")
    assert cabinet.ai_mame({k: v for k, v in PROCS.items() if k != 300}) is None


def test_launch_refuses_anything_outside_the_systems_rom_folder(tmp_path, monkeypatch):
    cabinet = load_cabinet()
    roms = tmp_path / "arcade"
    roms.mkdir()
    (roms / "pacman.zip").write_bytes(b"")
    monkeypatch.setattr(cabinet, "systems", lambda: [{"name": "arcade", "path": str(roms), "extensions": [".zip"]}])
    monkeypatch.setattr(cabinet, "end_games", lambda: (_ for _ in ()).throw(AssertionError("must not get this far")))
    for system, rom in (("nes", str(roms / "pacman.zip")), ("arcade", "/etc/passwd"),
                        ("arcade", str(roms / ".." / "arcade" / ".." / "x.zip")), ("arcade", str(roms / "none.zip"))):
        with pytest.raises(SystemExit):
            cabinet.launch(system, rom)


def test_the_ai_setup_is_read_from_the_game_package():
    s = ai_setup.schema("arcade/pacman")
    assert [k["value"] for k in s["knowledge"]][1:] == ["L0", "L1", "L2", "L3a", "L3b"]
    assert s["orders_example"] and s["goals"][0]["value"] == "auto"
    kinds = {f["name"]: f["kind"] for f in s["switches"]}
    assert kinds["reflex"] == "override" and kinds["park"] == "skill"
    assert set(ai_setup.ai_games()) >= {"arcade/pacman", "arcade/mspacman"}
    assert "arcade/bzone" not in ai_setup.ai_games()  # in the workshop: a profile and a RAM map, no player yet


def test_answers_become_plays_command_line():
    args = ai_setup.command_line("arcade/pacman", {
        "decider": "ollama", "model": "nimble", "knowledge": "L2", "goal": "auto", "strategist": "code", "games": 2,
        "orders": ["-starts with a dash", " "], "switches": {"reflex": False, "park": True, "chain_depth": 3}})
    assert args[:2] == ["--game", "arcade/pacman"]
    assert "--orders=-starts with a dash" in args and args.count("--games") == 1
    assert "--no-reflex" in args and "--park" in args and "--chain=3" in args


@pytest.mark.parametrize("answers", [
    {"decider": "nobody"},
    {"knowledge": "L9"},
    {"goal": "win"},
    {"goal": "clear_dots", "strategist": "ollama"},
    {"games": 0},
    {"switches": {"late": "never"}},
])
def test_answers_the_setup_does_not_offer_are_refused(answers):
    with pytest.raises(ValueError):
        ai_setup.command_line("arcade/pacman", answers)


@pytest.mark.parametrize("value", ["0.1", "1.5", "fast"])
def test_the_game_speed_stays_between_a_fifth_and_full(value):
    cabinet = load_cabinet()
    with pytest.raises((SystemExit, ValueError)):
        cabinet.main(["cabinet.py", "speed", value])


def test_the_setup_offers_the_speed_and_refuses_one_outside_it():
    s = ai_setup.schema("arcade/pacman")["speed"]
    assert s["default"] == 0.85 and s["min"] < s["default"] <= s["max"] == 1.0
