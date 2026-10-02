import socket
import threading
import time

import observatory
from arcadekit.decisions import ChoiceDecider
from arcadekit.observatory import LiveSink
from arcadekit.orders import HEADER, MAX_ORDERS, OrderedClient, Orders, clean


class Recorder:
    """A model that answers the first option and remembers what it was asked."""

    def __init__(self):
        self.asked = []

    def ask(self, state, questions, hint=None):
        self.asked.append((state, questions))
        name, q = next(iter(questions.items()))
        first = next(iter(q["criteria"]))
        return {"answers": {name: {"choice": first, "confidence": 0.9, "probabilities": {first: 0.9}}},
                "latency_ms": 5.0}


QUESTIONS = {"direction": {"type": "choice", "instructions": "Which way?", "criteria": {"UP": "a", "DOWN": "b"}}}


def test_without_orders_the_question_is_unchanged():
    model = Recorder()
    reply = OrderedClient(model, Orders()).ask("state", QUESTIONS)
    assert model.asked[0][1] == QUESTIONS and reply["orders_version"] == 0


def test_orders_go_in_front_of_every_question_and_the_reply_names_their_version():
    model, orders = Recorder(), Orders(["Keep to the left."])
    reply = OrderedClient(model, orders).ask("state", QUESTIONS)
    instructions = model.asked[0][1]["direction"]["instructions"]
    assert instructions == f"{HEADER}\n- Keep to the left.\n\nWhich way?"
    assert model.asked[0][0] == "state"  # the state text is left alone
    assert reply["orders_version"] == 1 and orders.asked == {1: 1}


def test_a_decision_records_the_orders_it_was_asked_under():
    orders = Orders(["a"])
    decider = ChoiceDecider(OrderedClient(Recorder(), orders),
                            lambda facts, goal: ("state", "Which way?", {"UP": "a", "DOWN": "b"}), None,
                            name="direction")
    assert decider.decide({}, "goal").orders == 1
    orders.set(["b"])
    assert decider.decide({}, "goal").orders == 2


def test_changes_are_logged_and_cleaned():
    logged = []
    orders = Orders()
    orders.log = lambda **record: logged.append(record)
    assert orders.set(["  Save   lives first  ", "", "Save lives first"]) == 1
    assert orders.set(["Save lives first"]) is None  # unchanged: no new version, nothing logged
    assert logged == [{"event": "orders", "version": 1, "orders": ["Save lives first"], "source": "operator"}]
    assert len(clean([str(i) for i in range(50)])) == MAX_ORDERS


def test_orders_typed_on_the_page_reach_the_player():
    hub = observatory.Hub()
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    address = probe.getsockname()
    probe.close()
    threading.Thread(target=observatory.events_loop, args=(hub, address), daemon=True).start()
    received = []
    live = None
    deadline = time.time() + 3
    while time.time() < deadline and not hub.players:
        if live is None:
            live = LiveSink(address, on_command=received.append, hello=lambda: [{"event": "run", "label": "r"}],
                            connect=lambda addr, timeout: socket.create_connection(addr, timeout=0.1))
        time.sleep(0.05)
    assert hub.players, "the player never connected"
    deadline = time.time() + 3
    while time.time() < deadline and "run" not in hub.sticky:
        time.sleep(0.02)
    assert hub.sticky["run"]["label"] == "r"  # the hello came first
    time.sleep(0.4)  # longer than the connection's timeout: a quiet connection must still take commands
    assert hub.command({"op": "orders", "orders": ["Stay low."]}) == 1
    deadline = time.time() + 3
    while time.time() < deadline and not received:
        time.sleep(0.02)
    assert received == [{"op": "orders", "orders": ["Stay low."]}]
    live.close(drain_seconds=0)


def test_the_page_has_an_orders_card_that_posts():
    page = open(observatory.PAGE, encoding="utf-8").read()
    assert 'fetch("/orders"' in page and 'id="orders"' in page
