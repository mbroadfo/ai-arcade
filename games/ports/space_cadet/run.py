"""Play one game of Space Cadet on the cabinet Pi with the model or a control, and log every decision.

    python -m games.ports.space_cadet.run --player model --model nimble
    python -m games.ports.space_cadet.run --player reflex      # control: flip when the ball is in reach (code)
    python -m games.ports.space_cadet.run --player idle        # control: no flippers

Time is stepped: the game waits while the player decides, then advances one window of 10 ms frames (--window). A run is
labelled "thinking time": the model's latency costs the game nothing. The log (runs/<label>.jsonl) has every decision with
its source (model, fallback or code), and the last line is the summary.
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from arcadekit.health import ModelHealth  # noqa: E402
from games.ports.space_cadet import observe  # noqa: E402
from games.ports.space_cadet.env import HOST, SpaceCadet  # noqa: E402
from games.ports.space_cadet.players import (HOLDS, IdleControl, ModelPlayer, NUDGES, PULLS,  # noqa: E402
                                            ReflexControl, flipper_facts)

KEYS = ("left", "right")


def apply_hold(game, held, want):
    """Press and release only what changed."""
    for key, was, now in zip(KEYS, held, want):
        if now and not was:
            game.press(key)
        elif was and not now:
            game.release(key)
    return want


STILL_RADIUS = 0.6  # the ball counts as staying put while it is within this of where it was


def play(game, player, window=8, max_game_s=900, max_wall_s=1800, log=None, health=None, say=print, seed=None,
         live=None, should_stop=None):
    """seed: [timing] wait a random 0 to 2 s before each launch (the game is deterministic, so without it every run of a
    player is the same game). The wait is the same for every kind of player and is logged."""
    rng = random.Random(seed) if seed is not None else None
    state = game.new_game()
    trail, shown = [], 0.0  # the ball's recent path, and when the Observatory was last sent a picture
    anchor = None  # (x, y, game time): where the ball was when it last moved more than STILL_RADIUS
    held, n, t0, drains, last_ball = (False, False), 0, time.time(), 0, state["ball_number"]
    decisions, up_windows = {}, {"left": 0, "right": 0}
    while state["game_mode"] == "in_game":
        if state["time"] > max_game_s or time.time() - t0 > max_wall_s:
            say("time limit reached")
            break
        if should_stop and should_stop():
            say("stopped")
            break
        if state["ball_number"] != last_ball:
            drains, last_ball = drains + 1, state["ball_number"]
            say(f"  ball lost: score {state['score']}, {state['ball_number']} left")
            if live:
                live.send({"event": "lab", "what": f"ball lost: score {state['score']}, {state['ball_number']} left",
                           "t": round(time.time(), 3)})
        if not state["balls"]:
            state = game.step(20)  # the next ball is on its way
            continue
        ff = flipper_facts(state, state["balls"][0])
        b = state["balls"][0]
        if anchor is None or abs(b["x"] - anchor[0]) > STILL_RADIUS or abs(b["y"] - anchor[1]) > STILL_RADIUS:
            anchor = (b["x"], b["y"], state["time"])
        ff["ball"]["still_s"] = state["time"] - anchor[2]
        for side, was_up in zip(KEYS, held):  # how long each flipper has been held up (a fact for the player)
            ff[side]["up_s"] = up_windows[side] * window / 100
            up_windows[side] = up_windows[side] + 1 if was_up else 0
        if ff["in_lane"]:
            held = apply_hold(game, held, (False, False))
            wait = rng.randint(0, 200) if rng else 0
            if wait:
                game.step(wait)
            d = player.launch(state)
            d["wait_frames"] = wait
            game.press("plunger")
            game.step(PULLS[d["choice"]])
            game.release("plunger")
            state = game.step(30)
            kind = "launch"
        else:
            d = player.flippers(state, ff, held)
            held = apply_hold(game, held, HOLDS[d["choice"]])
            if d.get("nudge"):  # a nudge goes with whatever the flippers are doing
                game.press(NUDGES[d["nudge"]])
                game.release(NUDGES[d["nudge"]])
            state = game.step(window)
            kind = "flippers"
        n += 1
        decisions[d["source"]] = decisions.get(d["source"], 0) + 1
        if health is not None and d["source"] in ("model", "fallback"):
            change = health.record(d["source"] == "model")
            if change:
                say("  " + (health.message() if change == "trouble" else "model answering again"))
        if live:
            if state["balls"]:
                trail = (trail + [(-state["balls"][0]["x"], state["balls"][0]["y"])])[-40:]
            for line in (d.get("note"),) if d.get("source") == "fallback" and d.get("note") else ():
                live.send({"event": "lab", "what": f"fallback: {line}", "t": round(time.time(), 3)})
            if kind == "launch" or d.get("nudge"):  # the timeline: the moves worth reading (flips are on the status line)
                took = f", {d['latency_ms'] / 1000:.1f} s" if d.get("latency_ms") else ""
                live.send({"event": "lab", "what": f"{kind}: {d.get('nudge') or d['choice']} ({d['source']}{took})",
                           "t": round(time.time(), 3)})
            if time.time() - shown >= 0.2:  # the Observatory: five pictures and status lines a second
                shown = time.time()
                live.send({"event": "frame", "png": observe.frame_png(state, trail)})
                live.send({**observe.status(state, d, kind, ff, drains, bool(health and health.trouble)),
                           "t": round(time.time(), 3)})
        if log:
            log.write(json.dumps({"n": n, "t": state["time"], "kind": kind, "score": state["score"], "ball": 4 - state["ball_number"],
                                  **d}) + "\n")
    apply_hold(game, held, (False, False))
    return {"score": state["score"], "balls_lost": drains, "game_time_s": round(state["time"], 1), "decisions": n,
            "by_source": decisions, "wall_s": round(time.time() - t0, 1), "ended": state["game_mode"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--player", "--policy", dest="player", choices=("model", "reflex", "idle"), default="model")
    ap.add_argument("--model", default="nimble")
    ap.add_argument("--window", type=int, default=None, help="[timing] frames of 10 ms between decisions (8 = 12.5 a second)")
    ap.add_argument("--hz", type=float, default=None, help="[timing] decisions per second of game time (100 / window)")
    ap.add_argument("--ask-when", choices=("near", "always"), default="near",
                    help="[timing] near: ask about a flipper only when the ball is near it; always: every window")
    ap.add_argument("--seed", type=int, default=None, help="[timing] vary the launch timing (see play)")
    ap.add_argument("--max-game-s", type=float, default=900)
    ap.add_argument("--max-wall-s", "--seconds", dest="max_wall_s", type=float, default=1800)
    ap.add_argument("--out", default=str(ROOT / "runs"))
    ap.add_argument("--tag", default="")
    ap.add_argument("--show", action="store_true", help="draw on the cabinet's screen (stop EmulationStation first)")
    ap.add_argument("--host", default=None, help="the cabinet Pi (the Observatory passes it)")
    ap.add_argument("--observatory", default="127.0.0.1:8770", help="HOST:PORT of the Observatory (tools/observatory.py), or none")
    args = ap.parse_args(argv)
    window = args.window or (max(1, round(100 / args.hz)) if args.hz else 8)

    if args.player == "model":
        from arcadekit.systemone import OllamaSystemOne
        player = ModelPlayer(OllamaSystemOne(model=args.model, timeout=4.0), args.ask_when)
    else:
        player = ReflexControl() if args.player == "reflex" else IdleControl()
    label = "-".join(p for p in (time.strftime("%Y%m%d-%H%M%S"), "ports_space_cadet", args.player,
                                 args.model if args.player == "model" else "", f"w{window}",
                                 f"s{args.seed}" if args.seed is not None else "", args.tag) if p)
    label = label.replace(":", "_")  # a model name like nimble:latest: a colon in a Windows file name starts a hidden stream
    path = Path(args.out) / f"{label}.jsonl"
    path.parent.mkdir(exist_ok=True)
    decider = (f"S1M {args.model}: every flipper, nudge and plunger choice (model)" if args.player == "model"
               else f"control: {args.player} (code)")
    run_record = {"event": "run", "label": label, "game": "ports/space_cadet", "policy": args.player, "hz": round(100 / window, 1),
                  "decider": decider, "model": args.model if args.player == "model" else None, "knowledge": None, "goal": None,
                  "strategist": None, "games": 1, "switches": {"window": window, "seed": args.seed, "ask_when": args.ask_when},
                  "mode": "stepped (thinking time): the game waits for each answer", "t": time.time()}
    stop = []

    def command(message):  # from the Observatory: stop the run
        if message.get("op") == "stop":
            stop.append(1)
    live = None
    if args.observatory != "none":
        from arcadekit.observatory import LiveSink
        host, _, port = args.observatory.rpartition(":")
        live = LiveSink((host, int(port)), hello=lambda: [run_record], on_command=command)
    if args.player == "model":  # a cold model takes ~10 s to answer the first question: load it before the game starts
        try:
            player.client.__class__(model=args.model, timeout=60).ask("warm-up", {"x": {"type": "choice", "instructions": "Pick.",
                                                                                         "criteria": {"a": "a", "b": "b"}}})
        except Exception as exc:
            print(f"warm-up failed: {exc}")
    summary = {}
    try:
        with open(path, "w", buffering=1) as log, SpaceCadet(host=f"pi@{args.host}" if args.host else HOST, show=args.show) as game:
            log.write(json.dumps(run_record) + chr(10))
            print(f"{player.kind}: {label}")
            summary = play(game, player, window, args.max_game_s, args.max_wall_s, log, ModelHealth(), seed=args.seed,
                           live=live, should_stop=lambda: bool(stop))
            summary.update(player=player.kind, model=args.model if args.player == "model" else None, window=window,
                           seed=args.seed, mode="stepped (thinking time)")
            log.write(json.dumps({"summary": summary}) + chr(10))
    finally:
        if live:
            live.send({"event": "lab", "what": "result: " + ", ".join(f"{k} {v}" for k, v in summary.items()
                                                                      if k in ("score", "balls_lost", "game_time_s", "decisions", "by_source")),
                       "t": round(time.time(), 3)})
            live.send({"event": "run_end", "label": label, "games_completed": int(summary.get("ended") == "game_over"),
                       "t": time.time()})
            live.close(2.0)
    print(json.dumps(summary, indent=1))
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
