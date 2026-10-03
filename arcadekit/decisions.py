"""Decisions: what a decider returns, asking a model one choice question, and answering off the control loop.

Decision        one answer: the choice, who made it (source), confidence, latency
ChoiceDecider   asks a System One model a choice question built by the game; the game's fallback decides when the model
                fails or is unsure (source "fallback"), so a player is never left without an answer
DecisionWorker  runs decider calls on threads, so slow answers never block steering. Requests queue up and are answered
                in order; a key that is already queued, running, or waiting to be taken is not accepted twice.
"""
import threading
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class Decision:
    choice: str  # one of the options asked about, in the game's own terms (Pac-Man: "UP", "LEFT", ...)
    source: str  # "model", "rule" (a rule decider: the control), "fallback" (the model failed or was unsure)
    confidence: float = 1.0
    latency_ms: float = 0.0
    probabilities: dict = field(default_factory=dict)
    note: str = ""
    orders: int = None  # the standing orders' version the model was asked under (arcadekit.orders), if any


class ChoiceDecider:
    """question(facts, goal) -> (state_text, instructions, {option: description}), supplied by the game.
    fallback: a decider with the same decide(facts, goal), used when the model errs or is below min_confidence."""

    def __init__(self, client, question, fallback, min_confidence=0.0, name="choice"):
        self.client, self.question, self.fallback = client, question, fallback
        self.min_confidence, self.name = min_confidence, name

    def _fallback(self, facts, goal, note, latency_ms=0.0):
        decision = self.fallback.decide(facts, goal)
        decision.source, decision.note, decision.latency_ms = "fallback", note, latency_ms
        return decision

    def decide(self, facts, goal):
        text, instructions, criteria = self.question(facts, goal)
        questions = {self.name: {"type": "choice", "instructions": instructions, "criteria": criteria}}
        try:
            reply = self.client.ask(text, questions, hint=dict(facts, goal=goal))
        except Exception as exc:  # model down or slow: never leave the player without a decision
            return self._fallback(facts, goal, f"model error: {exc}")
        answer = reply["answers"][self.name]
        if answer["confidence"] < self.min_confidence:
            decision = self._fallback(facts, goal, f"low confidence {answer['confidence']:.2f}", reply["latency_ms"])
        else:
            decision = Decision(answer["choice"], "model", answer["confidence"], reply["latency_ms"],
                                answer["probabilities"])
        decision.orders = reply.get("orders_version")
        return decision


class DecisionWorker:
    def __init__(self, decider, threads=1, max_queue=6):
        self.decider, self.max_queue = decider, max_queue
        self.queue, self.keys, self.done = deque(), set(), []
        self.active = 0  # questions being answered right now
        self.cond = threading.Condition()
        for _ in range(threads):
            threading.Thread(target=self._loop, daemon=True).start()

    def submit(self, key, goal, facts, urgent=False, front=False):
        """Queue a request. False if the key is already known or the queue is full.
        urgent: goes to the front (and is accepted even when the queue is full), for questions whose answer is
        worthless a moment later. front: goes to the front too (the decision point the player is heading to)."""
        with self.cond:
            if key in self.keys or (len(self.queue) >= self.max_queue and not (urgent or front)):
                return False
            self.keys.add(key)
            (self.queue.appendleft if urgent or front else self.queue.append)((key, goal, facts))
            self.cond.notify()
            return True

    def promote(self, key):
        """Move a queued (not started) request to the front. True if it moved (False if not queued or already first)."""
        with self.cond:
            for i, item in enumerate(self.queue):
                if item[0] == key:
                    if i == 0:
                        return False
                    del self.queue[i]
                    self.queue.appendleft(item)
                    return True
            return False

    def withdraw(self, keep):
        """Drop queued (not started) requests whose key fails keep(key). Returns the dropped keys."""
        with self.cond:
            dropped = [item[0] for item in self.queue if not keep(item[0])]
            if dropped:
                self.queue = deque(item for item in self.queue if keep(item[0]))
                self.keys.difference_update(dropped)
            return dropped

    def queued(self):
        with self.cond:
            return len(self.queue)

    def pending(self, key):
        with self.cond:
            return key in self.keys

    def _loop(self):
        while True:
            with self.cond:
                while not self.queue:
                    self.cond.wait()
                key, goal, facts = self.queue.popleft()
                self.active += 1
            decision = self.decider.decide(facts, goal)
            with self.cond:
                self.active -= 1
                self.done.append((key, goal, facts, decision, time.time()))

    def busy(self):
        """True while a question waits or is being answered (another layer sharing the model server can wait)."""
        with self.cond:
            return bool(self.queue) or self.active > 0

    def take_all(self):
        """Finished results since the last call: [(key, goal, facts, decision, finished_at)]."""
        with self.cond:
            out, self.done = self.done, []
            for item in out:
                self.keys.discard(item[0])
            return out

    def clear_queued(self):
        """Drop requests that have not started (a new game or life makes them meaningless)."""
        with self.cond:
            for key, _, _ in self.queue:
                self.keys.discard(key)
            self.queue.clear()
