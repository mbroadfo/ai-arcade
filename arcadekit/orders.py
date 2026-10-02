"""Standing orders: what the operator tells the model, in their own words, for as long as they stand.

The orders are text added to every question a model is asked (the game's decider, the slow layer's goal and stance,
any other model a game asks): OrderedClient wraps a System One client and puts them in front of each question's
instructions.
No code reads them: whether the model follows them, and whether that helps, is what a run measures. A rule decider or a
mock model never sees them, so those stay controls.

They are set at the start (play.py --orders) and changed during a run from the Observatory. Every change is logged as an
`orders` event with its version, and each answer records the version its question was asked under, so a run can be
split by the orders in force.
"""
import threading
import time

MAX_ORDERS = 10
MAX_LENGTH = 300  # characters per order
HEADER = "Standing orders from the operator:"


def clean(items):
    """Trimmed, non-empty, at most MAX_ORDERS orders of at most MAX_LENGTH characters."""
    out = []
    for item in items or ():
        text = " ".join(str(item).split())[:MAX_LENGTH]
        if text and text not in out:
            out.append(text)
    return out[:MAX_ORDERS]


def render(items):
    return HEADER + "".join(f"\n- {item}" for item in items) if items else ""


class Orders:
    def __init__(self, initial=(), clock=time.time):
        self.clock = clock
        self.lock = threading.Lock()
        self.items = clean(initial)
        self.version = 1 if self.items else 0
        self.history = [{"version": self.version, "orders": list(self.items), "source": "start", "t": round(clock(), 3)}]
        self.asked = {}  # version -> questions asked under it
        self.last = {}  # asker -> the last request exactly as sent (for the Observatory)
        self.log = None  # set by play.py to the player's log, so changes land in the decisions log

    def set(self, items, source="operator"):
        """Replace the orders. Returns the new version, or None if nothing changed."""
        items = clean(items)
        with self.lock:
            if items == self.items:
                return None
            self.items, self.version = items, self.version + 1
            record = {"version": self.version, "orders": list(items), "source": source, "t": round(self.clock(), 3)}
            self.history.append(record)
        if self.log:
            self.log(event="orders", version=record["version"], orders=record["orders"], source=source)
        return record["version"]

    def snapshot(self):
        with self.lock:
            return self.version, list(self.items)

    def count(self, version):
        with self.lock:
            self.asked[version] = self.asked.get(version, 0) + 1

    def record(self, asker, state, questions, version):
        """Keep the request as sent; the returned record gets the answer when it comes."""
        with self.lock:
            sent = {"asker": asker, "state": state, "questions": questions, "orders": version,
                    "t": round(self.clock(), 3)}
            self.last[asker] = sent
            return sent

    def latest(self):
        """The most recent request each asker sent, newest first."""
        with self.lock:
            return [dict(r) for r in sorted(self.last.values(), key=lambda r: -r["t"])]

    def summary(self):
        return {"history": self.history, "questions_by_version": {str(k): v for k, v in sorted(self.asked.items())}}


class OrderedClient:
    """A System One client that puts the standing orders in front of every question's instructions.
    asker: who is asking (e.g. "decisions"), for the Observatory's view of what each was asked."""

    def __init__(self, client, orders, asker="model"):
        self.client, self.orders, self.asker = client, orders, asker

    def ask(self, state, questions, hint=None):
        version, items = self.orders.snapshot()
        self.orders.count(version)
        if items:
            preface = render(items)
            questions = {name: {**q, "instructions": f"{preface}\n\n{q['instructions']}"} for name, q in questions.items()}
        sent = self.orders.record(self.asker, state, questions, version)
        reply = self.client.ask(state, questions, hint=hint)
        reply["orders_version"] = version
        sent["answer"] = {name: {"choice": a.get("choice"), "confidence": a.get("confidence")}
                          for name, a in reply.get("answers", {}).items()}
        sent["latency_ms"] = round(reply.get("latency_ms") or 0)
        return reply

    def __getattr__(self, name):  # model name, host and the like, for whoever reads them
        return getattr(self.client, name)
