"""Phase 3 transport pieces: holding several actions at once, region files with cpu/space, the game's image window."""
import pytest

from broker_link import BrokerLink
from games.arcade import pacman
from state_regions import expand, regions_lua


class Link(BrokerLink):
    def __init__(self):
        super().__init__("nowhere")
        self.sent = []

    def send(self, payload):
        self.sent.append((payload["op"], payload.get("action")))
        return {"ok": True}


def test_holding_a_set_releases_what_is_no_longer_wanted_then_presses_what_is_new():
    link = Link()
    link.hold({"LEFT", "BUTTON_1"})
    assert link.sent == [("press", "BUTTON_1"), ("press", "LEFT")] and link.held is None
    link.sent.clear()
    link.hold({"UP", "BUTTON_1"})  # fire stays held while the direction changes
    assert link.sent == [("release", "LEFT"), ("press", "UP")]
    link.sent.clear()
    link.hold({"UP", "BUTTON_1"})
    assert link.sent == []


def test_a_held_set_can_include_another_players_controls():
    link = Link()
    sent = []
    link.send = lambda payload: sent.append((payload["op"], payload["player"], payload["action"]))
    link.hold({(1, "UP"), (2, "UP")})
    assert sorted(sent) == [("press", 1, "UP"), ("press", 2, "UP")]
    sent.clear()
    link.hold({(1, "UP"), (2, "DOWN")})
    assert sent == [("release", 2, "UP"), ("press", 2, "DOWN")]


def test_steer_is_one_direction_held_exactly_as_before():
    link = Link()
    link.steer("LEFT")
    link.steer("LEFT")
    link.steer("UP")
    link.steer(None)
    assert link.sent == [("press", "LEFT"), ("release", "LEFT"), ("press", "UP"), ("release", "UP")]
    assert link.held is None
    link.steer("DOWN")
    assert link.held == "DOWN"


def test_the_regions_file_names_a_cpu_and_space_defaulting_to_the_main_cpu():
    text = regions_lua([(0x4D00, 0x4D3F, 1), (0x4040, 0x43BF, 4), (0x0100, 0x01FF, 2, ":audiocpu", "program")])
    assert text == ('return {{0x4D00, 0x4D3F, 1, ":maincpu", "program"}, {0x4040, 0x43BF, 4, ":maincpu", "program"}, '
                    '{0x100, 0x1FF, 2, ":audiocpu", "program"}}\n')


def test_the_image_window_comes_from_the_game_and_has_no_default():
    regions = [(0x4E00, 0x4E01, 1), (0x4D00, 0x4D00, 1)]
    image = expand(b"\x01\x02\x03", regions, *pacman.IMAGE)
    assert len(image) == pacman.IMAGE[1] and image[0xE00:0xE02] == b"\x01\x02" and image[0xD00] == 3
    with pytest.raises(TypeError):
        expand(b"\x01\x02\x03", regions)  # a game that forgets its IMAGE fails loudly
