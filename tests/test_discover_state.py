from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import discover_state as ds


def snap(**cells):
    """64-byte snapshot with the given {index: value} cells set (keys passed as c<index>)."""
    data = bytearray(64)
    for key, value in cells.items():
        data[int(key[1:])] = value
    return bytes(data)


def test_credits_rises_on_coin_and_drops_on_start():
    a = snap()
    credits = ds.find_credits(a, a, a, snap(c5=2), snap(c5=2), snap(c5=1))
    assert credits == [5]


def test_credits_ignores_bytes_that_never_drop():
    a = snap()
    assert ds.find_credits(a, a, a, snap(c5=1), snap(c5=1), snap(c5=1)) == []


def test_lives_steps_down_and_ignores_rise_after_game_over():
    series = [snap(c3=v) for v in (3, 3, 2, 2, 1, 1, 0, 0, 1, 1)]  # demo restarts with 1
    assert [h[0] for h in ds.find_lives(series)] == [3]


def test_lives_accepts_wrap_to_255():
    series = [snap(c3=v) for v in (2, 1, 1, 0, 255)]
    assert [h[0] for h in ds.find_lives(series)] == [3]


def test_counters_accept_bcd_carry_and_reject_two_way_motion():
    score = [0x60, 0x20, 0x70, 0x40, 0x10]  # +60, +50, +70, +70 mod 100
    wobble = [10, 12, 9, 13, 8]
    play = [snap(c1=a, c2=b) for a, b in zip(score, wobble)]
    idle = [snap(c1=0x10, c2=8)] * 4
    assert [h[0] for h in ds.find_counters(play, idle)] == [1]


def test_counters_require_constant_while_idle():
    play = [snap(c1=v) for v in (1, 2, 3, 4, 5)]
    idle = [snap(c1=1), snap(c1=2)]
    assert ds.find_counters(play, idle) == []


def holds_with(x_values, y_values):
    """Build L/R/U/D x4 holds where cell 1 is the x byte and cell 2 the y byte."""
    holds = {}
    for n in range(1, 5):
        for key, dx, dy in (("L", x_values[0], 0), ("R", x_values[1], 0),
                            ("U", 0, y_values[0]), ("D", 0, y_values[1])):
            holds[f"{key}{n}"] = (snap(c1=100, c2=100), snap(c1=100 + dx, c2=100 + dy))
    return holds


def test_position_axes_are_separated():
    horiz, vert = ds.find_position(holds_with((5, -5), (-4, 4)))
    assert [h[0] for h in horiz] == [1]
    assert [v[0] for v in vert] == [2]


def test_moves_name_two_axes_of_held_controls():
    moves = ds.parse_moves("turn:L=1.DOWN+2.UP/R=1.UP+2.DOWN;drive:F=1.UP+2.UP/B=1.DOWN+2.DOWN")
    assert moves[0] == ("turn", ("L", [(1, "DOWN"), (2, "UP")]), ("R", [(1, "UP"), (2, "DOWN")]))
    assert [m[0] for m in moves] == ["turn", "drive"]
    holds = {}
    for n in range(1, 5):
        for key, dx, dy in (("L", 5, 0), ("R", -5, 0), ("F", 0, 3), ("B", 0, -3)):
            holds[f"{key}{n}"] = (snap(c1=100, c2=100), snap(c1=100 + dx, c2=100 + dy))
    turn, drive = ds.find_position(holds, moves)
    assert [t[0] for t in turn] == [1] and [d[0] for d in drive] == [2]


def mirrored(value):
    """64-byte image whose second half mirrors the first (like 4Cxx == 6Cxx), cell 5 = value."""
    half = bytearray(32)
    half[5] = value
    return bytes(half) * 2


def test_mirrors_collapse_to_lowest_address():
    snaps = [mirrored(1), mirrored(2)]
    assert ds.collapse_mirrors([5, 37], snaps, radius=4) == [5]


def test_unrelated_bytes_that_move_together_are_not_mirrors():
    snaps = [snap(c4=7, c5=1, c19=9, c20=1), snap(c4=7, c5=2, c19=9, c20=2)]
    assert ds.collapse_mirrors([5, 20], snaps, radius=2) == [5, 20]
