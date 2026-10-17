"""Read-only audit of the cabinet's controller configuration on the Pi: what input devices exist, which of them
EmulationStation, RetroArch and MAME have a mapping for, who gets Player 1 and Player 2, and what is missing for a
physical P1/P2 panel (docs/CABINET_CONTROLS.md). Changes nothing on the Pi.

    python tools/audit_controls.py [--host ADDRESS] [--json] [--save raw.json]
    python tools/audit_controls.py --offline raw.json        # analyse a saved collection (also what the tests use)

Exit status 1 when a FAIL is reported (a panel device nothing maps), 0 otherwise. WARN means "will misbehave in some
emulator"; INFO is context.
"""
import argparse
import collections
import json
import re
import sys
import xml.etree.ElementTree as ET

from gamelib import DEFAULT_PI_HOST

CONFIGS = "/opt/retropie/configs"
PANEL_IDS = {"0079:0006"}  # the panel's two DragonRise encoders (vendor:product); any other pad is "another pad"
VIRTUAL_PHYS = "py-evdev-uinput"  # the AI Arcade broker's virtual pads (pi/controller_broker.py)
NOT_A_PANEL = ("pwr_button", "vc4-hdmi", "HDMI Jack", "Logitech", "Power Button", "Consumer Control", "System Control",
               "KT USB Audio")  # the USB audio adapter has volume keys

COMMANDS = {
    "devices": "cat /proc/bus/input/devices",
    "es_input": f"cat {CONFIGS}/all/emulationstation/es_input.cfg 2>/dev/null",
    "ra_cfg": f"cat {CONFIGS}/all/retroarch.cfg 2>/dev/null",
    "ra_joypads": f"for f in {CONFIGS}/all/retroarch-joypads/*.cfg; do echo \"@@ $f\"; cat \"$f\"; done 2>/dev/null",
    "ra_autoconfig": f"ls {CONFIGS}/all/retroarch/autoconfig 2>/dev/null",
    "mame_ctrlr": "for f in /home/pi/.mame/ctrlr/*.cfg; do echo \"@@ $f\"; cat \"$f\"; done 2>/dev/null",
    "mame_ini": f"cat {CONFIGS}/mame-0251/mame.ini 2>/dev/null",
    "advmame": f"grep -E '^(device_joystick|device_keyboard|input_hotkey)' {CONFIGS}/mame-advmame/advmame.rc 2>/dev/null",
    "emulators_all": f"cat {CONFIGS}/all/emulators.cfg 2>/dev/null",
    "systems": f"for d in {CONFIGS}/*/emulators.cfg; do echo \"@@ $d\"; grep '^default' \"$d\"; done 2>/dev/null",
    "sdl_gamecontroller": "ls /home/pi/.config/sdl2 /opt/retropie/emulators/*/gamecontrollerdb.txt 2>/dev/null",
}


def collect(ssh):
    """The raw text of every file the audit reads (nothing is written)."""
    raw = {}
    for name, command in COMMANDS.items():
        _, out, _ = ssh.exec_command(command, timeout=40)
        raw[name] = out.read().decode(errors="replace")
    return raw


def parse_devices(text):
    """/proc/bus/input/devices -> [{name, vendor, product, phys, handlers, js, virtual}]."""
    devices = []
    for block in re.split(r"\n\s*\n", text.strip()):
        fields = {}
        for line in block.splitlines():
            key, _, rest = line.partition(": ")
            fields[key] = rest
        if "N" not in fields:
            continue
        ident = dict(re.findall(r"(\w+)=(\w+)", fields.get("I", "")))
        handlers = fields.get("H", "").replace("Handlers=", "").split()
        name = re.search(r'Name="(.*)"', fields["N"]).group(1)
        phys = fields.get("P", "").replace("Phys=", "")
        js = next((int(h[2:]) for h in handlers if re.fullmatch(r"js\d+", h)), None)
        devices.append({"name": name, "vendor": ident.get("Vendor"), "product": ident.get("Product"), "phys": phys,
                        "handlers": handlers, "js": js, "keyboard": "kbd" in handlers and js is None and not any(h.startswith("mouse") for h in handlers),
                        "virtual": VIRTUAL_PHYS in phys})
    return devices


def parse_cfg(text):
    """RetroArch's key = "value" lines -> dict."""
    return {m.group(1): m.group(2) for m in (re.match(r'\s*([^#=\s]+)\s*=\s*"?([^"\n]*)"?\s*$', l) for l in text.splitlines()) if m}


def parse_files(text):
    """Blocks introduced by '@@ path' lines -> {path: body}."""
    files, current = {}, None
    for line in text.splitlines():
        if line.startswith("@@ "):
            current = line[3:].strip()
            files[current] = []
        elif current is not None:
            files[current].append(line)
    return {path: "\n".join(body) for path, body in files.items()}


def es_devices(text):
    """EmulationStation's es_input.cfg -> {device name: (type, guid)}."""
    if not text.strip():
        return {}
    root = ET.fromstring(text)
    return {c.get("deviceName"): (c.get("type"), c.get("deviceGUID")) for c in root.iter("inputConfig")}


def mame_ports(text):
    """A MAME ctrlr .cfg -> {system: {port type: sequence}}."""
    out = collections.defaultdict(dict)
    for system in ET.fromstring(text).iter("system"):
        for port in system.iter("port"):
            out[system.get("name")][port.get("type")] = (port.findtext("newseq") or "").strip()
    return out


def emulator_counts(text):
    counts = collections.Counter()
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            counts[(key.split("_")[0], value.strip().strip('"'))] += 1
    return counts


P2_MAME = ["P2_JOYSTICK_UP", "P2_JOYSTICK_DOWN", "P2_JOYSTICK_LEFT", "P2_JOYSTICK_RIGHT", "COIN2", "START2"]
P1_MAME = ["P1_JOYSTICK_UP", "P1_JOYSTICK_DOWN", "P1_JOYSTICK_LEFT", "P1_JOYSTICK_RIGHT", "COIN1", "START1"]
P1_BUTTONS = [f"P1_BUTTON{n}" for n in range(1, 7)]
P2_BUTTONS = [f"P2_BUTTON{n}" for n in range(1, 7)]
RA_P2_KEYS = ["input_player2_up", "input_player2_down", "input_player2_left", "input_player2_right", "input_player2_a",
              "input_player2_b", "input_player2_start", "input_player2_select"]


def analyze(raw):
    """-> {findings: [(level, area, text)], devices, panel, order}. Pure: the tests feed it saved text."""
    findings = []

    def say(level, area, text):
        findings.append((level, area, text))

    devices = parse_devices(raw["devices"])
    es = es_devices(raw["es_input"])
    ra = parse_cfg(raw["ra_cfg"])
    joypad_files = parse_files(raw["ra_joypads"])
    ra_names = {parse_cfg(body).get("input_device") for body in joypad_files.values()}
    ra_names |= {n.rsplit(".", 1)[0] for n in raw["ra_autoconfig"].split("\n") if n.endswith(".cfg")}
    mame = {}
    for path, body in parse_files(raw["mame_ctrlr"]).items():
        mame[path.rsplit("/", 1)[-1]] = mame_ports(body)

    ours = [d for d in devices if d["virtual"]]
    pads = [d for d in devices if d["js"] is not None and not d["virtual"] and not any(t in d["name"] for t in NOT_A_PANEL)]
    keyboards = [d for d in devices if d["keyboard"] and not d["virtual"] and not any(t in d["name"] for t in NOT_A_PANEL)]
    wireless = [d for d in devices if "Logitech" in d["name"] and d["keyboard"]]
    panel_pads = [d for d in pads if f"{d['vendor']}:{d['product']}" in PANEL_IDS]
    other_pads = [d for d in devices if d["js"] is not None and not d["virtual"] and d not in panel_pads]  # e.g. the F310
    panel = pads + [k for k in keyboards if k not in pads]

    # --- who is there
    for d in ours:
        say("INFO", "AI Arcade", f"virtual pad '{d['name']}' (js{d['js']}, {d['vendor']}:{d['product']}): the broker's, used by the "
                                 "AI and by Windows to drive EmulationStation")
    for d in wireless:
        say("INFO", "devices", f"'{d['name']}' is a keyboard (EmulationStation and the text games take it)")
    if not panel:
        say("INFO", "panel", "no physical panel device is connected (no gamepad-class device and no keyboard beyond the "
                              "wireless one): nothing to map yet")
    for d in pads:
        say("INFO", "panel", f"gamepad-class device '{d['name'].strip()}' js{d['js']} {d['vendor']}:{d['product']} ({d['phys']})")
    for name in dict.fromkeys(d["name"] for d in pads):
        if name not in es:
            say("FAIL", "EmulationStation", f"no es_input.cfg entry for '{name.strip()}': the menu will not take it "
                                            "(run EmulationStation's input configuration, or install the profile)")
        if name not in ra_names:
            say("FAIL", "RetroArch", f"no autoconfig for '{name.strip()}': RetroArch cores will not map it")
    if pads:
        say("INFO", "MAME", "standalone MAME addresses joysticks by order (JOYCODE_n), not by name: check n with the order below")
    for name, n in collections.Counter(d["name"] for d in pads).items():
        if n > 1:
            same = [d for d in pads if d["name"] == name]
            say("WARN", "identity", f"{n} devices share the name '{name.strip()}' and the id {same[0]['vendor']}:{same[0]['product']}: "
                                    "a profile by name or id cannot tell Player 1 from Player 2, so the order is the only "
                                    "difference (" + ", ".join(f"js{d['js']} = {d['phys']}" for d in same)
                                    + "); pin it to the USB port with a udev rule")
    for d in keyboards:
        say("INFO", "panel", f"keyboard-class device '{d['name']}' ({d['vendor']}:{d['product']}): every emulator already reads "
                             "a keyboard, so only Player 2 and the exit chord need keys")

    # --- who is Player 1 and 2
    order = sorted((d for d in devices if d["js"] is not None), key=lambda d: d["js"])
    ordered = [f"js{d['js']} {d['name']}" for d in order]
    if pads and ours and min(d["js"] for d in ours) < min(d["js"] for d in pads):
        say("WARN", "order", "the AI Arcade virtual pads sort BEFORE the physical panel (" + ", ".join(ordered) + "): "
                             "RetroArch and standalone MAME give Player 1 and Player 2 to the first two joysticks, so "
                             "the panel would be Player 3 and 4")
    elif ours and panel_pads and any(d["js"] < min(p["js"] for p in panel_pads) for d in other_pads):
        early = [d for d in other_pads if d["js"] < min(p["js"] for p in panel_pads)]
        say("WARN", "order", "another gamepad (" + ", ".join(f"js{d['js']} {d['name'].strip()}" for d in early) + ") sorts BEFORE "
                             "the panel (" + ", ".join(ordered) + "): it would be Player 1, and the panel Players 2 and 3")
    elif pads and ours:
        say("OK", "order", "the physical panel sorts before the AI Arcade virtual pads (" + ", ".join(ordered) + ")")
    elif not pads and ours:
        say("INFO", "order", "joystick order now: " + ", ".join(ordered) + " (the virtual pads are Player 1 and 2 until a "
                                                                        "panel is added)")

    # --- EmulationStation
    es_pads = [n for n, (t, _) in es.items() if t == "joystick"]
    say("INFO", "EmulationStation", f"es_input.cfg has {len(es)} device(s): "
                                    + ", ".join(f"{n} ({t})" for n, (t, _) in es.items()))
    if "Keyboard" not in es:
        say("WARN", "EmulationStation", "no keyboard entry in es_input.cfg")
    if not es_pads:
        say("WARN", "EmulationStation", "no joystick is configured in es_input.cfg")

    # --- RetroArch
    keys_p1 = [k for k in ("input_player1_up", "input_player1_a", "input_player1_start") if k in ra]
    p2_missing = [k for k in RA_P2_KEYS if k not in ra]
    if keys_p1 and p2_missing:
        say("WARN", "RetroArch", "keyboard bindings exist for Player 1 only (retroarch.cfg has no "
                                 + ", ".join(p2_missing[:4]) + ("..." if len(p2_missing) > 4 else "") + "): a keyboard-style "
                                 "panel cannot play two-player RetroArch games until Player 2's keys are added")
    if ra.get("input_joypad_driver") != "udev":
        say("WARN", "RetroArch", f"input_joypad_driver is {ra.get('input_joypad_driver')!r}, not udev")
    if ra.get("input_autodetect_enable") != "true":
        say("WARN", "RetroArch", "input_autodetect_enable is off: new pads will not map by themselves")
    hot_btn = [k for k in ra if k in ("input_enable_hotkey_btn", "input_exit_emulator_btn", "input_menu_toggle_btn")]
    if not hot_btn:
        say("WARN", "RetroArch", f"hotkeys are keyboard only (enable_hotkey = {ra.get('input_enable_hotkey')!r}, exit = "
                                 f"{ra.get('input_exit_emulator')!r}): a panel with no keyboard has no way to leave a RetroArch "
                                 "game or open its menu; needs a Select+Start style chord on the panel")

    # --- MAME 0.251 (human mode) and AI mode
    ctrlr = mame.get("aiarcade.cfg")
    if ctrlr is None:
        say("WARN", "MAME", "no ctrlr file aiarcade.cfg: MAME 0.251 runs on its own defaults")
    else:
        default = ctrlr.get("default", {})
        missing_p1 = [p for p in P1_MAME if p not in default]
        missing_p2 = [p for p in P2_MAME if p not in default]
        say("INFO", "MAME", f"aiarcade.cfg 'default' maps {len(default)} port(s); games with their own section: "
                            + (", ".join(s for s in ctrlr if s != "default") or "none"))
        if missing_p1:
            say("WARN", "MAME", "default section lacks " + ", ".join(missing_p1) + " (MAME's own default keys apply)")
        if missing_p2:
            say("WARN", "MAME", "default section has no Player 2 (" + ", ".join(missing_p2) + "): Player 2 only has MAME's "
                                "defaults (R/F/D/G keys, JOYCODE_2), so a physical P2 stick is not assigned")
        if not any(p in default for p in P1_BUTTONS + P2_BUTTONS):
            say("WARN", "MAME", "no action buttons are assigned in the default section: buttons use MAME's defaults "
                                "(Left Ctrl/Alt/Space/Shift, joystick buttons 1-4 in order)")
        joys = {m.group(1) for seq in default.values() for m in re.finditer(r"JOYCODE_(\d)_", seq)}
        if joys and ours and not pads:
            say("INFO", "MAME", f"JOYCODE_{'/'.join(sorted(joys))} currently means the AI Arcade virtual pad(s)")
        if joys and pads and ours and min(d["js"] for d in ours) < min(d["js"] for d in pads):
            say("WARN", "MAME", "JOYCODE_1 and 2 in aiarcade.cfg point at the virtual pads, not the panel")
    ini = raw["mame_ini"]
    if "ctrlr" in ini and "aiarcade" in ini:
        say("INFO", "MAME", "human mode (mame-0.251) uses the same ctrlr file as AI mode: one edit changes both")

    # --- other emulators
    if raw["advmame"].strip():
        say("INFO", "AdvanceMAME", "joystick/keyboard are 'auto': " + "; ".join(raw["advmame"].strip().splitlines()))
    counts = emulator_counts(raw["emulators_all"])
    by = collections.Counter()
    for (_, emulator), n in counts.items():
        by[emulator] += n
    if by:
        say("INFO", "emulators", "per-game launchers: " + ", ".join(f"{e} {n}" for e, n in by.most_common()))
    return {"findings": findings, "devices": devices, "order": ordered, "panel": [d["name"] for d in panel]}


def render(report):
    lines = []
    for level in ("FAIL", "WARN", "OK", "INFO"):
        rows = [(a, t) for l, a, t in report["findings"] if l == level]
        if rows:
            lines.append(f"\n{level}")
            lines += [f"  [{a}] {t}" for a, t in rows]
    counts = collections.Counter(l for l, _, _ in report["findings"])
    lines.append(f"\n{counts['FAIL']} FAIL, {counts['WARN']} WARN, {counts['OK']} OK, {counts['INFO']} INFO")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--offline", help="analyse a saved collection instead of connecting")
    parser.add_argument("--save", help="save the raw collection here")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.offline:
        raw = json.load(open(args.offline, encoding="utf-8"))
    else:
        import paramiko
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
        ssh.connect(args.host, username="pi", timeout=10)
        try:
            raw = collect(ssh)
        finally:
            ssh.close()
        if args.save:
            json.dump(raw, open(args.save, "w", encoding="utf-8"), indent=1)
    report = analyze(raw)
    print(json.dumps(report, indent=1) if args.json else render(report))
    return 1 if any(l == "FAIL" for l, _, _ in report["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
