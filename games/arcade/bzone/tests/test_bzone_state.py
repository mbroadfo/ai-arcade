"""The decoder against a scripted recording: what was pressed is known, so what the RAM must show is known."""
import gzip
import json
import struct
from pathlib import Path

from games.arcade.bzone.state import decode

FIXTURES = Path(__file__).parent / "fixtures"
RAW = gzip.decompress((FIXTURES / "scripted_run.bin.gz").read_bytes())
RECORDS = [(struct.unpack("<I", RAW[i:i + 4])[0], decode(RAW[i + 4:i + 1028])) for i in range(0, len(RAW), 1028)]
EVENTS = json.loads((FIXTURES / "scripted_run.json").read_text())["events"]


def during(label, n=0):
    e = [x for x in EVENTS if x["label"] == label][n]
    return [s for f, s in RECORDS if e["start"] + 6 <= f <= e["end"]]


def at(frame):
    return min(RECORDS, key=lambda r: abs(r[0] - frame))[1]


def test_attract_then_a_game_with_three_lives_after_two_coins_and_start():
    first = RECORDS[0][1]
    assert not first.playing and first.game_over and first.lives == 0
    start = [x for x in EVENTS if x["label"] == "start"][0]
    after = at(start["end"] + 12)
    assert after.playing and not after.game_over and after.lives == 3 and after.credits == 0


def test_turning_left_raises_the_angle_steadily_round_a_full_circle():
    angles = [s.tank.angle for s in during("turn left")]
    steps = [(b - a) % 256 for a, b in zip(angles, angles[1:])]
    assert all(0 <= d <= 4 for d in steps) and sum(steps) > 256  # 20 s: more than one full turn, never backwards
    per_second = sum(steps) / (len(steps) * 6 / 60)
    assert 20 < per_second < 25


def test_each_death_takes_a_life_and_counts_a_hit_taken_while_the_windshield_cracks():
    seq = [s for _, s in RECORDS if s.playing]
    deaths = [(a, b) for a, b in zip(seq, seq[1:]) if b.lives == a.lives - 1]
    assert len(deaths) == 2
    for a, b in deaths:
        assert b.hits_taken == a.hits_taken + 1 and b.dying > 0
    assert all(s.hits == 0 for s in seq)  # the blind firing hit nothing (the screen showed 0000)
