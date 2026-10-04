"""Screenshots from the Pi's frame stream around a control press, as one contact sheet (frames side by side), to see
what a control does on the screen. Code only presses and looks; nothing plays.

    python games/arcade/vanguard/scripts/shots.py OUT.png [--press 1.BUTTON_1] [--ms 300] [--frames 6] [--after 0.0]
"""
import argparse
import socket
import struct
import sys
import threading
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))

from controller_client import send  # noqa: E402
from gamelib import DEFAULT_PI_HOST  # noqa: E402
from observatory import decode_frame, read_exact  # noqa: E402


def frames(host, count, seconds, out):
    """Collect (time, image) from the frame server for `seconds`, keeping about `count` evenly spread."""
    got = []
    with socket.create_connection((host, 8767), timeout=5) as conn:
        end = time.time() + seconds
        while time.time() < end:
            kind = read_exact(conn, 1)
            payload = read_exact(conn, struct.unpack(">I", read_exact(conn, 4))[0])
            if kind == b"S":
                got.append((time.time(), decode_frame(payload)[1]))
    step = max(1, len(got) // count)
    out.extend(got[::step][:count])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--press", default="", help="PLAYER.ACTION[+PLAYER.ACTION], e.g. 1.BUTTON_1 or 1.UP+1.BUTTON_2")
    parser.add_argument("--ms", type=int, default=300)
    parser.add_argument("--frames", type=int, default=6)
    parser.add_argument("--seconds", type=float, default=1.2)
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    args = parser.parse_args()
    held = [(int(p), a) for p, _, a in (c.partition(".") for c in args.press.split("+") if c)]
    out = []
    thread = threading.Thread(target=frames, args=(args.host, args.frames, args.seconds, out))
    thread.start()
    time.sleep(0.15)
    for player, action in held:
        send(args.host, 8765, {"op": "press", "player": player, "action": action})
    time.sleep(args.ms / 1000)
    for player, action in held:
        send(args.host, 8765, {"op": "release", "player": player, "action": action})
    thread.join()
    w, h = out[0][1].size
    sheet = Image.new("RGB", (w * len(out), h))
    for i, (_, image) in enumerate(out):
        sheet.paste(image, (i * w, 0))
    sheet.save(args.out)
    print(f"{len(out)} frames of {w}x{h} -> {args.out}")


if __name__ == "__main__":
    main()
