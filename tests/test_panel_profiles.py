import xml.etree.ElementTree as ET

import panel_profiles as pp

PANEL = pp.load_panel()
ES = '''<?xml version="1.0"?>
<inputList>
  <inputAction type="onfinish">
    <command>/x/inputconfiguration.sh</command>
  </inputAction>
  <inputConfig type="joystick" deviceName="AI Arcade Player 1" deviceGUID="030000000912000001a1000001000000">
    <input name="up" type="axis" id="1" value="-1"/>
  </inputConfig>
  <inputConfig type="keyboard" deviceName="Keyboard" deviceGUID="-1">
    <input name="a" type="key" id="97" value="1"/>
  </inputConfig>
</inputList>
'''


def ports():
    return dict(pp.mame_ports(PANEL))


def test_button_numbers_are_codes_minus_the_first_code():
    assert pp.index(PANEL, "P1", "A") == 11 and pp.index(PANEL, "P2", "STAR") == 0


def test_the_flight_buttons_double_player_twos_first_two_buttons_only():
    assert pp.actions(PANEL, "P2")[1] == [5, 11] and pp.actions(PANEL, "P2")[2] == [3, 10]
    assert pp.actions(PANEL, "P1")[1] == [11]


def test_the_es_entry_is_xml_with_the_sdl_name_and_guid_and_players_ones_buttons():
    root = ET.fromstring("<r>" + pp.es_input_entry(PANEL) + "</r>")
    cfg = root.find("inputConfig")
    assert cfg.get("deviceName") == "DragonRise Inc. Generic USB Joystick"
    assert cfg.get("deviceGUID") == "0300457e790000000600000010010000"
    inputs = {i.get("name"): (i.get("type"), i.get("id"), i.get("value")) for i in cfg.findall("input")}
    assert inputs["a"] == ("button", "11", "1") and inputs["b"] == ("button", "9", "1")
    assert inputs["up"] == ("axis", "1", "-1") and inputs["right"] == ("axis", "0", "1")
    assert inputs["start"] == ("button", "4", "1") and inputs["select"] == ("button", "2", "1")


def test_merging_adds_then_replaces_and_leaves_other_devices_alone():
    entry = pp.es_input_entry(PANEL)
    once = pp.merge_es_input(ES, entry, "DragonRise Inc. Generic USB Joystick")
    twice = pp.merge_es_input(once, entry, "DragonRise Inc. Generic USB Joystick")
    assert once == twice  # idempotent
    root = ET.fromstring(once)
    assert [c.get("deviceName") for c in root.findall("inputConfig")] == ["AI Arcade Player 1", "Keyboard",
                                                                           "DragonRise Inc. Generic USB Joystick"]
    assert ES.split("</inputList>")[0] in once  # everything that was there is still there, byte for byte


def test_the_retroarch_autoconfig_names_the_raw_device_and_maps_arcade_buttons_in_order():
    text = pp.retroarch_autoconfig(PANEL)
    assert 'input_device = "DragonRise Inc.   Generic   USB  Joystick  "' in text
    for line in ('input_b_btn = "11"', 'input_a_btn = "9"', 'input_y_btn = "8"', 'input_x_btn = "10"', 'input_l_btn = "7"',
                 'input_r_btn = "6"', 'input_select_btn = "5"', 'input_start_btn = "4"', 'input_exit_emulator_btn = "3"',
                 'input_menu_toggle_btn = "2"', 'input_up_axis = "-1"', 'input_right_axis = "+0"'):
        assert line in text


def test_mame_maps_each_player_to_its_own_encoder_and_the_second_stick_is_inverted():
    p = ports()
    assert p["P1_JOYSTICK_UP"].startswith("JOYCODE_1_YAXIS_UP_SWITCH")
    assert p["P2_JOYSTICK_UP"].startswith("JOYCODE_2_YAXIS_DOWN_SWITCH")  # P2 wiring: up reads Y positive
    assert p["P2_JOYSTICK_LEFT"].startswith("JOYCODE_2_XAXIS_RIGHT_SWITCH")
    assert p["P1_BUTTON1"].startswith("JOYCODE_1_BUTTON12") and p["P1_BUTTON6"].startswith("JOYCODE_1_BUTTON7")
    assert p["P2_BUTTON1"].startswith("JOYCODE_2_BUTTON6 OR JOYCODE_2_BUTTON12")  # A, and the flight trigger
    assert p["P2_BUTTON2"].startswith("JOYCODE_2_BUTTON4 OR JOYCODE_2_BUTTON11")


def test_mame_coin_start_and_menu_keys_follow_the_decisions():
    p = ports()
    assert p["COIN1"].startswith("JOYCODE_1_BUTTON6") and p["START1"].startswith("JOYCODE_1_BUTTON5")
    assert p["COIN2"].startswith("JOYCODE_2_BUTTON7") and p["START2"].startswith("JOYCODE_2_BUTTON8")
    assert p["UI_CONFIGURE"].startswith("JOYCODE_1_BUTTON3")  # Tab on the P1 encoder
    assert p["UI_CANCEL"].startswith("JOYCODE_1_BUTTON4")  # Esc on the P1 encoder
    assert p["UI_SELECT"].startswith("JOYCODE_2_BUTTON9")  # Enter on the P2 encoder
    assert p["UI_PAUSE"].startswith("JOYCODE_2_BUTTON10")  # Pause on the P2 encoder


def test_twin_stick_games_get_the_second_stick_as_the_right_stick():
    p = ports()
    assert p["P1_JOYSTICKLEFT_UP"] == "JOYCODE_1_YAXIS_UP_SWITCH"
    assert p["P1_JOYSTICKRIGHT_UP"] == "JOYCODE_2_YAXIS_DOWN_SWITCH"


def test_the_joystick_numbers_can_be_moved_for_a_test_with_other_devices():
    p = dict(pp.mame_ports(PANEL, joy1=5, joy2=6))
    assert p["P1_BUTTON1"].startswith("JOYCODE_5_BUTTON12") and p["P2_BUTTON1"].startswith("JOYCODE_6_BUTTON6")


def test_the_ctrlr_file_is_valid_xml_with_every_port_once_in_each_system():
    root = ET.fromstring(pp.mame_ctrlr(PANEL))
    for system in root.findall("system"):
        types = [p.get("type") for p in system.iter("port")]
        assert len(types) == len(set(types))
    default = next(s for s in root.findall("system") if s.get("name") == "default")
    assert len(list(default.iter("port"))) == len(pp.mame_ports(PANEL))


def test_mame_ini_switches_its_controller_file():
    ini = "rompath x\nctrlr                     aiarcade\nvideo accel\n"
    assert "ctrlr                     panel\n" in pp.mame_ini_with_ctrlr(ini, "panel")


def test_expected_fields_name_what_each_control_should_press():
    e = pp.expected_mame_fields(PANEL)
    assert e[("P1", "A")] == ["P1 Button 1"] and e[("P2", "FLIGHT1")] == ["P2 Button 1"]
    assert e[("P2", "START")] == ["2 Players Start"] and e[("P1", "COIN")] == ["Coin 1"]


# --- tools/synth_panel.py: how a control name becomes events (no Pi needed)
import synth_panel  # noqa: E402


def test_the_pretend_panel_turns_names_into_the_encoders_events():
    s = synth_panel.SynthPanel(None, PANEL)
    assert s.events("P1", "A", True) == [(0, synth_panel.EV_KEY, 299, 1)]
    assert s.events("P1", "A", False) == [(0, synth_panel.EV_KEY, 299, 0)]
    assert s.events("P1", "UP", True) == [(0, synth_panel.EV_ABS, 1, 0)]  # P1 up reads Y negative
    assert s.events("P2", "UP", True) == [(1, synth_panel.EV_ABS, 1, 255)]  # P2 wiring: up reads Y positive
    assert s.events("P2", "LEFT", False) == [(1, synth_panel.EV_ABS, 0, 127)]  # released: back to the middle
    assert s.events("P2", "FLIGHT1", True) == [(1, synth_panel.EV_KEY, 299, 1)]


def test_the_launchers_for_the_four_games_move_and_nothing_else_changes():
    text = 'arcade_bzone = "advmame"\narcade_tempest = "advmame"\nnes_x = "lr-fceumm"\n'
    new = pp.move_launchers(text)
    assert 'arcade_bzone = "mame-0.251"' in new and 'arcade_tempest = "advmame"' in new and 'nes_x = "lr-fceumm"' in new
    assert 'arcade_dkong = "mame-0.251"' in new  # added when it had no line
    assert pp.move_launchers(new) == new  # idempotent


def test_advmame_gets_only_the_buttons_its_event_driver_can_see():
    visible_p1 = pp.advmame_visible_actions(PANEL, "P1")
    assert visible_p1 == ["B", "X", "SNOWFLAKE", "STAR"]  # A (299) and Y (298) are not visible to it
    assert pp.advmame_visible_actions(PANEL, "P2") == ["A", "Y"]
    values = dict(pp.advmame_inputs(PANEL))
    assert values["coin1"].startswith("joystick_button[0079_0006,b]") and values["start1"].startswith("joystick_button[0079_0006,y]")
    assert values["p2_button1"].startswith("joystick_button[0079_0006_2,b]") and "p1_button5" not in values
    assert values["p1_doubleright_up"] == "joystick_digital[0079_0006_2,stick,y,down]"  # P2's stick is inverted


def test_the_advmame_rc_keeps_every_other_line():
    rc = "config save_at_exit\ndevice_joystick auto\ninput_map[coin1] auto\ninput_map[p1_up] auto\n"
    new = pp.merge_advmame_rc(rc, pp.advmame_inputs(PANEL))
    assert new.startswith("config save_at_exit\ndevice_joystick auto\n")
    assert "input_map[coin1] joystick_button[0079_0006,b] or keyboard[0,5]" in new and "input_map[p1_up] joystick_digital" in new
    assert pp.merge_advmame_rc(new, pp.advmame_inputs(PANEL)) == new


def test_battlezones_fire_is_the_flight_sticks_trigger_not_player_ones_a():
    root = ET.fromstring(pp.mame_ctrlr(PANEL))
    for game in ("bzone", "bzonea"):
        system = next(s for s in root.findall("system") if s.get("name") == game)
        ports = {p.get("type"): p.findtext("newseq") for p in system.iter("port")}
        assert ports == {"P1_BUTTON1": "JOYCODE_2_BUTTON12"}  # the P2 encoder's code 299
    default = next(s for s in root.findall("system") if s.get("name") == "default")
    assert {p.get("type"): p.findtext("newseq") for p in default.iter("port")}["P1_BUTTON1"].startswith("JOYCODE_1_BUTTON12")


def test_a_game_dip_is_added_to_a_cfg_that_keeps_its_counters_and_replaced_when_there_already():
    mame_cfg = '\ufeff<?xml version="1.0"?>\n<mameconfig version="10">\n    <system name="bzone">\n        <counters>\n            <coins index="0" number="28" />\n        </counters>\n    </system>\n</mameconfig>\n'
    new = pp.set_game_dip(mame_cfg, "bzone", ":DSW1", 3, 3, 2)
    root = ET.fromstring(new)
    assert root.find("system/counters/coins").get("number") == "28"
    assert root.find("system/input/port").attrib == {"tag": ":DSW1", "type": "DIPSWITCH", "mask": "3", "defvalue": "3", "value": "2"}
    assert pp.set_game_dip(new, "bzone", ":DSW1", 3, 3, 0).count("DIPSWITCH") == 1  # replaced, not added again
    assert pp.set_game_dip(None, "bzone", ":DSW1", 3, 3, 2).count("DIPSWITCH") == 1  # no file yet
