"""The slow layer: a System One model picks the goal and the stance (modifier levels) every second or so.

General for any game. The game's adapter supplies the SCHEMA (goals, modifiers, what each means) and a
text summary of the situation; this module asks, validates and hands back advice. It never blocks the
control loop, and anything it cannot use (timeout, nonsense, low confidence) leaves the previous advice
in force. The fast layer (a decider choosing directions) and the survival reflex are separate.

SCHEMA = {
  "instructions": "what the situation is, in a sentence",
  "goals":     {goal: "what it means"},
  "modifiers": {name: {"about": "...", "levels": {level: "what it means"}, "default": level}},
}
"""
import threading
import time
from dataclasses import dataclass, field


@dataclass
class Advice:
    goal: str
    mods: dict = field(default_factory=dict)  # only the modifiers the model answered validly
    confidence: float = 1.0  # the goal answer's
    latency_ms: float = 0.0
    finished_at: float = 0.0
    orders: int = None  # the standing orders' version the question was asked under (arcadekit.orders), if any


def build_questions(schema, only=None, goals=None):
    """The goal question and one per modifier; only: the names to ask (default all), e.g. ("goal",).
    goals: the goals on offer (default all), e.g. only those with something to aim at right now."""
    offered = {g: text for g, text in schema["goals"].items() if goals is None or g in goals}
    questions = {"goal": {"type": "choice", "criteria": offered,
                          "instructions": f"{schema['instructions']} Which goal should be pursued now?"}}
    for name, mod in schema["modifiers"].items():
        questions[name] = {"type": "choice", "criteria": dict(mod["levels"]),
                           "instructions": f"{schema['instructions']} {mod['about']}"}
    return questions if only is None else {k: q for k, q in questions.items() if k in only}


def parse_reply(reply, schema, asked=None, goals=None):
    """(Advice or None, problems). A bad goal (or one not on offer) voids the advice; a bad modifier is left out."""
    answers, problems = reply.get("answers", {}), []
    goal = answers.get("goal", {})
    if goal.get("choice") not in schema["goals"] or (goals is not None and goal.get("choice") not in goals):
        return None, [f"goal {goal.get('choice')!r} is not one of the goals on offer"]
    mods = {}
    for name, mod in schema["modifiers"].items():
        if asked is not None and name not in asked:
            continue  # not asked this time: the stance it set before stands
        choice = answers.get(name, {}).get("choice")
        if choice in mod["levels"]:
            mods[name] = choice
        else:
            problems.append(f"{name} {choice!r} is not a level")
    return Advice(goal["choice"], mods, goal.get("confidence", 1.0), reply.get("latency_ms", 0.0), time.time(),
                  reply.get("orders_version")), problems


class Strategist:
    def __init__(self, client, schema, min_confidence=0.0):
        self.client, self.schema, self.min_confidence = client, schema, min_confidence
        self.lock, self.busy, self.result = threading.Lock(), False, None
        self.stats = {"asked": 0, "answered": 0, "errors": 0, "low_confidence": 0, "invalid": 0}
        self.last_error = ""

    def request(self, text, hint=None, only=None, goals=None):
        """Ask in the background. False (and nothing asked) if the previous question is still out.
        only: which questions (default all); asking the goal alone is several times quicker.
        goals: the goals on offer (default all)."""
        with self.lock:
            if self.busy:
                return False
            self.busy = True
            self.stats["asked"] += 1
        threading.Thread(target=self._ask, args=(text, hint, only, goals), daemon=True).start()
        return True

    def _ask(self, text, hint, only=None, goals=None):
        advice = None
        try:
            questions = build_questions(self.schema, only, goals)
            reply = self.client.ask(text, questions, hint=hint)
            advice, problems = parse_reply(reply, self.schema, asked=set(questions), goals=goals)
            if advice is None:
                self.stats["invalid"] += 1
                self.last_error = "; ".join(problems)
            elif advice.confidence < self.min_confidence:
                self.stats["low_confidence"] += 1
                advice = None
            else:
                self.stats["answered"] += 1
        except Exception as exc:  # model down or slow: the previous advice simply stays
            self.stats["errors"] += 1
            self.last_error = str(exc)
        with self.lock:
            self.result, self.busy = advice, False

    def take(self):
        """The newest finished advice, once; None if there is none since the last call."""
        with self.lock:
            out, self.result = self.result, None
            return out


class MockStrategistClient:
    """Stands in for a model: answers with whatever `chooser(hint)` says ({question: choice}) after a delay."""

    def __init__(self, chooser, latency_ms=(150, 400), seed=0):
        import random
        self.chooser, self.latency_ms, self.rng = chooser, latency_ms, random.Random(seed)

    def ask(self, state, questions, hint=None):
        latency = self.rng.uniform(*self.latency_ms)
        time.sleep(latency / 1000)
        choices = self.chooser(hint)
        return {"answers": {q: {"type": "choice", "choice": choices.get(q), "confidence": 1.0} for q in questions},
                "latency_ms": latency, "usage": None}
