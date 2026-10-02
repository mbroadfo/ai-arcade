"""Record the Pi's state stream (RAM images of the game's IMAGE window) to a pickle for offline analysis.

    python tools/record_stream.py --game arcade/pacman --seconds 240 --out recording.pkl
"""
import argparse
import pickle
import sys
import time

from gamelib import DEFAULT_GAME, load_game
from state_client import StateStream
from state_regions import expand


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--seconds", type=int, default=240)
    parser.add_argument("--out", required=True)
    parser.add_argument("--game", default=DEFAULT_GAME, help="<system>/<name>: whose IMAGE window to rebuild")
    args = parser.parse_args()

    game = load_game(args.game)
    stream = StateStream(args.host)
    frames, t_end = [], time.time() + args.seconds
    while time.time() < t_end:
        frame, body = stream.next_raw()
        frames.append((frame, expand(body, stream.regions, *game.IMAGE)))
    stream.close()
    with open(args.out, "wb") as f:
        pickle.dump(frames, f)
    print(f"recorded {len(frames)} snapshots over {args.seconds}s -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
