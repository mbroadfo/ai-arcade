"""The blue (frightened) flags: 4DA6 says an energizer is active, 4DA7-4DAA are red, pink, blue, orange.

The decoder used to read 4DA6-4DA9 as the four ghosts (one off): red always looked blue while an energizer was active,
and a ghost back from the house was reported normal under another ghost's name. Settled on the recordings: in all 29
cases where one flag cleared while the energizer was still active, it was the flag of the ghost whose eyes had just
reached home. The Ms. Pac-Man disassembly (shared code) documents the same layout.
"""
from games.arcade.pacman.state import GHOSTS, decode
from games.arcade.pacman.tests import replay

WITHIN = 5  # frames between the eyes reaching home and that ghost's blue flag clearing


def states():
    return [decode(img) for _, img in replay.load_frames()]


def test_a_ghost_back_from_the_house_stops_being_blue_and_no_other_ghost_changes():
    seq = states()
    checked = 0
    for i in range(1, len(seq)):
        for name in GHOSTS:
            if seq[i - 1].eyes[name] and not seq[i].eyes[name] and any(seq[i].frightened.values()):
                window = seq[i - 1: i + WITHIN + 1]
                cleared = {n for a, b in zip(window, window[1:]) for n in GHOSTS if a.frightened[n] and not b.frightened[n]}
                assert cleared == {name}, (i, name, cleared)
                checked += 1
    assert checked >= 1  # the recording has an eaten ghost going home while others are still blue


def test_while_an_energizer_is_active_the_flags_clear_one_ghost_at_a_time():
    seq = states()
    clears = 0
    for a, b in zip(seq, seq[1:]):
        cleared = [n for n in GHOSTS if a.frightened[n] and not b.frightened[n]]
        if cleared and any(b.frightened.values()):
            clears += 1
            assert len(cleared) == 1  # one ghost leaves blue mode, the others stay blue
    assert clears >= 1
