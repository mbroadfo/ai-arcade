"""Turn decoded Pac-Man state into compact structured facts for a decision model.

The model never plans routes (a single forward pass can't). Code does the geometry; the model
makes the judgment call: which way, given the current goal.
"""
from .goals import GOALS, WEIGHTS, scaled_weights, stance_text  # noqa: F401  (GOALS re-exported for deciders)
from .maze import ENERGIZER, LOWER_TO_UPPER, MOVES, OPPOSITE, Maze, step
from .park import hover_stop, nearest_energizer

ROOM_RADIUS = 8
GHOST_PACE = 0.5  # a blue ghost moves about half as fast as Pac-Man: it covers this many tiles per tile he covers


def ghost_modes(state):
    return {
        name: "eyes" if state.eyes[name] else "frightened" if state.frightened[name] else "normal"
        for name in state.ghosts
    }


def intercept_tile(maze, ghost, distance):
    """Where a blue ghost will probably be when Pac-Man gets there: on along its heading, a tile for every
    1/GHOST_PACE tiles Pac-Man still has to cover. Stops at a wall (the ghost turns there, we cannot know where)."""
    heading = LOWER_TO_UPPER.get(ghost.direction)
    tile = ghost.tile
    for _ in range(round(distance * GHOST_PACE)):
        nxt = step(tile, heading) if heading else tile
        if not maze.passable(nxt):
            break
        tile = nxt
    return tile


def option_facts(maze, state, modes, tile, direction, stop=None):
    """Facts about leaving `tile` in `direction`."""
    nxt = step(tile, direction)
    if not maze.passable(nxt):
        return None
    dist = maze.bfs(nxt, blocked=frozenset([tile]))
    food = [d for t, d in dist.items() if maze.has_food(t)]
    threats = [dist[g.tile] + 1 for name, g in state.ghosts.items()
               if modes[name] == "normal" and g.tile in dist]
    edible = []
    for name, g in state.ghosts.items():
        if modes[name] == "frightened" and g.tile in dist:
            meet = intercept_tile(maze, g, dist[g.tile])
            edible.append(dist.get(meet, dist[g.tile]) + 1)
    energizers = [d for t, d in dist.items() if maze.code(t) == ENERGIZER]
    fruit = dist.get(tuple(state.fruit_tile)) if state.fruit_tile else None
    return {
        "edible_count": sum(1 for d in edible if d <= GROUP_REACH),
        "stop_steps": dist[stop] + 1 if stop in dist else None,  # the wall-stop tile near the energizer (--park)
        "food_steps": min(food) + 1 if food else None,
        "energizer_steps": min(energizers) + 1 if energizers else None,
        "fruit_steps": fruit + 1 if fruit is not None else None,
        "threat_steps": min(threats) if threats else None,
        "edible_steps": min(edible) if edible else None,
        "room": sum(1 for d in dist.values() if d <= ROOM_RADIUS),
    }


def junction_facts(state, image, tile=None, arriving=None, park=False):
    """Structured facts for choosing a direction at `tile` (default: Pac-Man's current tile).
    park: waiting near an energizer is in play (park.py), so options say how far the wall-stop tile to wait at is."""
    maze = Maze(image)
    tile = tile or state.pacman.tile
    arriving = arriving or LOWER_TO_UPPER.get(state.pacman.direction)
    modes = ghost_modes(state)

    stop = None
    if park:
        pellet = nearest_energizer(maze, maze.bfs(tile))
        found = hover_stop(maze, pellet) if pellet else None
        stop = found[0] if found else None
    options = {}
    for direction in MOVES:
        facts = option_facts(maze, state, modes, tile, direction, stop)
        if facts is not None:
            facts["reverse"] = direction == OPPOSITE.get(arriving)
            options[direction] = facts

    here = maze.bfs(tile)
    close = [here[g.tile] for n, g in state.ghosts.items() if modes[n] == "normal" and g.tile in here]
    pressure = min(close) if close else None  # steps to the nearest normal ghost, any direction
    ghosts_close = sum(1 for d in close if d <= LURE_RADIUS)  # normal ghosts near enough to be caught in a feast
    for o in options.values():
        o["pressure"] = pressure
        o["ghosts_close"] = ghosts_close
    ghosts = [{
        "name": name,
        "mode": modes[name],
        "steps": here.get(g.tile),
        "heading": LOWER_TO_UPPER.get(g.direction, "?"),
    } for name, g in state.ghosts.items()]

    here_fruit = here.get(tuple(state.fruit_tile)) if state.fruit_tile else None
    return {
        "fruit_steps": here_fruit,
        "tile": list(tile),
        "arriving": arriving,
        "options": options,
        "ghosts": ghosts,
        "food_left": maze.food_left(),
        "lives": state.lives,
        "level": state.level,
    }


def threat_distance(state, image):
    """Graph steps from Pac-Man to the nearest normal-mode ghost, or None."""
    maze = Maze(image)
    modes = ghost_modes(state)
    here = maze.bfs(state.pacman.tile)
    steps = [here[g.tile] for name, g in state.ghosts.items() if modes[name] == "normal" and g.tile in here]
    return min(steps) if steps else None


def render_text(facts, goal, name):
    """Compact text rendering of the facts for a System One model (small context budgets). name: the player's."""
    lines = [f"GOAL: {goal} - {GOALS[goal]}", *([facts["stance"]] if facts.get("stance") else []),
             f"{name} heading {facts['arriving']}. Food left {facts['food_left']}. Lives {facts['lives']}."]
    for direction, o in facts["options"].items():
        lines.append(
            f"{direction}{' (reverse)' if o['reverse'] else ''}: "
            f"food in {o['food_steps']} steps, threat in {o['threat_steps']}, "
            f"edible ghost in {o['edible_steps']}, fruit in {o.get('fruit_steps')}, room {o['room']}")
    if facts.get("fruit_steps") is not None:
        lines.append(f"bonus fruit on screen, {facts['fruit_steps']} steps away")
    for g in facts["ghosts"]:
        where = "in the ghost house" if g["steps"] is None else f"{g['steps']} steps away"
        lines.append(f"ghost {g['name']} {g['mode']} {where}, heading {g['heading']}")
    return "\n".join(lines)


THREAT_HORIZON = 7
ROOM_PRESSURE = 12  # open room only matters when a normal ghost is this close (steps)
LURE_RADIUS = 9  # ambush: eat the energizer when 2+ normal ghosts are this close (or 1 within LURE_PANIC)
LURE_PANIC = 4
HOVER_STEPS = 4  # ambush: wait about this many steps from the energizer until the ghosts have closed in
FOOD_REACH = 45  # food pull is linear in distance up to this, so far-away dots still attract
GROUP_REACH = 16  # blue ghosts within this many steps down an exit count as the group that way
CHASE_REACH = 40  # a blue ghost's pull is linear up to this many steps: every step closer is worth the same
GROUP_BONUS = 1.5  # per extra blue ghost down an exit (a feast's later ghosts are worth 400, 800, 1600)
HUNT_TURN_BACK = 1.2  # while hunting, reversing needs a clear gain: dithering between two routes loses the ghost


def food_pull(steps):
    """Strictly decreasing in distance everywhere: near dots count most, far dots still beat no progress."""
    return 3.0 / (1 + steps) + 0.04 * (FOOD_REACH - min(steps, FOOD_REACH))


def chase_pull(steps):
    """Strictly decreasing in distance, steeply: the shortest route to the ghost always wins."""
    return 6.0 / (1 + steps) + 0.12 * (CHASE_REACH - min(steps, CHASE_REACH))


def park_pull(steps):
    """Ambush: head for the wall-stop tile near the energizer (see park.py); strictly nearer is better."""
    return 4.0 / (1 + steps) + 0.1 * (30 - min(steps, 30))


def ready_to_eat(option):
    """Ghosts have gathered close enough: go and eat the energizer."""
    pressure = option.get("pressure")
    return option.get("ghosts_close", 0) >= 2 or (pressure is not None and pressure <= LURE_PANIC)


def lure_score(option):
    """Ambush: close in on an energizer and wait, then eat it once ghosts have gathered close behind.
    With a wall-stop tile to wait at (--park), go there and hold, instead of pacing near the energizer."""
    es = option.get("energizer_steps")
    if ready_to_eat(option):
        return 0.0 if es is None else 8.0 / (1 + es)  # go and eat it now
    if option.get("stop_steps") is not None:
        return park_pull(option["stop_steps"])
    if es is None:
        return 0.0
    if es > HOVER_STEPS:
        return 3.0 * 3.0 / (1 + es)  # approach
    return -1.5 * (HOVER_STEPS + 1 - es)  # too close to eat it yet: hold back, ghosts still on their way


def score_option(goal, option, mods=None):
    """Heuristic desirability of one option. Shared by the rule decider and the mock model.
    mods: the stance (goals.STANCE levels) set by the slow layer, or None."""
    w_food, w_threat, w_room, w_edible, w_fruit, w_energizer, w_lure = scaled_weights(goal, mods)
    score = 0.0
    if option["food_steps"] is not None:
        score += w_food * food_pull(option["food_steps"])
    if option["threat_steps"] is not None and option["threat_steps"] < THREAT_HORIZON:
        score -= w_threat * (THREAT_HORIZON - option["threat_steps"]) / 2.0
    pressure = option.get("pressure")
    if pressure is not None and pressure <= ROOM_PRESSURE:  # no ghost near: where there is room is irrelevant
        score += w_room * min(option["room"], 30) / 30.0 * 3.0
    if option["edible_steps"] is not None:
        score += w_edible * (chase_pull(option["edible_steps"]) if w_edible > 0 else 4.0 / (1 + option["edible_steps"]))
        score += w_edible * GROUP_BONUS * max(option.get("edible_count", 1) - 1, 0)  # the way to the group beats the way to one
    if option.get("fruit_steps") is not None:
        score += w_fruit * 4.0 / (1 + option["fruit_steps"])
    if w_energizer and option.get("energizer_steps") is not None and option["edible_steps"] is None:
        score += w_energizer * 3.0 / (1 + option["energizer_steps"])
    if w_lure:
        score += w_lure * lure_score(option)
    if option["reverse"]:
        score -= HUNT_TURN_BACK if goal == "hunt_ghosts" and option["edible_steps"] is not None else 0.3
    return score
