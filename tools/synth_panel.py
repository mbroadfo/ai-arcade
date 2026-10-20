"""A pretend panel: two virtual USB encoders on the Pi that look like the real ones, driven from this PC, so the
panel's configuration can be tested without a person pressing anything.

    python tools/synth_panel.py --demo            # create the pair, press P1 A and P1 right, remove them

The devices are made with uinput (the pi user may), with the same name, vendor, product, version and capabilities as the
DragonRise encoders (12 buttons, five axes and a hat), so EmulationStation, RetroArch and MAME treat them as the real
thing: the same GUID and autoconfig. They are extra devices (the real encoders stay), so they come after them in joystick
order; they disappear when the session ends.

with SynthPanel(ssh) as panel: panel.press("P1", "A") presses a control by the names in pi/controls/panel.json: a button,
or a stick direction (the axis goes to its end and back to the middle). press_together holds several at once.
"""
import argparse
import json
import sys
import time

import paramiko

import panel_profiles as pp
from gamelib import DEFAULT_PI_HOST

EV_KEY, EV_ABS = 1, 3
REMOTE_PATH = "/tmp/ai-arcade-synth-panel.py"
REMOTE = r'''
import json, sys, time
from evdev import UInput, AbsInfo, ecodes as e
name, count, vendor, product, version, first = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
cap = {e.EV_KEY: list(range(first, first + 12)),
       e.EV_ABS: [(a, AbsInfo(127, 0, 255, 0, 15, 0)) for a in (0, 1, 2, 3, 5)]
                 + [(a, AbsInfo(0, -1, 1, 0, 0, 0)) for a in (16, 17)]}
devs = [UInput(cap, name=name, vendor=vendor, product=product, version=version, bustype=3) for _ in range(count)]
for d in devs:  # every axis rests in the middle, as the encoders do
    for a in (0, 1, 2, 3, 5):
        d.write(e.EV_ABS, a, 127)
    d.syn()
print(json.dumps({"ready": [d.device.path for d in devs]}), flush=True)
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    cmd = json.loads(line)
    for dev, kind, code, value in cmd["down"]:
        devs[dev].write(kind, code, value)
        devs[dev].syn()
    time.sleep(cmd.get("hold", 0.1))
    for dev, kind, code, value in cmd["up"]:
        devs[dev].write(kind, code, value)
        devs[dev].syn()
    print(json.dumps({"done": cmd.get("id")}), flush=True)
for d in devs:
    d.close()
'''


class SynthPanel:
    """Two pretend encoders (index 0 stands in for the Player 1 encoder, 1 for Player 2)."""

    def __init__(self, ssh, panel=None, name=None, count=2):
        self.panel = panel or pp.load_panel()
        self.name = name or self.panel["device"]["evdev_name"]
        self.ssh, self.count, self.paths, self.n = ssh, count, [], 0
        self.stdin = self.out = None

    def __enter__(self):
        d = self.panel["device"]
        sftp = self.ssh.open_sftp()
        with sftp.open(REMOTE_PATH, "w") as f:
            f.write(REMOTE.encode())
        sftp.close()
        self.stdin, self.out, _ = self.ssh.exec_command(
            f"python3 {REMOTE_PATH} {json.dumps(self.name)} {self.count} {int(d['vendor_id'], 16)} "
            f"{int(d['product_id'], 16)} {0x0110} {d['first_button_code']}", timeout=3600)
        self.out.channel.settimeout(20)
        ready = json.loads(self.out.readline())
        self.paths = ready["ready"]
        time.sleep(2)  # let EmulationStation, SDL and RetroArch notice the new devices
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        try:
            self.stdin.channel.shutdown_write()
            self.out.channel.settimeout(5)
            self.out.read()
        except Exception:
            pass
        time.sleep(1)

    def events(self, player, control, down):
        """The (device, type, code, value) events that press or release a control."""
        dev = {"P1": 0, "P2": 1}[player]
        spec = self.panel["players"][player]
        if control.lower() in spec["stick"]:
            _, axis, sign = spec["stick"][control.lower()]
            return [(dev, EV_ABS, axis, (255 if sign > 0 else 0) if down else 127)]
        return [(dev, EV_KEY, spec["buttons"][control], 1 if down else 0)]

    def press_together(self, controls, ms=150):
        """controls: [(player, control), ...] held together for ms milliseconds, then released."""
        self.n += 1
        down = [e for p, c in controls for e in self.events(p, c, True)]
        up = [e for p, c in controls for e in self.events(p, c, False)]
        self.stdin.write(json.dumps({"id": self.n, "down": down, "up": up, "hold": ms / 1000}) + "\n")
        self.stdin.flush()
        done = json.loads(self.out.readline())
        if done.get("done") != self.n:
            raise RuntimeError(f"pretend panel out of step: {done}")

    def press(self, player, control, ms=150):
        self.press_together([(player, control)], ms)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--demo", action="store_true", required=True)
    args = parser.parse_args()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.host, username="pi", timeout=10)
    try:
        with SynthPanel(ssh) as panel:
            print("pretend encoders:", panel.paths)
            panel.press("P1", "A")
            panel.press("P1", "RIGHT")
            print("pressed P1 A and P1 right")
    finally:
        ssh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
