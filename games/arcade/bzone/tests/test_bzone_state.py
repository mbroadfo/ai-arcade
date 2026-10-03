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
    per_second = sum(steps) / (len(steps) * 6 / 41)  # the game's frame counter runs at about 41 a second
    assert 14 < per_second < 17


def test_each_death_takes_a_life_and_counts_a_hit_taken_while_the_windshield_cracks():
    seq = [s for _, s in RECORDS if s.playing]
    deaths = [(a, b) for a, b in zip(seq, seq[1:]) if b.lives == a.lives - 1]
    assert len(deaths) == 2
    for a, b in deaths:
        assert b.hits_taken == a.hits_taken + 1 and b.dying > 0
    assert all(s.hits == 0 for s in seq)  # the blind firing hit nothing (the screen showed 0000)


def test_the_enemys_bearing_matches_the_games_own_within_one_unit():
    from games.arcade.bzone.facts import relative
    live = [s for _, s in RECORDS if s.playing and not s.dying]
    close = sum(abs(abs(relative(s.tank, (s.enemy.x, s.enemy.y))) - s.game_turn) <= 1 for s in live)
    assert len(live) > 300 and close >= 0.98 * len(live)


def test_beyond_the_radar_a_player_knows_only_the_side():
    from games.arcade.bzone.facts import derive
    for _, s in RECORDS:
        if s.playing:
            f = derive(s)
            assert f.enemy_side in ("ahead", "left", "right", "rear")
            if not f.enemy_on_radar and f.enemy_side != "ahead":
                assert f.enemy_bearing is None and f.enemy_distance is None and f.on_target is None


def test_the_hit_radius_follows_the_games_formula_head_on_to_side_on():
    from games.arcade.bzone.facts import hit_radius
    assert hit_radius(0, 0) == 224 and hit_radius(64, 0) == hit_radius(0, 64) == 320
    assert hit_radius(128, 0) == 224  # facing each other is head-on too


def test_each_death_was_an_enemy_shell_whose_path_crossed_the_tank():
    from games.arcade.bzone.facts import derive, shell_pass
    seq = [s for _, s in RECORDS if s.playing]
    deaths = [i for i in range(1, len(seq)) if seq[i].lives == seq[i - 1].lives - 1]
    for i in deaths:
        assert seq[i].enemy.fire >= 0x80  # the shell is exploding as the life goes
        flying = [s for s in seq[max(0, i - 15):i] if 0 < s.enemy.fire < 0x80]
        assert flying and all(derive(s).enemy_shell == "flying" for s in flying)
        passes = [shell_pass(s, seen_only=False) for s in flying]  # both came from off screen: a fact only in view
        assert all(abs(miss) < 224 for miss, _ in passes)
        assert passes[-1][1] < 0.15  # it arrived when the estimate said
        assert all(derive(s).shell_miss is None for s in flying)


def test_the_score_is_hits_read_as_bcd_thousands():
    from games.arcade.bzone.state import bcd
    assert bcd(0x18) == 18 and bcd(0x06) == 6 and bcd(0x0100) == 100  # the screen showed 18000 with HITS = $18


def test_the_scripts_compile():  # no test imports them: a broken lab.py would otherwise show only on the cabinet
    import py_compile
    for script in (Path(__file__).parents[1] / "scripts").glob("*.py"):
        py_compile.compile(str(script), doraise=True)
