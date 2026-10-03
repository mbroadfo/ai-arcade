"""The answer book: questions asked ahead of a decision point, and the answers waiting for it.

A real-time game cannot wait for a model, so a player asks about a decision point before it arrives and uses the stored
answer when it gets there. The book keeps that bookkeeping the same for every game:

- ask(key, ...): send a question unless one for `key` is already answered or on its way. `depth` says how far ahead
  of the player's own position it was asked (a chain of decision points, the game's own idea).
- collect(): answers that have come back. Ordinary answers are stored under their key; urgent ones (a question whose
  answer is worthless a moment later) are handed back and never stored.
- An answer is single-use: use(key) marks it, retire_except(key) drops used ones once the player has moved on, and
  drop_stale() drops any older than `ttl` seconds.
- late_reason(key): why there was no answer on arrival, in a fixed vocabulary.
- Order (a timing choice, never what is chosen): `next_point=True` puts a question at the front of the model's queue
  (the decision point the player is heading to), `spare=True` asks only when nothing is queued (a guess further
  ahead must not delay a real question), and withdraw(keep) drops queued questions no longer on the player's way.

The game decides what a key is (Pac-Man: a junction tile and the direction he arrives from) and what to ask.
"""

LATE_REASONS = ("seen_too_late", "in_flight", "other_arrival", "not_asked")


class AnswerBook:
    def __init__(self, worker, clock, ttl=4.0, urgent_worker=None):
        """worker: an arcadekit.decisions.DecisionWorker (or anything with its submit/pending/take_all/clear_queued).
        urgent_worker: a separate (faster) worker for urgent questions; None = the main worker, at the front."""
        self.worker, self.clock, self.ttl, self.urgent_worker = worker, clock, ttl, urgent_worker
        self.plan = {}  # key -> (Decision, goal, finished_at)
        self.depth = {}  # key -> how far ahead it was asked
        self.consumed = set()  # keys whose answer has been used at their decision point
        self.urgent = set()  # keys asked as urgent questions
        self.counts = {"promoted": 0, "withdrawn": 0, "spare_skipped": 0}

    def has(self, key):
        return key in self.plan

    def get(self, key):
        """(Decision, goal, finished_at) or None."""
        return self.plan.get(key)

    def pending(self, key):
        return self.worker.pending(key) or (self.urgent_worker is not None and self.urgent_worker.pending(key))

    def ask(self, key, goal, facts, depth=0, urgent=False, next_point=False, spare=False):
        """True if the question went out. Not asked again while an answer is stored or on its way (a queued
        next_point question is moved to the front instead)."""
        if urgent:
            worker = self.urgent_worker or self.worker
            if worker.submit(key, goal, facts, urgent=True):
                self.urgent.add(key)
                return True
            return False
        if key in self.plan:
            return False
        if self.worker.pending(key):
            if next_point and hasattr(self.worker, "promote") and self.worker.promote(key):
                self.counts["promoted"] += 1
            return False
        if spare and getattr(self.worker, "queued", lambda: 0)():
            self.counts["spare_skipped"] += 1
            return False
        ordered = next_point and hasattr(self.worker, "promote")  # a worker that keeps an order (DecisionWorker)
        if self.worker.submit(key, goal, facts, **({"front": True} if ordered else {})):
            self.depth[key] = depth
            return True
        return False

    def collect(self):
        """(answers, urgent_answers): each a list of (key, goal, facts, decision, finished_at). Answers are stored."""
        answers, urgent = [], []
        if self.urgent_worker is not None:
            urgent.extend(self.urgent_worker.take_all())
        for item in self.worker.take_all():
            key, goal, facts, decision, finished_at = item
            if key in self.urgent:
                urgent.append(item)
                continue
            self.plan[key] = (decision, goal, finished_at)
            answers.append(item)
        for item in urgent:
            self.urgent.discard(item[0])
        return answers, urgent

    def put(self, key, decision, goal):
        """Store a decision made on the spot (a late default), so it is used like an answer."""
        self.plan[key] = (decision, goal, self.clock())

    def use(self, key):
        self.consumed.add(key)

    def retire_except(self, key):
        """Drop answers already used anywhere other than `key` (the player has moved on). Returns the dropped keys."""
        done = [k for k in self.consumed if k != key]
        for k in done:
            self.plan.pop(k, None)
            self.consumed.discard(k)
        return done

    def drop_stale(self):
        now = self.clock()
        self.plan = {k: p for k, p in self.plan.items() if now - p[2] < self.ttl}

    def forget(self):
        """A life lost or a new game: stored answers no longer apply."""
        self.plan = {}

    def clear_queued(self):
        self.worker.clear_queued()

    def withdraw(self, keep):
        """Drop queued questions whose key fails keep(key) (no longer on the player's way). Returns how many."""
        dropped = self.worker.withdraw(keep) if hasattr(self.worker, "withdraw") else []
        for key in dropped:
            self.depth.pop(key, None)
        self.counts["withdrawn"] += len(dropped)
        return len(dropped)

    def late_reason(self, key, asked_now=False):
        """Why there was no stored answer on arrival. asked_now: this very tick was the first chance to ask (the decision
        point only came into view as the player reached it)."""
        if asked_now:
            return "seen_too_late"
        if self.worker.pending(key):
            return "in_flight"
        if any(k[0] == key[0] for k in self.plan):
            return "other_arrival"
        return "not_asked"
