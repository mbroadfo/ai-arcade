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
    assert ai_setup.ai_games()["arcade/bzone"]["kind"] == "lab"  # no model player yet: its lab of code policies
    assert ai_setup.ai_games()["arcade/pacman"]["kind"] == "model"


def test_a_lab_game_offers_its_policies_and_rate():
    s = ai_setup.schema("arcade/bzone")
    assert s["kind"] == "lab" and "track_and_fire" in [p["value"] for p in s["policies"]]
    args = ai_setup.command_line("arcade/bzone", {"policy": "turn_toward", "hz": 5, "seconds": 120})
    assert args == ["--game", "arcade/bzone", "--policy", "turn_toward", "--hz", "5", "--seconds", "120"]
    with pytest.raises(ValueError):
        ai_setup.command_line("arcade/bzone", {"policy": "cheat"})
    with pytest.raises(ValueError):
        ai_setup.command_line("arcade/bzone", {"hz": 500})


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


def test_a_lab_setup_leads_with_the_run_type_and_the_baselines():
    s = ai_setup.schema("arcade/bzone")
    assert [t["value"] for t in s["run_types"]] == ["manual", "lab", "ai"] and not s["run_types"][2]["disabled"]
    args = ai_setup.command_line("arcade/bzone", {"runtype": "ai"})  # by default the model drives
    assert args[args.index("--policy") + 1] == "pilot" and args[args.index("--model") + 1] == "nimble"
    args = ai_setup.command_line("arcade/bzone", {"runtype": "ai", "ai_mode": "tactics", "model": "nimble"})
    assert args[args.index("--policy") + 1] == "s1m" and args[args.index("--model") + 1] == "nimble"
    assert s["groups"][0] == "Targeting baselines" and {p["group"] for p in s["policies"]} == set(s["groups"])
    baseline = next(p for p in s["policies"] if p["value"] == "track_and_fire")
    assert baseline["tag"] == "baseline" and baseline["limitation"] and s["measures"]


class FakeRunner:
    """Stands in for ai_runner.Runner: a run lasts until `finish()` is called; every start is recorded."""

    def __init__(self):
        self.state, self.started, self.running = {"state": "idle"}, [], False

    def busy(self):
        return self.running

    def start(self, game, args, speed, script):
        self.started.append((game, script))
        self.running, self.state = True, {"state": "running", "game": game}

    def stop(self):
        self.running = False
        self.state = {"state": "ended"}
        return True

    def finish(self):
        self.running, self.state = False, {"state": "ended"}


def make_control(monkeypatch):
    import time
    import observatory
    from types import SimpleNamespace
    hub = observatory.Hub()
    control = observatory.Control.__new__(observatory.Control)
    control.hub, control.host, control.last = hub, "test", None
    control.auto, control.auto_token = {"on": False}, 0
    control.runner = FakeRunner()
    control.cabinet = SimpleNamespace(clear=lambda: None)
    monkeypatch.setattr(time, "sleep", lambda s: __import__("threading").Event().wait(0.01))
    return control


def wait_for(check, seconds=5):
    import time
    end = time.time() + seconds
    while time.time() < end:
        if check():
            return True
        time.sleep(0.02)
    return False


def test_autoplay_plays_each_game_in_turn_and_stops_when_a_person_chooses(monkeypatch):
    control = make_control(monkeypatch)
    state = control.autoplay(True, minutes=5)
    assert state["on"] and set(state["games"]) >= {"arcade/pacman", "arcade/mspacman", "arcade/bzone"}
    assert wait_for(lambda: len(control.runner.started) == 1)
    first = control.runner.started[0][0]
    control.runner.finish()  # that game ends: the next one starts
    assert wait_for(lambda: len(control.runner.started) == 2)
    assert control.runner.started[1][0] != first
    assert control.hub.panels["control"]["autoplay"]["on"]
    control.stop()  # a person pressing STOP wins
    assert not control.auto["on"] and not control.hub.panels["control"]["autoplay"]["on"]
    count = len(control.runner.started)
    control.runner.finish()
    assert not wait_for(lambda: len(control.runner.started) > count, seconds=0.5)


def test_autoplay_gives_way_to_a_person_playing_on_the_cabinet(monkeypatch):
    control = make_control(monkeypatch)
    control.hub.set_panel("cabinet", {"mode": "human"})
    control.autoplay(True)
    assert wait_for(lambda: not control.auto["on"])
    assert control.runner.started == [] and "Someone started playing" in control.auto["note"]


def test_autoplay_refuses_a_silly_time(monkeypatch):
    control = make_control(monkeypatch)
    with pytest.raises(ValueError):
        control.autoplay(True, minutes=0)
