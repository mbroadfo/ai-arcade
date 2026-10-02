"""What every game reports about how it went: deaths, a record per life lost, boards (levels) finished.

The game feeds it the decoded score, lives and level each frame, plus any running counts of its own to record per life
(Pac-Man: dots eaten in total). Game-specific skills (ghosts eaten, fruit, ...) stay in the game's own stats.
"""


class OutcomeStats:
    def __init__(self):
        self.deaths = self.boards_cleared = 0
        self.life_log = []  # one record per life lost: life, seconds, score earned, each progress count, score_at_end
        self._life = None  # (start time, start score, start progress) of the life in play
        self._prev = None  # (lives, level) last seen

    def update(self, score, lives, level, now=None, progress=None):
        """progress: {name: running total} the game wants recorded per life, e.g. {"dots": 812}."""
        progress = progress or {}
        if self._life is None:
            self._life = (now, score, dict(progress))
        if self._prev is not None:
            prev_lives, prev_level = self._prev
            if level > prev_level:
                self.boards_cleared += 1
            if lives < prev_lives:
                self.deaths += 1
                start_t, start_score, start_progress = self._life
                record = {"life": self.deaths,
                          "seconds": None if now is None or start_t is None else round(now - start_t),
                          "score": score - start_score}
                record.update({k: v - start_progress.get(k, 0) for k, v in progress.items()})
                record["score_at_end"] = score
                self.life_log.append(record)
                self._life = (now, score, dict(progress))
        self._prev = (lives, level)

    def summary(self):
        return {"deaths": self.deaths, "boards_cleared": self.boards_cleared, "lives": list(self.life_log)}
