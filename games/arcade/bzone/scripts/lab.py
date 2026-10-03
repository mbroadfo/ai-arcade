"""Battlezone's real-time lab: a fixed-rate loop running a diagnostic policy, logging every tick.

    observe -> decode -> facts -> policy(state, facts) -> hold controls -> wait for the next tick

Each tick's log line says when it ran and how late, which snapshot it saw and how old that was when the command went
out, the decoded state, what the policy chose and why, what was actually pressed and released, how long the decision
and the broker took, and what changed since the last tick (a life, a hit). explain.py reads it back.

Start the Pi side first (MAME, the state stream; full speed for timing work):
    python tools/start_pi_game.py --game arcade/bzone --speed 1.0
    python games/arcade/bzone/scripts/lab.py --policy pattern --hz 10 --seconds 60
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
from gamelib import DEFAULT_PI_HOST, ROOT, load_game  # noqa: E402  (puts the repository root on sys.path)

from arcadekit.clock import TickClock  # noqa: E402
from broker_link import BrokerLink  # noqa: E402
from games.arcade.bzone.controls import broker_actions, describe  # noqa: E402
from games.arcade.bzone.facts import derive  # noqa: E402
from games.arcade.bzone.policies import POLICIES  # noqa: E402
from state_client import StateStream  # noqa: E402


def digest(state):
    """The decoded state, flat, for the log."""
    return {"playing": state.playing, "lives": state.lives, "hits": state.hits, "hits_taken": state.hits_taken,
            "dying": state.dying, "angle": state.tank.angle, "x": state.tank.x, "y": state.tank.y,
            "enemy": [state.enemy.x, state.enemy.y, state.enemy.angle], "enemy_distance": state.enemy_distance,
            "enemy_in_range": state.enemy_in_range, "missile": state.missile, "saucer": state.saucer}


def changes(before, after):
    """Outcome changes between two observations."""
    out = []
    if before is None:
        return out
    if after.lives < before.lives:
        out.append("life lost")
    if after.hits != before.hits:
        out.append(f"hits {before.hits}->{after.hits}")
    if after.hits_taken != before.hits_taken:
        out.append(f"hit taken ({after.hits_taken})")
    if after.dying and not before.dying:
        out.append("windshield cracked")
    if after.playing != before.playing:
        out.append("game started" if after.playing else "game ended")
    return out


def start_game(stream, broker, coins):
    (_, state, _), _ = stream.latest_timed()
    if state.playing:
        return
    for _ in range(coins):
        broker.tap("COIN")
        time.sleep(0.6)
    # After a game with a high score the game asks for three initials, each entered with fire, and ignores START until
    # they are in: press fire, then start, until a game begins.
    deadline = time.time() + 45
    while time.time() < deadline:
        broker.tap("START")
        time.sleep(1.0)
        (_, state, _), _ = stream.latest_timed()
        if state.playing:
            return
        broker.tap("BUTTON_1")
        time.sleep(0.5)
    raise RuntimeError("the game did not start (coins, start, initials)")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", choices=sorted(POLICIES), default="pattern")
    parser.add_argument("--hz", type=float, default=10.0, help="decisions a second")
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--coins", type=int, default=None, help="coins one play costs (default: the game's "
                        "COINS_PER_PLAY, which assumes its SETTINGS were applied by start_pi_game.py)")
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--out", default=str(ROOT / "runs"))
    parser.add_argument("--tag", default="")
    args = parser.parse_args(argv)

    game = load_game("arcade/bzone")
    policy = POLICIES[args.policy]
    label = "-".join(p for p in (time.strftime("%Y%m%d-%H%M%S"), "arcade_bzone-lab", args.policy,
                                 f"{args.hz:g}hz", args.tag) if p)
    path = Path(args.out) / f"{label}.jsonl"
    path.parent.mkdir(exist_ok=True)
    log = open(path, "w", buffering=1)
    stream = StateStream(args.host, game=game)
    stream.start_latest()
    broker = BrokerLink(args.host)
    coins = game.COINS_PER_PLAY if args.coins is None else args.coins
    log.write(json.dumps({"event": "run", "label": label, "policy": args.policy, "hz": args.hz,
                          "seconds": args.seconds, "settings": game.SETTINGS, "coins": coins,
                          "t": time.time()}) + "\n")
    start_game(stream, broker, coins)

    clock = TickClock(args.hz)
    began, previous, last_frame, held = time.monotonic(), None, None, frozenset()
    try:
        while time.monotonic() - began < args.seconds:
            tick = clock.wait()
            (frame, state, _), arrived = stream.latest_timed(timeout=1.0)
            t = tick.began - began
            t0 = time.perf_counter()
            facts = derive(state)
            names, why = policy(state, facts, t, held)
            decide_ms = (time.perf_counter() - t0) * 1000  # facts and policy together
            held = frozenset(names)
            before = broker.holding
            t1 = time.perf_counter()
            broker.hold(broker_actions(names))
            broker_ms = (time.perf_counter() - t1) * 1000
            age_ms = (time.time() - arrived) * 1000  # how old the observation was when the command had gone out
            record = {"event": "tick", "tick": tick.index, "t": round(t, 3), "interval_ms": round(tick.interval * 1000, 1),
                      "late_ms": round(tick.late_ms, 1), "frame": frame, "new_frame": frame != last_frame,
                      "obs_age_ms": round(age_ms, 1), "state": digest(state), "facts": vars(facts),
                      "game_turn": state.game_turn, "action": sorted(names),
                      "action_words": describe(names), "why": why,
                      "pressed": sorted(map(list, broker.holding - before)),
                      "released": sorted(map(list, before - broker.holding)),
                      "decide_ms": round(decide_ms, 3), "broker_ms": round(broker_ms, 1),
                      "changes": changes(previous, state)}
            clock.done(tick)
            record["work_ms"] = round(tick.work_ms, 1)
            log.write(json.dumps(record) + "\n")
            previous, last_frame = state, frame
            if previous.playing is False and t > 5:
                break  # the game ended
    except KeyboardInterrupt:
        pass
    finally:
        broker.release_all()
        summary = {"event": "summary", "clock": clock.summary(), "final": digest(previous) if previous else None,
                   "t": time.time()}
        log.write(json.dumps(summary) + "\n")
        log.close()
        stream.close()
    print(json.dumps(summary["clock"], indent=1))
    print(f"log: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
