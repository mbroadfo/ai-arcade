"""Runs decider calls off the control loop, so slow answers never block steering.

Requests queue up and are answered in order by `threads` worker threads. A key that is already queued,
running, or waiting to be taken is not accepted twice.
"""
import threading
import time
from collections import deque


class DecisionWorker:
    def __init__(self, decider, threads=1, max_queue=6):
        self.decider, self.max_queue = decider, max_queue
        self.queue, self.keys, self.done = deque(), set(), []
        self.cond = threading.Condition()
        for _ in range(threads):
            threading.Thread(target=self._loop, daemon=True).start()

    def submit(self, key, goal, facts, urgent=False):
        """Queue a request. False if the key is already known or the queue is full.
        urgent: goes to the front (and is accepted even when the queue is full), for questions whose answer is
        worthless a moment later."""
        with self.cond:
            if key in self.keys or (len(self.queue) >= self.max_queue and not urgent):
                return False
            self.keys.add(key)
            (self.queue.appendleft if urgent else self.queue.append)((key, goal, facts))
            self.cond.notify()
            return True

    def pending(self, key):
        with self.cond:
            return key in self.keys

    def _loop(self):
        while True:
            with self.cond:
                while not self.queue:
                    self.cond.wait()
                key, goal, facts = self.queue.popleft()
            decision = self.decider.decide(facts, goal)
            with self.cond:
                self.done.append((key, goal, facts, decision, time.time()))

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
