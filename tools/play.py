"""Play a game with an AI: the Pi streams state, a decider chooses, the broker steers. Any game package.

The game's own switches (its experiment.OPTIONS) are added to the command line; see --help with --game.

    python tools/play.py --game arcade/pacman --decider rule --games 3
    python tools/play.py --game arcade/pacman --decider mock --latency 90,500 --games 5
    python tools/play.py --game arcade/pacman --decider ollama --model nimble --knowledge L2 --games 5

Every logged event, and a status line five times a second, also goes to the Observatory dashboard when one is running
(python tools/observatory.py; --observatory none to not send).

Standing orders (arcadekit/orders.py): text put in front of every question a model is asked. Set them at the start with
--orders (repeat for several) and change them during the run from the Observatory. Every change is logged.
    python tools/play.py --game arcade/pacman --decider ollama --knowledge L2 --orders "Play safe: a life matters more than points."
"""
import argparse
import json
import sys
import threading
import time
from pathlib import Path

from gamelib import DEFAULT_GAME, DEFAULT_PI_HOST, ROOT, load_game  # first: puts the repository root on sys.path

from arcadekit.decisions import DecisionWorker
from arcadekit.manifest import build_manifest
from arcadekit.observatory import DEFAULT_ADDRESS, EventSink, LiveSink
from arcadekit.orders import Orders, OrderedClient
from arcadekit.options import add_arguments, label_parts, values
from arcadekit.report import summary_lines
from arcadekit.strategist import MockStrategistClient, Strategist
from arcadekit.systemone import DEFAULT_HOST, MockSystemOne, OllamaSystemOne
from broker_link import BrokerLink
from state_client import StateStream


def build_decider(game, args, orders):
    if args.decider == "rule":
        return game.deciders.RuleDecider()
    if args.decider == "mock":
        lo, hi = (float(x) for x in args.latency.split(","))
        client = MockSystemOne(game.score_option, latency_ms=(lo, hi), seed=args.seed)
    else:
        client = OllamaSystemOne(model=args.model, host=args.ollama_host)
    return game.deciders.SystemOneDecider(OrderedClient(client, orders, "decisions"),
                                          min_confidence=args.min_confidence)


def chosen_game(argv):
    """The --game named on the command line (before full parsing: its options shape the parser)."""
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--game", default=DEFAULT_GAME)
    return pre.parse_known_args(argv)[0].game


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    game = load_game(chosen_game(argv))
    experiment = getattr(game, "experiment", None)
    game_options = experiment.OPTIONS if experiment else ()
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", default=DEFAULT_GAME, help="<system>/<name>")
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--decider", choices=("rule", "mock", "ollama"), default="rule")
    parser.add_argument("--latency", default="90,500", help="mock model latency range in ms")
    parser.add_argument("--model", default="nimble")
    parser.add_argument("--ollama-host", default=DEFAULT_HOST)
    parser.add_argument("--min-confidence", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--knowledge", choices=None, help="help rung the game offers, e.g. L0..L3b")
    parser.add_argument("--goal", default="auto", help="standing goal: auto, or pin one (game-specific names)")
    parser.add_argument("--strategist", choices=("code", "mock", "ollama"), default="code",
                        help="who sets the goal and stance: the game's own code (default), a mock model that "
                             "repeats the code's choice after a delay (latency control), or a System One model")
    parser.add_argument("--strategist-model", default="nimble")
    parser.add_argument("--tag", default="", help="label added to the run files")
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--seconds", type=int, default=3600)
    parser.add_argument("--out", default=str(ROOT / "runs"))
    parser.add_argument("--orders", action="append", default=[], metavar="TEXT",
                        help="a standing order for the model, in plain words (repeat for several); "
                             "the Observatory can change them during the run")
    parser.add_argument("--observatory", default="%s:%d" % DEFAULT_ADDRESS,
                        help="HOST:PORT of the Observatory dashboard (tools/observatory.py), or none")
    add_arguments(parser, game_options, f"{chosen_game(argv)} switches (kind in brackets; docs/GAME_WORKSHOP.md)")
    args = parser.parse_args(argv)
    game_values = values(args, game_options)
    if args.knowledge and args.knowledge not in game.knowledge.LEVELS:
        parser.error(f"--knowledge must be one of {game.knowledge.LEVELS}")
    if args.goal not in game.goals.MISSIONS:
        parser.error(f"--goal must be one of {game.goals.MISSIONS}")
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    label = "-".join(p for p in (stamp, args.game.replace("/", "_"), args.decider, args.knowledge,
                                 None if args.goal == "auto" else args.goal,
                                 None if args.strategist == "code" else f"strat-{args.strategist}",
                                 *label_parts(game_values, game_options), "orders" if args.orders else None,
                                 args.tag) if p)
    decisions_log = open(out_dir / f"{label}-decisions.jsonl", "w", buffering=1)
    orders = Orders(args.orders)
    # who reads the orders: only questions a real model answers (a rule decider and a mock model never see text)
    orders_reach = ((["decisions"] if args.decider == "ollama" else [])
                    + (["goal and stance"] if args.strategist == "ollama" else []))
    run_record = {"event": "run", "label": label, "game": args.game, "decider": args.decider,
                  "model": None if args.decider == "rule" else args.model, "knowledge": args.knowledge,
                  "goal": args.goal, "strategist": args.strategist, "games": args.games, "switches": game_values,
                  "orders_example": getattr(game, "ORDERS_EXAMPLE", ""), "t": round(time.time(), 3)}

    def orders_record(source):
        version, items = orders.snapshot()
        return {"event": "orders", "version": version, "orders": items, "source": source,
                "reaches": orders_reach, "t": round(time.time(), 3)}

    stop_requested = threading.Event()

    def command(message):  # from the Observatory
        if message.get("op") == "stop":  # end the run as Ctrl+C would: results and manifest are written
            stop_requested.set()
        if message.get("op") == "orders" and isinstance(message.get("orders"), list):
            if orders.set(message["orders"], source="operator") is None:
                live.send(orders_record("unchanged"))  # still confirm, so the page stops waiting

    live = None
    if args.observatory != "none":
        host, _, port = args.observatory.rpartition(":")
        live = LiveSink((host, int(port)), on_command=command,
                        hello=lambda: [run_record, orders_record("current")])
        decisions_log = EventSink(decisions_log, live)
    results_path = out_dir / f"{label}-games.jsonl"
    manifest_path = out_dir / f"{label}-manifest.json"
    manifest = build_manifest(args, label, game_options, game_values)
    manifest_path.write_text(json.dumps(manifest, indent=2))

    stream = StateStream(args.host, game=game)
    stream.start_latest()
    first, t0 = stream.latest()[0], time.time()  # emulated frames per second: a run at reduced MAME -speed must say so
    time.sleep(2.0)
    manifest["emulated_fps"] = round((stream.latest()[0] - first) / (time.time() - t0), 1)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    broker = BrokerLink(args.host)
    worker = DecisionWorker(build_decider(game, args, orders))

    def new_worker(model):  # for a game switch that names a second model
        orders_reach.append(f"{model} questions")
        return DecisionWorker(game.deciders.SystemOneDecider(
            OrderedClient(OllamaSystemOne(model=model, host=args.ollama_host, timeout=2.0), orders,
                          f"{model} questions"),
            min_confidence=args.min_confidence))

    extra = experiment.player_kwargs(game_values, new_worker) if experiment else {}
    manager = game.goals.GoalManager(args.goal)
    if args.strategist != "code":
        if args.goal != "auto":
            parser.error("--strategist needs --goal auto (a pinned goal leaves nothing to decide)")
        client = (MockStrategistClient(game.strategy.code_chooser, seed=args.seed) if args.strategist == "mock"
                  else OrderedClient(OllamaSystemOne(model=args.strategist_model, host=args.ollama_host), orders,
                                     "goal and stance"))
        manager = game.strategy.ModelGoalManager(Strategist(client, game.strategy.SCHEMA), manager)
    player = game.player.Player(stream, broker, worker, manager, decisions_log,
                                knowledge=args.knowledge, **extra)
    orders.log = player.log
    player.log(event="orders", version=orders.version, orders=orders.items, source="start", reaches=orders_reach)
    observe = getattr(player, "observe", None) if live else None
    observed_at = 0.0
    # the game's speed can change during the run (the Observatory's slider): measure it, log every change
    speed_mark = (stream.latest()[0], time.time())
    speeds = [{"t": round(time.time(), 3), "emulated_fps": manifest["emulated_fps"]}]

    results, deadline = [], time.time() + args.seconds
    last_good = time.time()
    print(f"playing {args.games} game(s) of {args.game} with decider={args.decider} "
          f"goal={args.goal} knowledge={args.knowledge}; logs in {out_dir}", flush=True)
    try:
        while time.time() < deadline and player.finished < args.games and not stop_requested.is_set():
            try:
                result = player.tick()
                last_good = time.time()
                if last_good - speed_mark[1] >= 3.0:
                    fps = round((player.last_frame - speed_mark[0]) / (last_good - speed_mark[1]), 1)
                    speed_mark = (player.last_frame, last_good)
                    if abs(fps - speeds[-1]["emulated_fps"]) >= 3:
                        speeds.append({"t": round(last_good, 3), "emulated_fps": fps})
                        player.log(event="speed", emulated_fps=fps)
                if observe and last_good - observed_at >= 0.2:
                    observed_at = last_good
                    live.send({**observe(), "asked": orders.latest(), "t": round(last_good, 3)})
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
        partial = player.partial_result() if player.finished < args.games else None
        if partial:
            results.append(partial)
            results_path.write_text("".join(json.dumps(r) + "\n" for r in results))
            print(f"STOPPED mid-game {partial['game']}: score={partial['score']} level={partial['level']} "
                  f"seconds={partial['seconds']} (partial)", flush=True)
        try:
            broker.release_all()
        except OSError:
            pass
        if live:
            live.send({"event": "run_end", "label": label, "games_completed": len(results), "t": round(time.time(), 3)})
        decisions_log.close()
        stream.close()
        manifest.update(ended=time.strftime("%Y-%m-%dT%H:%M:%S"), games_completed=len(results), speeds=speeds,
                        orders={**orders.summary(), "reaches": orders_reach})
        manifest_path.write_text(json.dumps(manifest, indent=2))

    print()
    for line in summary_lines(player, results, broker, experiment.METRICS if experiment else (),
                              experiment.report_lines(player, results) if experiment else ()):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
