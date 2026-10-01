"""What a System One model is told about Pac-Man, in rungs so each can be ablated.

    L0  raw state: coordinates and flags only, no help
    L1  + the rules of the game as static text (what things are, what kills you, what scores)
    L2  + a situation report: facts derived from the state in Pac-Man's own frame (distances along
          the maze, which exit each ghost comes from, approaching/leaving, bands like DANGER/NEAR/FAR)
    L3a + a text description of how each ghost chooses where to go
    L3b + each ghost's current target tile and the route it will take (from ghosts.forecast,
          with Pac-Man held at the decision tile; no guess at what Pac-Man will do next)
    L4  code picks the action: that is RuleDecider in deciders.py, the control, not a rung here.

Rungs are cumulative and L3a / L3b are independent switches on top of L2, so results can be labelled
with exactly what help the model had.
"""
from .ghosts import GHOST_NAMES, SCATTER_TARGETS, direction_between, forecast, targets
from .maze import MOVES, Maze, step

LEVELS = ("L0", "L1", "L2", "L3a", "L3b")
DANGER_STEPS, NEAR_STEPS = 4, 8
NAMES = {"red": "Red (Blinky)", "pink": "Pink (Pinky)", "blue": "Blue (Inky)", "orange": "Orange (Clyde)"}

RULES_L1 = """\
PAC-MAN RULES
You steer Pac-Man through a maze. You hold one of four directions (UP, DOWN, LEFT, RIGHT); Pac-Man keeps moving that way until a wall stops him. He may turn or reverse at any time.
- Pac-Man eats dots (10 points) by passing over them. Eating every dot clears the level. Energizers (4 big dots, 50 points) turn the ghosts blue for a short time.
- A bonus fruit appears in the middle of the maze, below the ghost house, after 70 and again after 170 dots are eaten. It vanishes after a few seconds. Eating it scores bonus points (100 on level 1).
- Four ghosts roam the maze: Red, Pink, Blue, Orange. A normal ghost touching Pac-Man costs a life. Ghosts move at about Pac-Man's speed, so a ghost behind you stays behind you but one ahead of you must be avoided.
- While blue (frightened), ghosts are harmless and can be eaten: 200, then 400, 800, 1600 points for each in a row. An eaten ghost shows only eyes and hurries home, harmless. Blue ghosts wander randomly and are slower.
- Ghosts never reverse on their own; at a junction they pick among the other exits. They all reverse when the mode changes (scatter to chase, or an energizer being eaten).
- The wrap-around tunnel in the middle row leads from one side of the maze to the other; ghosts are slow in it.
- A dead end is a trap. A junction with a ghost near on every side is a trap. Prefer exits with open room behind them.
- Goal: score as much as possible without losing lives. Survival beats dots. Eat blue ghosts only when it is safe.
"""

GHOST_BEHAVIOUR_L3A = """\
HOW THE GHOSTS CHOOSE (they are not random while normal)
Every ghost, at each tile, looks at the exits it may take (never straight back) and picks the one whose next tile is closest in a straight line to its TARGET tile. It does not plan ahead.
- Red chases Pac-Man's own tile.
- Pink aims 4 tiles in front of Pac-Man (a quirk: when Pac-Man faces UP she aims 4 up and 4 left).
- Blue aims at the point opposite Red: take the tile 2 in front of Pac-Man and mirror Red's position through it.
- Orange chases like Red until he is within 8 tiles of Pac-Man, then heads for his own corner (bottom left) instead.
- In scatter phases (which alternate with chase phases) ghosts ignore Pac-Man and head for their own corner of the maze. Red chases anyway once most dots are gone.
So a ghost's route follows from where Pac-Man is and which way he faces: a ghost that is far away can still be steered into a loop by where you go.
"""


def _rel(dl, dh):
    """Describe an offset in screen terms (down is +l, left is +h)."""
    parts = []
    if dl:
        parts.append(f"{abs(dl)} {'down' if dl > 0 else 'up'}")
    if dh:
        parts.append(f"{abs(dh)} {'left' if dh > 0 else 'right'}")
    return " and ".join(parts) or "on you"


def _modes(state):
    return {n: "eyes" if state.eyes[n] else "frightened" if state.frightened[n] else "normal"
            for n in state.ghosts}


def _band(steps):
    return "DANGER" if steps <= DANGER_STEPS else "NEAR" if steps <= NEAR_STEPS else "FAR"


def ghost_facts(state, image, tile):
    """Egocentric facts per ghost, relative to `tile`. Pure function of the state."""
    maze = Maze(image)
    here = maze.bfs(tile)
    modes = _modes(state)
    out = []
    for name in GHOST_NAMES:
        g = state.ghosts[name]
        steps = here.get(tuple(g.tile))
        fact = {"name": name, "mode": modes[name], "steps": steps,
                "offset": (g.tile[0] - tile[0], g.tile[1] - tile[1]), "via": None, "approaching": None}
        if steps is not None and steps > 0:
            from_ghost = maze.bfs(tuple(g.tile))
            reachable = [(from_ghost[step(tile, d)], d) for d in MOVES if step(tile, d) in from_ghost]
            fact["via"] = min(reachable)[1] if reachable else None
            nxt = here.get(tuple(g.next_tile))
            fact["approaching"] = None if nxt is None else nxt < steps
        out.append(fact)
    return out


def render_l0(state, tile, arriving):
    lines = [f"Pac-Man at {list(tile)} heading {arriving}. Lives {state.lives}. Level {state.level}. Score {state.score}."]
    modes = _modes(state)
    for n in GHOST_NAMES:
        g = state.ghosts[n]
        lines.append(f"{n} ghost at {list(g.tile)} heading {g.direction}, {modes[n]}")
    return "\n".join(lines)


def render_l2(state, image, tile, arriving, facts):
    """The situation report: how things stand from Pac-Man's seat, in plain words."""
    lines = [f"SITUATION. Pac-Man is at a junction, arrived heading {arriving}. "
             f"Lives {state.lives}, level {state.level}, dots left {facts['food_left']}."]
    for gf in ghost_facts(state, image, tile):
        label = NAMES[gf["name"]]
        if gf["mode"] == "eyes":
            lines.append(f"- {label}: eyes only, returning home, harmless.")
        elif gf["steps"] is None:
            lines.append(f"- {label}: {gf['mode']}, in the ghost house or out of reach.")
        elif gf["mode"] == "frightened":
            lines.append(f"- {label}: BLUE, edible, {gf['steps']} steps away ({_rel(*gf['offset'])}), "
                         f"reached first via {gf['via']}.")
        else:
            move = {True: "coming toward you", False: "moving away", None: "direction unclear"}[gf["approaching"]]
            lines.append(f"- {label}: {_band(gf['steps'])}, {gf['steps']} steps away ({_rel(*gf['offset'])}), "
                         f"{move}, would arrive via {gf['via']}.")
    if state.fruit_tile and facts.get("fruit_steps") is not None:
        lines.append(f"- BONUS FRUIT on screen, {facts['fruit_steps']} steps away; it will vanish soon.")
    lines.append("EXITS")
    for direction, o in facts["options"].items():
        bits = [f"nearest dot {o['food_steps']} steps" if o["food_steps"] is not None else "no dots reachable",
                f"nearest danger {o['threat_steps']} steps ({_band(o['threat_steps'])})"
                if o["threat_steps"] is not None else "no normal ghost reachable that way",
                f"open room {o['room']} tiles"]
        if o["edible_steps"] is not None:
            bits.append(f"blue ghost {o['edible_steps']} steps")
        if o.get("fruit_steps") is not None:
            bits.append(f"bonus fruit {o['fruit_steps']} steps")
        if o.get("energizer_steps") is not None:
            bits.append(f"energizer {o['energizer_steps']} steps")
        if o["reverse"]:
            bits.append("this is turning back")
        lines.append(f"- {direction}: " + ", ".join(bits))
    return "\n".join(lines)


def _route(tiles, first):
    """Compress a tile path into 'LEFT x3, UP x2'."""
    moves, prev = [], first
    for t in tiles:
        d = direction_between(prev, t)
        if d:
            if moves and moves[-1][0] == d:
                moves[-1][1] += 1
            else:
                moves.append([d, 1])
        prev = t
    return ", ".join(f"{d} x{n}" if n > 1 else d for d, n in moves)


def render_l3b(state, image, tile, route_steps=10):
    """Each ghost's current target and the route it will take. Pac-Man is held at `tile`, so this is
    where the ghosts head if he stays put; it does not assume anything about his next move."""
    maze = Maze(image)
    held = _hold_at(state, tile)
    aim = targets(held)
    paths = forecast(held, maze, steps=route_steps)
    lines = ["GHOST AIMS AND ROUTES (if Pac-Man stays at this junction)"]
    for name in GHOST_NAMES:
        if state.eyes[name]:
            continue
        if state.frightened[name]:
            lines.append(f"- {NAMES[name]}: blue, moves at random; no route.")
            continue
        corner = aim[name] == SCATTER_TARGETS[name] and aim[name] != tuple(tile)
        goal = ("its own corner (scatter)" if corner
                else "the tile " + _rel(aim[name][0] - tile[0], aim[name][1] - tile[1]))
        path = paths.get(name)
        route = f"will go {_route(path, tuple(state.ghosts[name].tile))}" if path else "route unknown"
        entry = ""
        if path and tuple(tile) in map(tuple, path):
            entry = f", and passes through this junction in {path.index(tuple(tile)) + 1} moves"
        lines.append(f"- {NAMES[name]}: aiming at {goal}; {route}{entry}.")
    return "\n".join(lines)


def _hold_at(state, tile):
    from dataclasses import replace
    return replace(state, pacman=replace(state.pacman, tile=tuple(tile)))


def build_state_text(level, state, image, facts, tile, arriving, goal_text=None):
    """The `state` string sent to the model for a given rung."""
    if level not in LEVELS:
        raise ValueError(f"unknown level {level}, expected one of {LEVELS}")
    rank = LEVELS.index(level)
    parts = []
    if rank >= 1:
        parts.append(RULES_L1)
    if rank >= 3:
        parts.append(GHOST_BEHAVIOUR_L3A)
    if goal_text:
        parts.append(goal_text)
    parts.append(render_l2(state, image, tile, arriving, facts) if rank >= 2
                 else render_l0(state, tile, arriving))
    if rank >= 4:
        parts.append(render_l3b(state, image, tile))
    return "\n\n".join(parts)


def main():
    import argparse
    from pathlib import Path

    from .features import junction_facts
    from .state import decode

    parser = argparse.ArgumentParser(description="Print what the model would be told, from a RAM image.")
    parser.add_argument("--level", choices=LEVELS, default="L3b")
    default = Path(__file__).resolve().parent / "tests" / "fixtures" / "pacman_play_ram.bin"
    parser.add_argument("--image", default=str(default))
    args = parser.parse_args()
    image = Path(args.image).read_bytes()
    state = decode(image)
    arriving = state.pacman.direction.upper()
    facts = junction_facts(state, image)
    print(build_state_text(args.level, state, image, facts, state.pacman.tile, arriving))


if __name__ == "__main__":
    main()
