"""Runs one decider call at a time off the control loop, so slow answers never block steering."""
import threading
import time


class DecisionWorker:
    def __init__(self, decider):
        self.decider = decider
        self.busy = False
        self.result = None  # (key, goal, facts, decision, finished_at)
        self.lock = threading.Lock()

    def submit(self, key, goal, facts):
        with self.lock:
            if self.busy:
                return False
            self.busy = True

        def run():
            decision = self.decider.decide(facts, goal)
            with self.lock:
                self.result = (key, goal, facts, decision, time.time())
                self.busy = False

        threading.Thread(target=run, daemon=True).start()
        return True

    def take(self):
        with self.lock:
            result, self.result = self.result, None
            return result
