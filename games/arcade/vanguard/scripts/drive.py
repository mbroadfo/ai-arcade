"""Scripted driver for recording sessions: coin, start, then hold all four fire buttons and sweep the ship up and down
(and sometimes left or right) for a while. Code presses controls only to produce varied data; nothing here plays well.

    python games/arcade/vanguard/scripts/drive.py [--seconds 120]
"""
import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))

from controller_client import send  # noqa: E402
from gamelib import DEFAULT_PI_HOST  # noqa: E402

FIRES = ["BUTTON_1", "BUTTON_2", "BUTTON_3", "BUTTON_4"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    args = parser.parse_args()
    rng = random.Random(4)
    do = lambda op, action: send(args.host, 8765, {"op": op, "player": 1, "action": action})  # noqa: E731
    send(args.host, 8765, {"op": "tap", "player": 1, "action": "COIN", "ms": 150})
    time.sleep(1)
    send(args.host, 8765, {"op": "tap", "player": 1, "action": "START", "ms": 150})
    time.sleep(3)
    # a held button fires one shot: pulse the four in turn
    end, held, next_move, shots = time.time() + args.seconds, None, 0, 0
    while time.time() < end:
        if time.time() >= next_move:
            move = rng.choice(["UP", "DOWN", "UP", "DOWN", "LEFT", "RIGHT", None])
            if held:
                do("release", held)
            held = move
            if move:
                do("press", move)
            next_move = time.time() + rng.uniform(0.4, 1.6)
        send(args.host, 8765, {"op": "tap", "player": 1, "action": FIRES[shots % 4], "ms": 60})
        shots += 1
        time.sleep(0.05)
    send(args.host, 8765, {"op": "release_all"})


if __name__ == "__main__":
    main()
