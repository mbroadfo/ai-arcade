"""Is the model answering in time? A player that falls back to code when the model is slow must not do it silently.

    health = ModelHealth()
    change = health.record(answered=True)    # "trouble", "recovered" or None: tell the operator when it changes
    if health.trouble: show(health.message())

A model server shared with something else (a game on the same GPU, a training run) slows every answer; each call can then
time out and the player quietly plays its fallback. The operator sees the state from this, in the Observatory.
"""
from collections import deque


class ModelHealth:
    def __init__(self, window=5, threshold=3):
        """Trouble when `threshold` of the last `window` answers did not come in time; clear again when fewer do."""
        self.recent = deque(maxlen=window)
        self.threshold = threshold
        self.trouble = False

    def record(self, answered):
        """Note one answer (True) or one that did not come in time (False). Returns "trouble" or "recovered" when the state
        changes, else None."""
        self.recent.append(bool(answered))
        now = self.misses() >= self.threshold
        changed = now != self.trouble
        self.trouble = now
        return ("trouble" if now else "recovered") if changed else None

    def misses(self):
        return sum(1 for ok in self.recent if not ok)

    def message(self):
        return (f"The model is not answering in time ({self.misses()} of the last {len(self.recent)} plans): the player is on its "
                "fallback. Something else may be using the GPU or the model server.")
