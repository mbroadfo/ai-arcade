"""Play a game with an AI: the Pi streams state, a decider chooses, the broker steers. Any game package.

    python tools/play.py --game arcade/pacman --decider rule --games 3
    python tools/play.py --game arcade/pacman --decider mock --latency 90,500 --games 5
    python tools/play.py --game arcade/pacman --decider ollama --model nimble --knowledge L2 --games 5
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from broker_link import BrokerLink
from decision_worker import DecisionWorker
from gamelib import DEFAULT_GAME, ROOT, load_game
from state_client import StateStream
from systemone import MockSystemOne, OllamaSystemOne


def build_decider(game, args):
    if args.decider == "rule":
        return game.deciders.RuleDecider()
    if args.decider == "mock":
        lo, hi = (float(x) for x in args.latency.split(","))
        client = MockSystemOne(game.score_option, latency_ms=(lo, hi), seed=args.seed)
    else:
        client = OllamaSystemOne(model=args.model, host=args.ollama_host)
    return game.deciders.SystemOneDecider(client, min_confidence=args.min_confidence)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", default=DEFAULT_GAME, help="<system>/<name>")
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--decider", choices=("rule", "mock", "ollama"), default="rule")
    parser.add_argument("--latency", default="90,500", help="mock model latency range in ms")
    parser.add_argument("--model", default="nimble")
    parser.add_argument("--ollama-host", default="http://localhost:11434")
    parser.add_argument("--min-confidence", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--lookahead", type=int, default=None, help="tiles ahead to query (game default if unset)")
    parser.add_argument("--knowledge", choices=None, help="help rung the game offers, e.g. L0..L3b")
    parser.add_argument("--tag", default="", help="label added to the run files")
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--seconds", type=int, default=3600)
    parser.add_argument("--out", default=str(ROOT / "runs"))
    args = parser.parse_args()

    game = load_game(args.game)
    if args.knowledge and args.knowledge not in game.knowledge.LEVELS:
        parser.error(f"--knowledge must be one of {game.knowledge.LEVELS}")
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    label = "-".join(p for p in (stamp, args.game.replace("/", "_"), args.decider, args.knowledge, args.tag) if p)
    decisions_log = open(out_dir / f"{label}-decisions.jsonl", "w", buffering=1)
    results_path = out_dir / f"{label}-games.jsonl"

    stream = StateStream(args.host, game=game)
    stream.start_latest()
    broker = BrokerLink(args.host)
    worker = DecisionWorker(build_decider(game, args))
    extra = {"lookahead": args.lookahead} if args.lookahead is not None else {}
    player = game.player.Player(stream, broker, worker, game.player.RuleStrategy(), decisions_log,
                                knowledge=args.knowledge, **extra)

    results, deadline = [], time.time() + args.seconds
    last_good = time.time()
    print(f"playing {args.games} game(s) of {args.game} with decider={args.decider} "
          f"knowledge={args.knowledge}; logs in {out_dir}", flush=True)
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
