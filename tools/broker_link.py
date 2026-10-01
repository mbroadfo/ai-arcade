"""Persistent connection to the Pi's controller broker (newline-delimited JSON, port 8765)."""
import json
import socket
import time


class BrokerLink:
    def __init__(self, host, port=8765):
        self.host, self.port, self.sock, self.held = host, port, None, None
        self.calls = 0
        self.call_ms = []

    def _connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=3)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.file = self.sock.makefile("rwb")

    def send(self, payload):
        t0 = time.time()
        for attempt in (0, 1):
            try:
                if self.sock is None:
                    self._connect()
                self.file.write((json.dumps(payload) + "\n").encode())
                self.file.flush()
                reply = self.file.readline()
                if not reply:
                    raise ConnectionError("broker closed the connection")
                self.calls += 1
                self.call_ms.append((time.time() - t0) * 1000)
                return json.loads(reply)
            except OSError:
                self.sock = None
                if attempt:
                    raise

    def tap(self, action, ms=200):
        self.send({"op": "tap", "player": 1, "action": action, "ms": ms})

    def steer(self, direction):
        """Hold exactly one direction (4-way gate): release the old one first."""
        if direction == self.held:
            return
        if self.held:
            self.send({"op": "release", "player": 1, "action": self.held})
        if direction:
            self.send({"op": "press", "player": 1, "action": direction})
        self.held = direction

    def release_all(self):
        self.send({"op": "release_all"})
        self.held = None
