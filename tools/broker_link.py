"""Persistent connection to the Pi's controller broker (newline-delimited JSON, port 8765)."""
import json
import socket
import time


class BrokerLink:
    def __init__(self, host, port=8765):
        self.host, self.port, self.sock = host, port, None
        self.holding = frozenset()  # the actions held down now
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

    @property
    def held(self):
        """The one action held, or None (for games that hold one direction at a time)."""
        return next(iter(self.holding)) if len(self.holding) == 1 else None

    def hold(self, actions):
        """Hold exactly these actions (directions and buttons together, e.g. {"LEFT", "BUTTON_1"}): release what is
        no longer wanted first, then press what is new. Holding the same set again sends nothing."""
        actions = frozenset(a for a in actions if a)
        for action in sorted(self.holding - actions):
            self.send({"op": "release", "player": 1, "action": action})
        for action in sorted(actions - self.holding):
            self.send({"op": "press", "player": 1, "action": action})
        self.holding = actions

    def steer(self, direction):
        """Hold exactly one direction (a 4-way stick), or nothing for None."""
        self.hold({direction} if direction else set())

    def release_all(self):
        self.send({"op": "release_all"})
        self.holding = frozenset()
