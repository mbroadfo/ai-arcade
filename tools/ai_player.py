"""PC-side Pac-Man player: the Pi streams state, a decider chooses directions, the broker steers.

Tiers (after Sean Goedecke's "tiered goals"): a slow strategy loop picks a goal from a fixed set;
a fast decider (rule, mock model, or a System One model) picks a direction at each junction given
that goal. Corridors and forced corners are followed by code, so the model is only asked real
questions. Because answers take 70-500 ms, a junction is queried a few tiles ahead and the
answer is applied when Pac-Man arrives; if it is late, a rule decides instead (and it is counted).

    python tools/ai_player.py --decider rule --games 3
    python tools/ai_player.py --decider mock --latency 90,500 --games 5
    python tools/ai_player.py --decider ollama --model nimble --games 5
"""
import argparse
import json
import socket
import statistics
import sys
import threading
import time
from pathlib import Path

from deciders import RuleDecider, SystemOneDecider
from pacman_features import junction_facts, threat_distance
from pacman_maze import LOWER_TO_UPPER, Maze
from state_client import StateStream
from systemone import MockSystemOne, OllamaSystemOne

LOOKAHEAD_STEPS = 8  # default: query a junction this many tiles ahead (~0.8 s of travel)
ROOT = Path(__file__).resolve().parent.parent


class BrokerLink:
    """Persistent connection to the controller broker (newline-delimited JSON)."""

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
        """Hold exactly one direction (Pac-Man's gate is 4-way): release the old one first."""
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


class RuleStrategy:
    """Slow-loop goal chooser. Replace with an LLM (e.g. Qwen) that returns one of GOALS."""

    def choose(self, state, image):
        if any(state.frightened[name] and not state.eyes[name] for name in state.ghosts):
            return "hunt_ghosts"
        threat = threat_distance(state, image)
        if threat is not None and threat <= 8:
            return "avoid_ghosts"
        return "clear_dots"


class DecisionWorker:
    """Runs one decider call at a time off the control loop, so slow answers never block steering."""

    def __init__(self, decider):
        self.decider = decider
        self.busy = False
        self.result = None  # (tile, goal, facts, decision, finished_at)
        self.lock = threading.Lock()

    def submit(self, tile, goal, facts):
        with self.lock:
            if self.busy:
                return False
            self.busy = True

        def run():
            decision = self.decider.decide(facts, goal)
            with self.lock:
                self.result = (tile, goal, facts, decision, time.time())
                self.busy = False

        threading.Thread(target=run, daemon=True).start()
        return True

    def take(self):
        with self.lock:
            result, self.result = self.result, None
            return result


class Player:
    def __init__(self, stream, broker, decider, strategy, decisions_log, strategy_interval=2.0,
                 lookahead=LOOKAHEAD_STEPS):
        self.lookahead = lookahead
        self.stream, self.broker, self.strategy = stream, broker, strategy
        self.worker = DecisionWorker(decider)
        self.rule = RuleDecider()
        self.decisions_log = decisions_log
        self.strategy_interval = strategy_interval
        self.goal, self.goal_at = "clear_dots", 0.0
        self.plan = {}  # junction tile -> (Decision, goal, finished_at)
        self.applied = set()  # junctions already counted, so stats are per junction, not per tick
        self.last_frame, self.last_start_attempt = -1, 0.0
        self.was_playing, self.game_started, self.last_state = False, 0.0, None
        self.finished = 0
        self.stats = {"on_time": 0, "late_rule": 0, "queries": 0}
        self.latencies, self.sources = [], {}

    def log(self, **record):
        record["t"] = round(time.time(), 3)
        self.decisions_log.write(json.dumps(record) + "\n")

    def _collect(self):
        got = self.worker.take()
        if not got:
            return
        tile, goal, facts, decision, finished_at = got
        self.plan[tile] = (decision, goal, finished_at)
        self.latencies.append(decision.latency_ms)
        self.sources[decision.source] = self.sources.get(decision.source, 0) + 1
        self.log(event="decision", tile=list(tile), goal=goal, direction=decision.direction,
                 source=decision.source, confidence=round(decision.confidence, 3),
                 latency_ms=round(decision.latency_ms), probabilities=decision.probabilities,
                 note=decision.note)

    def _pregame(self, state):
        """Attract/coin screens: put in a coin, press start. Returns True if it handled the frame."""
        if state.mode not in ("attract", "coin"):
            return False
        self.broker.steer(None)
        if time.time() - self.last_start_attempt > 4:
            self.last_start_attempt = time.time()
            self.broker.tap("COIN" if state.credits == 0 else "START")
        return True

    def tick(self):
        frame, state, image = self.stream.latest(newer_than=self.last_frame)
        self.last_frame = frame

        if state.mode in ("attract", "coin"):
            if self.was_playing:
                self.was_playing = False
                self.finished += 1
                last = self.last_state
                self.log(event="game_over", game=self.finished, score=last.score, level=last.level)
                return {"game": self.finished, "score": last.score, "level": last.level,
                        "dots": last.dots_eaten, "seconds": round(time.time() - self.game_started)}
            self._pregame(state)
            return None
        if state.mode != "playing":
            return None
        if not self.was_playing:
            self.game_started, self.plan = time.time(), {}
        self.was_playing, self.last_state = True, state

        if image[0x4E04 - 0x4000] != 3:  # READY screen, death animation, level transition
            self.broker.steer(None)
            self.plan = {}
            return None

        if time.time() - self.goal_at > self.strategy_interval:
            goal = self.strategy.choose(state, image)
            if goal != self.goal:
                self.log(event="goal", goal=goal)
            self.goal, self.goal_at = goal, time.time()

        self._collect()
        maze = Maze(image)
        me = state.pacman.tile
        heading = LOWER_TO_UPPER.get(state.pacman.direction)
        junction, steps, path = maze.walk_to_decision(me, heading)

        if junction is not None:
            self.plan = {t: p for t, p in self.plan.items() if t == junction}  # drop passed junctions
            self.applied &= {junction}
            if junction not in self.plan and steps <= self.lookahead:
                arriving = path[-1] if path else heading
                facts = junction_facts(state, image, tile=junction, arriving=arriving)
                if self.worker.submit(junction, self.goal, facts):
                    self.stats["queries"] += 1

        if junction is not None and steps <= 1 and junction in self.plan:
            decision = self.plan[junction][0]
            if junction not in self.applied:
                self.applied.add(junction)
                self.stats["on_time"] += 1
            self.broker.steer(decision.direction)
        elif junction is not None and steps == 0:
            # At the junction with no answer yet: a rule decides, and we count it as late.
            facts = junction_facts(state, image, tile=junction, arriving=heading)
            decision = self.rule.decide(facts, self.goal)
            self.plan[junction] = (decision, self.goal, time.time())
            self.applied.add(junction)
            self.stats["late_rule"] += 1
            self.log(event="late", tile=list(junction), direction=decision.direction)
            self.broker.steer(decision.direction)
        elif path:
            self.broker.steer(path[0])  # follow the corridor / forced corner
        return None


def build_decider(args):
    if args.decider == "rule":
        return RuleDecider()
    if args.decider == "mock":
        lo, hi = (float(x) for x in args.latency.split(","))
        return SystemOneDecider(MockSystemOne(latency_ms=(lo, hi), seed=args.seed),
                                min_confidence=args.min_confidence)
    return SystemOneDecider(OllamaSystemOne(model=args.model, host=args.ollama_host),
                            min_confidence=args.min_confidence)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--decider", choices=("rule", "mock", "ollama"), default="rule")
    parser.add_argument("--latency", default="90,500", help="mock model latency range in ms")
    parser.add_argument("--model", default="nimble")
    parser.add_argument("--ollama-host", default="http://localhost:11434")
    parser.add_argument("--min-confidence", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--lookahead", type=int, default=LOOKAHEAD_STEPS)
    parser.add_argument("--tag", default="", help="label added to the run files")
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--seconds", type=int, default=3600)
    parser.add_argument("--out", default=str(ROOT / "runs"))
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    label = f"{stamp}-{args.decider}" + (f"-{args.tag}" if args.tag else "")
    decisions_log = open(out_dir / f"{label}-decisions.jsonl", "w", buffering=1)
    results_path = out_dir / f"{label}-games.jsonl"

    stream = StateStream(args.host)
    stream.start_latest()
    broker = BrokerLink(args.host)
    player = Player(stream, broker, build_decider(args), RuleStrategy(), decisions_log,
                    lookahead=args.lookahead)

    results, deadline = [], time.time() + args.seconds
    last_good = time.time()
    print(f"playing {args.games} game(s) with decider={args.decider}; logs in {out_dir}", flush=True)
    try:
        while time.time() < deadline and player.finished < args.games:
            try:
                result = player.tick()
                last_good = time.time()
            except TimeoutError:
                if time.time() - last_good > 10:
                    print(f"WARNING: no game state for {time.time() - last_good:.0f} s "
                          f"(stream reconnects so far: {stream.reconnects})", flush=True)
                    last_good = time.time()
                continue
            if result:
                results.append(result)
                results_path.write_text("".join(json.dumps(r) + "\n" for r in results))
                print(f"GAME {len(results)}/{args.games} over: score={result['score']} "
                      f"level={result['level']} seconds={result['seconds']}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            broker.release_all()
        except OSError:
            pass
        decisions_log.close()
        stream.close()

    s = player.stats
    print(f"\ndecisions: {s['on_time']} on time, {s['late_rule']} late (rule filled in), "
          f"{s['queries']} model queries; sources {player.sources}")
    if player.latencies:
        print(f"model latency: median {statistics.median(player.latencies):.0f} ms, "
              f"max {max(player.latencies):.0f} ms")
    if broker.call_ms:
        print(f"broker calls: {broker.calls}, median {statistics.median(broker.call_ms):.1f} ms")
    if results:
        scores = [r["score"] for r in results]
        print(f"scores: mean {statistics.mean(scores):.0f}, best {max(scores)}, worst {min(scores)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
