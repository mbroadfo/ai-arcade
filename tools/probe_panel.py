"""Learn what a physical panel sends: listen to the Pi's input devices while someone presses each control once, in a
stated order, and write down which device, event type and code each press produced. Read-only: it opens the devices
to read and grabs nothing, so the menu and any running game see the same presses.

    python tools/probe_panel.py --list                       # the Pi's input devices, marking the AI Arcade virtual pads
    python tools/probe_panel.py --watch 15                   # print every event for 15 s (find out what is what)
    python tools/probe_panel.py --capture --out panel.json   # press the controls in the order printed, about a second apart

The virtual pads (the broker's) and the HDMI and power-button devices are left out. --device NAME limits it to one device.
"""
import argparse
import json
import sys
import time

from gamelib import DEFAULT_PI_HOST

# What to press, in this order: P1's stick, its action buttons, Start and Select/Coin; then Player 2's the same.
PLAYER_CONTROLS = ["UP", "DOWN", "LEFT", "RIGHT"] + [f"BUTTON_{n}" for n in range(1, 7)] + ["START", "COIN"]
SEQUENCE = [f"P{p}_{c}" for p in (1, 2) for c in PLAYER_CONTROLS]

REMOTE = r'''
import json, select, sys, time
import evdev
only = sys.argv[1]
seconds = float(sys.argv[2])
skip = ("pwr_button", "vc4-hdmi", "HDMI Jack", "AI Arcade Player")
devs = {}
for path in evdev.list_devices():
    d = evdev.InputDevice(path)
    if d.phys == "py-evdev-uinput" or any(s in d.name for s in skip) or (only and only != d.name):
        continue
    devs[d.fd] = d
print(json.dumps({"listening": [d.name for d in devs.values()]}), flush=True)
end = time.time() + seconds
while time.time() < end and devs:
    ready, _, _ = select.select(list(devs), [], [], 0.2)
    for fd in ready:
        d = devs[fd]
        for e in d.read():
            if e.type not in (1, 3) or (e.type == 1 and e.value == 2):
                continue
            row = {"t": round(e.timestamp(), 3), "dev": d.name, "vid": "%04x:%04x" % (d.info.vendor, d.info.product),
                   "type": e.type, "code": e.code, "value": e.value}
            if e.type == 3:
                info = d.absinfo(e.code)
                row["min"], row["max"] = info.min, info.max
            else:
                row["name"] = str(evdev.ecodes.KEY.get(e.code) or evdev.ecodes.BTN.get(e.code) or e.code)
            print(json.dumps(row), flush=True)
'''


def listen(ssh, seconds, device=""):
    """Events from the Pi's input devices for `seconds`: the dicts the remote reader prints."""
    stdin, out, _ = ssh.exec_command(f"python3 - {json.dumps(device)} {seconds}", timeout=seconds + 30)
    stdin.write(REMOTE)  # the program goes in on stdin: no shell quoting to get wrong
    stdin.channel.shutdown_write()
    events = []
    for line in out:
        line = line.strip()
        if line.startswith("{"):
            events.append(json.loads(line))
    return events


def presses(events):
    """Events -> the distinct controls pressed, in order of first press: [{dev, vid, kind, code, direction, name}].

    A key press is value 1. An axis counts as pressed when it leaves the middle of its range (a quarter in from an end);
    its direction is - or +. A hat or stick that returns to the middle is the release and is not a press."""
    seen, out, axis_state = set(), [], {}
    for e in events:
        if "listening" in e:
            continue
        if e["type"] == 1 and e["value"] == 1:
            key = (e["dev"], "key", e["code"], None)
            entry = {"dev": e["dev"], "vid": e.get("vid"), "kind": "key", "code": e["code"], "direction": None,
                     "name": e.get("name")}
        elif e["type"] == 3:
            lo, hi = e["min"], e["max"]
            span = max(hi - lo, 1)
            pos = (e["value"] - lo) / span
            was = axis_state.get((e["dev"], e["code"]), 0)
            now = -1 if pos < 0.25 else 1 if pos > 0.75 else 0
            axis_state[(e["dev"], e["code"])] = now
            if now == 0 or now == was:
                continue
            key = (e["dev"], "abs", e["code"], now)
            entry = {"dev": e["dev"], "vid": e.get("vid"), "kind": "abs", "code": e["code"], "direction": now, "name": None}
        else:
            continue
        if key not in seen:
            seen.add(key)
            out.append(entry)
    return out


def assign(found, sequence=SEQUENCE):
    """Name each distinct press from the stated order. Returns (mapping, problems)."""
    mapping, problems = {}, []
    for name, entry in zip(sequence, found):
        mapping[name] = entry
    if len(found) < len(sequence):
        problems.append(f"only {len(found)} distinct presses for {len(sequence)} controls: missing "
                        + ", ".join(sequence[len(found):]))
    if len(found) > len(sequence):
        problems.append(f"{len(found) - len(sequence)} extra press(es) after {sequence[-1]}: " + ", ".join(
            f"{e['dev']} {e['kind']} {e['code']}" for e in found[len(sequence):]))
    devices = sorted({e["dev"] for e in found})
    if len(devices) > 2:
        problems.append("presses came from more than two devices: " + ", ".join(devices))
    return mapping, problems


def connect(host):
    import paramiko
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(host, username="pi", timeout=10)
    return ssh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--device", default="", help="listen to this device name only")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--watch", type=float, metavar="SECONDS")
    mode.add_argument("--capture", action="store_true")
    parser.add_argument("--seconds", type=float, default=75, help="how long --capture listens (default 75)")
    parser.add_argument("--out", help="--capture: write the mapping here as JSON")
    args = parser.parse_args()
    ssh = connect(args.host)
    try:
        if args.list:
            _, out, _ = ssh.exec_command("cat /proc/bus/input/devices", timeout=20)
            import audit_controls
            for d in audit_controls.parse_devices(out.read().decode()):
                kind = "AI Arcade virtual pad" if d["virtual"] else "gamepad" if d["js"] is not None else \
                       "keyboard" if d["keyboard"] else "other"
                print(f"{d['name']:<42} {d['vendor']}:{d['product']}  {kind}  {' '.join(d['handlers'])}")
            return 0
        if args.watch:
            for e in listen(ssh, args.watch, args.device):
                print(json.dumps(e))
            return 0
        print("Press each control once, about a second apart, in this order:")
        print("  " + ", ".join(SEQUENCE))
        print(f"Listening for {args.seconds:g} s...", flush=True)
        found = presses(listen(ssh, args.seconds, args.device))
    finally:
        ssh.close()
    mapping, problems = assign(found)
    for name, e in mapping.items():
        what = f"{e['kind']} {e['code']}" + (f" ({e['name']})" if e.get("name") else "") + \
               (f" {'-' if e['direction'] < 0 else '+'}" if e["direction"] else "")
        print(f"{name:<14} {e['dev']}  {what}")
    for p in problems:
        print("PROBLEM:", p)
    if args.out:
        json.dump({"captured": time.strftime("%Y-%m-%d %H:%M:%S"), "mapping": mapping, "problems": problems},
                  open(args.out, "w", encoding="utf-8"), indent=1)
        print("wrote", args.out)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
