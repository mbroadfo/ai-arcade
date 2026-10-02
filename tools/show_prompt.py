"""Print what the model is told at a knowledge rung, for a RAM image. Any game whose knowledge offers show().

    python tools/show_prompt.py --game arcade/pacman --level L3b --image games/arcade/pacman/tests/fixtures/pacman_play_ram.bin
"""
import argparse
import sys
from pathlib import Path

from gamelib import DEFAULT_GAME, load_game


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", default=DEFAULT_GAME, help="<system>/<name>")
    parser.add_argument("--level", default="L3b", help="a rung the game offers, e.g. L0..L3b")
    parser.add_argument("--image", required=True, help="a RAM image of the game's IMAGE window (e.g. a test fixture)")
    args = parser.parse_args()
    game = load_game(args.game)
    if args.level not in game.knowledge.LEVELS:
        parser.error(f"--level must be one of {game.knowledge.LEVELS}")
    print(game.knowledge.show(Path(args.image).read_bytes(), args.level))
    return 0


if __name__ == "__main__":
    sys.exit(main())
