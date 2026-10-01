#!/usr/bin/env python3
"""Pac-Man agent that runs on the Pi: reads game state from MAME, drives the controller broker.

Reads /dev/shm/ai-arcade-state.bin (written by tools/mame_state_export.lua: 4-byte frame counter,
then RAM 0x4000-0x4FFF), plans a route with BFS over the maze in video RAM, and sends joystick
commands to the controller broker on localhost. Standard library only (Pi runs Python 3.7).
"""
import argparse
import json
import os
import signal
import socket
import struct
import sys
import time
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pacman_state import AGENT_REGIONS, decode, expand  # noqa: E402  (copied next to this script by run_pacman_agent.py)

STATE_FILE = "/dev/shm/ai-arcade-state.bin"
DOT, ENERGIZER, BLANK = 0x10, 0x14, 0x40
# Direction name -> (delta_l, delta_h); vector table $32FF: right h-1, down l+1, left h+1, up l-1.
MOVES = {"RIGHT": (0, -1), "DOWN": (1, 0), "LEFT": (0, 1), "UP": (-1, 0)}
DANGER_RADIUS = 2


def video_addr(l, h):
    return (0x4040 + (h - 0x20) * 32 + (l - 0x20)) & 0xFFFF


class Broker:
    def __init__(self, port=8765):
        self.port = port
        self.held = None

    def _send(self, payload):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=3)
        try:
            sock.sendall((json.dumps(payload) + "\n").encode())
            sock.recv(4096)
        finally:
            sock.close()

    def tap(self, action, ms=200):
        self._send({"op": "tap", "player": 1, "action": action, "ms": ms})

    def steer(self, direction):
        """Hold exactly one direction (Pac-Man's gate is 4-way): release the old one first."""
        if direction == self.held:
            return
        if self.held:
            self._send({"op": "release", "player": 1, "action": self.held})
        if direction:
            self._send({"op": "press", "player": 1, "action": direction})
        self.held = direction

    def release_all(self):
        self._send({"op": "release_all"})
        self.held = None


def read_state():
    try:
        with open(STATE_FILE, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    expected = 4 + sum(end - start + 1 for start, end, _ in AGENT_REGIONS)
    if len(raw) < expected:
        return None
    frame = struct.unpack("<I", raw[:4])[0]
    return frame, expand(raw[4:expected])


def tile_at(buf, l, h):
    return buf[video_addr(l, h) - 0x4000]


def passable(buf, l, h):
    return 0x20 <= l <= 0x3F and 0x1E <= h <= 0x3D and tile_at(buf, l, h) in (DOT, ENERGIZER, BLANK)


def bfs(buf, start, blocked):
    """Distances from start over passable, unblocked tiles."""
    dist = {start: 0}
    queue = deque([start])
    while queue:
        l, h = queue.popleft()
        for dl, dh in MOVES.values():
            nxt = (l + dl, h + dh)
            if nxt not in dist and nxt not in blocked and passable(buf, *nxt):
                dist[nxt] = dist[(l, h)] + 1
                queue.append(nxt)
    return dist


def dangerous_ghosts(state):
    return [g.tile for name, g in state.ghosts.items()
            if not state.frightened[name] and not state.eyes[name]]


def choose_direction(buf, state):
    me = state.pacman.tile
    ghosts = dangerous_ghosts(state)
    blocked = set()
    for gl, gh in ghosts:
        for dl in range(-DANGER_RADIUS, DANGER_RADIUS + 1):
            for dh in range(-DANGER_RADIUS, DANGER_RADIUS + 1):
                if abs(dl) + abs(dh) <= DANGER_RADIUS:
                    blocked.add((gl + dl, gh + dh))
    blocked.discard(me)

    dist = bfs(buf, me, blocked)
    targets = [t for t in dist if t != me and tile_at(buf, *t) in (DOT, ENERGIZER)]
    if targets:
        goal = min(targets, key=lambda t: dist[t])
        # Walk back from the goal to the first step.
        step = goal
        while dist[step] > 1:
            step = min((n for n in ((step[0] + dl, step[1] + dh) for dl, dh in MOVES.values())
                        if n in dist and dist[n] == dist[step] - 1), key=lambda n: n)
        for name, (dl, dh) in MOVES.items():
            if (me[0] + dl, me[1] + dh) == step:
                return name, "dot"

    # No safe route to a dot: flee to the neighbour farthest from the nearest dangerous ghost.
    best, best_score = None, -1
    ghost_dist = [bfs(buf, g, set()) for g in ghosts]
    for name, (dl, dh) in MOVES.items():
        nxt = (me[0] + dl, me[1] + dh)
        if passable(buf, *nxt):
            score = min((d.get(nxt, 99) for d in ghost_dist), default=99)
            if score > best_score:
                best, best_score = name, score
    return best, "flee"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--hz", type=float, default=20)
    parser.add_argument("--log", default="/tmp/ai-arcade-agent.log")
    parser.add_argument("--games", type=int, default=1, help="stop after this many finished games")
    parser.add_argument("--results", default="/tmp/ai-arcade-games.jsonl")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # let `finally` release the controls
    log = open(args.log, "w", buffering=1)
    broker = Broker()
    deadline = time.time() + args.seconds
    last_report, last_start_attempt, was_playing = 0, 0, False
    finished, game_started, last_state = 0, 0, None
    open(args.results, "w").close()

    try:
        while time.time() < deadline:
            time.sleep(1.0 / args.hz)
            snap = read_state()
            if snap is None:
                continue
            _, buf = snap
            state = decode(buf)
            sub_state = buf[0x4E04 - 0x4000]

            if state.mode in ("attract", "coin"):
                if was_playing:
                    finished += 1
                    result = {"game": finished, "score": last_state.score, "level": last_state.level,
                              "dots": last_state.dots_eaten, "seconds": round(time.time() - game_started)}
                    with open(args.results, "a") as results:
                        results.write(json.dumps(result) + "\n")
                    log.write("GAME %d/%d over: score=%d level=%d seconds=%d\n" % (
                        finished, args.games, result["score"], result["level"], result["seconds"]))
                    was_playing = False
                    if finished >= args.games:
                        break
                broker.steer(None)
                if time.time() - last_start_attempt > 4:
                    last_start_attempt = time.time()
                    if state.credits == 0:
                        broker.tap("COIN")
                        log.write("coin\n")
                    else:
                        broker.tap("START")
                        log.write("start\n")
                continue

            if state.mode != "playing":
                continue
            if not was_playing:
                game_started = time.time()
            was_playing = True
            last_state = state
            if sub_state != 3:  # READY screen, death animation, level transition
                broker.steer(None)
                continue

            direction, why = choose_direction(buf, state)
            broker.steer(direction)
            if time.time() - last_report > 1:
                last_report = time.time()
                log.write("score=%d lives=%d level=%d dots=%d tile=%s -> %s (%s)\n" % (
                    state.score, state.lives, state.level, state.dots_eaten,
                    state.pacman.tile, direction, why))
    finally:
        broker.release_all()
        log.write("agent exit\n")
        log.close()


if __name__ == "__main__":
    main()
