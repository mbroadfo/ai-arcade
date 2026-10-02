"""The player's events, live: what the decisions log records, also sent to the Observatory (tools/observatory.py).

A player writes one JSON line per event to its decisions log. EventSink stands in for that file: every line still goes
to the file, and also to a LiveSink, which forwards it to the dashboard server over TCP. The player needs no change and
the dashboard needs no knowledge of the game: it shows whatever standard events arrive.

LiveSink never slows the player. Lines go into a bounded queue that a background thread sends; with no dashboard
running, or one that has fallen behind, lines are dropped (the file has them all) and it reconnects every few seconds.
Besides the logged events, play.py sends `status` lines (what is on screen now) to the live sink only.

The same connection carries the operator's commands back: JSON lines from the dashboard, handed to `on_command` (play.py
sets it; the one command so far is {"op": "orders", "orders": [...]}, arcadekit.orders).
"""
import json
import queue
import socket
import threading
import time

DEFAULT_ADDRESS = ("127.0.0.1", 8770)
QUEUE_LINES = 2000
RETRY_SECONDS = 3.0


class LiveSink:
    def __init__(self, address=DEFAULT_ADDRESS, connect=socket.create_connection, on_command=None, hello=None):
        """hello: a callable giving the records a dashboard must have on every (re)connection, sent first (the run's
        opening record, the standing orders now)."""
        self.address, self.connect, self.on_command, self.hello = address, connect, on_command, hello
        self.lines = queue.Queue(maxsize=QUEUE_LINES)
        self.dropped = 0
        self.connected = False
        self.closed = False
        self.thread = threading.Thread(target=self._run, name="observatory-sink", daemon=True)
        self.thread.start()

    def write(self, line):
        """Queue one JSON line (with or without its newline). Never blocks."""
        if not line.endswith("\n"):
            line += "\n"
        try:
            self.lines.put_nowait(line)
        except queue.Full:
            self.dropped += 1

    def send(self, record):
        self.write(json.dumps(record))

    def _run(self):
        while not self.closed:
            try:
                conn = self.connect(self.address, timeout=2.0)
            except OSError:
                self._discard()  # nobody listening: what happened meanwhile is in the file
                time.sleep(RETRY_SECONDS)
                continue
            self.connected = True
            threading.Thread(target=self._commands, args=(conn,), name="observatory-commands", daemon=True).start()
            try:
                with conn:
                    for record in (self.hello() if self.hello else ()):
                        conn.sendall((json.dumps(record) + "\n").encode())
                    while not self.closed:
                        try:
                            line = self.lines.get(timeout=0.5)
                        except queue.Empty:
                            continue
                        conn.sendall(line.encode())
            except OSError:
                pass
            self.connected = False

    def _commands(self, conn):
        """Read the dashboard's commands until the connection ends."""
        buffer = b""
        while not self.closed:
            try:
                chunk = conn.recv(4096)
            except socket.timeout:  # the connection's timeout guards sends; for reading, quiet is normal
                continue
            except OSError:
                return
            if not chunk:
                return
            buffer += chunk
            *lines, buffer = buffer.split(b"\n")
            for line in lines:
                try:
                    command = json.loads(line)
                except ValueError:
                    continue
                if self.on_command and isinstance(command, dict):
                    try:
                        self.on_command(command)
                    except Exception:  # a bad command must not end the connection
                        pass

    def _discard(self):
        while True:
            try:
                self.lines.get_nowait()
            except queue.Empty:
                return
            self.dropped += 1

    def close(self, drain_seconds=1.0):
        """Stop, after giving queued lines (the last game's end, say) a moment to go out."""
        deadline = time.time() + drain_seconds
        while self.connected and not self.lines.empty() and time.time() < deadline:
            time.sleep(0.05)
        self.closed = True


class EventSink:
    """A file-like stand-in for the decisions log: writes go to the file and to every live sink."""

    def __init__(self, file, *live):
        self.file, self.live = file, live
        self.lock = threading.Lock()  # the player and the orders (from the dashboard's thread) both write

    def write(self, text):
        with self.lock:
            self.file.write(text)
            for sink in self.live:
                sink.write(text)

    def flush(self):
        self.file.flush()

    def close(self):
        self.file.close()
        for sink in self.live:
            sink.close()
