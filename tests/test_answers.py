from arcadekit.answers import AnswerBook
from arcadekit.decisions import Decision


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


class Worker:
    """Answers on the next take_all(); remembers what is in flight."""

    def __init__(self, choice="UP"):
        self.choice, self.done, self.keys, self.cleared = choice, [], set(), 0

    def submit(self, key, goal, facts, urgent=False):
        if key in self.keys:
            return False
        self.keys.add(key)
        self.done.append((key, goal, facts, Decision(self.choice, "model"), 100.0))
        return True

    def pending(self, key):
        return key in self.keys

    def take_all(self):
        out, self.done = self.done, []
        for item in out:
            self.keys.discard(item[0])
        return out

    def clear_queued(self):
        self.cleared += 1


def test_a_question_is_not_asked_again_while_answered_or_on_its_way():
    book = AnswerBook(Worker(), Clock())
    assert book.ask("A", "g", {}) and not book.ask("A", "g", {})  # on its way
    book.collect()
    assert book.has("A") and not book.ask("A", "g", {})  # answered
    assert book.get("A")[0].choice == "UP" and book.depth["A"] == 0


def test_an_answer_is_used_once_and_retired_when_the_player_moves_on():
    book = AnswerBook(Worker(), Clock())
    book.ask("A", "g", {})
    book.ask("B", "g", {}, depth=1)
    book.collect()
    book.use("A")
    assert book.retire_except("A") == [] and book.has("A")  # still at A
    assert book.retire_except("B") == ["A"] and not book.has("A") and book.has("B")


def test_answers_older_than_the_ttl_are_dropped():
    clock = Clock()
    book = AnswerBook(Worker(), clock, ttl=4.0)
    book.ask("A", "g", {})
    book.collect()  # finished at 100.0
    clock.now = 103.9
    book.drop_stale()
    assert book.has("A")
    clock.now = 104.0
    book.drop_stale()
    assert not book.has("A")


def test_urgent_answers_are_handed_back_not_stored_and_can_use_their_own_worker():
    main, fast = Worker(), Worker("DOWN")
    book = AnswerBook(main, Clock())
    assert book.ask("danger", "g", {}, urgent=True)
    answers, urgent = book.collect()
    assert answers == [] and [u[0] for u in urgent] == ["danger"] and not book.has("danger")
    book = AnswerBook(main, Clock(), urgent_worker=fast)
    book.ask("danger", "g", {}, urgent=True)
    assert fast.pending("danger") and not main.pending("danger")
    assert book.collect()[1][0][3].choice == "DOWN"


def test_late_reasons():
    book = AnswerBook(Worker(), Clock())
    key = ((1, 2), "UP")
    assert book.late_reason(key, asked_now=True) == "seen_too_late"
    assert book.late_reason(key) == "not_asked"
    book.ask(((1, 2), "LEFT"), "g", {})
    assert book.late_reason(((1, 2), "LEFT")) == "in_flight"
    book.collect()
    assert book.late_reason(key) == "other_arrival"  # answered, but for another arriving direction


def test_forget_and_a_late_default_stored_like_an_answer():
    book = AnswerBook(Worker(), Clock())
    book.put("A", Decision("LEFT", "rule"), "g")
    assert book.get("A")[0].choice == "LEFT" and book.get("A")[2] == 100.0
    book.forget()
    assert not book.has("A")
    book.clear_queued()
    assert book.worker.cleared == 1


class Gate:
    """A decider that answers only when let through, so the queue can be inspected while one question is out."""

    def __init__(self):
        import threading
        self.go, self.seen = threading.Event(), []

    def decide(self, facts, goal):
        from arcadekit.decisions import Decision
        self.seen.append(facts)
        self.go.wait(2)
        return Decision("UP", "model")


def queued_keys(worker):
    return [item[0] for item in worker.queue]


def test_the_next_decision_point_goes_ahead_of_guesses_and_off_path_questions_are_withdrawn():
    import time
    from arcadekit.answers import AnswerBook
    from arcadekit.decisions import DecisionWorker
    gate = Gate()
    worker = DecisionWorker(gate)
    book = AnswerBook(worker, time.time)
    book.ask("first", "g", "first")  # taken at once by the worker thread, which waits at the gate
    time.sleep(0.1)
    book.ask("guess-a", "g", "a", depth=1)
    book.ask("guess-b", "g", "b", depth=1)
    book.ask("next", "g", "next", next_point=True)
    assert queued_keys(worker) == ["next", "guess-a", "guess-b"]
    assert book.ask("guess-c", "g", "c", depth=1, spare=True) is False  # questions are waiting: no more guesses
    book.ask("guess-b", "g", "b", next_point=True)  # already queued: moved to the front instead
    assert queued_keys(worker)[0] == "guess-b" and book.counts["promoted"] == 1
    assert book.withdraw(lambda k: k != "guess-a") == 1 and "guess-a" not in queued_keys(worker)
    assert not worker.pending("guess-a")  # it can be asked again later
    gate.go.set()
