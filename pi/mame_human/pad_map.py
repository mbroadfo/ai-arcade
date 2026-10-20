#!/usr/bin/env python3
"""Work out, at each launch of a human-mode MAME game, which of the joysticks plugged in are which, and write MAME's
controller file for exactly that. Whatever is plugged in works; whatever is missing is left out:

  - the arcade panel's two encoders (found by the USB port they sit in, panel.json) play Player 1 and Player 2;
  - any other gamepad (a Logitech F310, say) plays Player 1, then Player 2, in the order they were plugged in,
    alongside the panel when it is there;
  - the keyboard always works (MAME's own keys, in every sequence);
  - the AI Arcade pads are hidden from the game, so they can never take a joystick number.

Joystick numbers are the order udev lists the joysticks, which SDL (so MAME) and RetroArch use: by the device's path in /sys
(see order_key), AI pads left out for MAME.
Output (for `eval`): environment for the launch and the ctrlr options. Standalone: `pad_map.py --show` says what it found.

Pure functions up top; nothing here decides anything about a game.
"""
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
AI_PADS = {("1209", "a101"), ("1209", "a102")}
CTRLR_DIR = "/tmp/ai-arcade-ctrlr"
CTRLR_NAME = "auto"


def order_key(d):
    """Where udev lists a joystick, which is the order RetroArch and SDL (so MAME) number them in: by the device's path
    in /sys, not by its event number (a pad on the other USB bus comes after both panel encoders whatever its event
    number, and the AI pads, which are virtual, come last). Where /sys is not there (tests), by event number."""
    path = f"/sys/class/input/event{d['event']}"
    return (0, os.path.realpath(path)) if os.path.exists(path) else (1, f"{d['event']:08d}")


def parse_devices(text):
    """/proc/bus/input/devices -> [{name, vendor, product, phys, event}] for every joystick, in udev's order."""
    out = []
    for block in text.strip().split("\n\n"):
        info = {}
        for line in block.splitlines():
            if line.startswith("I:"):
                m = re.search(r"Bus=(\w+) Vendor=(\w+) Product=(\w+) Version=(\w+)", line)
                if m:
                    info["bus"], info["vendor"], info["product"], info["version"] = (g.lower() for g in m.groups())
            elif line.startswith("N:"):
                info["name"] = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("P:"):
                info["phys"] = line.split("=", 1)[1].strip()
            elif line.startswith("H:"):
                handlers = line.split("=", 1)[1].split()
                if any(re.fullmatch(r"js\d+", h) for h in handlers):
                    ev = [int(h[5:]) for h in handlers if re.fullmatch(r"event\d+", h)]
                    info["event"] = ev[0] if ev else None
        if "event" in info and info["event"] is not None:
            out.append(info)
    return sorted(out, key=order_key)


def assign(devices, panel):
    """-> {"joy1", "joy2": the panel encoders' MAME numbers or None, "pads": {"P1": n, "P2": n}, "others": [names],
    "ai": number of AI pads hidden}. Numbers count from 1 over the joysticks MAME will see."""
    visible = [d for d in devices if (d.get("vendor"), d.get("product")) not in AI_PADS]
    ports = {p: panel["players"][p]["usb_port"] for p in ("P1", "P2")}
    vid, pid = panel["device"]["vendor_id"].lower(), panel["device"]["product_id"].lower()
    joy = {"P1": None, "P2": None}
    pads = []
    for n, d in enumerate(visible, 1):
        is_panel = (d.get("vendor"), d.get("product")) == (vid, pid)
        player = next((p for p, port in ports.items() if is_panel and port in d.get("phys", "")), None)
        if player:
            joy[player] = n
        else:
            pads.append((n, d.get("name", "?")))
    return {"joy1": joy["P1"], "joy2": joy["P2"],
            "pads": {f"P{i}": n for i, (n, _) in enumerate(pads[:2], 1)},
            "others": [name for _, name in pads],
            "ai": len(devices) - len(visible)}


def hide_ai_pads():
    return "SDL_GAMECONTROLLER_IGNORE_DEVICES=" + ",".join(f"0x{v}/0x{p}" for v, p in sorted(AI_PADS))


ES_INPUT = "/home/pi/.emulationstation/es_input.cfg"


def unknown_pads(devices, es_text, panel):
    """[(SDL name, GUID)] for plugged-in gamepads EmulationStation has no <inputConfig> for (not the panel, not AI pads)."""
    import panel_profiles as pp
    panel_ids = (panel["device"]["vendor_id"].lower(), panel["device"]["product_id"].lower())
    out = []
    for d in devices:
        guid = pp.sdl_guid(d["bus"], d["vendor"], d["product"], d["version"], d.get("name", ""))
        ids = (d.get("vendor"), d.get("product"))
        if ids in AI_PADS or ids == panel_ids or f'deviceGUID="{guid}"' in es_text:
            continue
        out.append((" ".join(d.get("name", "?").split()), guid))
    return out


def teach_es(devices, panel, path=ES_INPUT):
    """Add the standard gamepad layout to es_input.cfg for each pad it does not know. Returns the names added."""
    import panel_profiles as pp
    text = Path(path).read_text(encoding="utf-8")
    added = []
    for name, guid in unknown_pads(devices, text, panel):
        text = pp.merge_es_input(text, pp.es_gamepad_entry(name, guid), name)
        added.append(name)
    if added:
        Path(path).write_text(text, encoding="utf-8")
    return added


RA_JOYPADS = "/opt/retropie/configs/all/retroarch-joypads"
# Written at each launch and included by RetroArch's global config (install_mame_human.py adds the #include): runcommand
# rewrites its own per-launch options file after the onstart hook has run, so anything appended there is lost.
RA_PLAYERS = "/dev/shm/ai-arcade-pads.cfg"


def retroarch_players(devices, panel):
    """RetroArch's player order: [(player number, joypad index, "P1"/"P2" for a panel encoder or None for a gamepad)].
    RetroArch counts every joypad (the AI pads too) in the order the kernel lists them. It cannot let two devices share
    a player, so when a gamepad is plugged in it plays Player 1 (the next one Player 2) and the panel's encoders follow;
    with no gamepad the panel is 1 and 2."""
    panel_ids = (panel["device"]["vendor_id"].lower(), panel["device"]["product_id"].lower())
    ports = {panel["players"][p]["usb_port"]: p for p in ("P1", "P2")}
    pads, panels = [], []
    for index, d in enumerate(devices):
        ids = (d.get("vendor"), d.get("product"))
        if ids in AI_PADS:
            continue
        if ids == panel_ids:
            panels.append((index, next((p for port, p in ports.items() if port in d.get("phys", "")), None)))
        else:
            pads.append((index, None))
    return [(n, index, who) for n, (index, who) in enumerate(pads + panels, 1) if n <= 4]


def apply_pad_overrides(binds, player, panel, rom):
    """A gamepad's explicit binds with the game's changes from panel.json "pad_overrides" (keyed by the ROM's name)."""
    changes = panel.get("pad_overrides", {}).get(Path(rom or "").stem, {}).get("binds", {})
    out = []
    for line in binds:
        key, _, value = line.partition(" = ")
        name = key[len(f"input_player{player}_"):-len("_btn")] if key.endswith("_btn") else None
        out.append(f'{key} = "{changes[name]}"' if name in changes else line)
    return out


def teach_retroarch(devices, panel, joypads=RA_JOYPADS):
    """Write RetroArch's autoconfig for each gamepad that has none. Returns the names added."""
    import panel_profiles as pp
    panel_ids = (panel["device"]["vendor_id"].lower(), panel["device"]["product_id"].lower())
    added = []
    for d in devices:
        ids = (d.get("vendor"), d.get("product"))
        path = Path(joypads, d["name"] + ".cfg")
        if ids in AI_PADS or ids == panel_ids or path.exists():
            continue
        path.write_text(pp.retroarch_gamepad_autoconfig(d["name"], *ids), encoding="utf-8")
        added.append(d["name"])
    return added


def main(argv):
    import panel_profiles as pp
    panel = pp.load_panel(HERE / "panel.json")
    devices = parse_devices(Path("/proc/bus/input/devices").read_text(errors="replace"))
    if "--ra" in argv:  # runcommand-onstart: before a RetroArch core starts
        rom = argv[argv.index("--ra") + 1] if len(argv) > argv.index("--ra") + 1 else ""
        teach_retroarch(devices, panel)
        lines = []
        for n, index, who in retroarch_players(devices, panel):
            d = devices[index]
            text = (pp.retroarch_autoconfig(panel, who) if who else
                    pp.retroarch_gamepad_autoconfig(d["name"], d["vendor"], d["product"]))
            binds, hotkeys = pp.retroarch_player_binds(text, n)
            if not who:
                binds = apply_pad_overrides(binds, n, panel, rom)
            lines += [f'input_player{n}_joypad_index = "{index}"'] + binds + (hotkeys if n == 1 else [])
        Path(RA_PLAYERS).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0
    if "--es" in argv:  # before EmulationStation starts: give every gamepad it has not met a map
        print("; ".join(teach_es(devices, panel)) or "nothing to add")
        return 0
    found = assign(devices, panel)
    if "--show" in argv:
        print(json.dumps(found, indent=1))
        return 0
    os.makedirs(CTRLR_DIR, exist_ok=True)
    text = pp.mame_ctrlr(panel, found["joy1"], found["joy2"], found["pads"])
    Path(CTRLR_DIR, CTRLR_NAME + ".cfg").write_text(text, encoding="utf-8")
    print(f"export {hide_ai_pads()}")
    print(f"PAD_ARGS='-ctrlrpath {CTRLR_DIR} -ctrlr {CTRLR_NAME}'")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
