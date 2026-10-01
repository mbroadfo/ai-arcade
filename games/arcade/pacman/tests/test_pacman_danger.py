"""The danger query: in a corridor with a ghost close, the model is asked carry on or turn back, and its answer is executed."""
import io
import json
import time
from dataclasses import replace

from games.arcade.pacman import danger, features, goals, player
from games.arcade.pacman.deciders import Decision, SystemOneDecider
from games.arcade.pacman.maze import MOVES, OPPOSITE, Maze, step
from games.arcade.pacman.tests.test_pacman_chain import IMAGE, STATE, FakeWorker, Steer, Stream

MAZE = Maze(IMAGE)


def straight_corridor(length=6):
    """(tile, heading, ahead): a tile with exactly two opposite exits, and the tile `length` steps on along the same plain
    corridor (no junction or corner between)."""
    for l in range(0x20, 0x40):
        for h in range(0x1E, 0x3E):
            tile = (l, h)
            if not MAZE.passable(tile):
                continue
            for heading in MOVES:
                run, t = [], tile
                for _ in range(length + 1):
                    exits = MAZE.exits(t)
                    if sorted(exits) != sorted([heading, OPPOSITE[heading]]):
                        break
                    run.append(t)
                    t = step(t, heading)
                if len(run) == length + 1:
                    return tile, heading, run[-1]
    raise AssertionError("no straight corridor")


ME, HEADING, AHEAD = straight_corridor()
BEHIND = step(ME, OPPOSITE[HEADING])


def scene(ghost_tile=AHEAD, heading=HEADING):
    ghosts = {n: replace(g, tile=(0, 0), next_tile=(0, 0)) for n, g in STATE.ghosts.items()}
    ghosts["red"] = replace(ghosts["red"], tile=ghost_tile, next_tile=ghost_tile)
    return replace(STATE, mode="playing", ghosts=ghosts, pacman=replace(STATE.pacman, tile=ME, direction=heading.lower()),
                   frightened={n: False for n in STATE.ghosts}, eyes={n: False for n in STATE.ghosts})


class AnsweringWorker(FakeWorker):
    """Answers a danger question with `choice` (a direction); anything else with the rule decider."""

    def __init__(self, choice):
        super().__init__()
        self.choice, self.urgent = choice, []

    def submit(self, key, goal, facts, urgent=False):
        if key[0] != "danger":
            return super().submit(key, goal, facts)
        self.submitted.append(key)
        self.urgent.append(urgent)
        self.finished.append((key, goal, facts, Decision(self.choice, "model", 0.9, 40.0), time.time()))
        return True


def make(states, choice, **kw):
    steer, log = Steer(), io.StringIO()
    worker = AnsweringWorker(choice)
    p = player.Player(Stream([(i, s, IMAGE) for i, s in enumerate(states, start=1)]), steer, worker,
                      goals.GoalManager("clear_dots"), log, danger_query=kw.pop("danger_query", True), **kw)
    return p, steer, log, worker


def danger_events(log):
    return [e for e in (json.loads(line) for line in log.getvalue().splitlines()) if e["event"] == "danger"]


# ---------------------------------------------------------------- when to ask

def facts_for(ghost_tile):
    st = scene(ghost_tile)
    return features.junction_facts(st, IMAGE, tile=ME, arriving=HEADING)


def test_a_plain_corridor_offers_exactly_two_choices_carry_on_or_turn_back():
    options = danger.corridor_options(facts_for(AHEAD), HEADING)
    assert set(options) == {HEADING, OPPOSITE[HEADING]}


def test_a_ghost_ahead_within_range_or_just_behind_is_a_danger_a_far_one_is_not():
    assert danger.danger_facts(facts_for(AHEAD), HEADING)["danger"] is True
    assert danger.danger_facts(facts_for(BEHIND), HEADING) is not None
    far = [t for t, d in MAZE.bfs(ME).items() if d >= 20][0]
    assert danger.danger_facts(facts_for(far), HEADING) is None


def test_at_a_junction_there_is_no_corridor_choice_to_ask_about():
    junction = next(t for t in MAZE.bfs(ME) if len(MAZE.exits(t)) >= 3)
    st = scene()
    facts = features.junction_facts(replace(st, pacman=replace(st.pacman, tile=junction)), IMAGE, tile=junction, arriving="UP")
    assert danger.corridor_options(facts, "UP") is None


def test_the_question_says_the_pacman_is_in_a_corridor_with_a_ghost_close():
    seen = {}

    class Client:
        def ask(self, state, questions, hint=None):
            seen["instructions"] = questions["direction"]["instructions"]
            return {"answers": {"direction": {"type": "choice", "choice": HEADING, "probabilities": {}, "confidence": 1.0}},
                    "latency_ms": 1.0}
    SystemOneDecider(Client()).decide(danger.danger_facts(facts_for(AHEAD), HEADING), "clear_dots")
    assert "corridor" in seen["instructions"] and "turn back" in seen["instructions"]
    SystemOneDecider(Client()).decide(facts_for(AHEAD), "clear_dots")  # an ordinary junction question is unchanged
    assert seen["instructions"].startswith("Pac-Man is at a junction.")


# ---------------------------------------------------------------- in the player

def test_with_the_switch_on_a_ghost_ahead_makes_an_urgent_question_and_with_it_off_nothing_is_asked():
    p, steer, log, worker = make([scene()], HEADING)
    p.tick()
    assert [k[0] for k in worker.submitted if k[0] == "danger"] == ["danger"] and worker.urgent == [True]
    assert p.stats["danger"]["asked"] == 1
    p, steer, log, worker = make([scene()], HEADING, danger_query=False)
    p.tick()
    assert not any(k[0] == "danger" for k in worker.submitted)


def test_no_question_when_no_ghost_is_close():
    far = [t for t, d in MAZE.bfs(ME).items() if d >= 20][0]
    p, steer, log, worker = make([scene(far)], HEADING)
    p.tick()
    assert not any(k[0] == "danger" for k in worker.submitted)


def test_a_turn_back_answer_is_executed_and_booked_as_the_models_move():
    p, steer, log, worker = make([scene(), scene()], OPPOSITE[HEADING])
    p.tick()  # asks
    p.tick()  # the answer is in: turn back
    assert steer.sent[-1] == OPPOSITE[HEADING]
    assert p.stats["danger"]["turned_back"] == 1 and p.stats["moves"]["model-danger"] == 1
    event = danger_events(log)[0]
    assert event["phase"] == "turn back" and event["source"] == "model" and event["latency_ms"] == 40


def test_a_carry_on_answer_changes_nothing_but_is_counted():
    p, steer, log, worker = make([scene(), scene()], HEADING)
    p.tick()
    p.tick()
    assert OPPOSITE[HEADING] not in steer.sent and p.stats["danger"]["carried_on"] == 1


def test_an_answer_that_is_too_old_or_for_somewhere_else_is_dropped():
    p, steer, log, worker = make([scene(), scene(), scene()], OPPOSITE[HEADING])
    p.tick()
    worker.finished.clear()  # only the answers injected below
    key, decision, finished = ("danger", ME, HEADING), Decision(OPPOSITE[HEADING], "model"), time.time()
    p.danger_answer = (key, decision, finished - danger.MAX_AGE - 0.5)  # arrived too late
    p.tick()
    assert p.stats["danger"]["dropped"] == 1 and OPPOSITE[HEADING] not in steer.sent
    far_tile = (ME[0] + 10, ME[1])
    p.danger_answer = (("danger", far_tile, HEADING), decision, time.time())  # asked about a spot he has left
    p.tick()
    assert p.stats["danger"]["dropped"] == 2 and OPPOSITE[HEADING] not in steer.sent
