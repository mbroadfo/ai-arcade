import threading
import time

from decision_worker import DecisionWorker


class Decider:
    """Records the order requests were answered in; each takes `delay` seconds."""

    def __init__(self, delay=0.0):
        self.delay, self.seen = delay, []

    def decide(self, facts, goal):
        time.sleep(self.delay)
        self.seen.append(facts)
        return f"answer-{facts}"


def wait_for(worker, count, timeout=3.0):
    got, deadline = [], time.time() + timeout
    while len(got) < count and time.time() < deadline:
        got += worker.take_all()
        time.sleep(0.005)
    return got


def test_requests_are_answered_in_order():
    worker = DecisionWorker(Decider(0.01))
    for n in range(4):
        assert worker.submit(("j", n), "goal", n)
    got = wait_for(worker, 4)
    assert [item[0] for item in got] == [("j", n) for n in range(4)]
    assert got[2][3] == "answer-2"


def test_a_key_is_accepted_once_until_its_answer_is_taken():
    worker = DecisionWorker(Decider(0.05))
    assert worker.submit("k", "goal", 1)
    assert not worker.submit("k", "goal", 1)  # queued or running
    assert worker.pending("k")
    wait_for(worker, 1)
    assert not worker.pending("k")
    assert worker.submit("k", "goal", 2)  # taken: may be asked again


def test_queue_is_bounded_and_can_be_cleared():
    gate = threading.Event()

    class Blocked:
        def decide(self, facts, goal):
            gate.wait(2)
            return facts

    worker = DecisionWorker(Blocked(), max_queue=2)
    assert worker.submit("running", "g", 0)
    time.sleep(0.05)  # the thread has taken it off the queue
    assert worker.submit("a", "g", 1) and worker.submit("b", "g", 2)
    assert not worker.submit("c", "g", 3)  # queue full
    worker.clear_queued()
    assert worker.submit("c", "g", 3)
    gate.set()
    keys = {item[0] for item in wait_for(worker, 2)}
    assert "running" in keys and "a" not in keys
