"""The danger query: the one choice a corridor offers (carry on or turn back) goes to the model when a ghost is close.

In a corridor the model is normally never asked anything: it decides at junctions, and nothing could turn Pac-Man round in
between except the survival reflex (code). A human decides to turn back mid-corridor the moment they see a ghost coming. So
when a ghost is near, the corridor choice is asked as a fast, urgent question with the threat data (steps, which way it
comes from, room each way) and the model's answer is executed. Code only decides *when to ask* (a ghost within range along
the way ahead, or close behind) and drops answers that arrive too late to matter. Switch: `--danger-query`.
"""
from .maze import OPPOSITE

AHEAD_RANGE = 8  # ask when a normal ghost is this many steps away along the way ahead ...
BEHIND_RANGE = 3  # ... or this close behind
ASK_EVERY = 0.12  # seconds between questions while the danger lasts (the previous one must have come back)
MAX_AGE = 0.4  # seconds: an answer older than this is dropped, the situation has moved on
MAX_DRIFT = 2  # ... and so is one for a spot more than this many tiles from where it was asked


def corridor_options(facts, heading):
    """The two real choices in a plain corridor: carry on `heading` or turn back. None at a junction or a corner."""
    options = facts["options"]
    back = OPPOSITE[heading]
    if heading not in options or back not in options or len(options) != 2:
        return None
    return {heading: options[heading], back: options[back]}


def in_danger(options, heading):
    """A ghost is close enough to ask about: ahead within range, or just behind."""
    ahead = options[heading]["threat_steps"]
    behind = options[OPPOSITE[heading]]["threat_steps"]
    return (ahead is not None and ahead <= AHEAD_RANGE) or (behind is not None and behind <= BEHIND_RANGE)


def danger_facts(facts, heading):
    """`facts` (for Pac-Man's own tile) cut down to the corridor choice and marked as a danger question, or None."""
    options = corridor_options(facts, heading)
    if options is None or not in_danger(options, heading):
        return None
    return dict(facts, options=options, danger=True)
