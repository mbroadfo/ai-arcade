"""A discovered maneuver, and how far an agent has taken it.

A shared tape is none of these stages. One solved search does not make six
models competent.
"""
from __future__ import annotations

STAGES = (
    "discovered",
    "verified_demonstration",
    "practiced",
    "independently_mastered",
)


def new_skill(
    name: str,
    objective: str,
    challenge_id: str,
    trajectory: list[dict],
    *,
    world: int,
    stage: int,
    start: dict,
) -> dict:
    """A search result. It is a demonstration candidate, not a mastered skill."""
    return {
        "version": 1,
        "name": name,
        "objective": objective,
        "challenge": challenge_id,
        "stage": "discovered",
        "world": int(world),
        "stage_number": int(stage),
        "start": dict(start),
        "trajectory": trajectory,
        "provenance": "search",
        "agents": {},
    }


def verify_demonstration(skill: dict, repeats: list[bool]) -> dict:
    """Promote to a verified demonstration only when every repeat succeeded."""
    updated = {**skill, "agents": dict(skill.get("agents") or {})}
    updated["repeats"] = [bool(item) for item in repeats]
    if repeats and all(repeats) and len(repeats) >= 2 and skill.get("stage") == "discovered":
        updated["stage"] = "verified_demonstration"
    return updated


def record_practice(skill: dict, agent: str) -> dict:
    """This agent practiced the skill. The others are unchanged."""
    updated = {**skill, "agents": dict(skill.get("agents") or {})}
    updated["agents"][agent] = "practiced"
    if updated.get("stage") == "verified_demonstration":
        updated["stage"] = "practiced"
    return updated


def record_mastery(skill: dict, agent: str, evaluation: dict) -> dict:
    """Mark one agent only when an independent evaluation succeeded.

    A failed evaluation, an assisted record, or a tape replay leaves the agent
    where it was.
    """
    updated = {**skill, "agents": dict(skill.get("agents") or {})}
    if (
        isinstance(evaluation, dict)
        and not evaluation.get("assisted")
        and not evaluation.get("failed")
        and evaluation.get("record") in (None, "independent")
        and int(evaluation.get("successes") or 0) >= 1
        and float(evaluation.get("success_rate") or 0) > 0
    ):
        updated["agents"][agent] = "independently_mastered"
    return updated


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
