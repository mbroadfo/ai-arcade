"""Tile-by-tile simulation of the player's decision loop on a real maze with no ghosts.

Used to check endgame behaviour (few dots left, nothing threatening) without the cabinet.
"""
import random
from dataclasses import replace
from pathlib import Path

from games.arcade.pacman import deciders as _deciders

RuleDecider = _deciders.RuleDecider
from games.arcade.pacman import features as _features
junction_facts = _features.junction_facts
from games.arcade.pacman.maze import BLANK, DOT, ENERGIZER, LOWER_TO_UPPER, Maze, step
from games.arcade.pacman.state import decode

IMAGE = (Path(__file__).parent / "fixtures" / "pacman_play_ram.bin").read_bytes()
BASE_STATE = decode(IMAGE)
GONE = (0, 0)  # a ghost tile no path reaches: no threat anywhere


def food_tiles(image):
    maze = Maze(image)
    return [(l, h) for l in range(0x20, 0x40) for h in range(0x1E, 0x3E) if maze.has_food(l, h)] \
        if False else [(l, h) for l in range(0x20, 0x40) for h in range(0x1E, 0x3E) if maze.has_food((l, h))]


def leave_dots(image, keep):
    """Image with every dot and energizer removed except the tiles in `keep`."""
    img = bytearray(image)
    maze = Maze(image)
    for tile in food_tiles(image):
        if tile not in keep:
            img[maze._addr(*tile) - 0x4000] = BLANK
    return bytes(img)


def eat(image, tile):
    maze = Maze(image)
    if not maze.has_food(tile):
        return image, False
    img = bytearray(image)
    img[maze._addr(*tile) - 0x4000] = BLANK
    return bytes(img), True


def simulate(image, start, heading, goal="clear_dots", max_steps=600, decider=None):
    """Walk Pac-Man until all food is eaten or max_steps. Returns (steps_taken, food_left, trail)."""
    decider = decider or RuleDecider()
    me, trail = start, [start]
    ghosts = {n: replace(g, tile=GONE, next_tile=GONE) for n, g in BASE_STATE.ghosts.items()}
    for taken in range(max_steps):
        maze = Maze(image)
        if maze.food_left() == 0:
            return taken, 0, trail
        state = replace(BASE_STATE, ghosts=ghosts,
                        pacman=replace(BASE_STATE.pacman, tile=me, direction=heading.lower()))
        junction, steps, path = maze.walk_to_decision(me, heading)
        if junction is not None and steps == 0:
            facts = junction_facts(state, image, tile=me, arriving=heading)
            move = decider.decide(facts, goal).choice
        elif path:
            move = path[0]
        else:
            return taken, maze.food_left(), trail  # dead end: stuck
        me, heading = step(me, move), move
        image, _ = eat(image, me)
        trail.append(me)
    return max_steps, Maze(image).food_left(), trail


def random_scenarios(n, dots=3, seed=1):
    """(image, start, heading) cases: only `dots` pieces of food left, scattered; random junction starts."""
    rng = random.Random(seed)
    tiles = food_tiles(IMAGE)
    maze = Maze(IMAGE)
    corridors = [t for t in tiles if len(maze.exits(t)) >= 2]
    for _ in range(n):
        keep = set(rng.sample(tiles, dots))
        start = rng.choice(corridors)
        heading = rng.choice(maze.exits(start))
        yield leave_dots(IMAGE, keep), start, heading
