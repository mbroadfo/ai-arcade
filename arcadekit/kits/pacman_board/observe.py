"""What the Observatory shows of a game on Pac-Man's board: facts read from the state, for people watching.

Display only: nothing here decides, and the player never reads it. The dashboard knows no game; it draws these as
labelled values (facts) and lines over time (series). What the model was asked is captured where it is sent
(arcadekit.orders.OrderedClient), so it is exact for every game.
"""
from .maze import Maze


def facts(state, image, steps):
    """[{label, value, tone}]: what is going on now. tone: "bad", "good", "warn" or None (how the page colours it)."""
    maze = Maze(image)
    blue = [n for n in state.ghosts if state.frightened[n] and not state.eyes[n]]
    eyes = [n for n in state.ghosts if state.eyes[n]]
    out = [
        {"label": "phase", "value": "chase" if state.phase % 2 else "scatter", "tone": "warn" if state.phase % 2 else None},
        {"label": "blue ghosts", "value": len(blue), "tone": "good" if blue else None},
        {"label": "food left", "value": maze.food_left(), "tone": None},
        {"label": "energizers", "value": maze.energizers_left(), "tone": None},
    ]
    if eyes:
        out.append({"label": "eyes going home", "value": len(eyes), "tone": None})
    if state.elroy:
        out.append({"label": "Blinky", "value": "Cruise Elroy (faster)", "tone": "bad"})
    if state.fruit_tile:
        out.append({"label": "fruit", "value": f"{steps.get(state.fruit_tile, '?')} steps", "tone": "good"})
    return out


def series(state, steps):
    """[{key, label, value, unit, worse, alarm, colour}]: numbers worth watching over time. worse: "low" or "high" (or
    None); alarm: the value past which (in the worse direction) the page marks the line."""
    normal = [steps[g.tile] for n, g in state.ghosts.items()
              if not state.frightened[n] and not state.eyes[n] and g.tile in steps]
    blue = [steps[g.tile] for n, g in state.ghosts.items()
            if state.frightened[n] and not state.eyes[n] and g.tile in steps]
    return [
        {"key": "threat", "label": "nearest ghost", "value": min(normal) if normal else None, "unit": "steps",
         "worse": "low", "alarm": 8, "colour": "#ff8aa8"},
        {"key": "prey", "label": "nearest blue ghost", "value": min(blue) if blue else None, "unit": "steps", "worse": None,
         "colour": "#5b7bff"},
        {"key": "score", "label": "score", "value": state.score, "unit": "", "worse": None},
    ]
