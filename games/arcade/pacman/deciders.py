"""Deciders: given junction facts and a goal, choose a direction.

RuleDecider is the deterministic algorithmic reference (same features, no model).
SystemOneDecider asks a System One model and falls back to the rule when it is unsure or fails.
"""
from dataclasses import dataclass, field

from .features import GOALS, render_text, score_option


@dataclass
class Decision:
    direction: str
    source: str  # "rule", "model", "fallback"
    confidence: float = 1.0
    latency_ms: float = 0.0
    probabilities: dict = field(default_factory=dict)
    note: str = ""


class RuleDecider:
    def decide(self, facts, goal):
        best = max(facts["options"], key=lambda d: score_option(goal, facts["options"][d], facts.get("mods")))
        return Decision(best, "rule")


def describe_option(o):
    parts = [f"food {o['food_steps']} steps" if o["food_steps"] is not None else "no food",
             f"threat {o['threat_steps']} steps" if o["threat_steps"] is not None else "no threat",
             f"room {o['room']}"]
    if o["edible_steps"] is not None:
        parts.append(f"edible ghost {o['edible_steps']} steps")
    if o.get("fruit_steps") is not None:
        parts.append(f"bonus fruit {o['fruit_steps']} steps")
    if o.get("energizer_steps") is not None:
        parts.append(f"energizer {o['energizer_steps']} steps")
    if o["reverse"]:
        parts.append("reverse")
    return ", ".join(parts)


class SystemOneDecider:
    def __init__(self, client, fallback=None, min_confidence=0.0):
        self.client, self.fallback, self.min_confidence = client, fallback or RuleDecider(), min_confidence

    def _fallback(self, facts, goal, note, latency_ms=0.0):
        decision = self.fallback.decide(facts, goal)
        decision.source, decision.note, decision.latency_ms = "fallback", note, latency_ms
        return decision

    def decide(self, facts, goal):
        criteria = {d: describe_option(o) for d, o in facts["options"].items()}
        where = ("Pac-Man is in a corridor and a ghost is close: he can carry on or turn back."
                 if facts.get("danger") else "Pac-Man is at a junction.")
        questions = {"direction": {
            "type": "choice",
            "instructions": f"{where} Goal: {goal} - {GOALS[goal]} Which direction should Pac-Man take?",
            "criteria": criteria,
        }}
        try:
            reply = self.client.ask(facts.get("state_text") or render_text(facts, goal), questions, hint=dict(facts, goal=goal))
        except Exception as exc:  # model down or slow: never leave Pac-Man without a decision
            return self._fallback(facts, goal, f"model error: {exc}")
        answer = reply["answers"]["direction"]
        if answer["confidence"] < self.min_confidence:
            return self._fallback(facts, goal, f"low confidence {answer['confidence']:.2f}",
                                  reply["latency_ms"])
        return Decision(answer["choice"], "model", answer["confidence"], reply["latency_ms"],
                        answer["probabilities"])
