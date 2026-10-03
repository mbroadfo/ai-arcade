"""Run a game's real-time lab (code policies on a fixed-rate clock) with the given arguments. Any game that offers one.

    python tools/run_lab.py --game <system>/<name> [the lab's own arguments]

The Observatory starts this instead of play.py for a game with a lab and no model player (tools/ai_runner.py).
"""
import argparse
import sys

from gamelib import load_game


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--game", required=True)
    known, rest = pre.parse_known_args(argv)
    game = load_game(known.game)
    if not hasattr(game, "lab_main"):
        raise SystemExit(f"{known.game} has no lab")
    return game.lab_main(rest)


if __name__ == "__main__":
    sys.exit(main())
