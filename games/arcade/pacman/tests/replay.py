"""Replay a recorded stream through the Pac-Man player and compare its log with a stored one.

The safety net for refactoring (docs/REFACTOR_PLAN.md, phase 0): the recorded states are fed to Player.tick() one frame at
a time, the rule decider answers every question on the next tick, and time is the recorded frame number at 60 frames a
second, so the decisions log is identical on every run. Any change to it is either a bug or a deliberate change in play,
which then updates the stored log in the same commit:

    python -m games.arcade.pacman.tests.replay --update        # after a deliberate change
    python -m games.arcade.pacman.tests.replay --make-fixture runs/v3.pkl 366 3600   # once, from a recording

The fixture holds only the agent regions (state.AGENT_REGIONS) of each frame, gzipped. The player steers nothing real:
the recording is open-loop, so this checks decisions for given states, not how well they play.
"""
import argparse
import gzip
import io
import json
import pickle
import struct
import time
from pathlib import Path

from games.arcade.pacman import goals, player
from games.arcade.pacman import deciders as _deciders
RuleDecider = _deciders.RuleDecider
from games.arcade.pacman.state import AGENT_REGIONS, BASE, decode

FIXTURES = Path(__file__).parent / "fixtures"
RECORDING = FIXTURES / "pacman_replay_v3.bin.gz"
FPS = 60.0
# the switch sets replayed: defaults, and everything that steers turned on
CONFIGS = {"default": {}, "all_on": {"park": True, "refuge": True, "danger_query": True, "revise": True},
           "model_alone": {"late": "keep", "reflex": False}}


def golden_path(name):
    return FIXTURES / f"pacman_replay_v3.{name}.jsonl.gz"


def make_fixture(pkl, start, end):
    frames = pickle.load(open(pkl, "rb"))[start:end]
    out = io.BytesIO()
    for frame, image in frames:
        out.write(struct.pack("<I", frame))
        for a, b, _ in AGENT_REGIONS:
            out.write(image[a - BASE: b - BASE + 1])
    RECORDING.write_bytes(gzip.compress(out.getvalue(), 9, mtime=0))
    print(f"{len(frames)} frames -> {RECORDING} ({RECORDING.stat().st_size // 1024} KB)")


def load_frames():
    raw = gzip.decompress(RECORDING.read_bytes())
    size = 4 + sum(b - a + 1 for a, b, _ in AGENT_REGIONS)
    frames = []
    for i in range(0, len(raw), size):
        chunk, image, pos = raw[i:i + size], bytearray(0x1000), 4
        for a, b, _ in AGENT_REGIONS:
            image[a - BASE: b - BASE + 1] = chunk[pos: pos + b - a + 1]
            pos += b - a + 1
        frames.append((struct.unpack("<I", chunk[:4])[0], bytes(image)))
    return frames


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class ReplayStream:
    def __init__(self, frames, clock):
        self.frames, self.clock, self.i = frames, clock, 0

    def latest(self, newer_than=-1, timeout=2.0):
        frame, image = self.frames[self.i]
        self.i += 1
        self.clock.now = frame / FPS
        return frame, decode(image), image


class ReplayWorker:
    """Answers with the rule decider, stamped with replay time. latency=0: on the next take_all(). latency > 0: like
    our model server, one question at a time, each taking `latency` seconds of replay time (urgent ones first)."""

    def __init__(self, clock, latency=0.0):
        self.clock, self.latency, self.rule, self.done, self.keys = clock, latency, RuleDecider(), [], set()
        self.free_at = 0.0  # when the server finishes what it already has

    def submit(self, key, goal, facts, urgent=False):
        if key in self.keys:
            return False
        self.keys.add(key)
        ready = max(self.clock(), self.free_at) + self.latency
        self.free_at = ready
        self.done.append((ready, (key, goal, facts, self.rule.decide(facts, goal))))
        return True

    def pending(self, key):
        return key in self.keys

    def take_all(self):
        now = self.clock()  # latency 0: everything asked is ready by the next take_all, stamped when it was asked
        out = [item + (ready,) for ready, item in self.done if ready <= now]
        self.done = [(ready, item) for ready, item in self.done if ready > now]
        for item in out:
            self.keys.discard(item[0])
        return out

    def clear_queued(self):
        pass


class Broker:
    def __init__(self):
        self.held = None

    def steer(self, direction):
        self.held = direction

    def tap(self, *a, **k):
        pass


def replay(config, latency=0.0, switches=None):
    """The decisions log of the recorded minute under CONFIGS[config] (or `switches`), answers taking `latency` s."""
    frames, clock, log = load_frames(), Clock(), io.StringIO()
    p = player.Player(ReplayStream(frames, clock), Broker(), ReplayWorker(clock, latency),
                      goals.GoalManager("auto", clock=clock), log, clock=clock,
                      **(CONFIGS[config] if switches is None else switches))
    for _ in frames:
        p.tick()
    return log.getvalue()


def stored(config):
    return gzip.decompress(golden_path(config).read_bytes()).decode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="store the current logs as the expected ones")
    parser.add_argument("--make-fixture", nargs=3, metavar=("PKL", "START", "END"))
    args = parser.parse_args()
    if args.make_fixture:
        pkl, start, end = args.make_fixture
        make_fixture(pkl, int(start), int(end))
    for config in CONFIGS:
        t0 = time.time()
        text = replay(config)
        events = [json.loads(line)["event"] for line in text.splitlines()]
        summary = {e: events.count(e) for e in sorted(set(events))}
        print(f"{config}: {len(events)} events in {time.time() - t0:.1f} s {summary}")
        if args.update:
            golden_path(config).write_bytes(gzip.compress(text.encode(), 9, mtime=0))


if __name__ == "__main__":
    main()
