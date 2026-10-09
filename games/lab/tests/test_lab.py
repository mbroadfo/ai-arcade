"""Catalog grades, Mario RAM, ranking, and what a finished round keeps. No ROM and no torch."""
import json

import pytest

from games.lab.catalog import games_from, load_path
from games.lab.integrations.smb_1_1 import describe, ram_vector, skip_title
from games.lab.lineage import champion, collapsed_history, seats_for_generation
from games.lab.models import registry
from games.lab.paths import REPO_ROOT
from games.lab.publish import finalize
from games.lab.ranking import winner
from games.lab.roms import SMB_SHA1, SMB_SHA256, RomRejected, accept_smb
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
    assert len(ram_vector(bytes(ram))) == 7


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
    assert winner(rows)["seat"] == 0
    assert winner([{"seat": 3, "score": 10, "flag": False}, {"seat": 1, "score": 10, "flag": False}])["seat"] == 1


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


def test_rom_pin_rejects_anything_else():
    assert SMB_SHA1 == "ea343f4e445a9050d4b4fbac2c77d0693b1d0922"
    assert len(SMB_SHA256) == 64
    with pytest.raises(RomRejected):
        accept_smb(b"NES\x1a" + b"\x00" * 32)


def test_registry_lists_four_and_ram_refuses_a_bootable_game():
    assert registry.ids() == ["ppo_cnn", "ppo_lstm", "dqn_cnn", "ppo_ram"]
    registry.check("ppo_cnn", None)
    with pytest.raises(ValueError):
        registry.check("ppo_ram", None)


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
    found = champion(tmp_path, "ppo_cnn")
    assert found["score"] == 1950 and found["seat"] == 0
    assert found["path"].parent.name == "0"


def test_seed_from_and_resume_are_exclusive(tmp_path):
    with pytest.raises(ValueError):
        train(None, "ppo_cnn", 1, 10, tmp_path, {}, True, seed_from=tmp_path / "seed.zip")


def test_resume_without_a_checkpoint_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        train(None, "ppo_cnn", 1, 10, tmp_path, {}, True)


def test_missing_seed_zip_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        train(None, "ppo_cnn", 1, 10, tmp_path, {}, False, seed_from=tmp_path / "missing.zip")
