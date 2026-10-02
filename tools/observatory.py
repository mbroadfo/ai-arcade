"""The Observatory: a dashboard in the browser showing the game's video beside what the player is doing and why.

Three inputs, each independent of the others:
  video    the Pi's frame server (pi/frame_server.py, port 8767; started by tools/start_pi_game.py)
  events   play.py's logged events and status lines (arcadekit/observatory.py sends them here, port 8770)
  browser  http://localhost:8780/ (the page is tools/observatory.html; it reads /events, a server-sent event stream)

It decides nothing and knows no game: it relays the video and whatever standard events arrive. It can run before,
during and between runs; play.py reconnects to it and the video reconnects to the Pi.

    python tools/observatory.py [--host PI] [--http-port 8780]
"""
import argparse
import base64
import collections
import io
import json
import socket
import struct
import sys
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from gamelib import DEFAULT_PI_HOST
from arcadekit.observatory import DEFAULT_ADDRESS

PAGE = Path(__file__).with_name("observatory.html")
FRAME_PORT = 8767
HEADER = 10  # frame (4), width (2), height (2), quarter turns (2): pi/frame_server.py
KEEP_EVENTS = 300  # recent events a newly opened page is given
TURN = {0: None, 1: Image.Transpose.ROTATE_270, 2: Image.Transpose.ROTATE_180, 3: Image.Transpose.ROTATE_90}


def decode_frame(payload):
    """A frame server message's payload -> (emulated frame number, upright RGB image)."""
    frame, width, height, turns = struct.unpack("<IHHH", payload[:HEADER])
    pixels = zlib.decompress(payload[HEADER:])
    image = Image.frombuffer("RGB", (width, height), pixels, "raw", "BGRX", 0, 1)
    if TURN.get(turns % 4):
        image = image.transpose(TURN[turns % 4])
    return frame, image


def png_base64(image):
    out = io.BytesIO()
    image.save(out, "PNG", compress_level=1)
    return base64.b64encode(out.getvalue()).decode()


class Hub:
    """What the pages are sent: recent events (numbered), the newest status, the newest video frame."""

    def __init__(self):
        self.cond = threading.Condition()
        self.events = collections.deque(maxlen=KEEP_EVENTS)
        self.seq = 0
        self.status, self.status_seq = None, 0
        self.frame, self.frame_seq = None, 0
        self.video = {"connected": False, "frame": None, "fps": None}
        self.video_seq = 0

    def add_event(self, record):
        with self.cond:
            if record.get("event") == "status":
                self.status, self.status_seq = record, self.status_seq + 1
            else:
                if record.get("event") == "run":
                    self.events.clear()  # a new run starts the page's timeline afresh
                self.seq += 1
                self.events.append((self.seq, record))
            self.cond.notify_all()

    def set_frame(self, png):
        with self.cond:
            self.frame, self.frame_seq = png, self.frame_seq + 1
            self.cond.notify_all()

    def set_video(self, **info):
        with self.cond:
            self.video.update(info)
            self.video_seq += 1
            self.cond.notify_all()


def read_exact(conn, n):
    data = bytearray()
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("frame server closed the connection")
        data += chunk
    return bytes(data)


def video_loop(hub, host, port):
    """Keep a connection to the Pi's frame server; turn each frame into a PNG for the pages."""
    while True:
        try:
            with socket.create_connection((host, port), timeout=5) as conn:
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                shown, since = 0, time.time()
                hub.set_video(connected=True)
                while True:
                    kind = read_exact(conn, 1)
                    payload = read_exact(conn, struct.unpack(">I", read_exact(conn, 4))[0])
                    if kind != b"S":
                        continue
                    frame, image = decode_frame(payload)
                    hub.set_frame(png_base64(image))
                    shown += 1
                    if time.time() - since >= 2:
                        hub.set_video(frame=frame, fps=round(shown / (time.time() - since), 1))
                        shown, since = 0, time.time()
        except (OSError, ConnectionError, zlib.error, struct.error):
            hub.set_video(connected=False, fps=None)
            time.sleep(2)


def events_loop(hub, address):
    """Accept players (play.py) and pass on each JSON line they send."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(address)
    listener.listen(4)

    def serve(conn):
        with conn, conn.makefile("r", encoding="utf-8", errors="replace") as lines:
            for line in lines:
                try:
                    hub.add_event(json.loads(line))
                except json.JSONDecodeError:
                    continue

    while True:
        conn, _ = listener.accept()
        threading.Thread(target=serve, args=(conn,), daemon=True).start()


def make_handler(hub):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = PAGE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/events":
                self.stream()
            else:
                self.send_error(404)

        def send(self, kind, data):
            text = data if isinstance(data, str) else json.dumps(data)
            self.wfile.write(f"event: {kind}\ndata: {text}\n\n".encode())

        def stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            seen, status_seen, frame_seen, video_seen = 0, 0, 0, -1
            try:
                while True:
                    with hub.cond:
                        hub.cond.wait_for(lambda: (hub.seq != seen or hub.status_seq != status_seen
                                                   or hub.frame_seq != frame_seen or hub.video_seq != video_seen),
                                          timeout=15)
                        if hub.events and hub.events[0][0] > seen + 1 and seen:
                            seen = hub.events[0][0] - 1  # fell behind past what is kept: skip to what there is
                        events = [r for n, r in hub.events if n > seen]
                        seen = hub.seq
                        status = hub.status if hub.status_seq != status_seen else None
                        status_seen = hub.status_seq
                        frame = hub.frame if hub.frame_seq != frame_seen else None
                        frame_seen = hub.frame_seq
                        video = dict(hub.video) if hub.video_seq != video_seen else None
                        video_seen = hub.video_seq
                    if video is not None:
                        self.send("video", video)
                    for record in events:
                        self.send("event", record)
                    if status is not None:
                        self.send("status", status)
                    if frame is not None:
                        self.send("frame", frame)
                    if not (video or events or status or frame):
                        self.wfile.write(b": still here\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_PI_HOST, help="the Pi (its frame server)")
    parser.add_argument("--video-port", type=int, default=FRAME_PORT)
    parser.add_argument("--events-port", type=int, default=DEFAULT_ADDRESS[1], help="where play.py sends events")
    parser.add_argument("--http-port", type=int, default=8780)
    parser.add_argument("--listen", default="127.0.0.1",
                        help="address for the page (0.0.0.0 to watch from another device on the LAN)")
    args = parser.parse_args()
    hub = Hub()
    threading.Thread(target=video_loop, args=(hub, args.host, args.video_port), daemon=True).start()
    threading.Thread(target=events_loop, args=(hub, (DEFAULT_ADDRESS[0], args.events_port)), daemon=True).start()
    server = ThreadingHTTPServer((args.listen, args.http_port), make_handler(hub))
    server.daemon_threads = True
    print(f"Observatory on http://{'localhost' if args.listen == '127.0.0.1' else args.listen}:{args.http_port}/ "
          f"(video from {args.host}:{args.video_port}, events on port {args.events_port})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
