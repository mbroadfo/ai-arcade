"""Controlled session on the Pi: one input at a time while work RAM is sampled as fast as the link allows, saved for
offline analysis (analyze.py). Finds which addresses each control moves and which fire button shoots which way.

    python games/arcade/vanguard/scripts/probe.py [--out runs/vanguard/probe.pkl]

Stops any game on the Pi first. Code only presses controls here; nothing plays.
"""
import argparse
import pickle
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))

from discover_state import Session  # noqa: E402
from gamelib import DEFAULT_PI_HOST  # noqa: E402

# (label, controls held together, seconds held, seconds idle after)
SCHEDULE = ([("idle", [], 3.0, 0.0)]
            + [(name, [(1, name)], 1.0, 1.0) for name in ("UP", "DOWN", "LEFT", "RIGHT")]
            + [(f"BUTTON_{n}", [(1, f"BUTTON_{n}")], 0.6, 1.2) for n in (1, 2, 3, 4)]
            + [(f"UP+BUTTON_{n}", [(1, "UP"), (1, f"BUTTON_{n}")], 0.6, 1.2) for n in (1, 2, 3, 4)])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "runs" / "vanguard" / "probe.pkl"))
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    args = parser.parse_args()
    session = Session(SimpleNamespace(host=args.host, user="pi", broker_port=8765, romset="vanguard", system="arcade",
                                      start=0x0000, end=0x03FF))
    samples, label, lock, running = [], ["wait"], threading.Lock(), [True]

    def sampler():
        while running[0]:
            try:
                data = session.snap()
            except Exception as error:  # a missed sample is only a gap
                print("snap failed:", error)
                continue
            with lock:
                samples.append((time.time(), label[0], bytes(data)))

    try:
        session.start_mame()
        session.tap("COIN")
        time.sleep(1)
        session.tap("START")
        time.sleep(4)
        thread = threading.Thread(target=sampler, daemon=True)
        thread.start()
        for name, controls, hold, idle in SCHEDULE:
            label[0] = name
            if controls:
                session.hold(controls, hold)
            else:
                time.sleep(hold)
            label[0] = name + ".after"
            time.sleep(idle)
        running[0] = False
        thread.join(timeout=5)
    finally:
        session.close()
    with open(args.out, "wb") as f:
        pickle.dump(samples, f)
    print(f"{len(samples)} samples -> {args.out}")


if __name__ == "__main__":
    main()
