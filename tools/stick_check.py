"""Check a stick's wiring and say exactly which wires to swap. Run it yourself at the panel, in a terminal.

    python tools/stick_check.py [--player P2]            # push the stick in each direction when asked
    python tools/stick_check.py --player P2 --live       # just report each push as it happens, while you try wires

A standard stick (Player 1's) reads: up = axis 1 negative, down = axis 1 positive, left = axis 0 negative, right = axis 0
positive. Each of the stick's four switches goes to one of the encoder's four direction terminals, and the encoder turns
the terminal into one of those four readings. When a switch is on the wrong terminal, the stick reads as another
direction; this program asks for each direction, sees what the encoder reported, and works out which terminals' wires
trade places.

(Read-only: it listens to the encoder on its USB port and changes nothing.)
"""
import argparse
import queue
import sys
import threading
import time

from gamelib import DEFAULT_PI_HOST
from guided_capture import stream
from probe_panel import connect

# what a reading means on a standard stick: (axis, sign) -> the terminal / direction it comes from
STANDARD = {(1, -1): "UP", (1, 1): "DOWN", (0, -1): "LEFT", (0, 1): "RIGHT"}
ORDER = ["UP", "DOWN", "LEFT", "RIGHT"]
USB_PORTS = {"P1": "usb-xhci-hcd.0-1.2/input0", "P2": "usb-xhci-hcd.0-1.3/input0"}


def reading(event):
    """A raw axis event -> the standard direction it reads as ('UP'...), or None when the axis is near the middle."""
    if event.get("type") != 3 or event.get("code") not in (0, 1):
        return None
    span = max(event["max"] - event["min"], 1)
    pos = (event["value"] - event["min"]) / span
    sign = -1 if pos < 0.25 else 1 if pos > 0.75 else 0
    return STANDARD.get((event["code"], sign)) if sign else None


def plan(observed):
    """observed: {direction pushed: direction it read as}. -> (list of instructions, wired right?).

    The switch for UP is on the terminal that reads as observed['UP'], and so on: a permutation of the four terminals.
    Each pair of terminals that hold each other's switches needs their wires traded."""
    notes, seen = [], set()
    for start in ORDER:
        if start in seen:
            continue
        cycle, d = [], start
        while d not in seen and d in observed:
            seen.add(d)
            cycle.append(d)
            d = observed[d]
        if len(cycle) == 2 and observed[cycle[0]] == cycle[1] and observed[cycle[1]] == cycle[0]:
            a, b = cycle
            notes.append(f"swap the wires on the encoder's {a} and {b} terminals "
                         f"(the stick's {a} switch is on the {b} terminal, and its {b} switch on the {a} terminal)")
        elif len(cycle) > 1:
            notes.append("these three or four terminals go round in a circle, " + " -> ".join(cycle + [cycle[0]]) +
                         ": the stick's switch for each is on the terminal named after the next. Move each wire to the terminal named for its own direction")
    return notes, all(observed.get(d) == d for d in ORDER)


def wait_push(events, port, seconds=30):
    """The first push of a stick axis on the encoder at `port`: its direction, or None after `seconds`."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            e = events.get(timeout=0.2)
        except queue.Empty:
            continue
        if "listening" in e or (e.get("phys") or "") != port:
            continue
        direction = reading(e)
        if direction:
            return direction
    return None


def let_go(events, port, seconds=1.2):
    """Drain events until the stick has been quiet for `seconds`."""
    quiet = time.time()
    while time.time() - quiet < seconds:
        try:
            e = events.get(timeout=0.2)
        except queue.Empty:
            continue
        if (e.get("phys") or "") == port and e.get("type") == 3:
            quiet = time.time()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--player", choices=("P1", "P2"), default="P2")
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--live", action="store_true", help="report every push as it happens (Ctrl-C to stop)")
    args = parser.parse_args()
    port = USB_PORTS[args.player]
    ssh = connect(args.host)
    events, stop = queue.Queue(), threading.Event()
    threading.Thread(target=stream, args=(ssh, events, stop), daemon=True).start()
    try:
        events.get(timeout=15)
        if args.live:
            print(f"{args.player}'s stick, live. Push in any direction; it says what the encoder reads. Ctrl-C to stop.")
            last = None
            while True:
                e = events.get()
                if (e.get("phys") or "") != port:
                    continue
                d = reading(e)
                if d and d != last:
                    print("  reads as", d, flush=True)
                last = d if d else None
        observed = {}
        print(f"{args.player}'s stick: push it each way when asked, hold about a second, then let go.\n")
        for want in ORDER:
            print(f"Push the stick {want}", flush=True)
            got = wait_push(events, port)
            if got is None:
                print("  nothing seen")
                continue
            observed[want] = got
            print(f"  it read as {got}  " + ("OK" if got == want else f"WRONG (should read as {want})"), flush=True)
            let_go(events, port)
        notes, right = plan(observed)
        print()
        if len(observed) < 4:
            print("Not all four directions were seen, so no plan. Check the stick's connections and run it again.")
        elif right:
            print(f"{args.player}'s stick is wired like Player 1's. Nothing to swap.")
        else:
            print("To wire it like Player 1's:")
            for n in notes:
                print("  - " + n)
            print("then run this again to check.")
        return 0 if right else 1
    except KeyboardInterrupt:
        return 0
    finally:
        stop.set()
        ssh.close()


if __name__ == "__main__":
    sys.exit(main())
