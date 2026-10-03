"""Layer 2: discover game-state RAM addresses for a MAME game by scripted experiment.

Drives the game through the controller broker (coin, start, direction holds, idle until a life
is lost) while taking whole-address-space snapshots, then ranks candidate addresses for:
credits, lives, progress counters (score-like) and horizontal/vertical player position.
No per-game knowledge is used. Usage: python tools/discover_state.py pacman [--end 0xFFFF]

A game that moves by other means than one stick names its two movement axes with --moves, each as two opposite holds
of one or more controls held together (player.ACTION, joined by +):

    python tools/discover_state.py bzone --end 0x03FF \
        --moves "turn:L=1.DOWN+2.UP/R=1.UP+2.DOWN;drive:F=1.UP+2.UP/B=1.DOWN+2.DOWN"
"""
import argparse
import json
import pickle
import struct
import sys
import time
from pathlib import Path

import paramiko

from controller_client import send
from probe_mame_input import MAME_LOG, run
from gamelib import DEFAULT_PI_HOST, pi_rompath

REMOTE_DIR = "/home/pi/ai-arcade"
REQ = "/dev/shm/ai-arcade-snap.req"
OUT = "/dev/shm/ai-arcade-snap.bin"
PROFILES = Path(__file__).resolve().parent.parent / "games"


class Session:
    def __init__(self, args):
        self.args = args
        self.ssh = paramiko.SSHClient()
        self.ssh.load_system_host_keys()
        self.ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
        self.ssh.connect(hostname=args.host, username=args.user, timeout=10)
        self.seq = 0

    def start_mame(self):
        here = Path(__file__).parent
        run(self.ssh, f"mkdir -p {REMOTE_DIR}")
        sftp = self.ssh.open_sftp()
        sftp.put(str(here / "mame_snapshot_service.lua"), f"{REMOTE_DIR}/mame_snapshot_service.lua")
        with sftp.file(f"{REMOTE_DIR}/regions.lua", "w") as f:
            f.write(f"return {{{{0x{self.args.start:X}, 0x{self.args.end:X}}}}}\n")
        sftp.close()
        run(self.ssh, f"pkill -9 -x mame || true; rm -f {REQ} {OUT}")
        run(self.ssh, f"nohup mame {self.args.romset} -rompath {pi_rompath(self.args.system)} "
                      "-sound none -video accel -nowindow -skip_gameinfo -joystick "
                      "-joystickprovider sdl -ctrlrpath /home/pi/.mame/ctrlr -ctrlr aiarcade "
                      f"-autoboot_script {REMOTE_DIR}/mame_snapshot_service.lua "
                      f"> {MAME_LOG} 2>&1 < /dev/null &")
        time.sleep(15)

    def snap(self):
        """Request a snapshot and return the memory bytes (frame header stripped)."""
        self.seq += 1
        run(self.ssh, f"touch {REQ}")
        for _ in range(100):
            time.sleep(0.1)
            _, out, _ = self.ssh.exec_command(f"cat {OUT} 2>/dev/null", timeout=15)
            raw = out.read()
            if len(raw) > 4 and struct.unpack("<I", raw[:4])[0] >= self.seq:
                return raw[4:]
        raise RuntimeError("snapshot service did not answer; see MAME log on the Pi")

    def tap(self, control, ms=200):
        send(self.args.host, self.args.broker_port, {"op": "tap", "player": 1, "action": control, "ms": ms})

    def hold(self, controls, seconds):
        """controls: [(player, action), ...] held together."""
        for player, action in controls:
            send(self.args.host, self.args.broker_port, {"op": "press", "player": player, "action": action})
        time.sleep(seconds)
        for player, action in controls:
            send(self.args.host, self.args.broker_port, {"op": "release", "player": player, "action": action})

    def close(self):
        try:
            send(self.args.host, self.args.broker_port, {"op": "release_all"})
        except Exception:
            pass
        self.ssh.close()


def sdelta(a, b):
    """Signed byte difference b - a."""
    d = (b - a) & 0xFF
    return d - 256 if d > 127 else d


def sign(n):
    return (n > 0) - (n < 0)


def find_credits(a0, a1, a2, b1, b2, c1):
    """Stable in attract, increases on coin (then stable), drops by exactly 1 once START is pressed."""
    return [i for i in range(len(a0))
            if a0[i] == a1[i] == a2[i] and sdelta(a2[i], b1[i]) > 0 and b1[i] == b2[i]
            and sdelta(b2[i], c1[i]) == -1]


# Two movement axes, each (name, (label, controls) one way, (label, controls) the other way): one stick by default.
STICK_MOVES = (("horizontal", ("L", [(1, "LEFT")]), ("R", [(1, "RIGHT")])),
               ("vertical", ("U", [(1, "UP")]), ("D", [(1, "DOWN")])))
REPEATS = 4  # each hold is done this many times, the four kinds interleaved


def parse_moves(text):
    """ "turn:L=1.DOWN+2.UP/R=1.UP+2.DOWN;drive:F=1.UP+2.UP/B=1.DOWN+2.DOWN" -> moves like STICK_MOVES."""
    moves = []
    for part in text.split(";"):
        name, _, holds = part.partition(":")
        sides = []
        for side in holds.split("/"):
            label, _, combo = side.partition("=")
            sides.append((label, [(int(p), a) for p, _, a in (c.partition(".") for c in combo.split("+"))]))
        if len(sides) != 2:
            raise ValueError(f"axis {name!r} needs two opposite holds, got {holds!r}")
        moves.append((name, *sides))
    if len(moves) != 2 or len({label for _, *sides in moves for label, _ in sides}) != 4:
        raise ValueError("--moves needs two axes with four different hold labels")
    return tuple(moves)


def find_position(holds, moves=STICK_MOVES):
    """holds: label -> (before, after) for each hold label and repeat (L1..L4, R1..R4, ... by default).

    Walls block some holds (delta 0), so score by sign agreement instead of demanding all four:
    axis score = (sum sign(delta) over the "positive" holds - same over the opposite holds) / holds.
    A true axis byte scores near +-1 on its own axis and near 0 on the other (purity).
    Returns the candidates for the first axis and for the second.
    """
    def axis(d, plus, minus):
        return (sum(sign(d[k]) for k in plus) - sum(sign(d[k]) for k in minus)) / (len(plus) + len(minus))

    keys = [([f"{plus[0]}{n}" for n in range(1, REPEATS + 1)], [f"{minus[0]}{n}" for n in range(1, REPEATS + 1)])
            for _, plus, minus in moves]
    first, second = [], []
    for i in range(len(next(iter(holds.values()))[0])):
        d = {k: sdelta(v[0][i], v[1][i]) for k, v in holds.items()}
        x, y = axis(d, *keys[0]), axis(d, *keys[1])
        if abs(x) >= 0.5 and abs(y) <= 0.25:
            first.append((i, x))
        elif abs(y) >= 0.5 and abs(x) <= 0.25:
            second.append((i, y))
    return first, second


def is_bcd(byte):
    return (byte >> 4) <= 9 and (byte & 0xF) <= 9


def bcd_value(byte):
    return (byte >> 4) * 10 + (byte & 0xF)


def find_counters(play, idle_start):
    """Score-like bytes: constant while idle, change in 3+ play intervals, mostly upward.

    A byte counts as a counter if its changes are mostly increases read as a binary counter,
    or (when every value is valid BCD) mostly increases mod 100, so a tens-digit carry such as
    0x60 -> 0x20 still reads as "+60". Position bytes move both ways, so they fail both tests.
    """
    hits = []
    for i in range(len(play[0])):
        if len({s[i] for s in idle_start}) != 1:
            continue
        pairs = [(a[i], b[i]) for a, b in zip(play, play[1:]) if a[i] != b[i]]
        if len(pairs) < 3:
            continue
        binary_up = sum(1 for a, b in pairs if 0 < sdelta(a, b))
        bcd_up = 0
        if all(is_bcd(a) and is_bcd(b) for a, b in pairs):
            bcd_up = sum(1 for a, b in pairs if 0 < (bcd_value(b) - bcd_value(a)) % 100 < 90)
        if max(binary_up, bcd_up) >= 0.8 * len(pairs):
            hits.append((i, len(pairs)))
    return hits


def find_lives(series):
    """Bytes (starting 1..9) that step down by exactly 1 (mod 256) at least twice before first rising.

    The series is cut at the first increase: after game over the attract demo reuses the byte.
    """
    hits = []
    for i in range(len(series[0])):
        v = [s[i] for s in series]
        if not 1 <= v[0] <= 9:
            continue
        prefix = [v[0]]
        for x in v[1:]:
            if x != prefix[-1] and sdelta(prefix[-1], x) != -1:
                break
            prefix.append(x)
        steps = sum(1 for a, b in zip(prefix, prefix[1:]) if a != b)
        if steps >= 2:
            hits.append((i, prefix[0], prefix[-1], steps))
    return hits


def collapse_mirrors(indices, snapshots, radius=16):
    """Hardware often mirrors RAM (4Cxx == 6Cxx == ...).

    Two addresses are mirrors only if the bytes around them are identical in every snapshot;
    comparing a single byte would merge unrelated variables that happen to move together.
    """
    kept, seen = [], set()
    for i in sorted(indices):
        lo = max(0, i - radius)
        neighborhood = tuple(bytes(s[lo:i + radius + 1]) for s in snapshots) + (i - lo,)
        if neighborhood not in seen:
            seen.add(neighborhood)
            kept.append(i)
    return kept


def run_experiment(args):
    s = Session(args)
    try:
        s.start_mame()

        print("attract idle...")
        a0 = s.snap(); time.sleep(1); a1 = s.snap(); time.sleep(1); a2 = s.snap()
        print("coin...")
        for _ in range(args.coins):  # as many as one play costs (Battlezone: 2 coins, 1 play)
            s.tap("COIN"); time.sleep(1)
        time.sleep(1); b1 = s.snap(); time.sleep(1); b2 = s.snap()
        print("start...")
        s.tap("START"); time.sleep(3); c1 = s.snap()
        time.sleep(7)

        print("movement holds...")
        holds, after_each = {}, []
        kinds = [side for _, plus, minus in args.moves for side in (plus, minus)]
        sequence = [(f"{k}{n}", c) for n in range(1, REPEATS + 1) for k, c in kinds]
        for label, controls in sequence:
            before = s.snap()
            s.hold(controls, 1.0)
            after = s.snap()
            holds[label] = (before, after)
            after_each.append(after)

        print(f"idle {args.idle_seconds}s until lives are lost...")
        life_series = [after_each[-1]]
        t_end = time.time() + args.idle_seconds
        while time.time() < t_end:
            time.sleep(2)
            life_series.append(s.snap())
    finally:
        s.close()
    return {"attract_coin_start": (a0, a1, a2, b1, b2, c1), "holds": holds,
            "after_each": after_each, "life_series": life_series}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("romset")
    parser.add_argument("--system", default="arcade", help="EmulationStation system folder (arcade, nes, ...)")
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--user", default="pi")
    parser.add_argument("--broker-port", type=int, default=8765)
    parser.add_argument("--start", type=lambda s: int(s, 0), default=0x0000)
    parser.add_argument("--end", type=lambda s: int(s, 0), default=0xFFFF)
    parser.add_argument("--idle-seconds", type=int, default=80)
    parser.add_argument("--coins", type=int, default=1, help="coins one play costs (the game's coinage setting)")
    parser.add_argument("--moves", type=parse_moves, default=STICK_MOVES,
                        help="two movement axes as opposite holds (see the module help); default one stick")
    parser.add_argument("--save", help="pickle the raw snapshots here for offline analysis")
    parser.add_argument("--load", help="analyze a previously saved pickle instead of running the game")
    args = parser.parse_args()
    base = args.start

    if args.load:
        data = pickle.loads(Path(args.load).read_bytes())
    else:
        data = run_experiment(args)
        if args.save:
            Path(args.save).write_bytes(pickle.dumps(data))
    a0, a1, a2, b1, b2, c1 = data["attract_coin_start"]
    holds, after_each, life_series = data["holds"], data["after_each"], data["life_series"]

    all_snaps = [a0, a1, a2, b1, b2, c1] + [x for pair in holds.values() for x in pair]         + life_series
    play = [holds[f"{args.moves[0][1][0]}1"][0]] + after_each

    def uniq(hits):
        keep = set(collapse_mirrors([h if isinstance(h, int) else h[0] for h in hits], all_snaps))
        return [h for h in hits if (h if isinstance(h, int) else h[0]) in keep]

    credits = uniq(find_credits(a0, a1, a2, b1, b2, c1))
    horiz, vert = find_position(holds, args.moves)
    horiz = sorted(uniq(horiz), key=lambda h: -abs(h[1]))[:12]
    vert = sorted(uniq(vert), key=lambda h: -abs(h[1]))[:12]
    counters = uniq(find_counters(play, life_series[:4]))
    lives = uniq(find_lives(life_series))

    anchors = {}
    game_dir = PROFILES / args.system / args.romset
    profile = game_dir / "profile.json"
    if profile.exists():
        for e in json.loads(profile.read_text())["named_ram"]:
            anchors[e["address"]] = e["description"]

    def label(i):
        addr = base + i
        return f"0x{addr:04X}" + (f" [cheat.dat: {anchors[addr]}]" if addr in anchors else "")

    report = {
        "credits": [label(i) for i in credits],
        "lives": [dict(addr=label(i), start=a, end=b, drops=n) for i, a, b, n in lives],
        f"position_{args.moves[0][0]}": [dict(addr=label(i), axis_score=x) for i, x in horiz],
        f"position_{args.moves[1][0]}": [dict(addr=label(i), axis_score=y) for i, y in vert],
        "progress_counters": [dict(addr=label(i), changed_intervals=c) for i, c in counters],
    }
    game_dir.mkdir(parents=True, exist_ok=True)
    out = game_dir / "discovered.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
