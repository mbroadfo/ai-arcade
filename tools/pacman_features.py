"""Turn decoded Pac-Man state into compact structured facts for a decision model.

The model never plans routes (a single forward pass can't). Code does the geometry; the model
makes the judgment call: which way, given the current goal.
"""
from pacman_maze import LOWER_TO_UPPER, MOVES, OPPOSITE, Maze, step

GOALS = {
    "clear_dots": "Eat all the dots. Prefer the direction with the nearest food, unless a ghost threatens it.",
    "avoid_ghosts": "Survive first. Prefer the direction away from threatening ghosts with the most open room.",
    "hunt_ghosts": "Blue ghosts are edible right now. Prefer the direction toward the nearest blue ghost; avoid others.",
}
ROOM_RADIUS = 8


def ghost_modes(state):
    return {
        name: "eyes" if state.eyes[name] else "frightened" if state.frightened[name] else "normal"
        for name in state.ghosts
    }


def option_facts(maze, state, modes, tile, direction):
    """Facts about leaving `tile` in `direction`."""
    nxt = step(tile, direction)
    if not maze.passable(nxt):
        return None
    dist = maze.bfs(nxt, blocked=frozenset([tile]))
    food = [d for t, d in dist.items() if maze.has_food(t)]
    threats = [dist[g.tile] + 1 for name, g in state.ghosts.items()
               if modes[name] == "normal" and g.tile in dist]
    edible = [dist[g.tile] + 1 for name, g in state.ghosts.items()
              if modes[name] == "frightened" and g.tile in dist]
    return {
        "food_steps": min(food) + 1 if food else None,
        "threat_steps": min(threats) if threats else None,
        "edible_steps": min(edible) if edible else None,
        "room": sum(1 for d in dist.values() if d <= ROOM_RADIUS),
    }


def junction_facts(state, image, tile=None, arriving=None):
    """Structured facts for choosing a direction at `tile` (default: Pac-Man's current tile)."""
    maze = Maze(image)
    tile = tile or state.pacman.tile
    arriving = arriving or LOWER_TO_UPPER.get(state.pacman.direction)
    modes = ghost_modes(state)

    options = {}
    for direction in MOVES:
        facts = option_facts(maze, state, modes, tile, direction)
        if facts is not None:
            facts["reverse"] = direction == OPPOSITE.get(arriving)
            options[direction] = facts

    here = maze.bfs(tile)
    ghosts = [{
        "name": name,
        "mode": modes[name],
        "steps": here.get(g.tile),
        "heading": LOWER_TO_UPPER.get(g.direction, "?"),
    } for name, g in state.ghosts.items()]

    return {
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


def render_text(facts, goal):
    """Compact text rendering of the facts for a System One model (small context budgets)."""
    lines = [f"GOAL: {goal} - {GOALS[goal]}",
             f"Pac-Man heading {facts['arriving']}. Food left {facts['food_left']}. Lives {facts['lives']}."]
    for direction, o in facts["options"].items():
        lines.append(
            f"{direction}{' (reverse)' if o['reverse'] else ''}: "
            f"food in {o['food_steps']} steps, threat in {o['threat_steps']}, "
            f"edible ghost in {o['edible_steps']}, room {o['room']}")
    for g in facts["ghosts"]:
        where = "in the ghost house" if g["steps"] is None else f"{g['steps']} steps away"
        lines.append(f"ghost {g['name']} {g['mode']} {where}, heading {g['heading']}")
    return "\n".join(lines)


GOAL_WEIGHTS = {  # food, threat, room, edible
    "clear_dots": (1.0, 1.6, 0.25, 0.0),
    "avoid_ghosts": (0.2, 2.4, 0.6, 0.0),
    "hunt_ghosts": (0.3, 1.4, 0.2, 1.4),
}
THREAT_HORIZON = 7


def score_option(goal, option):
    """Heuristic desirability of one option. Shared by the rule decider and the mock model."""
    w_food, w_threat, w_room, w_edible = GOAL_WEIGHTS[goal]
    score = 0.0
    if option["food_steps"] is not None:
        score += w_food * 3.0 / (1 + option["food_steps"])
    if option["threat_steps"] is not None and option["threat_steps"] < THREAT_HORIZON:
        score -= w_threat * (THREAT_HORIZON - option["threat_steps"]) / 2.0
    score += w_room * min(option["room"], 30) / 30.0 * 3.0
    if option["edible_steps"] is not None:
        score += w_edible * 4.0 / (1 + option["edible_steps"])
    if option["reverse"]:
        score -= 0.3
    return score
