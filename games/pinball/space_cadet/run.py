"""Play one game of Space Cadet on the cabinet Pi with the model or a control, and log every decision.

    python -m games.pinball.space_cadet.run --player model --model nimble
    python -m games.pinball.space_cadet.run --player reflex      # control: flip when the ball is in reach (code)
    python -m games.pinball.space_cadet.run --player idle        # control: no flippers

Time is stepped: the game waits while the player decides, then advances one window of 10 ms frames (--window). A run is
labelled "thinking time": the model's latency costs the game nothing. The log (runs/<label>.jsonl) has every decision with
its source (model, fallback or code), and the last line is the summary.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from arcadekit.health import ModelHealth  # noqa: E402
from games.pinball.space_cadet.env import SpaceCadet  # noqa: E402
from games.pinball.space_cadet.player import (HOLDS, IdleControl, ModelPlayer, NUDGES, PULLS,  # noqa: E402
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


def play(game, player, window=8, max_game_s=900, max_wall_s=1800, log=None, health=None, say=print):
    state = game.new_game()
    held, n, t0, drains, last_ball = (False, False), 0, time.time(), 0, state["ball_number"]
    decisions, up_windows = {}, {"left": 0, "right": 0}
    while state["game_mode"] == "in_game":
        if state["time"] > max_game_s or time.time() - t0 > max_wall_s:
            say("time limit reached")
            break
        if state["ball_number"] != last_ball:
            drains, last_ball = drains + 1, state["ball_number"]
            say(f"  ball lost: score {state['score']}, {state['ball_number']} left")
        if not state["balls"]:
            state = game.step(20)  # the next ball is on its way
            continue
        ff = flipper_facts(state, state["balls"][0])
        for side, was_up in zip(KEYS, held):  # how long each flipper has been held up (a fact for the player)
            ff[side]["up_s"] = up_windows[side] * window / 100
            up_windows[side] = up_windows[side] + 1 if was_up else 0
        if ff["in_lane"]:
            held = apply_hold(game, held, (False, False))
            d = player.launch(state)
            game.press("plunger")
            game.step(PULLS[d["choice"]])
            game.release("plunger")
            state = game.step(30)
            kind = "launch"
        else:
            d = player.flippers(state, ff, held)
            if d["choice"] in NUDGES:  # a nudge leaves the flippers as they are
                game.press(NUDGES[d["choice"]])
                game.release(NUDGES[d["choice"]])
            else:
                held = apply_hold(game, held, HOLDS[d["choice"]])
            state = game.step(window)
            kind = "flippers"
        n += 1
        decisions[d["source"]] = decisions.get(d["source"], 0) + 1
        if health is not None and d["source"] in ("model", "fallback"):
            change = health.record(d["source"] == "model")
            if change:
                say("  " + (health.message() if change == "trouble" else "model answering again"))
        if log:
            log.write(json.dumps({"n": n, "t": state["time"], "kind": kind, "score": state["score"], "ball": 4 - state["ball_number"],
                                  **d}) + "\n")
    apply_hold(game, held, (False, False))
    return {"score": state["score"], "balls_lost": drains, "game_time_s": round(state["time"], 1), "decisions": n,
            "by_source": decisions, "wall_s": round(time.time() - t0, 1), "ended": state["game_mode"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--player", choices=("model", "reflex", "idle"), default="model")
    ap.add_argument("--model", default="nimble")
    ap.add_argument("--window", type=int, default=8, help="[timing] frames of 10 ms between decisions")
    ap.add_argument("--max-game-s", type=float, default=900)
    ap.add_argument("--max-wall-s", type=float, default=1800)
    ap.add_argument("--out", default=str(ROOT / "runs"))
    ap.add_argument("--tag", default="")
    ap.add_argument("--show", action="store_true", help="draw on the cabinet's screen (stop EmulationStation first)")
    args = ap.parse_args(argv)

    if args.player == "model":
        from arcadekit.systemone import OllamaSystemOne
        player = ModelPlayer(OllamaSystemOne(model=args.model, timeout=4.0))
    else:
        player = ReflexControl() if args.player == "reflex" else IdleControl()
    label = "-".join(p for p in (time.strftime("%Y%m%d-%H%M%S"), "pinball_space_cadet", args.player,
                                 args.model if args.player == "model" else "", f"w{args.window}", args.tag) if p)
    path = Path(args.out) / f"{label}.jsonl"
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", buffering=1) as log, SpaceCadet(show=args.show) as game:
        print(f"{player.kind}: {label}")
        summary = play(game, player, args.window, args.max_game_s, args.max_wall_s, log, ModelHealth())
        summary.update(player=player.kind, model=args.model if args.player == "model" else None, window=args.window,
                       mode="stepped (thinking time)")
        log.write(json.dumps({"summary": summary}) + "\n")
    print(json.dumps(summary, indent=1))
    print(path)


if __name__ == "__main__":
    main()
