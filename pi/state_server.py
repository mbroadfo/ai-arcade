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


def message(kind, payload):
    return kind + struct.pack(">I", len(payload)) + payload


class StateServer(object):
    def __init__(self, state_file, regions, port=DEFAULT_PORT, host="0.0.0.0", poll=0.004):
        self.state_file = state_file
        self.hello = message(b"H", json.dumps({"regions": regions}).encode())
        self.poll = poll
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind((host, port))
        self.listener.listen(4)
        self.port = self.listener.getsockname()[1]
        self.clients = []
        self.last_frame = None

    def _accept(self):
        ready, _, _ = select.select([self.listener], [], [], 0)
        if not ready:
            return
        conn, _ = self.listener.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        conn.settimeout(0.05)  # a stalled client must not hold up the others
        try:
            conn.sendall(self.hello)
            self.clients.append(conn)
            self.last_frame = None  # send the current snapshot to the new client immediately
        except OSError:
            conn.close()

    def _read_snapshot(self):
        try:
            with open(self.state_file, "rb") as f:
                raw = f.read()
        except OSError:
            return None
        return raw if len(raw) > 4 else None

    def _broadcast(self, payload):
        data = message(b"S", payload)
        for conn in list(self.clients):
            try:
                conn.sendall(data)
            except OSError:
                self.clients.remove(conn)
                conn.close()

    def step(self):
        """One poll: accept clients, publish the snapshot if it is new. Returns True if published."""
        self._accept()
        raw = self._read_snapshot()
        if raw is None:
            return False
        frame = struct.unpack("<I", raw[:4])[0]
        if frame == self.last_frame:
            return False
        self.last_frame = frame
        if self.clients:
            self._broadcast(raw)
        return True

    def serve_forever(self, stop=lambda: False):
        while not stop():
            if not self.step():
                time.sleep(self.poll)

    def close(self):
        for conn in self.clients:
            conn.close()
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
