"""Who made each move: one record per executed decision, in a vocabulary every game shares.

`by` is fixed here and a game cannot add to it, so "the model's own %" means the same in every game:

    model          the model's answer, executed as given                       (the model's own)
    rule           the rule decider, in a control run
    code-late      no answer in time; the late default decided
    code-fallback  the model failed or was unsure; code decided
    code-override  the model (or rule) proposed, code changed it
    code-skill     a code skill steered on its own

`via` names the question or helper (junction, danger, reflex, revise, park, refuge, ...); a game may add its own.
Mechanical moves (a single way on, coin, start) are not booked. See docs/GAME_WORKSHOP.md.
"""

BY = ("model", "rule", "code-late", "code-fallback", "code-override", "code-skill")

# labels written before the ledger (runs up to v15), so old logs can be read with new tools
OLD_LABELS = {"model": ("model", "junction"), "model-danger": ("model", "danger"), "rule": ("rule", "junction"),
              "code-late": ("code-late", "junction"), "code-fallback": ("code-fallback", "junction"),
              "reflex-override": ("code-override", "reflex"), "code-revise": ("code-override", "revise"),
              "code-hold": ("code-skill", "hold")}

# a decider's Decision.source -> by, when code did not step in
SOURCE_BY = {"model": "model", "rule": "rule", "fallback": "code-fallback"}


class Ledger:
    """log: a callable taking keyword fields (the game's decisions log). counts: (by, via) -> moves."""

    def __init__(self, log):
        self.log, self.counts = log, {}

    def book(self, by, via, **record):
        if by not in BY:
            raise ValueError(f"unknown by {by!r}: one of {BY}")
        self.counts[(by, via)] = self.counts.get((by, via), 0) + 1
        self.log(event="move", by=by, via=via, **record)

    def count(self, by, via):
        """Count a move without a log line (for a helper that writes its own event)."""
        if by not in BY:
            raise ValueError(f"unknown by {by!r}: one of {BY}")
        self.counts[(by, via)] = self.counts.get((by, via), 0) + 1

    def by(self):
        out = {}
        for (by, _), n in self.counts.items():
            out[by] = out.get(by, 0) + n
        return out

    def total(self):
        return sum(self.counts.values())

    def model_share(self):
        """The model's own moves as a fraction of all booked moves (None before any)."""
        total = self.total()
        return None if not total else self.by().get("model", 0) / total

    def summary(self):
        """Printable: each by/via with its count, most first, and the model's own %."""
        total = self.total()
        if not total:
            return "no booked moves"
        parts = ", ".join(f"{by} ({via}) {n}" for (by, via), n in sorted(self.counts.items(), key=lambda kv: -kv[1]))
        return f"moves by who executed them ({total}): {parts}. The model's own: {100 * self.model_share():.0f}%."
