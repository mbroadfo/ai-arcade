#!/usr/bin/env python3
"""Stream MAME game-state snapshots from the Pi to any number of PC clients over TCP.

The Pi only runs the game: tools/mame_state_export.lua writes /dev/shm/ai-arcade-state.bin
(4-byte little-endian frame counter + the exported regions). This process pushes every new
snapshot to connected clients and does nothing else. Inputs go the other way through the
controller broker (port 8765).

Wire format, both directions of framing identical: 1 byte kind, 4 byte big-endian length, payload.
  kind "H": JSON hello, sent once on connect: {"regions": [[start, end, every], ...]}
  kind "S": one snapshot, the raw state file bytes

Standard library only (Pi runs Python 3.7). No authentication, same trust model as the broker:
keep it on the cabinet LAN.
"""
import argparse
import json
import select
import socket
import struct
import sys
import time

DEFAULT_PORT = 8766
STATE_FILE = "/dev/shm/ai-arcade-state.bin"
STALL_SECONDS = 10.0  # drop a client only if it accepts no data at all for this long


def message(kind, payload):
    return kind + struct.pack(">I", len(payload)) + payload


class Client(object):
    """One connected PC. Holds at most one unsent snapshot so a slow reader sees the newest data."""

    def __init__(self, conn, hello):
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        conn.setblocking(False)
        self.conn = conn
        self.out = bytearray(hello)
        self.protect = len(hello)  # unsent hello bytes must never be replaced by a newer snapshot
        self.sent_any = False  # whether part of self.out has already gone onto the wire
        self.last_progress = time.time()

    def offer(self, data):
        """Queue a snapshot unless a message is partly sent. An unsent older one is replaced."""
        if not self.sent_any:
            self.out = self.out[:self.protect] + bytearray(data)

    def pump(self):
        """Send what the socket will take now. Returns False if the client is gone or stalled."""
        if not self.out:
            return True
        try:
            n = self.conn.send(self.out)
        except (BlockingIOError, InterruptedError):
            return time.time() - self.last_progress < STALL_SECONDS
        except OSError:
            return False
        if n:
            self.last_progress = time.time()
            self.sent_any = True
            del self.out[:n]
            self.protect = max(0, self.protect - n)
            if not self.out:
                self.sent_any = False
        return True


class StateServer(object):
    def __init__(self, state_file, regions, port=DEFAULT_PORT, host="0.0.0.0", poll=0.004, hello=None, encode=None):
        """hello: the JSON sent on connect (default {"regions": regions}). encode: applied to each new snapshot before
        it is sent (default: none, the file's bytes as they are); pi/frame_server.py compresses video frames with it."""
        self.state_file = state_file
        self.hello = message(b"H", json.dumps({"regions": regions} if hello is None else hello).encode())
        self.encode = encode or (lambda raw: raw)
        self.poll = poll
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind((host, port))
        self.listener.listen(4)
        self.port = self.listener.getsockname()[1]
        self.clients = []
        self.last_frame = None
        self.latest = None  # newest snapshot message, so a new client gets data immediately

    def _accept(self):
        ready, _, _ = select.select([self.listener], [], [], 0)
        if not ready:
            return
        conn, _ = self.listener.accept()
        client = Client(conn, self.hello)
        if self.latest:
            client.out += self.latest
        self.clients.append(client)

    def _read_snapshot(self):
        try:
            with open(self.state_file, "rb") as f:
                raw = f.read()
        except OSError:
            return None
        return raw if len(raw) > 4 else None

    def _drop_dead(self):
        for client in list(self.clients):
            if not client.pump():
                self.clients.remove(client)
                client.conn.close()

    def step(self):
        """One poll: accept clients, publish the snapshot if it is new, flush queues.
        Returns True if a new snapshot was published."""
        self._accept()
        raw = self._read_snapshot()
        published = False
        if raw is not None:
            frame = struct.unpack("<I", raw[:4])[0]
            if frame != self.last_frame:
                self.last_frame = frame
                self.latest = message(b"S", self.encode(raw))
                for client in self.clients:
                    client.offer(self.latest)
                published = True
        self._drop_dead()
        return published

    def serve_forever(self, stop=lambda: False):
        while not stop():
            if not self.step():
                time.sleep(self.poll)

    def close(self):
        for client in self.clients:
            client.conn.close()
        self.listener.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--state-file", default=STATE_FILE)
    parser.add_argument("--regions", required=True,
                        help='JSON list of [start, end, every] matching regions.lua, e.g. "[[19712,19775,1]]"')
    args = parser.parse_args()
    server = StateServer(args.state_file, json.loads(args.regions), port=args.port)
    sys.stderr.write("state server listening on %d\n" % server.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()


if __name__ == "__main__":
    main()
