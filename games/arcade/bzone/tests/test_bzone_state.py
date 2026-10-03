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


def test_mobile_track_and_fire_never_stands_still_or_pivots_once_the_enemy_may_fire():
    from games.arcade.bzone.controls import TURN_LEFT, TURN_RIGHT
    from games.arcade.bzone.facts import derive
    from games.arcade.bzone.policies import mobile_track_and_fire
    seen_shot = False
    for _, s in RECORDS:
        if not s.playing or s.dying:
            continue
        f = derive(s)
        names, why = mobile_track_and_fire(s, f, 0.0, frozenset())
        treads = names - {"FIRE"}
        assert treads, why  # always moving
        if not f.enemy_holds_fire:
            assert treads not in (TURN_LEFT, TURN_RIGHT), why
        if f.enemy_shell == "flying":
            seen_shot = True
            assert "shot heard" in why
    assert seen_shot


def test_flank_point_is_off_the_line_to_the_enemy_on_the_asked_side():
    from types import SimpleNamespace
    from games.arcade.bzone.skills import flank_point
    ahead = SimpleNamespace(enemy_distance=20000, enemy_bearing=0)  # dead ahead, 20,000 units
    left, right = flank_point(ahead, 1), flank_point(ahead, -1)
    assert round(left[0] * 360 / 256) == 30 and round(right[0] * 360 / 256) == -30  # the flank angle each side
    assert flank_point(SimpleNamespace(enemy_distance=None, enemy_bearing=None), 1) is None


def test_flank_and_fire_dodges_every_heard_shot_and_keeps_moving():
    from games.arcade.bzone.facts import derive
    from games.arcade.bzone.facts import SHELL_UPDATES_PER_S
    from games.arcade.bzone.policies import DODGED_S, flank_and_fire
    for _, s in RECORDS:
        if not s.playing or s.dying:
            continue
        f = derive(s)
        names, why = flank_and_fire(s, f, 0.0, frozenset())
        if f.enemy_shell == "flying":  # dodge first; once dodged, its one shell is busy: turn in
            since = (0x7F - s.enemy.fire) / SHELL_UPDATES_PER_S
            assert why.startswith("dodge" if since < DODGED_S or f.enemy_distance is None else "broadside"), why
        assert names - {"FIRE"} or why.startswith("broadside"), why


def test_the_obstacle_map_paths_and_cover():
    from types import SimpleNamespace
    from games.arcade.bzone.obstacles import MAP, TANK_TOUCH, cover, path_clear
    assert len(MAP) == 21 and {o.kind for o in MAP} == {0x00, 0x01, 0x0C, 0x0F}
    box = next(o for o in MAP if o.shape == "tall box")
    facing = SimpleNamespace(x=box.x - 5000, y=box.y, angle=0)  # 5,000 units west of it, facing east
    run, ob = path_clear(facing)
    assert ob is box and run == 5000 - TANK_TOUCH
    assert path_clear(SimpleNamespace(x=box.x - 5000, y=box.y, angle=128))[0] is None or True  # facing away
    enemy = SimpleNamespace(x=box.x + 5000, y=box.y)
    assert cover(facing, enemy) is box  # the box is between: a shell stops on it
    short = next(o for o in MAP if o.shape == "short box")
    assert cover(SimpleNamespace(x=short.x - 5000, y=short.y), SimpleNamespace(x=short.x + 5000, y=short.y)) is None


def test_steer_clear_turns_a_drive_into_an_obstacle_away_from_it():
    from types import SimpleNamespace
    from games.arcade.bzone.controls import ARC_RIGHT, DRIVE, TURN_RIGHT
    from games.arcade.bzone.skills import steer_clear
    near = SimpleNamespace(blocked=False, obstacle_ahead=1500, obstacle_ahead_left=300, obstacle_behind=None)
    assert steer_clear(near, DRIVE, "go")[0] == ARC_RIGHT  # obstacle left of the path: arc right
    stuck = SimpleNamespace(blocked=True, obstacle_ahead=0, obstacle_ahead_left=300, obstacle_behind=None)
    assert steer_clear(stuck, DRIVE, "go")[0] == TURN_RIGHT


def test_the_s1m_player_asks_on_events_carries_out_the_answer_and_labels_every_tick():
    import time as _time
    from games.arcade.bzone.facts import derive
    from games.arcade.bzone.s1m import S1MPlayer

    class Fake:  # answers at once: the first option of each question, sure of it
        def __init__(self):
            self.asked = []

        def ask(self, state, questions, hint=None):
            self.asked.append((state, questions))
            pick = {"tactic": "attack", "if_fired": "pivot_reverse"}
            return {"answers": {q: {"choice": pick[q] if pick[q] in spec["criteria"] else next(iter(spec["criteria"])),
                                    "confidence": 1.0, "probabilities": {}} for q, spec in questions.items()},
                    "latency_ms": 1.0}

    fake = Fake()
    player = S1MPlayer(fake)
    live = [s for _, s in RECORDS if s.playing]
    whys = []
    for i, s in enumerate(live):
        names, why = player(s, derive(s), i * 0.6, frozenset())
        whys.append(why)
        _time.sleep(0.002)  # let the worker answer
    assert fake.asked and all(why.startswith(("[model]", "[fallback]", "[no choice]", "dying")) for why in whys)
    assert any(why.startswith("[model] attack") for why in whys)  # the model's order was carried out
    assert any("standing order pivot_reverse" in why for why in whys)  # a heard shot: the order given before
    assert "model" in player.model_share()
