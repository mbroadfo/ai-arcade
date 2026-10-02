"""The survival instinct: overrides the chosen direction when a ghost is about to catch Pac-Man.

Sits above every goal and every decider (rule, model, fallback). It only fires when the chosen way
leads to a normal ghost within DEADLY_STEPS and another way is clearly safer; otherwise it stays quiet
and the goal's choice stands.
"""
DEADLY_STEPS = 4  # a ghost this close along the chosen way is about to catch us (head-on it closes two tiles a tile)
MARGIN = 2  # the safer way must be at least this many steps further from the nearest ghost


def _safety(option):
    threat = option["threat_steps"]
    return (99 if threat is None else threat, option["room"])


def reflex(facts, chosen):
    """Return a safer direction to override `chosen`, or None to let it stand."""
    options = facts["options"]
    if chosen not in options:
        return None
    threat = options[chosen]["threat_steps"]
    if threat is None or threat > DEADLY_STEPS:
        return None
    best = max(options, key=lambda d: _safety(options[d]))
    if best == chosen or _safety(options[best])[0] < threat + MARGIN:
        return None
    return best
