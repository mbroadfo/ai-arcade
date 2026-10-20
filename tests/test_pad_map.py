"""pi/mame_human/pad_map.py: which joystick is which, whatever is plugged in."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "pi" / "mame_human")]

import pad_map  # noqa: E402
import panel_profiles as pp  # noqa: E402

PANEL = pp.load_panel()


def block(vendor, product, name, phys, event):
    return (f'I: Bus=0003 Vendor={vendor} Product={product} Version=0110\nN: Name="{name}"\nP: Phys={phys}\n'
            f"H: Handlers=event{event} js{event}\n")


P1 = block("0079", "0006", "DragonRise", "usb-xhci-hcd.0-1.2/input0", 7)
P2 = block("0079", "0006", "DragonRise", "usb-xhci-hcd.0-1.3/input0", 12)
F310 = block("046d", "c21d", "Logitech Gamepad F310", "usb-xhci-hcd.0-2.1/input0", 9)
AI = block("1209", "a101", "AI Arcade Player 1", "py-evdev-uinput", 13)
KEYBOARD = 'I: Bus=0003 Vendor=046d Product=4023 Version=0111\nN: Name="kbd"\nP: Phys=x\nH: Handlers=sysrq kbd event5\n'


def found(*blocks):
    return pad_map.assign(pad_map.parse_devices("\n".join(blocks)), PANEL)


def test_panel_alone_is_one_and_two():
    f = found(KEYBOARD, P1, P2)
    assert (f["joy1"], f["joy2"], f["pads"]) == (1, 2, {})


def test_ai_pads_never_take_a_number_and_are_counted():
    f = found(P1, P2, AI)
    assert (f["joy1"], f["joy2"], f["ai"]) == (1, 2, 1)


def test_a_gamepad_plugged_between_the_encoders_shifts_the_second_one():
    f = found(P1, F310, P2, AI)
    assert (f["joy1"], f["joy2"], f["pads"]) == (1, 3, {"P1": 2})


def test_a_gamepad_alone_is_player_one_and_the_missing_panel_leaves_no_dangling_numbers():
    f = found(F310)
    assert (f["joy1"], f["joy2"], f["pads"]) == (None, None, {"P1": 1})
    ports = dict(pp.mame_ports(PANEL, None, None, f["pads"]))
    assert ports["P1_BUTTON1"] == "KEYCODE_LCONTROL OR JOYCODE_1_BUTTON1"
    assert "JOYCODE_90" not in str(ports) and "JOYCODE_91" not in str(ports)
    assert ports["COIN1"].count("BUTTON7") == 1 and ports["START1"].count("BUTTON8") == 1


def test_only_the_second_encoder_plugged_in():
    f = found(P2)
    assert (f["joy1"], f["joy2"]) == (None, 1)
    ports = dict(pp.mame_ports(PANEL, f["joy1"], f["joy2"]))
    assert ports["P1_BUTTON1"] == "KEYCODE_LCONTROL"  # P1 falls back to the keyboard alone


def test_two_gamepads_play_one_and_two_beside_the_panel():
    f = found(P1, P2, F310, block("046d", "c21d", "Second F310", "usb-xhci-hcd.0-2.2/input0", 10))
    assert (f["joy1"], f["joy2"], f["pads"]) == (1, 4, {"P1": 2, "P2": 3})  # event order: P1, pad, pad, P2
    ports = dict(pp.mame_ports(PANEL, f["joy1"], f["joy2"], f["pads"]))
    assert "JOYCODE_1_BUTTON" in ports["P1_BUTTON1"] and "JOYCODE_2_BUTTON1" in ports["P1_BUTTON1"]
    assert "JOYCODE_4_BUTTON" in ports["P2_BUTTON1"] and "JOYCODE_3_BUTTON1" in ports["P2_BUTTON1"]


def test_battlezone_fire_keeps_the_pads_button():
    games = pp.game_ports(PANEL, 1, 2, {"P1": 3}, pp.load_game_controls())
    assert dict(games["bzone"])["P1_BUTTON1"] == "JOYCODE_2_BUTTON12 OR JOYCODE_3_BUTTON1"


def test_ctrlr_still_parses():
    import xml.etree.ElementTree as ET
    ET.fromstring(pp.mame_ctrlr(PANEL, None, 2, {"P1": 1}))


def test_sdl_guid_matches_what_sdl_reports():
    assert pp.sdl_guid("0003", "046d", "c21d", "4014", "Logitech Gamepad F310") == "030005ff6d0400001dc2000014400000"
    assert pp.sdl_guid("0003", "0079", "0006", "0110", "DragonRise Inc.   Generic   USB  Joystick  ") == PANEL["device"]["sdl_guid"]


def test_only_pads_es_has_not_met_are_taught(tmp_path):
    devices = pad_map.parse_devices("\n".join([P1, F310, AI]))
    es = tmp_path / "es_input.cfg"
    es.write_text("<inputList>\n</inputList>\n", encoding="utf-8")
    assert pad_map.teach_es(devices, PANEL, es) == ["Logitech Gamepad F310"]
    text = es.read_text(encoding="utf-8")
    assert text.count('deviceName="Logitech Gamepad F310"') == 1 and 'type="hat"' in text
    assert "AI Arcade" not in text and "DragonRise" not in text  # panel and AI pads have their own entries
    assert pad_map.teach_es(devices, PANEL, es) == []  # nothing more to add the second time


def test_retroarch_players_the_panel_is_one_and_two_then_the_pads_and_ai_pads_are_skipped():
    devices = pad_map.parse_devices("\n".join([P1, P2, F310, AI]))  # events 7, 9, 12, 13 -> P1, F310, P2, AI
    assert pad_map.retroarch_players(devices, PANEL) == [(1, 0, "P1"), (2, 2, "P2"), (3, 1, None)]
    assert pad_map.retroarch_players(pad_map.parse_devices("\n".join([P1, P2, AI])), PANEL) == [(1, 0, "P1"), (2, 1, "P2")]


def test_retroarch_explicit_binds_follow_the_player_not_the_port():
    pad, hotkeys = pp.retroarch_player_binds(pp.retroarch_gamepad_autoconfig("F310", "046d", "c21d"), 1)
    assert "input_player1_select_btn = \"6\"" in pad and "input_player1_up_btn = \"h0up\"" in pad
    assert 'input_player1_left_axis = "-0"' in pad and 'input_player1_down_axis = "+1"' in pad  # the stick moves too
    assert not any(l.startswith(("input_device", "input_driver", "input_vendor")) for l in pad)
    assert 'input_enable_hotkey_btn = "8"' in hotkeys and 'input_exit_emulator_btn = "7"' in hotkeys
    p2, no_hotkeys = pp.retroarch_player_binds(pp.retroarch_autoconfig(PANEL, "P2"), 2)
    assert "input_player2_b_btn" in " ".join(p2) and no_hotkeys == []


def test_retroarch_autoconfig_is_written_once_for_unknown_pads(tmp_path):
    devices = pad_map.parse_devices("\n".join([P1, F310, AI]))
    assert pad_map.teach_retroarch(devices, PANEL, tmp_path) == ["Logitech Gamepad F310"]
    text = (tmp_path / "Logitech Gamepad F310.cfg").read_text(encoding="utf-8")
    assert 'input_select_btn = "6"' in text and 'input_vendor_id = "1133"' in text and "h0up" in text
    assert pad_map.teach_retroarch(devices, PANEL, tmp_path) == []


def test_a_games_own_folder_changes_the_pads_buttons_and_no_folder_means_the_defaults():
    games = pp.load_game_controls()
    pad, _ = pp.retroarch_player_binds(pp.retroarch_gamepad_autoconfig("F310", "046d", "c21d"), 1)
    for rom in ("asteroid", "astdelux"):  # thrust moves from X to B
        changed = pad_map.apply_pad_overrides(pad, 1, games, f"/home/pi/RetroPie/roms/arcade/{rom}.zip")
        assert 'input_player1_y_btn = "1"' in changed and 'input_player1_a_btn = "2"' in changed
        assert 'input_player1_b_btn = "0"' in changed and 'input_player1_x_btn = "3"' in changed  # fire and hyperspace stay
    assert pad_map.apply_pad_overrides(pad, 1, games, "/roms/pacman.zip") == pad
    assert pad_map.apply_pad_overrides(pad, 1, {}, "/roms/asteroid.zip") == pad  # the framework alone knows no game


def test_the_framework_names_no_game():
    import re
    for path in (ROOT / "tools" / "panel_profiles.py", ROOT / "pi" / "mame_human" / "pad_map.py", ROOT / "pi" / "controls" / "panel.json"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b(asteroid|astdelux|bzone|bzonea|bradley|dkong|pisces)\b", text), path.name


def mouse_block(vendor, product, name, phys, event):
    return (f'I: Bus=0003 Vendor={vendor} Product={product} Version=0111\nN: Name="{name}"\nP: Phys={phys}\n'
            f"H: Handlers=mouse{event} event{event}\n")


SPINNER = mouse_block("fafa", "0060", "GGG TurboTwist 2 Spinner", "usb-xhci-hcd.0-1.1/input0", 4)
TRACKBALL = mouse_block("fafa", "0020", "GGG Electric ICE-T Trackball", "usb-xhci-hcd.0-1.4/input0", 6)
LOGITECH = mouse_block("046d", "4023", "Logitech Wireless Mouse", "usb-xhci-hcd.0-2/input1:2", 3)


def test_retroarch_picks_the_mouse_a_game_asks_for_and_none_when_it_is_missing():
    mice = pad_map.parse_devices("\n".join([SPINNER, LOGITECH, TRACKBALL]), r"mouse\d+")  # event order 3, 4, 6
    assert [m["name"] for m in mice] == ["Logitech Wireless Mouse", "GGG TurboTwist 2 Spinner", "GGG Electric ICE-T Trackball"]
    assert pad_map.retroarch_mouse_index(mice, PANEL, "spinner") == 1
    assert pad_map.retroarch_mouse_index(mice, PANEL, "trackball") == 2
    assert pad_map.retroarch_mouse_index(mice, PANEL, None) is None
    assert pad_map.retroarch_mouse_index(pad_map.parse_devices(LOGITECH, r"mouse\d+"), PANEL, "trackball") is None


def test_every_game_that_plays_with_the_spinner_or_trackball_says_so_in_its_own_folder():
    games = pp.load_game_controls()
    pointers = {rom: g["pointer"] for rom, g in games.items() if "pointer" in g}
    assert {"missile", "centiped", "wacko", "marble"} <= {r for r, p in pointers.items() if p == "trackball"}
    assert {"tempest", "arkanoid", "sbrkout", "superbug"} <= {r for r, p in pointers.items() if p == "spinner"}
    assert set(pointers.values()) <= {"spinner", "trackball"}


def test_retroarch_with_only_a_gamepad_it_is_player_one():
    assert pad_map.retroarch_players(pad_map.parse_devices("\n".join([F310, AI])), PANEL) == [(1, 0, None)]
