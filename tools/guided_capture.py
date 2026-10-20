"""Guided panel capture: it tells you which control to press ("Press P1 A"), waits until it sees it, shows what it was,
and moves on. Run it yourself in a terminal while standing at the panel. Read-only: it listens to the Pi's input
devices (the AI Arcade virtual pads, the keyboard and the audio adapter are left out) and changes nothing.

    python tools/guided_capture.py                      # P1, P2, the spinner and the trackball
    python tools/guided_capture.py --section p2stick,flight,trackball   # only some sections
                                                        # (p1, p2, p2stick, spinner, trackball, flight, free)
    python tools/guided_capture.py --idle 10            # touch nothing for 10 s: which devices chatter by themselves
    python tools/guided_capture.py --check              # listen for 4 seconds and list the devices, then stop

While it waits, from the panel's side of the room: on the Logitech keyboard or the Logitech F310 gamepad (both are
commands only, never captured as controls):  S or gamepad A = skip this control,  B or gamepad B = go back one,
Q or gamepad Start = stop and save what it has. The same s / b / q keys work in this terminal. Or just wait: a control
nothing is pressed for is skipped after --timeout seconds (25 by default).
A control it has already seen is refused ("already P1 UP"), so a wrong press does not shift everything after it.
Result: runs/panel-capture-<time>.json and a summary of which USB port each player's controls came from.
"""
import argparse
import json
import queue
import re
import sys
import threading
import time

from gamelib import DEFAULT_PI_HOST, ROOT
from probe_panel import REMOTE, connect, describe

try:
    import msvcrt  # Windows: keys without Enter
except ImportError:  # pragma: no cover
    msvcrt = None

SECTIONS = {
    "p1": ("Player 1's controller", [("P1", n) for n in
           ["UP", "DOWN", "RIGHT", "LEFT", "A", "B", "X", "Y", "SNOWFLAKE", "STAR", "COIN 1", "P1 START", "ESC", "TAB"]]),
    "p2": ("Player 2's controller", [("P2", n) for n in
           ["UP", "DOWN", "RIGHT", "LEFT", "A", "B", "X", "Y", "SNOWFLAKE", "STAR", "COIN 2", "P2 START", "ENTER", "PAUSE"]]),
    "p2stick": ("Player 2's stick alone (after rewiring it)", [("P2", n) for n in ["UP", "DOWN", "RIGHT", "LEFT"]]),
    "flight": ("the flight controller", [("FLIGHT", "button 1"), ("FLIGHT", "button 2")]),
    "spinner": ("the spinner", [("SPINNER", "turn clockwise"), ("SPINNER", "turn counter-clockwise")]),
    "trackball": ("the trackball (rolling only: its three buttons are not used)",
                  [("TRACKBALL", n) for n in ["roll up", "roll down", "roll left", "roll right"]]),
}
ORDER = ["p1", "p2", "spinner", "trackball", "flight"]
# Command devices: never captured as controls. Their keys steer the capture (keyboard S, B, Q; the F310's A, B, Start).
COMMAND_KEYS = {"KEY_S": "s", "KEY_B": "b", "KEY_Q": "q", "BTN_SOUTH": "s", "BTN_A": "s", "BTN_EAST": "b", "BTN_B": "b",
                "BTN_START": "q"}


def command_of(e):
    """"s", "b" or "q" when this event is a command key press from a command device; None otherwise. Every other
    event from a command device is ignored too (see is_command_device)."""
    if e.get("type") == 1 and e.get("value") == 1 and is_command_device(e):
        # evdev may report several names for one code ("['BTN_A', 'BTN_GAMEPAD', 'BTN_SOUTH']"): match whole names
        for name in re.findall(r"[A-Z][A-Z_0-9]+", str(e.get("name"))):
            if name in COMMAND_KEYS:
                return COMMAND_KEYS[name]
    return None


def is_command_device(e):
    return "Logitech" in (e.get("dev") or "")
REL_QUIET = 0.6  # seconds without motion before a spinner or trackball counts as stopped
REL_WINDOW = 0.5  # a spinner or trackball is judged on the motion of its first half second
MIN_MOTION = 12  # ... and must have moved this far (counts) in one direction to count at all
DOMINANCE = 0.6  # ... and that direction must be this share of everything it moved (a diagonal roll is not a "left")


class Detector:
    """Turns raw events into 'presses' one at a time, and says when everything is let go again.

    A key is pressed at value 1 and released at 0. An axis is pressed when it leaves the middle half of its range, in
    one direction, and released when it comes back. A mouse-like spinner or trackball is judged on how far it moved, not
    on the first touch: its motion is added up for REL_WINDOW seconds from the first movement, and the direction with the
    most gain counts, if it moved at least `min_motion` counts and made up DOMINANCE of everything it moved. A brush or a
    wobble is ignored, a sideways roll is not taken for "up". It is then held until the device is quiet for REL_QUIET.
    Devices are told apart by node (two identical encoders have the same name); each press carries its USB port."""

    def __init__(self, min_motion=MIN_MOTION):
        self.min_motion = min_motion
        self.down = {}  # (path, kind, code) -> direction while held
        self.rel_win = {}  # path -> {"start", "sums": {code: motion}, "base"} while a motion is being measured
        self.rel_held = {}  # path -> time of the last motion, while a counted motion is still going on

    def feed(self, e, now=None):
        """-> a press dict for a key or an axis, or None. Relative motion only accumulates: see poll."""
        now = time.time() if now is None else now
        who = e.get("path") or e["dev"]
        base = {"dev": e["dev"].strip(), "path": e.get("path"), "phys": e.get("phys"), "vid": e.get("vid")}
        if e["type"] == 1:
            key = (who, "key", e["code"])
            if e["value"] == 1 and key not in self.down:
                self.down[key] = None
                return {**base, "kind": "key", "code": e["code"], "direction": None, "name": e.get("name")}
            if e["value"] == 0:
                self.down.pop(key, None)
        elif e["type"] == 3:
            span = max(e["max"] - e["min"], 1)
            pos = (e["value"] - e["min"]) / span
            now_dir = -1 if pos < 0.25 else 1 if pos > 0.75 else 0
            key = (who, "abs", e["code"])
            if now_dir == 0:
                self.down.pop(key, None)
            elif self.down.get(key) != now_dir:
                self.down[key] = now_dir
                return {**base, "kind": "abs", "code": e["code"], "direction": now_dir, "name": None}
        elif e["type"] == 2 and e["value"]:
            if who in self.rel_held:  # a counted motion is still going on: keep it held, count nothing more
                self.rel_held[who] = now
                return None
            win = self.rel_win.setdefault(who, {"start": now, "sums": {}, "base": base})
            win["sums"][e["code"]] = win["sums"].get(e["code"], 0) + e["value"]
        return None

    def poll(self, now=None):
        """Judge every spinner or trackball whose first half second is over. -> the press with the most gain, or None."""
        now = time.time() if now is None else now
        best, best_gain = None, 0
        for who, win in list(self.rel_win.items()):
            if now - win["start"] < REL_WINDOW:
                continue
            del self.rel_win[who]
            total = sum(abs(v) for v in win["sums"].values())
            code, motion = max(win["sums"].items(), key=lambda kv: abs(kv[1]))
            if abs(motion) < self.min_motion or abs(motion) < DOMINANCE * total:
                continue  # a brush, a wobble, or too diagonal: not a direction
            self.rel_held[who] = now
            if abs(motion) > best_gain:
                best_gain = abs(motion)
                best = {**win["base"], "kind": "rel", "code": code, "direction": 1 if motion > 0 else -1, "name": None}
        return best

    def idle(self, now=None):
        """True when nothing is held and nothing is moving: keys and axes up, motions quiet for REL_QUIET."""
        now = time.time() if now is None else now
        for who, last in list(self.rel_held.items()):
            if now - last > REL_QUIET:
                del self.rel_held[who]
        return not self.down and not self.rel_win and not self.rel_held


def identity(press):
    return (press.get("path") or press["dev"], press["kind"], press["code"], press["direction"])


def stream(ssh, events, stop):
    """Run the reader on the Pi and put its events on a queue until `stop` is set."""
    stdin, out, _ = ssh.exec_command("python3 - '' 3600 commands", timeout=3700)
    stdin.write(REMOTE)
    stdin.channel.shutdown_write()
    for line in out:
        if stop.is_set():
            break
        line = line.strip()
        if line.startswith("{"):
            events.put(json.loads(line))


def key_pressed():
    """The key the user pressed in this terminal, or None (Windows only; elsewhere skipping needs Ctrl-C)."""
    if msvcrt and msvcrt.kbhit():
        return msvcrt.getwch().lower()
    return None


def run(events, steps, say=print, poll=key_pressed, timeout=25, min_motion=MIN_MOTION):
    """Walk the steps. Returns {label: press or None (skipped)} in order."""
    detector, got, taken, i = Detector(min_motion), {}, {}, 0
    while i < len(steps):
        group, name = steps[i]
        label = f"{group} {name}"
        say(f"\n[{i + 1}/{len(steps)}] Press  {label}   (skip: S / gamepad A; back: B; stop: Q / Start; or wait {timeout:g} s)")
        deadline, result = time.time() + timeout, "timeout"
        while time.time() < deadline:
            k = poll()
            if k in ("s", "b", "q"):
                result = {"s": "skip", "b": "back", "q": "quit"}[k]
                break
            press = detector.poll()  # a spinner or trackball whose first half second just ended
            if not press:
                try:
                    e = events.get(timeout=0.1)
                except queue.Empty:
                    continue
                if "listening" in e:
                    continue
                if is_command_device(e):  # steering, never a control
                    k = command_of(e)
                    if k:
                        result = {"s": "skip", "b": "back", "q": "quit"}[k]
                        break
                    continue
                press = detector.feed(e)
                if not press:
                    continue
            who = identity(press)
            if who in taken:
                say(f"      that was already {taken[who]} ({describe(press).strip()}): press {label}")
                continue
            got[label] = press
            taken[who] = label
            say(f"      got it: {describe(press)}")
            result = "ok"
            break
        if result == "ok":
            let_go = time.time() + 5
            while not detector.idle() and time.time() < let_go:  # let go of it first
                detector.poll()
                try:
                    detector.feed(events.get(timeout=0.1))
                except queue.Empty:
                    pass
            i += 1
        elif result == "skip" or result == "timeout":
            if result == "timeout":
                say("      nothing seen: skipped")
            got.setdefault(label, None)
            i += 1
        elif result == "back" and i > 0:
            i -= 1
            prev = f"{steps[i][0]} {steps[i][1]}"
            old = got.pop(prev, None)
            if old:
                taken.pop(identity(old), None)
        elif result == "quit":
            break
    return got


def noise(events):
    """Events seen while nobody touched anything -> {(port, kind, code): count}, the busiest first. A mouse-like device
    that chatters (a spinner) or an axis that wanders shows up here. Command devices are left out."""
    counts = {}
    for e in events:
        if "listening" in e or is_command_device(e):
            continue
        if e["type"] == 3:
            span = max(e["max"] - e["min"], 1)
            if 0.25 <= (e["value"] - e["min"]) / span <= 0.75:
                continue  # an axis resting near the middle is not a press, only its jitter
        kind = {1: "key", 2: "rel", 3: "abs"}.get(e["type"])
        key = (e.get("phys") or e.get("path") or e["dev"], kind, e["code"])
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def summary(got):
    """Lines for the end: what came from where, and what looks wrong."""
    lines, ports, problems = [], {}, []
    for label, press in got.items():
        group = label.split(" ")[0]
        if press is None:
            problems.append(f"{label}: nothing was pressed")
            continue
        ports.setdefault(group, {}).setdefault(press["phys"] or press["path"], []).append(label)
    for group, by_port in ports.items():
        for port, labels in by_port.items():
            lines.append(f"{group}: {port}  ({len(labels)} controls)")
        if len(by_port) > 1 and group in ("P1", "P2"):
            main = max(by_port, key=lambda p: len(by_port[p]))
            for port, labels in by_port.items():
                if port != main:
                    problems.append(f"{', '.join(labels)} came from {port}, not {main} with the rest of {group}: "
                                    "wired to the wrong encoder?")
    if "P1" in ports and "P2" in ports:
        p1 = max(ports["P1"], key=lambda p: len(ports["P1"][p]))
        p2 = max(ports["P2"], key=lambda p: len(ports["P2"][p]))
        if p1 == p2:
            problems.append(f"Player 1 and Player 2 both came from {p1}: one encoder is doing both")
    return lines, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--section", default=",".join(ORDER), help="comma list of: " + ", ".join(SECTIONS) + ", free")
    parser.add_argument("--timeout", type=float, default=25, help="seconds to wait for each control before skipping it")
    parser.add_argument("--idle", type=float, metavar="SECONDS",
                        help="touch nothing for this long and list what the devices send by themselves")
    parser.add_argument("--min-motion", type=int, default=MIN_MOTION,
                        help="spinner and trackball: counts of movement in one direction before it counts "
                             f"(default {MIN_MOTION}; raise it if a light touch still registers)")
    parser.add_argument("--check", action="store_true", help="listen for 4 seconds, list the devices, stop")
    parser.add_argument("--out", help="where to save (default runs/panel-capture-<time>.json)")
    args = parser.parse_args()
    ssh = connect(args.host)
    events, stop = queue.Queue(), threading.Event()
    threading.Thread(target=stream, args=(ssh, events, stop), daemon=True).start()
    try:
        first = events.get(timeout=15)
        print("Listening to:")
        for d in first.get("listening", []):
            print("  " + d)
        if args.check:
            time.sleep(4)
            return 0
        if args.idle:
            print(f"\nTouch nothing for {args.idle:g} seconds...", flush=True)
            time.sleep(args.idle)
            seen = []
            while not events.empty():
                seen.append(events.get())
            found = noise(seen)
            print("Nothing sent anything by itself." if not found else "Sent by themselves (count, where, what):")
            for (where, kind, code), n in found.items():
                print(f"  {n:5d}  {where}  {kind} {code}")
            return 1 if found else 0
        steps = []
        for name in [s.strip() for s in args.section.split(",") if s.strip()]:
            if name == "free":
                continue
            title, items = SECTIONS[name]
            print(f"\n=== {title}: {len(items)} controls")
            steps += items
        print("\nPress each control once when asked, then let go. Stand at the panel; this window needs to stay open.")
        got = run(events, steps, timeout=args.timeout, min_motion=args.min_motion)
        if "free" in args.section:
            while True:
                name = input("\nName another control to capture (blank to finish): ").strip()
                if not name:
                    break
                got.update(run(events, [("EXTRA", name)], timeout=args.timeout))
    except KeyboardInterrupt:
        print("\nstopped")
        got = {}
    finally:
        stop.set()
        ssh.close()
    lines, problems = summary(got)
    print("\n=== Where each controller's presses came from")
    print("\n".join(lines) or "(nothing captured)")
    for p in problems:
        print("PROBLEM:", p)
    out = args.out or str(ROOT / "runs" / f"panel-capture-{time.strftime('%Y%m%d-%H%M%S')}.json")
    (ROOT / "runs").mkdir(exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"captured": time.strftime("%Y-%m-%d %H:%M:%S"), "controls": got, "problems": problems}, f, indent=1)
    print("saved", out)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
