"""Mario observation formula, stamp compatibility, and accepted RAM fixtures.

No emulator and no torch. Real dumps are checked only after the validator has
accepted them and written fixtures/expect.json.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from games.lab.integrations.smb_1_1 import (
    SMB_ACTIONS,
    INTEGRATION,
    observation_spec,
    observation_vector,
    ram_vector,
)
from games.lab.observations import spec_digest

_CHECKS_PATH = (
    Path(__file__).resolve().parents[1] / "experiments" / "tile-observation" / "checks.py"
)
_FIXTURES = _CHECKS_PATH.parent / "fixtures"
_EXPECT = _FIXTURES / "expect.json"
_BUTTONS = (0x000A, 0x000D, 0x06FC, 0x074A)
_FORBIDDEN = (0x000A, 0x000D, 0x06FC, 0x074A, 0x0016, 0x0057, 0x009F)
_PAIRWISE = ("title", "goomba", "contact", "on-pipe", "past")


def _checks():
    spec = importlib.util.spec_from_file_location("tile_observation_checks", _CHECKS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ram() -> bytearray:
    return bytearray(2048)


def _anchor(ram: bytearray, screen_x: int = 40, screen_y: int = 176, level_x: int = 40) -> None:
    ram[0x03AD] = screen_x
    ram[0x03B8] = screen_y
    ram[0x006D] = (level_x >> 8) & 0xFF
    ram[0x0086] = level_x & 0xFF


class _RecordingRAM(bytes):
    def __new__(cls, data: bytes):
        obj = bytes.__new__(cls, data)
        obj.reads = []
        return obj

    def __getitem__(self, key):
        if isinstance(key, int):
            index = key if key >= 0 else len(self) + key
            self.reads.append(index)
        elif isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            self.reads.extend(range(start, stop, step))
        return bytes.__getitem__(self, key)


def _allowed(enemy_x: int, enemy_y: int) -> set[int]:
    allowed = {0x006D, 0x0086, 0x03AD, 0x03B8}
    allowed.update(range(0x0500, 0x06A0))
    allowed.update(range(0x000F, 0x0014))
    allowed.update(range(enemy_x, enemy_x + 5))
    allowed.update(range(enemy_y, enemy_y + 5))
    return allowed


def test_a_planted_block_and_a_drawn_enemy_land_on_the_computed_cells():
    ram = _ram()
    _anchor(ram)
    # screen x 40 + 12 -> column 3. Window origin world x is 48, buffer row 2.
    ram[0x0523] = 0x54
    ram[0x000F] = 1
    ram[0x03AE] = 64
    ram[0x03B9] = 64
    ram[0x0524] = 0x10
    vector = observation_vector(bytes(ram), spec_id="smb-tiles-v1")
    assert len(vector) == 80
    assert vector[0] == 1.0
    assert vector[1] == -1.0
    assert vector[78] == 1.0
    assert sum(vector[70:80]) == 1.0
    assert all(value in (-1.0, 0.0, 1.0) for value in vector[:70])


def test_the_second_block_page_uses_the_208_byte_stride():
    ram = _ram()
    _anchor(ram, screen_x=0, level_x=256)
    ram[0x03B8] = 176
    # column 0, world x 256, buffer row 2 -> 0x0500 + 208 + 32.
    ram[0x05F0] = 0x02
    vector = observation_vector(bytes(ram), spec_id="smb-tiles-v1")
    assert vector[0] == 1.0


def test_registered_bias_toggles_move_only_the_matching_axis():
    ram = _ram()
    _anchor(ram)
    ram[0x0522] = 0x07
    unbiased = observation_vector(bytes(ram), spec_id="smb-tiles-v1", decoder={"x_bias": 0})
    assert unbiased[0] == 1.0
    biased = observation_vector(bytes(ram), spec_id="smb-tiles-v1")
    assert biased[0] == 0.0
    low = observation_vector(bytes(ram), spec_id="smb-tiles-v1", decoder={"y_bias": 0})
    assert low[70 + 7] == 1.0
    assert sum(low[70:80]) == 1.0
    high = observation_vector(bytes(ram), spec_id="smb-tiles-v1")
    assert high[70 + 8] == 1.0


def test_a_column_past_the_screen_stays_empty_and_is_not_read():
    ram = _ram()
    _anchor(ram, screen_x=240, level_x=240)
    ram[0x05F0] = 0xFF
    recorded = _RecordingRAM(bytes(ram))
    vector = observation_vector(recorded, spec_id="smb-tiles-v1")
    assert vector[1] == 0.0
    assert 0x05F0 not in recorded.reads


def test_the_vector_reads_only_its_allow_list():
    ram = _ram()
    _anchor(ram)
    ram[0x0523] = 1
    ram[0x000F] = 1
    ram[0x03AE] = 64
    ram[0x03B9] = 64
    for address in _BUTTONS:
        ram[address] = 192
    recorded = _RecordingRAM(bytes(ram))
    observation_vector(recorded, spec_id="smb-tiles-v1")
    assert set(recorded.reads) <= _allowed(0x03AE, 0x03B9)
    assert set(recorded.reads).isdisjoint(_FORBIDDEN)
    assert 0x03AE in recorded.reads
    assert 0x0087 not in recorded.reads
    changed = bytearray(ram)
    for address in _BUTTONS:
        changed[address] = (changed[address] + 128) & 0xFF
    assert observation_vector(bytes(changed), spec_id="smb-tiles-v1") == observation_vector(
        bytes(ram), spec_id="smb-tiles-v1"
    )


def test_the_fallback_enemy_pair_is_the_only_position_read():
    ram = _ram()
    _anchor(ram)
    ram[0x000F] = 1
    ram[0x0087] = 64
    ram[0x00CF] = 64
    ram[0x03AE] = 0
    ram[0x03B9] = 0
    decoder = {"enemy_x": "0x0087", "enemy_y": "0x00CF"}
    recorded = _RecordingRAM(bytes(ram))
    vector = observation_vector(recorded, spec_id="smb-tiles-v1", decoder=decoder)
    assert vector[1] == -1.0
    assert 0x0087 in recorded.reads
    assert 0x00CF in recorded.reads
    assert 0x03AE not in recorded.reads
    assert 0x03B9 not in recorded.reads


def test_unknown_decoder_toggles_are_rejected():
    ram = bytes(2048)
    with pytest.raises(ValueError):
        observation_vector(ram, spec_id="smb-tiles-v1", decoder={"x_bias": 8})
    with pytest.raises(ValueError):
        observation_vector(ram, spec_id="smb-tiles-v1", decoder={"enemy_x": "0x000A", "enemy_y": "0x000B"})
    with pytest.raises(ValueError):
        observation_spec("smb-tiles-v2")


def test_both_documents_omit_the_disabled_fields():
    narrow = observation_spec("smb-tiles-v1")
    wide = observation_spec("smb-tiles-v1w10")
    assert narrow["shape"] == [80]
    assert wide["shape"] == [110]
    assert narrow["low"] == -1.0 and narrow["high"] == 1.0
    assert narrow["layout"]["motion"]["enabled"] is False
    assert narrow["layout"]["previous_action"]["enabled"] is False
    assert len(observation_vector(bytes(2048), spec_id="smb-tiles-v1w10")) == 110
    ram = _ram()
    _anchor(ram, screen_x=40, level_x=40)
    ram[0x052C] = 0x03
    wide_vector = observation_vector(bytes(ram), spec_id="smb-tiles-v1w10")
    assert wide_vector[9] == 1.0


def test_progress_and_speed_stamps_stay_nine_floats():
    progress = INTEGRATION.stamp()
    speed = INTEGRATION.stamp("smb-1-1-speed")
    assert progress == {
        "actions": [list(chord) for chord in SMB_ACTIONS],
        "objective": "progress",
        "ram": 9,
    }
    assert "observation" not in progress
    assert "observation" not in speed
    assert speed["objective"] == "smb-1-1-speed"
    assert speed["ram"] == 9
    assert speed["actions"] == progress["actions"]
    assert len(ram_vector(bytes(2048))) == 9
    with pytest.raises(ValueError):
        INTEGRATION.stamp("smb-points")
    with pytest.raises(ValueError):
        INTEGRATION.stamp(observation="smb-tiles-v2")


def test_an_observation_stamp_uses_that_documents_length():
    stamped = INTEGRATION.stamp(observation="smb-tiles-v1")
    assert stamped["objective"] == "progress"
    assert stamped["ram"] == 80
    assert stamped["observation"] == "smb-tiles-v1"
    assert stamped["actions"] == INTEGRATION.stamp()["actions"]
    wide = INTEGRATION.stamp("smb-1-1-speed", "smb-tiles-v1w10")
    assert wide["objective"] == "smb-1-1-speed"
    assert wide["ram"] == 110
    assert wide["observation"] == "smb-tiles-v1w10"


def test_pipe_rule_uses_the_body_row_and_the_row_above():
    checks = _checks()
    rows = [[0] * 7 for _ in range(10)]
    for offset in range(7):
        rows[9][offset] = 1
    rows[7][1] = rows[7][2] = 1
    rows[8][1] = rows[8][2] = 1
    assert checks.floor_solid(rows, 8) is True
    assert checks.pipe_columns(rows, 8) == [1, 2]
    assert checks.air_above(rows, 8, [1, 2]) is True
    above_only = [[0] * 7 for _ in range(10)]
    above_only[9][0] = 1
    above_only[6][1] = above_only[7][1] = 1
    assert checks.pipe_columns(above_only, 8) == []
    body_only = [[0] * 7 for _ in range(10)]
    body_only[8][0] = 1
    assert checks.floor_solid(body_only, 8) is False
    rows[5][1] = 1
    assert checks.air_above(rows, 8, [1, 2]) is False


@pytest.mark.skipif(not _EXPECT.is_file(), reason="validator has not accepted a grid")
def test_accepted_dumps_match_the_recorded_screen():
    checks = _checks()
    expect = json.loads(_EXPECT.read_text(encoding="utf-8"))
    spec = observation_spec(expect["spec_id"])
    assert spec_digest(spec) == expect["spec_digest"]
    assert spec["decoder"] == expect["decoder"]
    width = int(expect["width"])
    height = int(expect["height"])
    ground = int(expect["ground_index"])
    decoded = {}
    for name, meta in expect["samples"].items():
        path = _FIXTURES / meta["file"]
        blob = path.read_bytes()
        assert len(blob) == 2048
        assert hashlib.sha256(blob).hexdigest() == meta["sha256"]
        vector = observation_vector(blob, spec_id=expect["spec_id"])
        changed = bytearray(blob)
        for address in _BUTTONS:
            changed[address] = (changed[address] + 128) & 0xFF
        assert observation_vector(bytes(changed), spec_id=expect["spec_id"]) == vector
        rows, hot = checks.split_vector(vector, width, height)
        assert checks.one_hot_index(hot) == meta["one_hot"]
        decoded[name] = (vector, rows)
    vectors = [decoded[name][0] for name in _PAIRWISE]
    assert all(name in decoded for name in _PAIRWISE)
    assert len(vectors) == len({tuple(vector) for vector in vectors})
    approach_rows = decoded["approach"][1]
    contact_rows = decoded["contact"][1]
    assert checks.pipe_columns(approach_rows, ground) == []
    assert checks.floor_solid(approach_rows, ground) is True
    pipes = checks.pipe_columns(contact_rows, ground)
    assert pipes and min(pipes) in (1, 2)
    assert min(pipes) == expect["samples"]["contact"]["pipe_min"]
    assert decoded["contact"][0][width * height + ground] == 1.0
    assert expect["samples"]["on-pipe"]["one_hot"] == ground - 2
    assert expect["samples"]["past"]["one_hot"] == ground
    assert decoded["past"][0] != decoded["contact"][0]
    goomba = expect["samples"]["goomba"]
    index = int(goomba["enemy_index"])
    assert decoded["goomba"][0][index] == -1.0
    assert goomba["enemy_col_offset"] in range(1, width)
    assert abs(int(goomba["enemy_window_row"]) - ground) in (0, 1)
