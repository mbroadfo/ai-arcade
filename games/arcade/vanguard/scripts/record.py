"""Record a play session: every RAM image from the state stream and the video frames (PNG, with the emulated frame
number to line them up), to one pickle for offline analysis. Someone plays on the cabinet meanwhile.

    python games/arcade/vanguard/scripts/record.py --seconds 150 --out runs/vanguard/human1.pkl
"""
import argparse
import io
import pickle
import socket
import struct
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))

from gamelib import DEFAULT_PI_HOST, load_game  # noqa: E402
from observatory import decode_frame, read_exact  # noqa: E402
from state_client import StateStream  # noqa: E402
from state_regions import expand  # noqa: E402


def record_video(host, end, out):
    with socket.create_connection((host, 8767), timeout=5) as conn:
        while time.time() < end:
            kind = read_exact(conn, 1)
            payload = read_exact(conn, struct.unpack(">I", read_exact(conn, 4))[0])
            if kind == b"S":
                frame, image = decode_frame(payload)
                png = io.BytesIO()
                image.save(png, "PNG", compress_level=1)
                out.append((frame, time.time(), png.getvalue()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--seconds", type=int, default=150)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    game = load_game("arcade/vanguard")
    stream = StateStream(args.host)
    video, ram, end = [], [], time.time() + args.seconds
    thread = threading.Thread(target=record_video, args=(args.host, end, video), daemon=True)
    thread.start()
    print("recording...", flush=True)
    while time.time() < end:
        try:
            frame, body = stream.next_raw()
        except TimeoutError:  # a paused or menu-held game sends nothing: wait it out
            continue
        ram.append((frame, time.time(), expand(body, stream.regions, *game.IMAGE)))
    stream.close()
    thread.join(timeout=3)
    with open(args.out, "wb") as f:
        pickle.dump({"ram": ram, "video": video}, f)
    print(f"{len(ram)} RAM images, {len(video)} video frames over {args.seconds}s -> {args.out}")


if __name__ == "__main__":
    main()
