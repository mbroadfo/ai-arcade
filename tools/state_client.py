"""PC-side client for the Pi state stream (pi/state_server.py), plus a latency measurement.

    python tools/state_client.py --measure          # needs MAME + state server running on the Pi
"""
import argparse
import json
import socket
import statistics
import struct
import sys
import threading
import time

from controller_client import send
from gamelib import DEFAULT_GAME, load_game
from state_regions import expand

DEFAULT_PORT = 8766


class StateStream:
    """Connects to the Pi and yields snapshots. `game` (a game package) supplies decode(); without it
    only raw snapshots (next_raw) are available."""

    def __init__(self, host, port=DEFAULT_PORT, timeout=5.0, game=None):
        self.host, self.port, self.timeout, self.game = host, port, timeout, game
        self.reconnects = 0
        self._closed = False
        self._connect()

    def _connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        kind, payload = self._read_message()
        if kind != b"H":
            raise RuntimeError("expected hello from state server, got %r" % kind)
        self.regions = [tuple(r) for r in json.loads(payload)["regions"]]

    def _read_exact(self, n):
        chunks = []
        while n:
            chunk = self.sock.recv(n)
            if not chunk:
                raise ConnectionError("state server closed the connection")
            chunks.append(chunk)
            n -= len(chunk)
        return b"".join(chunks)

    def _read_message(self):
        header = self._read_exact(5)
        return header[:1], self._read_exact(struct.unpack(">I", header[1:])[0])

    def next_raw(self):
        """Block for the next snapshot; returns (frame, payload bytes after the frame counter)."""
        kind, payload = self._read_message()
        while kind != b"S":
            kind, payload = self._read_message()
        return struct.unpack("<I", payload[:4])[0], payload[4:]

    def next_state(self):
        """Block for the next snapshot; returns (frame, decoded game state, 4096-byte RAM image)."""
        frame, body = self.next_raw()
        image = expand(body, self.regions)
        return frame, self.game.decode(image), image

    def start_latest(self):
        """Read continuously in a background thread so latest() never returns a stale queue entry."""
        self._latest = None
        self._closed = False
        self._lock = threading.Lock()
        self._fresh = threading.Condition(self._lock)

        def pump():
            backoff = 0.2
            while not self._closed:
                try:
                    item = self.next_state()
                except (OSError, ConnectionError) as exc:
                    if self._closed:
                        return
                    print(f"[state_client] stream lost ({exc!r}); reconnecting", file=sys.stderr, flush=True)
                    while not self._closed:
                        try:
                            self._connect()
                            self.reconnects += 1
                            backoff = 0.2
                            break
                        except OSError:
                            time.sleep(backoff)
                            backoff = min(backoff * 2, 5.0)
                    continue
                with self._fresh:
                    self._latest = item
                    self._fresh.notify_all()

        threading.Thread(target=pump, daemon=True).start()

    def latest(self, newer_than=-1, timeout=2.0):
        """Newest (frame, state, image) with frame > newer_than; waits up to timeout for one."""
        with self._fresh:
            if not self._fresh.wait_for(lambda: self._latest and self._latest[0] > newer_than, timeout):
                raise TimeoutError("no newer snapshot from the Pi")
            return self._latest

    def close(self):
        self._closed = True
        self.sock.close()


def measure(args):
    stream = StateStream(args.host, args.state_port, game=load_game(args.game))
    print("connected; regions:", stream.regions)

    print(f"\nstream rate over {args.seconds}s ...")
    start, frames, arrivals, last = time.time(), 0, [], None
    first_frame = last_frame = None
    nbytes = 0
    while time.time() - start < args.seconds:
        frame, body = stream.next_raw()
        now = time.time()
        if last is not None:
            arrivals.append((now - last) * 1000)
        last = now
        first_frame = frame if first_frame is None else first_frame
        last_frame = frame
        nbytes += len(body) + 9
        frames += 1
    elapsed = time.time() - start
    assert first_frame is not None and last_frame is not None, "no snapshots received"
    print(f"  snapshots/s: {frames / elapsed:.1f}   emulated fps: {(last_frame - first_frame) / elapsed:.1f}"
          f"   bandwidth: {nbytes / elapsed / 1024:.0f} KiB/s")
    print(f"  gap between snapshots: median {statistics.median(arrivals):.1f} ms,"
          f" p95 {sorted(arrivals)[int(len(arrivals) * 0.95)]:.1f} ms, max {max(arrivals):.1f} ms")

    print("\ncontrol -> state loop (press COIN, time from sending the press until credits change) ...")
    broker_ms, visible_ms = [], []
    for _ in range(args.taps):
        _, state, _ = stream.next_state()
        before = state.credits
        t0 = time.time()
        send(args.host, args.broker_port, {"op": "press", "player": 1, "action": "COIN"})
        broker_ms.append((time.time() - t0) * 1000)
        while time.time() - t0 < 3:
            _, state, _ = stream.next_state()
            if state.credits != before:
                visible_ms.append((time.time() - t0) * 1000)
                break
        else:
            print("  no credit change within 3 s (game not in attract/coin mode?)")
        send(args.host, args.broker_port, {"op": "release", "player": 1, "action": "COIN"})
        time.sleep(0.5)
    if visible_ms:
        print(f"  broker round trip (press accepted): median {statistics.median(broker_ms):.0f} ms")
        print(f"  press sent -> effect visible in state stream: median {statistics.median(visible_ms):.0f} ms,"
              f" min {min(visible_ms):.0f}, max {max(visible_ms):.0f}")
    stream.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--state-port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--broker-port", type=int, default=8765)
    parser.add_argument("--game", default=DEFAULT_GAME, help="<system>/<name>, e.g. arcade/pacman")
    parser.add_argument("--measure", action="store_true")
    parser.add_argument("--seconds", type=int, default=10)
    parser.add_argument("--taps", type=int, default=5)
    args = parser.parse_args()
    if args.measure:
        measure(args)
        return 0
    stream = StateStream(args.host, args.state_port, game=load_game(args.game))
    while True:
        frame, state, _ = stream.next_state()
        print(frame, state)


if __name__ == "__main__":
    sys.exit(main())
