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


# --- tools/guided_capture.py
import queue  # noqa: E402

import guided_capture  # noqa: E402

PORT_A, PORT_B = "usb-xhci-hcd.0-1.2/input0", "usb-xhci-hcd.0-1.3/input0"


def ev(kind, code, value, path="/dev/input/event6", phys=PORT_A, **extra):
    return {"type": kind, "code": code, "value": value, "dev": "DragonRise Generic  ", "path": path, "phys": phys,
            "vid": "0079:0006", "min": 0, "max": 255, "name": f"BTN_{code}", **extra}


def feed_all(events, steps, **kw):
    q = queue.Queue()
    for e in events:
        q.put(e)
    said = []
    got = guided_capture.run(q, steps, say=said.append, poll=lambda: None, timeout=0.5, **kw)
    return got, said


def test_a_press_is_taken_then_the_next_control_is_asked_for():
    got, _ = feed_all([ev(3, 1, 0), ev(3, 1, 127), ev(1, 288, 1), ev(1, 288, 0)], [("P1", "UP"), ("P1", "A")])
    assert got["P1 UP"]["kind"] == "abs" and got["P1 UP"]["direction"] == -1
    assert got["P1 A"]["code"] == 288 and got["P1 A"]["phys"] == PORT_A


def test_a_control_already_taken_is_refused_not_counted_again():
    got, said = feed_all([ev(1, 288, 1), ev(1, 288, 0), ev(1, 288, 1), ev(1, 288, 0), ev(1, 289, 1), ev(1, 289, 0)],
                         [("P1", "A"), ("P1", "B")])
    assert got["P1 A"]["code"] == 288 and got["P1 B"]["code"] == 289
    assert any("already P1 A" in s for s in said)


def test_two_identical_encoders_are_told_apart_by_their_port():
    got, _ = feed_all([ev(1, 288, 1), ev(1, 288, 0), ev(1, 288, 1, path="/dev/input/event7", phys=PORT_B),
                       ev(1, 288, 0, path="/dev/input/event7", phys=PORT_B)], [("P1", "A"), ("P2", "A")])
    assert got["P1 A"]["phys"] == PORT_A and got["P2 A"]["phys"] == PORT_B


def test_a_silent_control_is_skipped_and_reported():
    got, said = feed_all([], [("P1", "A")])
    assert got == {"P1 A": None} and any("nothing seen" in s for s in said)
    lines, problems = guided_capture.summary(got)
    assert "P1 A: nothing was pressed" in problems


def test_the_summary_flags_a_button_wired_to_the_other_encoder_and_one_encoder_doing_both_players():
    def p(phys):
        return {"phys": phys, "path": phys, "dev": "x"}
    lines, problems = guided_capture.summary({"P1 UP": p(PORT_A), "P1 A": p(PORT_A), "P1 B": p(PORT_B),
                                              "P2 UP": p(PORT_B), "P2 A": p(PORT_B)})
    assert any("P1 B" in x and "wired to the wrong encoder" in x for x in problems)
    _, same = guided_capture.summary({"P1 UP": p(PORT_A), "P2 UP": p(PORT_A)})
    assert any("one encoder is doing both" in x for x in same)


def test_a_mouse_like_spinner_counts_once_per_direction_until_it_stops():
    d = guided_capture.Detector()
    spin = {"type": 2, "code": 0, "value": 3, "dev": "Spinner", "path": "/dev/input/event5", "phys": "usb-1.1"}
    assert d.feed(spin, now=0.0)["direction"] == 1
    assert d.feed(spin, now=0.1) is None and not d.idle(now=0.2)
    assert d.feed({**spin, "value": -3}, now=0.3)["direction"] == -1
    assert d.idle(now=2.0)


def test_the_keyboard_and_the_gamepad_steer_the_capture_and_are_never_captured():
    kb = {"type": 1, "code": 31, "value": 1, "dev": "Logitech Wireless Keyboard PID:4023", "name": "KEY_S"}
    pad = {"type": 1, "code": 304, "value": 1, "dev": "Logitech Gamepad F310", "name": "['BTN_A', 'BTN_GAMEPAD', 'BTN_SOUTH']"}
    space = {**kb, "name": "KEY_SPACE"}
    assert guided_capture.command_of(kb) == "s" and guided_capture.command_of(pad) == "s"
    assert guided_capture.command_of(space) is None  # KEY_SPACE is not KEY_S
    assert guided_capture.command_of({**kb, "dev": "DragonRise Generic"}) is None
    # a skip from the keyboard moves on without taking a control; the next press is the next control
    got, _ = feed_all([kb, ev(1, 288, 1), ev(1, 288, 0)], [("P1", "UP"), ("P1", "A")])
    assert got["P1 UP"] is None and got["P1 A"]["code"] == 288
    # back and quit
    q = {**kb, "name": "KEY_Q"}
    got, _ = feed_all([ev(1, 288, 1), ev(1, 288, 0), q], [("P1", "A"), ("P1", "B")])
    assert "P1 A" in got and "P1 B" not in got
