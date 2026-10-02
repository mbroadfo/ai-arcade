"""Check the ghost-targeting rules against a recording of real gameplay (tools/record_stream.py).

Each time the game plans a ghost's next move (its `next_tile` changes) the ROM picks the exit
direction toward the ghost's target, using Pac-Man's tile at that moment. We predict that choice
from the same state and compare it with the direction the game then queued.
"""
import argparse
import collections
import pickle
import sys

import _bootstrap  # noqa: F401
from games.arcade.pacman import ghosts as _ghosts
GHOST_NAMES = _ghosts.GHOST_NAMES
LOWER = _ghosts.LOWER
choose_exit = _ghosts.choose_exit
direction_between = _ghosts.direction_between
is_scatter = _ghosts.is_scatter
targets = _ghosts.targets
from games.arcade.pacman.maze import Maze
from games.arcade.pacman.state import decode

SETTLE_FRAMES = 3  # the game queues the new choice a frame or two after next_tile changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("recording")
    parser.add_argument("--show", type=int, default=8, help="mismatches to print")
    args = parser.parse_args()
    frames = pickle.load(open(args.recording, "rb"))
    states = [decode(img) for _, img in frames]

    tally = collections.Counter()
    per = collections.defaultdict(lambda: [0, 0])
    mismatches = []
    for i in range(1, len(states) - SETTLE_FRAMES):
        prev, now, later = states[i - 1], states[i], states[i + SETTLE_FRAMES]
        if now.mode != "playing" or now.substate != 3:
            continue
        maze = None
        for k, name in enumerate(GHOST_NAMES):
            g0, g1 = prev.ghosts[name], now.ghosts[name]
            if g1.next_tile == g0.next_tile:
                continue  # the game has not just planned a new move for this ghost
            if now.frightened[name] or now.eyes[name] or later.ghosts[name].next_tile != g1.next_tile:
                continue
            if not (0x20 <= g1.next_tile[0] <= 0x3F and 0x1E <= g1.next_tile[1] <= 0x3D):
                continue
            maze = maze or Maze(frames[i][1])
            arriving = direction_between(tuple(g1.tile), tuple(g1.next_tile)) or LOWER.get(g0.queued)
            predicted = choose_exit(maze, tuple(g1.next_tile), arriving, targets(now)[name])
            actual = LOWER.get(later.ghosts[name].queued)
            mode = "scatter" if is_scatter(now) else "chase"
            ok = predicted == actual
            per[(name, mode)][0] += ok
            per[(name, mode)][1] += 1
            tally["ok" if ok else "bad"] += 1
            if not ok:
                mismatches.append((i, name, mode, tuple(g1.next_tile), arriving, predicted, actual,
                                   targets(now)[name], tuple(now.pacman.tile)))

    total = tally["ok"] + tally["bad"]
    print(f"{len(states)} frames; {total} ghost decisions checked; "
          f"{tally['ok']} match ({100 * tally['ok'] / max(total, 1):.1f}%)")
    for (name, mode), (ok, n) in sorted(per.items()):
        print(f"  {name:7s} {mode:8s} {ok:4d}/{n:<4d} {100 * ok / n:5.1f}%")
    for m in mismatches[:args.show]:
        print("  mismatch frame %d %s %s next=%s arriving=%s predicted=%s actual=%s target=%s pac=%s" % m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
