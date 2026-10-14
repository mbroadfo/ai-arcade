"""Catalog grades, Mario RAM, ranking, and what a finished round keeps. No ROM and no torch."""
import json

import pytest

from games.lab.catalog import games_from, load_path
from games.lab.integrations.smb_1_1 import (
    DEATH_PENALTY,
    FULL_CLOCK,
    SMB_ACTIONS,
    CLEAR_X,
    STAGE_SPAN,
    STALL_PENALTY,
    describe,
    diagnose,
    note_clear,
    progress,
    ram_vector,
    skip_title,
    step_reward,
)
from games.lab.stamp import write_stamp
from games.lab.lineage import champion, collapsed_history, seats_for_generation
from games.lab.models import registry
from games.lab.paths import REPO_ROOT, chain_followup, pause_requested, stop_requested
from games.lab.supervisor import _budget_met, resume_chain
from games.lab.publish import finalize
from games.lab.ranking import winner
from games.lab.mario.rom import SMB_SHA1, SMB_SHA256, accept_smb, pinned_smb
from games.lab.roms import RomRejected
from games.lab.worker import main as worker_main
from games.lab.worker import train


def _game(system, name, filename):
    return {"name": name, "path": f"/home/pi/RetroPie/roms/{system}/{filename}", "type": "game",
            "source_system": system}


def _catalog():
    return {"systems": [
        {"name": "nes", "is_game_system": True, "entries": [
            _game("nes", "Legend Of Zelda, The", "Legend of Zelda, The (USA) (Rev A).zip"),
            _game("nes", "Legend of Zelda, The (USA) (Rev A)", "Legend of Zelda, The (USA) (Rev A).nes"),
            _game("nes", "Super Mario Bros.", "Super Mario Bros. (Japan, USA).zip"),
            _game("nes", "Wrecking Crew", "Wrecking Crew (World).zip"),
        ]},
        {"name": "atari2600", "entries": [
            _game("atari2600", "Yars' Revenge", "Yar's Revenge.zip"),
        ]},
        {"name": "sega32x", "entries": [
            _game("sega32x", "Sonic the Hedgehog", "Sonic the Hedgehog.bin"),
            _game("sega32x", "Sonic The Hedgehog", "Sonic the Hedgehog.zip"),
        ]},
        {"name": "arcade", "entries": [_game("arcade", "Amidar", "amidar.zip")]},
        {"name": "ports", "entries": [_game("ports", "Quake", "Quake.sh")]},
        {"name": "trs-80", "entries": [_game("trs-80", "timetrk1", "timetrk1.cmd")]},
        {"name": "zmachine", "entries": [_game("zmachine", "zork1", "zork1.dat")]},
        {"name": "retropie", "is_game_system": False, "entries": [
            _game("retropie", "Configuration Editor", "configedit.rp"),
        ]},
    ]}


def test_grades_and_dedupes():
    games = {game.id: game for game in games_from(_catalog())}
    assert games["nes/super-mario-bros-japan-usa"].grade == "scored"
    assert games["nes/super-mario-bros-japan-usa"].integration == "smb_1_1"
    assert games["nes/super-mario-bros-japan-usa"].path.endswith(".zip")
    zelda = [game for game in games.values() if "zelda" in game.id and "ii" not in game.id]
    assert len(zelda) == 1
    assert zelda[0].path.endswith(".nes")
    assert zelda[0].grade == "bootable"
    assert games["nes/wrecking-crew-world"].grade == "bootable"
    assert games["atari2600/yar-s-revenge"].grade == "bootable"
    sonic = [game for game in games.values() if game.system == "sega32x"]
    assert len(sonic) == 1 and sonic[0].grade == "unavailable" and "Picodrive" in sonic[0].reason
    assert "MAME" in games["arcade/amidar"].reason
    assert games["ports/quake"].grade == "unavailable"
    assert games["trs-80/timetrk1"].grade == "unavailable"
    assert "observatory" in games["zmachine/zork1"].reason
    assert games["retropie/configedit"].grade == "unavailable"
    assert games["arcade/amidar"].selectable is False
    assert games["nes/wrecking-crew-world"].selectable is True


def test_cached_cabinet_catalog_if_present():
    folder = REPO_ROOT / ".manifests" / "es-catalog"
    files = sorted(folder.glob("*.json")) if folder.is_dir() else []
    if not files:
        pytest.skip("no local ES catalog")
    games = load_path(files[-1])
    scored = [game for game in games if game.grade == "scored"]
    assert [game.id for game in scored] == ["nes/super-mario-bros-japan-usa"]
    assert any(game.id == "nes/wrecking-crew-world" and game.grade == "bootable" for game in games)
    assert any(game.system == "atari2600" and game.grade == "bootable" for game in games)
    assert any(game.system == "arcade" and game.grade == "unavailable" for game in games)
    stems = [(game.system, game.path.rsplit("/", 1)[-1].rsplit(".", 1)[0].casefold()) for game in games]
    assert len(stems) == len(set(stems))


def test_smb_ram_facts():
    ram = bytearray(2048)
    ram[0x006D] = 1
    ram[0x0086] = 10
    ram[0x07F8] = 4
    facts = describe(bytes(ram))
    assert facts["x_pos"] == 266 and facts["time"] == 400 and facts["flag_get"] is False
    ram[0x000E] = 0x0B
    assert describe(bytes(ram))["dying"] is True
    ram[0x000E] = 0x08
    ram[0x0016] = 0x31
    ram[0x001D] = 3
    assert describe(bytes(ram))["flag_get"] is True
    assert len(ram_vector(bytes(ram))) == 9
    assert ("DOWN",) in SMB_ACTIONS and ("UP",) in SMB_ACTIONS


def test_later_level_beats_the_flag_and_death_is_a_loss():
    flag = {"world": 1, "stage": 1, "x_pos": 3161, "time": 400, "flag_get": True, "dead": False, "dying": False, "game_over": False}
    assert progress(flag) == 3161
    next_level = {"world": 1, "stage": 2, "x_pos": 0, "time": 400, "flag_get": False, "dead": False, "dying": False, "game_over": False}
    assert progress(next_level) == STAGE_SPAN
    reward, high, dead = step_reward(3161, next_level, True)
    gain = STAGE_SPAN - 3161
    assert dead is False and high == STAGE_SPAN and reward == gain * (1 + 400 / FULL_CLOCK)
    # The clear sequence counts the timer down while the flag is still set.
    clearing = {**flag, "time": 0}
    reward, high, dead = step_reward(3161, clearing, True)
    assert dead is False and reward == 0 and high == 3161
    timeout = {**flag, "time": 0, "flag_get": False, "x_pos": 200}
    reward, high, dead = step_reward(200, timeout, True)
    assert dead is True and reward == -DEATH_PENALTY and high == 200
    warp = {"world": 4, "stage": 1, "x_pos": 40, "time": 400, "flag_get": False, "dead": False, "dying": False, "game_over": False}
    assert progress(warp) > progress(next_level)
    # The flag object is gone and the timer has hit 0, but Mario is still walking into the castle.
    state = note_clear(None, flag)
    assert state["cleared"] is True
    castle = {**flag, "time": 0, "flag_get": False, "x_pos": 3266, "dying": True, "player_state": 0x08}
    state = note_clear(state, castle)
    assert state["cleared"] is True
    reward, high, dead = step_reward(3266, castle, True, state["cleared"])
    assert dead is False and high == 3266 and reward == 0
    state = note_clear(state, next_level)
    assert state["cleared"] is False
    reward, high, dead = step_reward(3266, next_level, True, state["cleared"])
    assert dead is False and high == STAGE_SPAN
    # The level number ticks up while Mario is still at the castle.
    bump = {**castle, "world": 1, "stage": 2, "x_pos": CLEAR_X}
    latch = note_clear(None, flag)
    latch = note_clear(latch, castle)
    latch = note_clear(latch, bump)
    assert latch["cleared"] is True
    reward, high, dead = step_reward(CLEAR_X, bump, True, True, latch["at"])
    assert dead is False and high == CLEAR_X and reward == 0
    latch = note_clear(latch, {**bump, "time": 400})
    assert latch["cleared"] is True
    _, high, dead = step_reward(CLEAR_X, {**bump, "time": 400}, True, True, latch["at"])
    assert dead is False and high == CLEAR_X
    opened = {**next_level, "x_pos": 120}
    assert note_clear(latch, opened)["cleared"] is False
    _, high, dead = step_reward(CLEAR_X, opened, True, False)
    assert dead is False and high == STAGE_SPAN + 120
    crushed = {**castle, "player_state": 0x0B}
    assert step_reward(3266, crushed, True, True)[2] is True
    # The card score stays the position. A full clock doubles a gain. Half clock is 1.5x.
    moving = {"world": 1, "stage": 1, "x_pos": 100, "time": FULL_CLOCK, "flag_get": False, "dead": False, "dying": False, "game_over": False}
    reward, high, dead = step_reward(80, moving, True)
    assert dead is False and high == 100 and reward == 40
    late_reward, late_high, late_dead = step_reward(80, {**moving, "time": 200}, True)
    assert late_dead is False and late_high == 100 and late_reward == 30 and late_reward < reward
    # Standing still costs one demerit. The flag, the clear, and a death do not add it.
    stall_reward, stall_high, stall_dead = step_reward(80, {**moving, "x_pos": 80}, True)
    assert stall_dead is False and stall_high == 80 and stall_reward == -STALL_PENALTY
    assert step_reward(3161, clearing, True)[0] == 0
    assert step_reward(3266, castle, True, True)[0] == 0
    assert step_reward(200, timeout, True)[0] == -DEATH_PENALTY


def test_skip_title_stops_once_the_clock_runs():
    class Fake:
        def __init__(self):
            self.ram = bytearray(2048)
            self.n = 0
            self.pressed = False

        def frame(self, buttons):
            self.n += 1
            if "START" in buttons:
                self.pressed = True
            if self.n >= 6:
                self.ram[0x07F8] = 4
                self.ram[0x000E] = 0x08
            if self.n > 10:
                self.ram[0x07F8] = 3
                self.ram[0x07F9] = 9
                self.ram[0x07FA] = 9

        def ram_bytes(self):
            return bytes(self.ram)

        def poke(self, address, value):
            self.ram[address] = value

    fake = Fake()
    skip_title(fake)
    assert fake.pressed and fake.n < 80


def test_farther_right_wins_and_ties_prefer_the_lower_seat():
    rows = [
        {"seat": 0, "score": 3000, "flag": False},
        {"seat": 1, "score": 100, "flag": True},
        {"seat": 2, "score": 100, "flag": True},
    ]
    assert winner(rows, sense="maximize")["seat"] == 0
    assert winner([{"seat": 3, "score": 10, "flag": False}, {"seat": 1, "score": 10, "flag": False}], sense="maximize")["seat"] == 1


def test_finalize_drops_thumbnails_and_keeps_the_video(tmp_path):
    seat = tmp_path / "seats" / "0"
    seat.mkdir(parents=True)
    (seat / "latest.jpg").write_bytes(b"jpeg")
    (seat / "checkpoint.zip").write_bytes(b"zip")
    (seat / "best.gif").write_bytes(b"gif")
    (seat / "best.zip").write_bytes(b"best")
    (tmp_path / "best.mp4").write_bytes(b"video")
    (tmp_path / "results.json").write_text("{}", encoding="utf-8")
    removed = finalize(tmp_path)
    assert [path.name for path in removed] == ["latest.jpg"]
    assert (tmp_path / "best.mp4").is_file()
    assert (seat / "checkpoint.zip").is_file()
    assert (seat / "best.gif").is_file()
    assert (seat / "best.zip").is_file()
    assert not (seat / "latest.jpg").exists()


def test_pinned_smb_skips_a_file_that_is_not_the_world_rom(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    (tmp_path / "roms").mkdir()
    (tmp_path / "roms" / "smb.nes").write_bytes(b"NES\x1a" + b"\x00" * 32)
    assert pinned_smb() is None


def test_rom_pin_rejects_anything_else():
    assert SMB_SHA1 == "ea343f4e445a9050d4b4fbac2c77d0693b1d0922"
    assert len(SMB_SHA256) == 64
    with pytest.raises(RomRejected):
        accept_smb(b"NES\x1a" + b"\x00" * 32)


def test_registry_lists_the_menu_and_ram_refuses_a_bootable_game():
    assert registry.ids() == [
        "ppo_cnn", "ppo_cnn_explore", "ppo_cnn_steady", "ppo_lstm", "dqn_cnn", "ppo_ram",
    ]
    registry.check("ppo_cnn", None)
    with pytest.raises(ValueError):
        registry.check("ppo_ram", None)


def test_default_lineup_is_six_different_models():
    from games.lab.models.ppo_cnn import ENT_COEF as standard
    from games.lab.models.ppo_cnn_explore import ENT_COEF as explore
    from games.lab.models.ppo_cnn_steady import ENT_COEF as steady
    from games.lab.seats import DEFAULT_MODELS, default_seat_specs

    class _Scored:
        capabilities = {"ram": True}

        def ram_vector(self, _ram):
            return ()

    specs = default_seat_specs()
    assert [spec["model"] for spec in specs] == list(DEFAULT_MODELS)
    assert len(set(DEFAULT_MODELS)) == 6
    assert [spec["seed"] for spec in specs] == [1, 2, 3, 4, 5, 6]
    for model_id in DEFAULT_MODELS:
        registry.check(model_id, _Scored())
    assert standard == 0.01 and explore == 0.05 and steady == 0.001


def test_alive_check_leaves_the_process_running():
    import subprocess
    import sys
    import time

    from games.lab.supervisor import _alive

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        time.sleep(0.3)
        assert proc.poll() is None
        assert _alive(proc.pid)
        time.sleep(0.3)
        assert proc.poll() is None
    finally:
        proc.kill()
        proc.wait(timeout=5)
    assert _alive(proc.pid) is False


def test_page_mentions_six_seats():
    text = (REPO_ROOT / "games" / "lab" / "static" / "index.html").read_text(encoding="utf-8")
    assert "Training Lab" in text and "Hall of fame" in text and "Bootable only" in text
    assert "Best so far" in text and ">Stop<" in text
    assert "/replay/" not in text
    assert "showWinner" not in text
    assert "repeat(3, minmax(0, 1fr))" in text
    assert "defaultModels" in text and "openModel" in text
    assert "practice the best run" in text
    assert "Training record." in text and "Challenges" in text
    challenge = (REPO_ROOT / "games" / "lab" / "static" / "challenge.html").read_text(encoding="utf-8")
    assert "Independent" in challenge and "Searched" in challenge and "success rate" in challenge
    assert "This generation" in text and "Networks" in text and "Hints" in text
    assert "window.open" in text and "/watch/" in text
    watch = (REPO_ROOT / "games" / "lab" / "static" / "watch.html").read_text(encoding="utf-8")
    assert "Full speed" in watch and "Training keeps going" in watch


def _seat(seat, name, score, steps, deaths):
    return {
        "seat": seat, "name": name, "model": "ppo_cnn", "score": score,
        "deaths": deaths, "steps": steps, "episodes": deaths,
    }


def test_history_collapses_identical_rounds_and_skips_short_ones():
    full = {
        "id": "a", "game": "Super Mario Bros.", "objective": "x_pos", "winner": 0,
        "seats": [_seat(0, "Red", 1950, 200192, 1189), _seat(1, "Green", 1631, 200192, 1376)],
    }
    again = {**full, "id": "b"}
    short = {
        "id": "c", "winner": 5, "game": "Super Mario Bros.", "objective": "x_pos",
        "seats": [_seat(5, "White", 10, 512, 1)],
    }
    better = {
        "id": "d", "winner": 3, "game": "Super Mario Bros.", "objective": "x_pos",
        "seats": [_seat(0, "Red", 1900, 200000, 100), _seat(3, "Gold", 2100, 200000, 80)],
    }
    rows = collapsed_history([better, again, short, full])
    assert [row["id"] for row in rows] == ["a", "d"]
    assert rows[0]["winner_name"] == "Red" and rows[0]["delta"] is None and rows[0]["generation"] == 0
    assert rows[0]["record"] == "training"
    assert rows[1]["winner_name"] == "Gold" and rows[1]["score"] == 2100 and rows[1]["delta"] == 150


def test_generation_seeds_move_by_six():
    seats = [{"model": "ppo_cnn", "seed": 1}, {"model": "ppo_cnn", "seed": 6}]
    assert [seat["seed"] for seat in seats_for_generation(seats, 0)] == [1, 6]
    assert [seat["seed"] for seat in seats_for_generation(seats, 2)] == [13, 18]


def test_champion_is_the_highest_long_run_with_a_zip(tmp_path):
    def write(run, seat, score, steps, payload):
        folder = tmp_path / run / "seats" / str(seat)
        folder.mkdir(parents=True)
        if payload is not None:
            (folder / "best.zip").write_bytes(payload)
        (tmp_path / run / "results.json").write_text(json.dumps({
            "winner": seat,
            "seats": [{"seat": seat, "name": "Red", "model": "ppo_cnn", "score": score, "steps": steps, "deaths": 1}],
        }), encoding="utf-8")

    write("old", 0, 1950, 200000, b"best")
    write("short", 0, 9999, 256, b"nope")
    write("missing", 0, 3000, 200000, None)
    write("tie", 1, 1950, 200000, b"other")
    found = champion(tmp_path, "ppo_cnn", sense="maximize")
    assert found["score"] == 1950 and found["seat"] == 0
    assert found["path"].parent.name == "0"
    current = {"actions": [["RIGHT"]], "objective": "progress", "ram": 9}
    assert champion(tmp_path, "ppo_cnn", current, sense="maximize") is None
    kept = tmp_path / "tie" / "seats" / "1" / "best.zip"
    write_stamp(kept, current)
    stamped = champion(tmp_path, "ppo_cnn", current, sense="maximize")
    assert stamped["score"] == 1950 and stamped["path"] == kept


def test_seed_from_and_resume_are_exclusive(tmp_path):
    with pytest.raises(ValueError):
        train(None, "ppo_cnn", 1, 10, tmp_path, {}, True, seed_from=tmp_path / "seed.zip")


def test_resume_without_a_checkpoint_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        train(None, "ppo_cnn", 1, 10, tmp_path, {}, True)


def test_missing_seed_zip_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        train(None, "ppo_cnn", 1, 10, tmp_path, {}, False, seed_from=tmp_path / "missing.zip")


def test_stop_file_is_visible(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_RUNS", str(tmp_path))
    assert stop_requested() is False
    (tmp_path / "stop.request").write_text("stop\n", encoding="utf-8")
    assert stop_requested() is True
    assert pause_requested() is False


def test_pause_leaves_the_generation_and_stop_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_RUNS", str(tmp_path))
    assert chain_followup(False, False) == "continue"
    assert chain_followup(False, True) == "pause"
    assert chain_followup(True, True) == "stop"
    (tmp_path / "pause.request").write_text("pause\n", encoding="utf-8")
    assert pause_requested() is True
    code = worker_main([
        "--system", "nes",
        "--rom", str(tmp_path / "missing.nes"),
        "--model", "ppo_cnn",
        "--seed", "1",
        "--steps", "256",
        "--seat-dir", str(tmp_path / "seat"),
        "--seat", "0",
        "--name", "Red",
        "--color", "#d64545",
        "--objective", "progress",
    ])
    assert code == 0
    assert not (tmp_path / "seat").exists()


def test_paused_seat_still_owes_the_rest_of_its_budget(tmp_path):
    seat = tmp_path / "seats" / "0"
    seat.mkdir(parents=True)
    (seat / "status.json").write_text(json.dumps({"steps": 50000, "finished": True}), encoding="utf-8")
    assert _budget_met(seat, 200000) is False
    (seat / "status.json").write_text(json.dumps({"steps": 200192, "finished": True}), encoding="utf-8")
    assert _budget_met(seat, 200000) is True


def test_resume_without_a_pause_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_RUNS", str(tmp_path))
    with pytest.raises(RuntimeError):
        resume_chain()


def test_shared_run_replays_the_best_prefix_and_can_enter_1_2(tmp_path):
    from games.lab.tape import (
        Route,
        applied_action,
        best_saved,
        compatible,
        make_tape,
        peak_prefix,
        publish,
        seed_run,
        shield_reward,
        write_tape,
    )
    actions = [1, 2, 3, 4, 5]
    # The presses after the high-water mark are the death. They stay out of the run.
    assert peak_prefix(actions, [10, 50, 3161, 3161, 100]) == [1, 2, 3]
    # Entering 1-2 scores STAGE_SPAN, above the flag, so the run keeps those presses.
    assert peak_prefix(actions, [10, 3161, STAGE_SPAN, STAGE_SPAN + 40, STAGE_SPAN + 40]) == [1, 2, 3, 4]
    # A later world stays in the run up to the furthest step. The repeated score is the death.
    assert peak_prefix(
        [1, 2, 3, 4, 5, 6],
        [3161, CLEAR_X, STAGE_SPAN + 40, STAGE_SPAN + 200, 2 * STAGE_SPAN + 15, 2 * STAGE_SPAN + 15],
    ) == [1, 2, 3, 4, 5]

    flag = make_tape([1, 2], 3161, 1, 1, 0, "Red", 12, "progress")
    shared = tmp_path / "best.tape.json"
    assert publish(shared, flag) is True
    assert publish(shared, {**flag, "score": 3161, "actions": [0, 1]}) is False
    assert publish(shared, {**flag, "score": 90, "actions": [0]}) is False
    into_1_2 = make_tape([1, 2, 11], STAGE_SPAN, 1, 2, 2, "Blue", 12, "progress")
    assert publish(shared, into_1_2) is True
    saved = json.loads(shared.read_text(encoding="utf-8"))
    assert saved["score"] == STAGE_SPAN and saved["world"] == 1 and saved["stage"] == 2
    assert saved["actions"] == [1, 2, 11]

    assert applied_action(saved, 0, 9, 12, "progress") == (1, True)
    assert applied_action(saved, 1, 9, 12, "progress") == (2, True)
    assert applied_action(saved, 3, 9, 12, "progress") == (9, False)
    old_pad = {**saved, "n_actions": 7}
    assert compatible(old_pad, 12, "progress") is False
    assert applied_action(old_pad, 0, 9, 12, "progress") == (9, False)
    assert applied_action(saved, 0, 9, 12, "steps") == (9, False)

    matched = [8.0]
    shield_reward(matched, [1], {"forced": True, "applied_action": 1}, True)
    assert matched == [8.0]
    missed = [STAGE_SPAN - 3161]
    shield_reward(missed, [4], {"forced": True, "applied_action": 1}, True)
    assert missed == [0.0]
    dqn = [STAGE_SPAN - 3161]
    shield_reward(dqn, [4], {"forced": True, "applied_action": 1}, False)
    assert dqn == [STAGE_SPAN - 3161]
    free = [3.0]
    shield_reward(free, [4], {"forced": False, "applied_action": 4}, True)
    assert free == [3.0]

    route = Route(shared, 12, "progress")
    route.on_reset()
    assert route.on_step(9) == (1, True)
    assert route.on_step(9) == (2, True)
    assert route.on_step(9) == (11, True)
    assert route.on_step(9) == (9, False)
    route.on_reset()
    write_tape(shared, make_tape([4], 7, 1, 1, 1, "Green", 7, "progress"))
    # A different button count is not this seat's run. The loaded 1-2 run stays.
    assert route.on_step(9) == (1, True)

    adopted = tmp_path / "adopt.json"
    seat = Route(adopted, 12, "progress")
    seat.on_reset()
    assert seat.on_step(3) == (3, False)
    write_tape(adopted, into_1_2)
    # Mid-life the buttons stay as they are. The next life takes the better run.
    assert seat.on_step(3) == (3, False)
    seat.on_reset()
    assert seat.on_step(3) == (1, True)
    fresh = Route(adopted, 12, "progress")
    fresh.on_reset()
    write_tape(adopted, make_tape([6, 6], STAGE_SPAN + 80, 1, 2, 4, "Gold", 12, "progress"))
    # Published after reset, before the first press, so this life already follows it.
    assert fresh.on_step(3) == (6, True)
    assert fresh.on_step(3) == (6, True)
    assert fresh.on_step(3) == (3, False)

    runs = tmp_path / "runs"
    early = runs / "20261001T000000Z"
    early.mkdir(parents=True)
    write_tape(early / "best.tape.json", flag)
    later = runs / "20261002T000000Z" / "seats" / "2"
    later.mkdir(parents=True)
    write_tape(later / "best.tape.json", into_1_2)
    (runs / "20261002T000000Z").mkdir(exist_ok=True)
    other = runs / "other"
    other.mkdir()
    write_tape(other / "best.tape.json", make_tape([1], 99999, 1, 1, 0, "Red", 12, "steps"))
    new_run = runs / "20261003T000000Z"
    new_run.mkdir()
    assert seed_run(new_run, runs, 12, "progress") is True
    seeded = json.loads((new_run / "best.tape.json").read_text(encoding="utf-8"))
    assert seeded["score"] == STAGE_SPAN and seeded["stage"] == 2
    write_tape(new_run / "best.tape.json", flag)
    # The generation had the flag life. The saved 1-2 run is better, so it replaces that file.
    assert seed_run(new_run, runs, 12, "progress") is True
    assert json.loads((new_run / "best.tape.json").read_text(encoding="utf-8"))["score"] == STAGE_SPAN
    assert seed_run(new_run, runs, 12, "progress") is False
    assert best_saved(runs, 7, "progress") is None


def test_a_shorter_run_does_not_replace_the_flag_life(tmp_path):
    from games.lab.tape import Route, make_tape, parent_floor, seed_run, write_tape
    (tmp_path / "manifest.json").write_text(json.dumps({"parent_score": 3266}), encoding="utf-8")
    assert parent_floor(tmp_path) == 3266
    assert parent_floor(tmp_path / "missing") == 0
    weak = make_tape([1, 2, 2], 1427, 1, 1, 0, "Red", 12, "progress")
    path = tmp_path / "live" / "best.tape.json"
    write_tape(path, weak)
    route = Route(path, 12, "progress", min_score=3266)
    route.on_reset()
    # 1427 is behind the flag life, so the policy's own button is played.
    assert route.on_step(4) == (4, False)
    opened = make_tape([8, 8], STAGE_SPAN, 1, 2, 1, "Green", 12, "progress")
    write_tape(path, opened)
    route.on_reset()
    assert route.on_step(4) == (8, True)
    assert route.on_step(4) == (8, True)
    assert route.on_step(4) == (4, False)

    runs = tmp_path / "runs"
    old = runs / "old"
    old.mkdir(parents=True)
    write_tape(old / "best.tape.json", weak)
    fresh = runs / "new"
    fresh.mkdir()
    assert seed_run(fresh, runs, 12, "progress", 3266) is False
    assert not (fresh / "best.tape.json").is_file()
    write_tape(fresh / "best.tape.json", weak)
    write_tape(old / "best.tape.json", opened)
    assert seed_run(fresh, runs, 12, "progress", 3266) is True
    saved = json.loads((fresh / "best.tape.json").read_text(encoding="utf-8"))
    assert saved["score"] == STAGE_SPAN and saved["stage"] == 2
    tied = make_tape([3, 3], 3266, 1, 1, 1, "Green", 12, "progress")
    tied_root = tmp_path / "tied-runs"
    source = tied_root / "old"
    source.mkdir(parents=True)
    write_tape(source / "best.tape.json", tied)
    matched = tied_root / "matched"
    matched.mkdir()
    assert seed_run(matched, tied_root, 12, "progress", 3266) is True
    assert json.loads((matched / "best.tape.json").read_text(encoding="utf-8"))["score"] == 3266
    route = Route(matched / "best.tape.json", 12, "progress", min_score=3266)
    route.on_reset()
    assert route.on_step(4) == (3, True)


def test_a_real_later_world_replaces_the_castle_bump(tmp_path):
    from games.lab.tape import Route, comparable, floor_value, make_tape, publish, write_tape
    glitch = make_tape([1, 2], STAGE_SPAN + CLEAR_X, 1, 2, 3, "Gold", 12, "progress")
    assert comparable(glitch) == CLEAR_X
    assert floor_value(STAGE_SPAN + CLEAR_X) == CLEAR_X
    real = make_tape(
        [1, 2, 3, 4], STAGE_SPAN + 120, 1, 2, 1, "Green", 12, "progress", scored_clear=True
    )
    assert comparable(real) == STAGE_SPAN + 120
    path = tmp_path / "best.tape.json"
    assert publish(path, glitch) is True
    assert publish(path, real) is True
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["actions"] == [1, 2, 3, 4]
    assert saved["score"] == STAGE_SPAN + 120 and saved["world"] == 1 and saved["stage"] == 2
    # The old file is still practiced: its buttons clear 1-1, and the floor was the bump.
    old = tmp_path / "old.json"
    write_tape(old, glitch)
    route = Route(old, 12, "progress", min_score=STAGE_SPAN + CLEAR_X)
    route.on_reset()
    assert route.on_step(9) == (1, True)
    route = Route(path, 12, "progress", min_score=STAGE_SPAN + CLEAR_X)
    route.on_reset()
    assert route.on_step(9) == (1, True)
    assert route.on_step(9) == (2, True)
    assert route.on_step(9) == (3, True)
    assert route.on_step(9) == (4, True)


def test_the_same_place_with_more_time_or_fewer_presses_replaces(tmp_path):
    from games.lab.tape import (
        Route,
        best_saved,
        better,
        further_or_faster,
        make_tape,
        pace,
        publish,
        search_life,
        seed_run,
        write_tape,
    )
    slow = make_tape([1, 2, 3, 4], 3161, 1, 1, 0, "Red", 12, "progress", time=200)
    fast = make_tape([5, 6, 7, 8], 3161, 1, 1, 1, "Green", 12, "progress", time=340)
    short = make_tape([1, 4], 3161, 1, 1, 2, "Blue", 12, "progress", time=200)
    plain = make_tape([1, 2, 3, 4], 3161, 1, 1, 0, "Red", 12, "progress")
    assert pace(plain) is None and pace(slow) == 200
    assert better(fast, slow) is True
    assert better(slow, fast) is False
    assert better(slow, slow) is False
    # More time left wins even when that run used more presses.
    assert better(fast, short) is True
    assert better(short, fast) is False
    # An older file has no clock. Fewer presses replaces it. More presses do not.
    assert better(short, plain) is True
    assert better(make_tape([1, 2, 3, 4, 5, 6], 3161, 1, 1, 0, "Red", 12, "progress"), plain) is False
    further = make_tape([1], STAGE_SPAN, 1, 2, 2, "Blue", 12, "progress", time=10)
    assert better(further, fast) is True
    assert further_or_faster(3161, 340, 4, 3161, 200, 4) is True
    assert further_or_faster(3161, 100, 2, 3161, 200, 4) is False
    assert further_or_faster(STAGE_SPAN, 10, 9, 3161, 340, 2) is True
    assert search_life(8) is True and search_life(16) is True
    assert search_life(1) is False and search_life(7) is False and search_life(0) is False

    path = tmp_path / "best.tape.json"
    assert publish(path, slow) is True
    assert publish(path, {**slow, "actions": [0, 1, 2, 3]}) is False
    assert publish(path, fast) is True
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["time"] == 340 and saved["score"] == 3161 and saved["actions"] == [5, 6, 7, 8]
    route = Route(path, 12, "progress", min_score=3161)
    route.on_reset()
    assert route.on_step(9) == (5, True)
    write_tape(path, slow)
    # A slower file on disk does not pull the loaded run backward.
    assert route.on_step(9) == (6, True)
    route.on_reset()
    assert route.on_step(9) == (5, True)
    route.on_reset(search=True)
    assert route.on_step(9) == (9, False)
    assert route.on_step(4) == (4, False)

    runs = tmp_path / "runs"
    early = runs / "a"
    early.mkdir(parents=True)
    write_tape(early / "best.tape.json", slow)
    later = runs / "b" / "seats" / "1"
    later.mkdir(parents=True)
    write_tape(later / "best.tape.json", fast)
    assert best_saved(runs, 12, "progress")["time"] == 340
    dest = runs / "new"
    dest.mkdir()
    write_tape(dest / "best.tape.json", slow)
    assert seed_run(dest, runs, 12, "progress", 3161) is True
    assert json.loads((dest / "best.tape.json").read_text(encoding="utf-8"))["time"] == 340
    assert seed_run(dest, runs, 12, "progress", 3161) is False


def test_worker_exits_before_training_when_stop_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_RUNS", str(tmp_path))
    (tmp_path / "stop.request").write_text("stop\n", encoding="utf-8")
    code = worker_main([
        "--system", "nes",
        "--rom", str(tmp_path / "missing.nes"),
        "--model", "ppo_cnn",
        "--seed", "1",
        "--steps", "256",
        "--seat-dir", str(tmp_path / "seat"),
        "--seat", "0",
        "--name", "Red",
        "--color", "#d64545",
        "--objective", "x_pos",
    ])
    assert code == 0
    assert not (tmp_path / "seat").exists()


def test_generation_rank_orders_the_six_models_by_score():
    from games.lab.ranking import generation_rank
    seats = [
        {"seat": 0, "name": "Red", "model": "ppo_cnn", "score": 1127, "color": "#d64545"},
        {"seat": 1, "name": "Green", "model": "ppo_lstm", "score": 7362, "color": "#3c9d5a"},
        {"seat": 3, "name": "Gold", "model": "ppo_ram", "score": 7362, "color": "#d4a017"},
    ]
    ranked = generation_rank(seats, 3266, sense="maximize")
    assert [row["name"] for row in ranked] == ["Green", "Gold", "Red"]
    assert ranked[0]["rank"] == 1 and ranked[0]["delta"] == 7362 - 3266
    assert ranked[1]["delta"] == 7362 - 3266
    assert ranked[2]["delta"] == 1127 - 3266
    assert ranked[0]["record"] == "training"
    assert generation_rank(seats, None, sense="maximize")[0]["delta"] is None


def test_networks_show_the_shape_of_each_learner():
    from games.lab.models.networks import layer_params
    described = {item["id"]: item["network"] for item in registry.describe()}
    assert set(described) == {
        "ppo_cnn", "ppo_cnn_explore", "ppo_cnn_steady", "ppo_lstm", "dqn_cnn", "ppo_ram",
    }
    assert layer_params({"kind": "conv", "in": 4, "out": 32, "k": 8}) == 8224
    assert layer_params({"kind": "linear", "in": 9, "out": 64}) == 640
    assert layer_params({"kind": "lstm", "in": 512, "hidden": 128}) == 4 * 128 * (512 + 128 + 2)
    cnn = described["ppo_cnn"]["parameters"]
    assert described["ppo_cnn_explore"]["parameters"] == cnn
    assert described["ppo_cnn_steady"]["parameters"] == cnn
    assert described["ppo_cnn_explore"]["note"] != described["ppo_cnn_steady"]["note"]
    assert described["dqn_cnn"]["parameters"] < cnn
    assert described["ppo_lstm"]["parameters"] > cnn
    assert described["ppo_ram"]["parameters"] < 20_000
    assert cnn > 1_000_000
    assert described["ppo_ram"]["input"].startswith("9")
    assert described["ppo_cnn"]["input"].startswith("4 grayscale")


def test_a_hint_plays_after_the_shared_run_and_a_note_does_not(tmp_path):
    from games.lab.hints import add_hint, change_hint, hint_button, labels, parse_actions, read_hints
    from games.lab.tape import Route, make_tape, write_tape
    names = labels(SMB_ACTIONS)
    assert parse_actions("RIGHT+B, DOWN", names) == [SMB_ACTIONS.index(("RIGHT", "B")), SMB_ACTIONS.index(("DOWN",))]
    assert parse_actions("", names) == []
    store = tmp_path / "hints.json"
    note = add_hint(store, {"title": "World 1-2 warp", "world": 1, "stage": 2, "note": "along the ceiling", "actions": []})
    assert note["actions"] == [] and note["enabled"] is True
    assert hint_button(read_hints(store), 1, 2, 0, 12) is None
    played = add_hint(store, {"title": "Down the pipe", "world": 1, "stage": 2, "note": "", "actions": [10, 10]})
    assert hint_button(read_hints(store), 1, 2, 0, 12) == 10
    change_hint(store, played["id"], enabled=False)
    assert hint_button(read_hints(store), 1, 2, 0, 12) is None
    change_hint(store, played["id"], enabled=True)
    tape = tmp_path / "best.tape.json"
    write_tape(tape, make_tape([1, 2], 3161, 1, 1, 0, "Red", 12, "progress"))
    route = Route(tape, 12, "progress", hints_path=store)
    route.on_reset()
    assert route.on_step(9, 1, 1) == (1, True)
    assert route.on_step(9, 1, 1) == (2, True)
    assert route.on_step(9, 1, 1) == (9, False)
    assert route.on_step(9, 1, 2) == (10, True)
    assert route.on_step(9, 1, 2) == (10, True)
    assert route.on_step(9, 1, 2) == (9, False)
    change_hint(store, note["id"], remove=True)
    change_hint(store, played["id"], remove=True)
    assert read_hints(store) == []


def test_playback_shows_every_frame_of_the_saved_buttons():
    from games.lab.playback import drive, film_matches
    seen = []
    count = drive(
        [1, 3],
        lambda action: ("button", action),
        4,
        lambda buttons: seen.append(buttons) or buttons,
        lambda frame: None,
    )
    assert count == 8
    assert seen == [("button", 1)] * 4 + [("button", 3)] * 4
    tape = {"actions": [1, 1], "score": 7362, "n_actions": 12}
    assert film_matches({"score": 7362, "presses": 2, "n_actions": 12, "frames": 9}, tape) is True
    assert film_matches({"score": 3161, "presses": 2, "n_actions": 12, "frames": 9}, tape) is False
    assert film_matches(None, tape) is False


def test_diagnostic_ram_stays_out_of_the_policy_vector():
    ram = bytearray(2048)
    ram[0x001D] = 1
    ram[0x0057] = 0x18
    ram[0x009F] = 0xFB
    ram[0x000F] = 1
    ram[0x0016] = 0x06
    ram[0x006E] = 0
    ram[0x0087] = 180
    facts = diagnose(bytes(ram))
    assert facts["physics"] == "jumping"
    assert facts["x_speed"] == 0x18
    assert facts["y_speed"] == -5
    assert facts["enemies"][0]["screen_x"] == 180
    assert facts["enemies"][0]["id"] == 0x06
    assert len(ram_vector(bytes(ram))) == 9
    assert "x_speed" not in describe(bytes(ram))
    assert "enemies" not in describe(bytes(ram))


def test_demonstration_stays_out_of_both_learners(tmp_path):
    from games.lab.hints import add_hint
    from games.lab.tape import Route, learnable_transition, make_tape, take_demonstration, write_tape
    store = tmp_path / "hints.json"
    add_hint(store, {"title": "Down the pipe", "world": 1, "stage": 2, "note": "", "actions": [10]})
    tape = tmp_path / "best.tape.json"
    write_tape(tape, make_tape([1, 2], 100, 1, 1, 0, "Red", 12, "progress"))
    route = Route(tape, 12, "progress", hints_path=store)
    route.on_reset()
    where = {"stage": 1}

    def place():
        return 1, where["stage"]

    def act(button):
        if button == 2:
            where["stage"] = 2
        return True

    assert take_demonstration(route, place, act) == [1, 2, 10]
    assert route.peek_action(9, 1, 2) == (9, False)
    searching = Route(tape, 12, "progress", hints_path=store)
    searching.on_reset(search=True)
    assert take_demonstration(searching, lambda: (1, 1)) == []
    assert learnable_transition({"forced": True}, algorithm="ppo") is False
    assert learnable_transition({"forced": True}, algorithm="dqn") is False
    assert learnable_transition({"forced": False}, algorithm="ppo") is True
    assert learnable_transition(None, algorithm="dqn") is True
    with pytest.raises(ValueError):
        learnable_transition({"forced": True}, algorithm="other")


def test_independent_eval_rejects_assistance_and_a_mismatched_zip(tmp_path):
    from games.lab.eval import (
        accept_eval,
        begin_life,
        blank_milestones,
        checkpoint_sha256,
        compare_independent,
        decide,
        evaluate_attempts,
        play_loaded,
        write_eval,
    )
    from games.lab.integrations.smb_1_1 import BENCHMARKS, evaluation_protocol, update_milestones
    protocol = evaluation_protocol()
    identity = {
        "rom_sha1": "abc",
        "core_sha1": "def",
        "checkpoint_sha256": "fff",
        "model": "ppo_cnn",
        "seed": 0,
    }
    assisted = evaluate_attempts(lambda seed: {"forced": True, "score": 99, "success": True}, 2, identity, protocol)
    assert assisted["failed"] is True and assisted["assisted"] is False and assisted["successes"] == 0
    missing = evaluate_attempts(lambda _seed: {}, 1, {"model": "ppo_cnn"}, protocol)
    assert missing["failed"] is True and "rom_sha1" in missing["failure"]

    flag = update_milestones(blank_milestones(protocol), {"world": 1, "stage": 1, "flag_get": True, "dead": False})
    assert flag["clear-1-1-flag"] is True
    assert flag["enter-world-4"] is False and flag["reach-world-1-2"] is False
    warp = update_milestones(blank_milestones(protocol), {"world": 4, "stage": 1, "dead": False, "flag_get": False})
    assert warp["enter-world-4"] is True and warp["reach-world-1-2"] is True
    assert update_milestones(blank_milestones(protocol), {"world": 4, "stage": 1, "dead": True})["enter-world-4"] is False

    def play(seed):
        entered = seed == 1
        return {
            "score": 40 if entered else 10,
            "world": 4 if entered else 1,
            "stage": 1,
            "x_pos": 40 if entered else 10,
            "dead": False,
            "time": 300,
            "decisions": 2,
            "frames": 8,
            "forced": False,
            "assisted": False,
            "demonstration_steps": 0,
            "milestones": {
                "clear-1-1-flag": not entered,
                "reach-world-1-2": entered,
                "enter-world-4": entered,
            },
        }

    before = evaluate_attempts(play, 2, identity, protocol)
    assert before["failed"] is False and before["success_rate"] == 0.5 and before["record"] == "independent"
    assert before["benchmark"] == "enter-world-4"
    assert before["milestone_counts"]["clear-1-1-flag"] == 1
    assert before["milestone_counts"]["enter-world-4"] == 1
    assert before["protocol"] == "smb-unassisted-v1" and before["attempts"] == 2
    assert before["seeds"] == [0, 1]
    after = evaluate_attempts(lambda seed: {**play(1), "score": 80, "x_pos": 80}, 2, identity, protocol)
    compared = compare_independent(before, after)
    assert compared["improved"] is True and compared["benchmark"] == "enter-world-4"
    with pytest.raises(ValueError):
        compare_independent(assisted, before)
    with pytest.raises(ValueError):
        compare_independent(before, {**after, "benchmark": "clear-1-1-flag"})
    with pytest.raises(ValueError):
        compare_independent(before, {**after, "seeds": [5, 6]})
    weights = tmp_path / "best.zip"
    weights.write_bytes(b"weights-v1")
    digest = checkpoint_sha256(weights)
    # Two attempts describe a result. They are not the fixed five-life protocol.
    short = {**before, "checkpoint_sha256": digest}
    assert accept_eval(short, weights, protocol=protocol) is False

    def five(entered):
        body = evaluate_attempts(lambda _seed: play(1 if entered else 2), 5, identity, protocol)
        return {**body, "checkpoint_sha256": digest}

    entered = five(True)
    assert entered["attempts"] == 5 and entered["success_rate"] == 1.0
    assert accept_eval(entered, weights, protocol=protocol, model="ppo_cnn") is True
    assert accept_eval(entered, weights, protocol=protocol, model="ppo_lstm") is False
    assert accept_eval({**entered, "checkpoint_sha256": "nope"}, weights, protocol=protocol) is False
    assert accept_eval({**entered, "assisted": True}, weights, protocol=protocol) is False
    assert accept_eval({**entered, "failed": True}, weights, protocol=protocol) is False
    assert accept_eval(entered, weights, protocol={**protocol, "name": "other-v1"}) is False
    flagged = five(False)
    assert flagged["success_rate"] == 0.0 and flagged["milestone_counts"]["clear-1-1-flag"] == 5
    assert accept_eval(flagged, weights, protocol=protocol) is True
    forged = {**flagged, "successes": 5, "success_rate": 1.0}
    assert accept_eval(forged, weights, protocol=protocol) is False
    lied_rows = [
        {
            **episode,
            "success": True,
            "milestones": {**episode["milestones"], "enter-world-4": True},
        }
        for episode in flagged["episodes"]
    ]
    lied = {**flagged, "episodes": lied_rows, "successes": 5, "success_rate": 1.0}
    assert lied["episodes"][0]["world"] == 1
    assert accept_eval(lied, weights, protocol=protocol) is False
    other_seeds = {**entered, "seed": 3, "seeds": [3, 4, 5, 6, 7]}
    other_seeds["episodes"] = [{**episode, "seed": 3 + index} for index, episode in enumerate(entered["episodes"])]
    assert accept_eval(other_seeds, weights, protocol=protocol) is False
    assert BENCHMARKS["enter-world-4"] != BENCHMARKS["clear-1-1-flag"]
    write_eval(weights.with_suffix(".eval.json"), entered)

    class Memory:
        def __init__(self):
            self.calls = []

        def set_random_seed(self, seed):
            self.seed = seed

        def get_env(self):
            return self.vec

        def predict(self, observation, state=None, episode_start=None, deterministic=False):
            self.calls.append((state, list(episode_start), deterministic))
            return [0], (1 if state is None else state + 1)

    class OneLife:
        num_envs = 1

        def __init__(self):
            self.steps = 0
            self.reset_infos = [{
                "forced": False,
                "assisted": False,
                "demonstration_steps": 0,
                "world": 1,
                "stage": 1,
                "score": 0,
                "x_pos": 40,
                "dead": False,
                "dying": False,
                "time": 400,
                "flag_get": False,
            }]

        def reset(self):
            self.steps = 0
            return [0]

        def step(self, _action):
            self.steps += 1
            done = self.steps >= 3
            info = {
                "forced": False,
                "assisted": False,
                "world": 1,
                "stage": 1,
                "score": 3161 if done else self.steps,
                "x_pos": 3161 if done else 40,
                "dead": False,
                "dying": False,
                "time": 300,
                "flag_get": done,
            }
            return [0], [0], [done], [info]

    memory = Memory()
    memory.vec = OneLife()
    life = begin_life(1)
    _action, life = decide(memory, [0], life)
    _action, life = decide(memory, [0], life)
    again = begin_life(1)
    decide(memory, [0], again)
    assert memory.calls[0] == (None, [True], True)
    assert memory.calls[1][0] == 1 and memory.calls[1][1] == [False]
    assert memory.calls[2] == (None, [True], True)
    played = play_loaded(memory, seed=7, protocol=protocol, limit=10)
    starts = [call[1] for call in memory.calls[3:]]
    states = [call[0] for call in memory.calls[3:]]
    assert starts == [[True], [False], [False]]
    assert states == [None, 1, 2]
    assert all(call[2] for call in memory.calls)
    assert played["milestones"]["clear-1-1-flag"] is True
    assert played["milestones"]["enter-world-4"] is False
    assert played["success"] is False
    assert played["decisions"] == 3
    assert played["frames"] == 3 * protocol["frame_skip"]


def test_promotion_uses_the_independent_eval_not_the_training_score(tmp_path, monkeypatch):
    from games.lab.eval import checkpoint_sha256, write_eval
    from games.lab.lineage import champion, promoted_parent
    from games.lab.supervisor import _seed_sources, _weight_sources
    monkeypatch.setattr("games.lab.supervisor.runs_root", lambda: tmp_path)

    def write(run, seat, score, payload, evaluation):
        folder = tmp_path / run / "seats" / str(seat)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "best.zip").write_bytes(payload)
        (tmp_path / run / "results.json").write_text(json.dumps({
            "winner": seat,
            "seats": [{
                "seat": seat,
                "name": "Red" if seat == 0 else "Green",
                "model": "ppo_cnn",
                "score": score,
                "steps": 200000,
                "deaths": 1,
            }],
        }), encoding="utf-8")
        if evaluation is not None:
            evaluation = {**evaluation, "checkpoint_sha256": checkpoint_sha256(folder / "best.zip")}
            write_eval(folder / "best.eval.json", evaluation)

    from games.lab.integrations.smb_1_1 import BENCHMARKS, evaluation_protocol
    protocol = evaluation_protocol()

    def measurement(success, score):
        episodes = []
        for seed in range(5):
            episodes.append({
                "seed": seed,
                "failed": False,
                "score": score,
                "world": 4 if success else 1,
                "stage": 1,
                "x_pos": score,
                "dead": False,
                "time": 300,
                "frames": 8,
                "success": success,
                "milestones": {
                    "clear-1-1-flag": True,
                    "reach-world-1-2": success,
                    "enter-world-4": success,
                },
            })
        return {
            "assisted": False,
            "failed": False,
            "record": "independent",
            "protocol": "smb-unassisted-v1",
            "benchmark": "enter-world-4",
            "benchmark_definition": BENCHMARKS["enter-world-4"],
            "game": "smb_1_1",
            "objective": "progress",
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
                "world": 4 if success else 1,
                "stage": 1,
                "x_pos": score,
                "time": 300,
            },
            "episodes": episodes,
        }

    write("trained", 0, 9999, b"trained-only", None)
    assert champion(tmp_path, "ppo_cnn", sense="maximize")["score"] == 9999
    assert promoted_parent(tmp_path, "ppo_cnn", protocol=protocol) is None
    seats = [{"model": "ppo_cnn"}, {"model": "ppo_cnn"}]
    assert _seed_sources(seats, sense="maximize")[0]["score"] == 9999
    assert _weight_sources(seats) == [None, None]
    # A measured flagpole is a parent candidate. Its success rate on the requested benchmark is 0.
    write("trained", 0, 9999, b"trained-only", measurement(False, 3161))
    flagged = promoted_parent(tmp_path, "ppo_cnn", protocol=protocol)
    assert flagged["record"] == "independent" and flagged["success_rate"] == 0.0 and flagged["score"] == 3161
    write("evaluated", 1, 10, b"evaluated", measurement(True, 20))
    parent = promoted_parent(tmp_path, "ppo_cnn", protocol=protocol)
    assert parent["record"] == "independent" and parent["score"] == 20 and parent["seat"] == 1
    assert parent["success_rate"] == 1.0
    assert _weight_sources(seats, protocol=protocol)[0]["path"] == parent["path"]
    other = {**protocol, "name": "puzzle-v1", "game": "puzzle", "objective": "pieces", "default_benchmark": "solved"}
    other["benchmarks"] = {"solved": "The puzzle is solved."}
    assert promoted_parent(tmp_path, "ppo_cnn", protocol=other) is None
    # A hash that does not match the zip is not a parent. The flagpole measurement remains.
    stale = tmp_path / "evaluated" / "seats" / "1" / "best.eval.json"
    body = json.loads(stale.read_text(encoding="utf-8"))
    body["checkpoint_sha256"] = "0" * 64
    stale.write_text(json.dumps(body), encoding="utf-8")
    fallback = promoted_parent(tmp_path, "ppo_cnn", protocol=protocol)
    assert fallback["seat"] == 0 and fallback["success_rate"] == 0.0
    elsewhere = measurement(True, 999)
    elsewhere["core_sha1"] = "not-the-same-core"
    write("other-core", 0, 50, b"other-core", elsewhere)
    assert promoted_parent(tmp_path, "ppo_cnn", protocol=protocol) is None


def test_beam_search_clears_a_gap_and_keeps_the_frame_count():
    from games.lab.search import beam_search, frames_of

    class Gap:
        def __init__(self):
            self.simulated = 0

        def replay(self, trajectory):
            self.simulated += frames_of(trajectory)
            x = 0
            air = 0
            dead = False
            for step in trajectory:
                buttons = step["buttons"]
                for _ in range(int(step["frames"])):
                    if dead:
                        break
                    if air == 0 and "A" in buttons:
                        air = 3
                    if "RIGHT" in buttons:
                        x += 1
                    if x == 3 and air == 0:
                        dead = True
                    elif air > 0:
                        air -= 1
            return {"x": x, "dead": dead, "dying": dead}

    gap = Gap()

    def success(facts):
        return facts["x"] >= 4 and not facts["dead"]

    def rank(facts):
        return -100 if facts["dead"] else facts["x"]

    actions = [(), ("RIGHT",), ("RIGHT", "A"), ("A",)]
    found = beam_search(
        gap, actions, success, rank, width=4, depth=6, hold=1, max_attempts=80, max_frames=400,
        subgoals=[("across", success)],
    )
    assert found["solved"] is True
    assert found["trajectory"]
    assert all(step["frames"] == 1 for step in found["trajectory"])
    assert frames_of(found["trajectory"]) == found["trajectory_frames"]
    assert found["frame_accounting"] == "full-prefix"
    assert found["frames"] == gap.simulated
    assert found["decisions"] == len(found["trajectory"])
    assert found["frames"] > found["trajectory_frames"]
    assert found["subgoals"][0]["reached"] is True and found["subgoals"][0]["name"] == "across"
    end = gap.replay(found["trajectory"])
    again = gap.replay(found["trajectory"])
    assert end == again and end["x"] >= 4 and end["dead"] is False
    right_only = beam_search(gap, [("RIGHT",)], success, rank, width=2, depth=6, hold=1, max_attempts=20)
    assert right_only["solved"] is False
    stopped = beam_search(gap, actions, success, rank, depth=6, cancel=lambda: True)
    assert stopped["cancelled"] is True and stopped["solved"] is False
    partial = beam_search(gap, actions, success, rank, width=4, depth=1, hold=1, max_attempts=80)
    assert partial["solved"] is False
    resumed = beam_search(
        gap, actions, success, rank, width=4, depth=6, hold=1, max_attempts=200, resume=partial["resume"]
    )
    assert resumed["solved"] is True and resumed["attempts"] > partial["attempts"]
    limited = beam_search(gap, actions, success, rank, width=4, depth=6, hold=1, max_attempts=2)
    assert limited["budget_exhausted"] is True


def test_search_counts_every_replayed_prefix():
    from games.lab.search import action_step, beam_search, frames_of
    assert action_step({"buttons": ["RIGHT", "A"], "frames": 1}, 15) == {"buttons": ["RIGHT", "A"], "frames": 1}
    assert action_step(("RIGHT",), 15)["frames"] == 15

    class Log:
        def __init__(self):
            self.played = 0

        def replay(self, trajectory):
            cost = frames_of(trajectory)
            self.played += cost
            return {"x": cost, "dead": False, "dying": False}

    log = Log()
    actions = [{"buttons": ["RIGHT"], "frames": 15}, {"buttons": ["A"], "frames": 1}]
    found = beam_search(
        log,
        actions,
        lambda facts: facts["x"] >= 16,
        lambda facts: facts["x"],
        width=2,
        depth=3,
        hold=1,
        max_attempts=20,
        max_frames=5000,
    )
    assert found["solved"] is True
    assert found["frames"] == log.played
    assert found["trajectory_frames"] == frames_of(found["trajectory"])
    assert found["frames"] > found["trajectory_frames"]
    assert found["decisions"] == len(found["trajectory"])
    assert found["frame_accounting"] == "full-prefix"


def test_an_oversized_action_does_not_block_a_shorter_one():
    from games.lab.search import beam_search, frames_of

    class Log:
        def replay(self, trajectory):
            return {"x": frames_of(trajectory), "dead": False, "dying": False}

    actions = [{"buttons": ["RIGHT"], "frames": 100}, {"buttons": ["A"], "frames": 1}]
    found = beam_search(
        Log(),
        actions,
        lambda facts: facts["x"] >= 1,
        lambda facts: facts["x"],
        width=2,
        depth=2,
        hold=1,
        max_attempts=20,
        max_frames=10,
    )
    assert found["solved"] is True
    assert found["trajectory"] == [{"buttons": ["A"], "frames": 1}]
    assert found["decisions"] == 1
    assert found["trajectory_frames"] == 1
    assert found["budget_exhausted"] is False
    blocked = beam_search(
        Log(),
        [{"buttons": ["RIGHT"], "frames": 100}],
        lambda facts: facts["x"] >= 1,
        lambda facts: facts["x"],
        width=2,
        depth=2,
        hold=1,
        max_attempts=20,
        max_frames=10,
    )
    assert blocked["solved"] is False and blocked["budget_exhausted"] is True


def test_the_evaluator_follows_the_adapter_and_drops_an_incomplete_run(tmp_path):
    from games.lab.eval import accept_eval, checkpoint_sha256, compare_independent, evaluate_attempts
    protocol = {
        "name": "puzzle-v1",
        "attempts": 2,
        "limit": 10,
        "frame_skip": 2,
        "n_actions": 3,
        "seed": 0,
        "default_benchmark": "solved",
        "game": "puzzle",
        "objective": "pieces",
        "start": "game",
        "benchmarks": {"solved": "The puzzle is solved."},
        "supports": lambda episode, _benchmark: bool(episode.get("solved_position")),
        "metrics": lambda info: {"score": int(info.get("score") or 0), "dead": bool(info.get("dead"))},
    }
    identity = {
        "rom_sha1": "rom",
        "core_sha1": "core",
        "checkpoint_sha256": "hash",
        "model": "ppo_cnn",
        "seed": 0,
    }

    def play(_seed):
        return {
            "score": 3,
            "dead": False,
            "decisions": 4,
            "frames": 8,
            "forced": False,
            "assisted": False,
            "demonstration_steps": 0,
            "solved_position": True,
            "milestones": {"solved": True},
        }

    done = evaluate_attempts(play, 2, identity, protocol)
    assert done["failed"] is False and done["benchmark"] == "solved" and done["game"] == "puzzle"
    assert done["decisions"] == 4 and done["frames"] == 8 and done["seeds"] == [0, 1]
    weights = tmp_path / "best.zip"
    weights.write_bytes(b"puzzle")
    digest = checkpoint_sha256(weights)
    assert accept_eval({**done, "checkpoint_sha256": digest}, weights, protocol=protocol) is True
    unsupported = {
        **done["episodes"][0],
        "solved_position": False,
    }
    forged = {**done, "checkpoint_sha256": digest, "episodes": [unsupported, done["episodes"][1]]}
    assert accept_eval(forged, weights, protocol=protocol) is False

    def boom(seed):
        if seed == 1:
            raise RuntimeError("dropped")
        return play(seed)

    partial = evaluate_attempts(boom, 2, identity, protocol)
    assert partial["failed"] is True and partial["success_rate"] == 0.0
    assert accept_eval({**partial, "checkpoint_sha256": digest}, weights, protocol=protocol) is False
    shifted = evaluate_attempts(play, 2, {**identity, "seed": 4}, protocol)
    with pytest.raises(ValueError):
        compare_independent(done, shifted)


def test_challenge_refuses_an_incompatible_state(tmp_path):
    from games.lab.challenge import (
        ChallengeError,
        catalog,
        load_challenge,
        same_start,
        save_challenge,
    )
    from games.lab.integrations.smb_1_1 import reached_warp
    state = b"savestate-bytes"
    document = {
        "id": "smb-1-2-ceiling-warp",
        "objective": "Reach world 4 from the ceiling route in 1-2",
        "game": "Super Mario Bros.",
        "rom_sha1": "rom",
        "core_sha1": "core",
        "core_name": "fceumm",
        "success": "world-4-from-1-2",
        "start": {"world": 1, "stage": 2, "x_pos": 10, "y_pos": 20, "time": 361, "player_state": 8},
    }
    folder = save_challenge(tmp_path, document, state)
    loaded, blob = load_challenge(folder, rom_sha1="rom", core_sha1="core")
    assert blob == state and loaded["state_sha256"]
    assert same_start(loaded["start"], dict(loaded["start"]))
    with pytest.raises(ChallengeError):
        load_challenge(folder, rom_sha1="rom", core_sha1="other-core")
    with pytest.raises(ChallengeError):
        load_challenge(folder, rom_sha1="other-rom", core_sha1="core")
    (folder / "state.bin").write_bytes(b"different")
    with pytest.raises(ChallengeError):
        load_challenge(folder, rom_sha1="rom", core_sha1="core")
    (folder / "state.bin").write_bytes(state)
    broken = json.loads((folder / "challenge.json").read_text(encoding="utf-8"))
    broken["version"] = 2
    (folder / "challenge.json").write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ChallengeError):
        load_challenge(folder, rom_sha1="rom", core_sha1="core")
    with pytest.raises(ChallengeError):
        save_challenge(tmp_path, {**document, "id": "../escape"}, state)
    start = {"world": 1, "stage": 2}
    assert reached_warp(start, {"world": 4, "stage": 1, "dead": False, "dying": False}) is True
    assert reached_warp(start, {"world": 1, "stage": 2, "dead": False, "score": 99999}) is False
    assert reached_warp(start, {"world": 4, "stage": 1, "dead": True}) is False
    listed = catalog(tmp_path)
    assert listed and listed[0]["id"] == "smb-1-2-ceiling-warp"
    assert listed[0]["records"]["assisted"] is None


def test_a_tape_can_omit_world_and_stage():
    from games.lab.integrations.smb_1_1 import INTEGRATION, clock_running, present
    from games.lab.tape import make_tape
    saved = make_tape(
        [1, 1, 1],
        3,
        n_actions=2,
        objective="progress",
        sense="maximize",
        integration="grid",
        context={"cell": 3},
    )
    assert saved["score"] == 3
    assert "world" not in saved and "stage" not in saved
    assert saved["context"] == {"cell": 3}
    mario = make_tape([1], 10, 1, 2, 0, "Red", 12, "progress")
    assert mario["world"] == 1 and mario["stage"] == 2 and "context" not in mario
    assert callable(INTEGRATION.open_env)
    assert clock_running({"time": 400}) is True
    assert clock_running({"time": 0}) is False
    shown = present({"world": 2, "stage": 1, "x_pos": 10}, {"cleared": True, "at": (1, 1)})
    assert shown["world"] == 1 and shown["stage"] == 1
    plain = present({"world": 1, "stage": 1}, {"cleared": False, "at": None})
    assert plain["world"] == 1 and plain["stage"] == 1


def test_a_skill_does_not_spread_and_the_curriculum_is_not_running():
    from games.lab.skill import curriculum_plan, new_skill, record_mastery, record_practice, verify_demonstration
    skill = new_skill(
        "opening jump",
        "jump the gap",
        "gap",
        [{"buttons": ["RIGHT", "A"], "frames": 1}],
        world=1,
        stage=1,
        start={"x_pos": 0},
        benchmark="opening-jump",
    )
    assert skill["stage"] == "discovered" and skill["agents"] == {}
    verified = verify_demonstration(skill, [True, True])
    assert verified["stage"] == "verified_demonstration"
    rejected = verify_demonstration(skill, [True, False])
    assert rejected["stage"] == "discovered"
    practiced = record_practice(verified, "Red")
    assert practiced["stage"] == "practiced" and practiced["agents"] == {"Red": "practiced"}
    mastered = record_mastery(practiced, "Red", {
        "assisted": False,
        "failed": False,
        "record": "independent",
        "benchmark": "opening-jump",
        "successes": 1,
        "success_rate": 1,
    })
    assert mastered["agents"]["Red"] == "verified_fixed_state"
    assert mastered["standing"] == "verified_fixed_state"
    assert mastered["stage"] == "practiced"
    declared = record_mastery(practiced, "Red", {
        "assisted": False,
        "failed": False,
        "record": "independent",
        "benchmark": "opening-jump",
        "successes": 5,
        "success_rate": 1,
        "generalized": True,
        "starts": [{"x_pos": 0}, {"x_pos": 40}],
    })
    assert declared["agents"]["Red"] == "verified_fixed_state"
    assert declared["standing"] == "verified_fixed_state"
    assert declared["stage"] == "practiced"
    missed = record_mastery(practiced, "Red", {
        "assisted": False,
        "failed": False,
        "record": "independent",
        "benchmark": "opening-jump",
        "successes": 5,
        "success_rate": 1,
        "conditions": [
            {"start": {"x_pos": 0}, "attempts": 2, "successes": 2},
            {"start": {"x_pos": 40}, "attempts": 2, "successes": 0},
        ],
    })
    assert missed["agents"]["Red"] == "verified_fixed_state"
    assert missed["stage"] == "practiced"
    generalized = record_mastery(practiced, "Red", {
        "assisted": False,
        "failed": False,
        "record": "independent",
        "benchmark": "opening-jump",
        "successes": 5,
        "success_rate": 1,
        "conditions": [
            {"start": {"x_pos": 0}, "attempts": 2, "successes": 2},
            {"condition": {"x_pos": 40}, "attempts": 2, "successes": 1},
        ],
    })
    assert generalized["agents"]["Red"] == "generalized"
    assert generalized["standing"] == "generalized"
    assert generalized["stage"] == "generalized"
    flagpole = record_mastery(practiced, "Red", {
        "assisted": False,
        "failed": False,
        "record": "independent",
        "benchmark": "clear-1-1-flag",
        "successes": 1,
        "success_rate": 1,
    })
    assert flagpole["agents"]["Red"] == "practiced"
    left = record_mastery(practiced, "Green", {
        "assisted": True,
        "failed": False,
        "record": "independent",
        "successes": 1,
        "success_rate": 1,
    })
    assert "Green" not in left["agents"]
    plan = curriculum_plan("smb-1-2-ceiling-warp")
    assert [item["stage"] for item in plan] == ["at_obstacle", "farther_back", "level_start", "game_start"]
    assert [item["implemented"] for item in plan] == [False, False, False, False]
    assert all(item["assisted"] is False for item in plan)
