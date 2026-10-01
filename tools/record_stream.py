"""Record the Pi's state stream (full 4096-byte RAM images) to a pickle for offline analysis.

    python tools/record_stream.py --seconds 240 --out recording.pkl
"""
import argparse
import pickle
import sys
import time

from state_client import StateStream


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--seconds", type=int, default=240)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    stream = StateStream(args.host)
    frames, t_end = [], time.time() + args.seconds
    while time.time() < t_end:
        frame, _, image = stream.next_state()
        frames.append((frame, image))
    stream.close()
    with open(args.out, "wb") as f:
        pickle.dump(frames, f)
    print(f"recorded {len(frames)} snapshots over {args.seconds}s -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
