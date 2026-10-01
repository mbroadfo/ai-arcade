"""Deciders: given junction facts and a goal, choose a direction.

RuleDecider is the deterministic algorithmic reference (same features, no model).
SystemOneDecider asks a System One model (arcadekit.decisions.ChoiceDecider with Pac-Man's question) and falls back to
the rule when it is unsure or fails.
"""
from arcadekit.decisions import ChoiceDecider, Decision

from .features import GOALS, render_text, score_option

__all__ = ["Decision", "RuleDecider", "SystemOneDecider", "describe_option", "question"]


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


def question(facts, goal):
    """Pac-Man's choice question: (state text, instructions, {direction: what lies that way})."""
    where = ("Pac-Man is in a corridor and a ghost is close: he can carry on or turn back."
             if facts.get("danger") else "Pac-Man is at a junction.")
    instructions = f"{where} Goal: {goal} - {GOALS[goal]} Which direction should Pac-Man take?"
    criteria = {d: describe_option(o) for d, o in facts["options"].items()}
    return facts.get("state_text") or render_text(facts, goal), instructions, criteria


def SystemOneDecider(client, fallback=None, min_confidence=0.0):  # noqa: N802 (kept: the name the adapter contract uses)
    return ChoiceDecider(client, question, fallback or RuleDecider(), min_confidence, name="direction")
