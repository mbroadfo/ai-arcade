"""A discovered maneuver, and how far an agent has taken it.

A shared tape is none of these stages. One solved search does not make six
models competent. Five successes from one deterministic state are a fixed-state
verification. They are not generalization.
"""
from __future__ import annotations

import json

STAGES = (
    "discovered",
    "verified_demonstration",
    "practiced",
    "verified_fixed_state",
    "generalized",
)

# Written before the standing vocabulary. It means the fixed state, not generalization.
LEGACY_FIXED_STATE = "independently_mastered"


def precise_status(label: str | None) -> str | None:
    """The claim the stored word actually supports."""
    if label == LEGACY_FIXED_STATE:
        return "verified_fixed_state"
    return label


def new_skill(
    name: str,
    objective: str,
    challenge_id: str,
    trajectory: list[dict],
    *,
    start: dict,
    benchmark: str = "",
    context: dict | None = None,
    world: int | None = None,
    stage: int | None = None,
    integration: str | None = None,
) -> dict:
    """A search result. It is a demonstration candidate, not a mastered skill.

    context is the game's own precondition. world and stage are that context
    for a game that has them. benchmark is the milestone an independent
    evaluation must name before this skill can be called verified.
    """
    ctx = dict(context or {})
    if world is not None:
        ctx["world"] = int(world)
    if stage is not None:
        ctx["stage"] = int(stage)
    document = {
        "version": 2,
        "name": name,
        "objective": objective,
        "challenge": challenge_id,
        "stage": "discovered",
        "standing": "discovered",
        "benchmark": benchmark,
        "context": ctx,
        "start": dict(start),
        "trajectory": trajectory,
        "provenance": "search",
        "agents": {},
    }
    if integration:
        document["integration"] = str(integration)
    if "world" in ctx:
        document["world"] = ctx["world"]
    if "stage" in ctx:
        document["stage_number"] = ctx["stage"]
    return document


def verify_demonstration(skill: dict, repeats: list[bool]) -> dict:
    """Promote to a verified demonstration only when every repeat succeeded."""
    updated = {**skill, "agents": dict(skill.get("agents") or {})}
    updated["repeats"] = [bool(item) for item in repeats]
    if repeats and all(repeats) and len(repeats) >= 2 and skill.get("stage") == "discovered":
        updated["stage"] = "verified_demonstration"
        updated["standing"] = "verified_demonstration"
    return updated


def record_practice(skill: dict, agent: str) -> dict:
    """This agent practiced the skill. The others are unchanged."""
    updated = {**skill, "agents": dict(skill.get("agents") or {})}
    updated["agents"][agent] = "practiced"
    if updated.get("stage") == "verified_demonstration":
        updated["stage"] = "practiced"
        updated["standing"] = "practiced"
    return updated


def _condition_identity(start) -> str:
    if isinstance(start, (dict, list)):
        return json.dumps(start, sort_keys=True, default=str)
    return str(start)


def _proven_conditions(evaluation: dict) -> bool:
    """True when every listed condition succeeded and two starts differ.

    A condition with no successes, or a row that cannot be read, blocks the
    claim. Declaring generalized, or listing starts, is not this evidence.
    """
    rows = evaluation.get("conditions")
    if not isinstance(rows, list) or len(rows) < 2:
        return False
    seen = set()
    for item in rows:
        if not isinstance(item, dict):
            return False
        try:
            attempts = int(item["attempts"])
            successes = int(item["successes"])
        except (KeyError, TypeError, ValueError):
            return False
        if attempts < 1 or successes < 1 or successes > attempts:
            return False
        if item.get("start") is not None:
            start = item.get("start")
        elif item.get("condition") is not None:
            start = item.get("condition")
        else:
            return False
        seen.add(_condition_identity(start))
    return len(seen) >= 2


def record_mastery(skill: dict, agent: str, evaluation: dict) -> dict:
    """Record what the evaluation actually showed for this one agent.

    A failed evaluation, an assisted record, or a tape replay leaves the agent
    where it was. Success on one scenario is verified_fixed_state. generalized
    requires a successful result on each of at least two distinct conditions.
    The stage stays where it was until that evidence is present.
    """
    updated = {**skill, "agents": dict(skill.get("agents") or {})}
    expected = str(skill.get("benchmark") or "")
    observed = str((evaluation or {}).get("benchmark") or "")
    succeeded = (
        expected
        and observed == expected
        and isinstance(evaluation, dict)
        and not evaluation.get("assisted")
        and not evaluation.get("failed")
        and evaluation.get("record") == "independent"
        and int(evaluation.get("successes") or 0) >= 1
        and float(evaluation.get("success_rate") or 0) > 0
    )
    if not succeeded:
        return updated
    if _proven_conditions(evaluation):
        updated["agents"][agent] = "generalized"
        updated["standing"] = "generalized"
        updated["stage"] = "generalized"
        return updated
    updated["agents"][agent] = "verified_fixed_state"
    updated["standing"] = "verified_fixed_state"
    return updated


def standing_of(skill: dict | None) -> str | None:
    """The precise claim, including a legacy independently_mastered label."""
    if not isinstance(skill, dict):
        return None
    if skill.get("standing") in STAGES:
        return skill["standing"]
    agents = skill.get("agents") or {}
    labels = {precise_status(value) for value in agents.values()}
    if "generalized" in labels:
        return "generalized"
    if "verified_fixed_state" in labels:
        return "verified_fixed_state"
    stage = precise_status(skill.get("stage"))
    return stage if stage in STAGES or stage == skill.get("stage") else stage


def curriculum_plan(challenge_id: str) -> list[dict]:
    """The order a later milestone will train and test. Nothing here trains.

    Gates D and E use this shape. implemented is false until that experiment
    has actually been run.
    """
    stages = (
        ("at_obstacle", "Practice from the saved state in front of the obstacle."),
        ("farther_back", "Start further before the obstacle."),
        ("level_start", "Start at the beginning of the level."),
        ("game_start", "Start from the normal beginning of the game, with no scripted buttons."),
    )
    return [
        {
            "challenge": challenge_id,
            "stage": name,
            "detail": detail,
            "assisted": False,
            "implemented": False,
        }
        for name, detail in stages
    ]
