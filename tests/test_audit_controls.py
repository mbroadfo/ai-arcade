import json
from pathlib import Path

import audit_controls

FIXTURE = Path(__file__).parent / "fixtures" / "cabinet_audit_raw.json"  # the Pi as audited on 15 October 2026


def raw():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def findings(report, level):
    return [f"[{a}] {t}" for l, a, t in report["findings"] if l == level]


# A USB gamepad-class panel as the kernel lists it (vendor and product are made up: the real encoder is not known yet)
PANEL = """
I: Bus=0003 Vendor=0079 Product=0006 Version=0110
N: Name="Generic Arcade Encoder"
P: Phys=usb-xhci-hcd.0-1/input0
H: Handlers=event11 js2

"""


def with_panel(js_first=False):
    data = raw()
    devices = data["devices"]
    if js_first:  # the panel comes up before the broker's pads
        devices = PANEL.replace("js2", "js0") + devices.replace("js0", "js2").replace("js1", "js3")
    else:
        devices += "\n" + PANEL
    data["devices"] = devices
    return data


def test_the_live_pi_has_no_panel_and_the_virtual_pads_are_players_one_and_two():
    report = audit_controls.analyze(raw())
    assert report["panel"] == []
    assert report["order"] == ["js0 AI Arcade Player 1", "js1 AI Arcade Player 2"]
    assert not findings(report, "FAIL")


def test_the_mouse_is_not_taken_for_a_keyboard():
    report = audit_controls.analyze(raw())
    assert not any("Wireless Mouse" in t for t in findings(report, "INFO") if "is a keyboard" in t)


def test_the_known_gaps_are_reported():
    warns = " ".join(findings(audit_controls.analyze(raw()), "WARN"))
    assert "Player 1 only" in warns  # RetroArch keyboard bindings
    assert "no way to leave a RetroArch game" in warns  # hotkeys are keyboard only
    assert "no Player 2" in warns  # MAME ctrlr
    assert "no action buttons" in warns


def test_a_new_pad_nothing_maps_fails_for_the_menu_and_retroarch():
    report = audit_controls.analyze(with_panel())
    fails = " ".join(findings(report, "FAIL"))
    assert "es_input.cfg entry for 'Generic Arcade Encoder'" in fails and "no autoconfig for 'Generic Arcade Encoder'" in fails
    assert report["panel"] == ["Generic Arcade Encoder"]


def test_a_panel_that_sorts_after_the_virtual_pads_is_warned_about():
    report = audit_controls.analyze(with_panel())
    assert any("sort BEFORE the physical panel" in w for w in findings(report, "WARN"))
    assert any("JOYCODE_1 and 2" in w for w in findings(report, "WARN"))


def test_a_panel_that_sorts_first_is_ok():
    report = audit_controls.analyze(with_panel(js_first=True))
    assert any("sorts before the AI Arcade virtual pads" in t for t in findings(report, "OK"))
    assert not any("sort BEFORE" in w for w in findings(report, "WARN"))


def test_a_panel_with_both_mappings_installed_stops_failing():
    data = with_panel()
    data["es_input"] = data["es_input"].replace(
        "</inputList>", '<inputConfig type="joystick" deviceName="Generic Arcade Encoder" deviceGUID="x"/></inputList>')
    data["ra_joypads"] += '\n@@ /x/Generic Arcade Encoder.cfg\ninput_device = "Generic Arcade Encoder"\n'
    assert not findings(audit_controls.analyze(data), "FAIL")


def test_the_parsers_read_the_real_files():
    data = raw()
    assert [d["name"] for d in audit_controls.parse_devices(data["devices"])][-2:] == ["AI Arcade Player 1", "AI Arcade Player 2"]
    assert set(audit_controls.es_devices(data["es_input"])) == {"AI Arcade Player 1", "AI Arcade Player 2", "Keyboard"}
    assert audit_controls.parse_cfg(data["ra_cfg"])["input_player1_a"] == "a"
    ports = audit_controls.mame_ports(audit_controls.parse_files(data["mame_ctrlr"])["/home/pi/.mame/ctrlr/aiarcade.cfg"])
    assert ports["bzone"]["P1_JOYSTICKRIGHT_UP"].startswith("JOYCODE_2_")


# --- tools/probe_panel.py
import probe_panel  # noqa: E402


def key(dev, code, value=1):
    return {"type": 1, "code": code, "value": value, "dev": dev, "vid": "0079:0006", "name": f"BTN_{code}"}


def axis(dev, code, value, lo=0, hi=255):
    return {"type": 3, "code": code, "value": value, "dev": dev, "vid": "0079:0006", "min": lo, "max": hi}


def test_presses_come_out_in_order_and_releases_and_repeats_are_ignored():
    events = [{"listening": ["Pad"]},
              axis("Pad", 1, 0), axis("Pad", 1, 127),  # up, released
              axis("Pad", 1, 255), axis("Pad", 1, 127),  # down, released
              axis("Pad", 0, 0), axis("Pad", 0, 127),  # left
              key("Pad", 288), key("Pad", 288, 0), key("Pad", 288),  # button once, then pressed again
              key("Pad", 289), key("Pad", 289, 2)]  # auto-repeat is not a press
    found = probe_panel.presses(events)
    assert [(e["kind"], e["code"], e["direction"]) for e in found] == [
        ("abs", 1, -1), ("abs", 1, 1), ("abs", 0, -1), ("key", 288, None), ("key", 289, None)]


def test_a_full_capture_is_named_from_the_stated_order():
    events = []
    for p, dev in ((1, "Pad A"), (2, "Pad B")):
        for n in range(4):
            events += [axis(dev, n // 2, 0 if n % 2 == 0 else 255), axis(dev, n // 2, 127)]
        events += [key(dev, 288 + n) for n in range(8)]
    mapping, problems = probe_panel.assign(probe_panel.presses(events))
    assert problems == [] and len(mapping) == len(probe_panel.SEQUENCE) == 24
    assert mapping["P1_UP"]["dev"] == "Pad A" and mapping["P2_START"]["dev"] == "Pad B"


def test_a_short_capture_says_what_is_missing():
    mapping, problems = probe_panel.assign(probe_panel.presses([key("Pad", 288), key("Pad", 289)]))
    assert list(mapping) == ["P1_UP", "P1_DOWN"] and "missing P1_LEFT" in problems[0]
