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
