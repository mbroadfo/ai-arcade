"""The refactoring safety net: a recorded minute of play gives exactly the stored decisions log (tests/replay.py)."""
import difflib

import pytest

from games.arcade.pacman.tests import replay


@pytest.mark.parametrize("config", sorted(replay.CONFIGS))
def test_a_recorded_minute_of_play_gives_the_stored_decisions(config):
    got, want = replay.replay(config), replay.stored(config)
    if got != want:
        diff = "\n".join(list(difflib.unified_diff(want.splitlines(), got.splitlines(), "stored", "now", lineterm=""))[:40])
        pytest.fail(f"the {config} replay changed. A bug, or a deliberate change in play: then run "
                    f"`python -m games.arcade.pacman.tests.replay --update` and say why in the commit.\n{diff}")
