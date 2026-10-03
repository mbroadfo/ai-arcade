"""The Observatory: the cabinet's control panel and the AI's dashboard, in the browser.

Inputs, each independent of the others:
  cabinet  pi/cabinet/cabinet.py over SSH (tools/cabinet_link.py): what is on the screen, every two seconds, and the
           catalog of games
  video    the Pi's frame server (pi/frame_server.py, port 8767; started by tools/start_pi_game.py)
  events   play.py's logged events and status lines (arcadekit/observatory.py sends them here, port 8770)
  browser  http://localhost:8780/ (the page is tools/observatory.html; it reads /events, a server-sent event stream)

What goes the other way, all on the operator's request:
  /api/play     start a game for a person (as EmulationStation would)
  /api/ai       start an AI run: MAME for the game, then play.py with the AI setup's answers (tools/ai_runner.py)
  /api/stop     end what is playing (an AI run is asked to finish its files first); /api/menu: back to the menu
  /api/speed    AI mode's game speed, while it runs (the player logs the speed it measures)
  /orders       standing orders for the running player (arcadekit/orders.py), which confirms with an `orders` event

It decides nothing about play and knows no game: the AI setup is read from the game package (tools/ai_setup.py) and
the dashboard shows the standard events whatever the game.

    python tools/observatory.py [--host PI] [--http-port 8780] [--listen 0.0.0.0]
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
import urllib.request
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from gamelib import DEFAULT_PI_HOST
from arcadekit.observatory import DEFAULT_ADDRESS
from arcadekit.systemone import DEFAULT_HOST as OLLAMA_HOST

PAGE = Path(__file__).with_name("observatory.html")
FRAME_PORT = 8767
HEADER = 10  # frame (4), width (2), height (2), quarter turns (2): pi/frame_server.py
KEEP_EVENTS = 300  # recent events a newly opened page is given
TURN = {0: None, 1: Image.Transpose.ROTATE_270, 2: Image.Transpose.ROTATE_180, 3: Image.Transpose.ROTATE_90}
POLL_SECONDS = 2.0
HIDDEN_SYSTEMS = {"retropie"}  # RetroPie's own settings menu, not games


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
    """What the pages are sent: recent events (numbered), the newest status, the newest video frame, and panels
    (named states that replace each other: what the cabinet shows, the AI run's progress)."""

    def __init__(self):
        self.cond = threading.Condition()
        self.events = collections.deque(maxlen=KEEP_EVENTS)
        self.seq = 0
        self.status, self.status_seq = None, 0
        self.sticky = {}  # the run's opening event and the orders now: every page that opens is given them
        self.players = []  # the connections of running players (play.py), for the operator's commands
        self.frame, self.frame_seq = None, 0
        self.video = {"connected": False, "frame": None, "fps": None}
        self.video_seq = 0
        self.panels, self.panels_seq = {}, {}

    def add_event(self, record):
        with self.cond:
            if record.get("event") == "status":
                self.status, self.status_seq = record, self.status_seq + 1
            else:
                if record.get("event") == "run":
                    self.events.clear()  # a new run starts the page's timeline afresh
                    self.sticky = {}
                if record.get("event") in ("run", "orders"):
                    self.sticky[record["event"]] = record
                self.seq += 1
                self.events.append((self.seq, record))
            self.cond.notify_all()

    def set_panel(self, name, value):
        with self.cond:
            if self.panels.get(name) == value:
                return
            self.panels[name] = value
            self.panels_seq[name] = self.panels_seq.get(name, 0) + 1
            self.cond.notify_all()

    def command(self, message):
        """Send a command to every connected player. Returns how many got it."""
        line = (json.dumps(message) + "\n").encode()
        sent = 0
        with self.cond:
            players = list(self.players)
        for conn in players:
            try:
                conn.sendall(line)
                sent += 1
            except OSError:
                pass
        return sent

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
        with hub.cond:
            hub.players.append(conn)
        hub.set_panel("players", len(hub.players))
        try:
            with conn, conn.makefile("r", encoding="utf-8", errors="replace") as lines:
                for line in lines:
                    try:
                        hub.add_event(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        finally:
            with hub.cond:
                hub.players.remove(conn)
            hub.set_panel("players", len(hub.players))

    while True:
        conn, _ = listener.accept()
        threading.Thread(target=serve, args=(conn,), daemon=True).start()


class Control:
    """The cabinet and AI runs, for the page's requests. None of it runs unless the operator asks."""

    def __init__(self, hub, host):
        from ai_runner import Runner
        from cabinet_link import Cabinet
        self.hub, self.host = hub, host
        self.cabinet = Cabinet(host)
        self.runner = Runner(self.cabinet, hub.command, lambda state: hub.set_panel("control", state), host)
        hub.set_panel("control", self.runner.state)
        self.catalog_cache, self.catalog_lock = None, threading.Lock()

    def poll(self):
        """What the cabinet shows, every POLL_SECONDS, as the "cabinet" panel."""
        from cabinet_link import CabinetError
        while True:
            try:
                state = self.cabinet.status()
                state.pop("t", None)
            except CabinetError as exc:
                state = {"mode": "offline", "error": str(exc)}
            self.hub.set_panel("cabinet", state)
            time.sleep(POLL_SECONDS)

    def catalog(self, refresh=False):
        import ai_setup
        with self.catalog_lock:
            if self.catalog_cache is None or refresh:
                raw = self.cabinet.catalog()
                ai = {(spec.split("/")[0], info["file"]): spec for spec, info in ai_setup.ai_games().items()}
                systems = []
                for s in raw["systems"]:
                    if s["name"] in HIDDEN_SYSTEMS:
                        continue
                    for g in s["games"]:
                        g["ai"] = ai.get((s["name"], g["stem"]))
                    systems.append(s)
                self.catalog_cache = {"systems": systems, "t": raw.get("t")}
            return self.catalog_cache

    def play(self, system, path):
        self._end_ai()
        return self.cabinet.launch(system, path)

    def start_ai(self, game, answers):
        import ai_setup
        args = ai_setup.command_line(game, answers)  # checked before anything is stopped
        script = "run_lab.py" if ai_setup.schema(game).get("kind") == "lab" else "play.py"
        speed = float(answers.get("speed", 0.85))
        if not 0.2 <= speed <= 1.0:
            raise ValueError("speed: 0.2 to 1.0")
        if self.runner.state["state"] == "starting":
            raise RuntimeError("an AI run is starting: wait for it, or stop it")

        def go():  # the run on screen (if any) finishes its files first, as the picker says it will
            self.hub.set_panel("control", {**self.runner.state, "state": "stopping", "next": game})
            self._end_ai()
            self.runner.start(game, args, speed, script)
        if self.runner.busy() or self.hub.players:
            threading.Thread(target=go, daemon=True).start()
            return {"args": args, "after": "stopping the current run"}
        self.runner.start(game, args, speed, script)
        return {"args": args}

    def _end_ai(self, wait=25):
        if self.runner.stop() or self.hub.command({"op": "stop"}):
            deadline = time.time() + wait
            while time.time() < deadline and (self.runner.busy() or self.hub.players):
                time.sleep(0.2)

    def stop(self):
        if self.runner.busy() or self.hub.players:  # an AI run: the player writes its results; the game stays up
            threading.Thread(target=self._end_ai, daemon=True).start()  # for another run, or Back to menu
            return {"ok": True, "stopping": "ai"}
        return self.cabinet.stop()

    def menu(self):
        def go():
            self._end_ai()
            self.cabinet.menu()
        threading.Thread(target=go, daemon=True).start()
        return {"ok": True}


def ollama_models():
    with urllib.request.urlopen(OLLAMA_HOST.rstrip("/") + "/api/tags", timeout=3) as r:
        return sorted(m["name"] for m in json.loads(r.read()).get("models", []))


def make_handler(hub, control=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, data):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path, _, query = self.path.partition("?")
            if path in ("/", "/index.html"):
                body = PAGE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/events":
                self.stream()
            elif path == "/api/catalog" and control:
                self.guarded(lambda: control.catalog(refresh="refresh" in query))
            elif path.startswith("/api/ai/") and control:
                import ai_setup
                self.guarded(lambda: ai_setup.schema(path[len("/api/ai/"):]))
            elif path == "/api/models":
                self.guarded(ollama_models)
            else:
                self.send_error(404)

        def guarded(self, action):
            try:
                self.reply(200, action())
            except (ValueError, KeyError, RuntimeError, ModuleNotFoundError, OSError) as exc:
                self.reply(409 if isinstance(exc, RuntimeError) else 400, {"error": str(exc)})

        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            except ValueError:
                self.reply(400, {"error": "expected JSON"})
                return
            if self.path == "/orders":
                items = body.get("orders")
                if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
                    self.reply(400, {"error": "expected {\"orders\": [text, ...]}"})
                    return
                sent = hub.command({"op": "orders", "orders": items})
                self.reply(200 if sent else 409, {"players": sent})
            elif control and self.path == "/api/play":
                self.guarded(lambda: control.play(str(body["system"]), str(body["path"])))
            elif control and self.path == "/api/ai":
                self.guarded(lambda: control.start_ai(str(body["game"]), body.get("answers") or {}))
            elif control and self.path == "/api/stop":
                self.guarded(control.stop)
            elif control and self.path == "/api/speed":
                self.guarded(lambda: control.cabinet.speed(float(body["speed"])))
            elif control and self.path == "/api/menu":
                self.guarded(control.menu)
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
            seen, status_seen, frame_seen, video_seen, panels_seen = 0, 0, 0, -1, {}
            with hub.cond:
                for record in hub.sticky.values():  # the run and the orders, if they are older than the events kept
                    if not any(r is record for _, r in hub.events):
                        self.send("event", record)
            try:
                while True:
                    with hub.cond:
                        hub.cond.wait_for(lambda: (hub.seq != seen or hub.status_seq != status_seen
                                                   or hub.frame_seq != frame_seen or hub.video_seq != video_seen
                                                   or hub.panels_seq != panels_seen), timeout=15)
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
                        panels = {n: hub.panels[n] for n, q in hub.panels_seq.items() if panels_seen.get(n) != q}
                        panels_seen = dict(hub.panels_seq)
                    for name, value in panels.items():
                        self.send("panel", {"name": name, "value": value})
                    if video is not None:
                        self.send("video", video)
                    for record in events:
                        self.send("event", record)
                    if status is not None:
                        self.send("status", status)
                    if frame is not None:
                        self.send("frame", frame)
                    if not (panels or video or events or status or frame):
                        self.wfile.write(b": still here\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_PI_HOST, help="the Pi (its frame server and cabinet controls)")
    parser.add_argument("--video-port", type=int, default=FRAME_PORT)
    parser.add_argument("--events-port", type=int, default=DEFAULT_ADDRESS[1], help="where play.py sends events")
    parser.add_argument("--http-port", type=int, default=8780)
    parser.add_argument("--listen", default="127.0.0.1",
                        help="address for the page (0.0.0.0: anyone on the LAN can watch and control the cabinet)")
    parser.add_argument("--watch-only", action="store_true", help="no cabinet controls: the dashboard alone")
    args = parser.parse_args()
    hub = Hub()
    threading.Thread(target=video_loop, args=(hub, args.host, args.video_port), daemon=True).start()
    threading.Thread(target=events_loop, args=(hub, (DEFAULT_ADDRESS[0], args.events_port)), daemon=True).start()
    control = None
    if not args.watch_only:
        control = Control(hub, args.host)
        threading.Thread(target=control.poll, daemon=True).start()
    hub.set_panel("features", {"control": control is not None, "host": args.host})
    server = ThreadingHTTPServer((args.listen, args.http_port), make_handler(hub, control))
    server.daemon_threads = True
    print(f"Observatory on http://{'localhost' if args.listen == '127.0.0.1' else args.listen}:{args.http_port}/ "
          f"(cabinet {args.host}, video port {args.video_port}, events on port {args.events_port})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
