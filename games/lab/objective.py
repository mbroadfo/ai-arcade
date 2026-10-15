"""Objective rules that are not a game.

Ranking, a no-progress cutoff, and whether one checkpoint may initialize
another objective live here. A game adapter measures the episode. This module
does not name a game, a button, or a score address.
"""
from __future__ import annotations


def next_stall_run(run: int, gained: int) -> int:
    """How many decisions in a row have failed to raise the maximum."""
    try:
        current = int(run)
    except (TypeError, ValueError):
        current = 0
    try:
        moved = int(gained)
    except (TypeError, ValueError):
        moved = 0
    if moved > 0:
        return 0
    return current + 1


def stalled(run: int, limit) -> bool:
    """True when a configured cutoff has been reached. No cutoff stays open."""
    if limit is None:
        return False
    try:
        cap = int(limit)
        current = int(run)
    except (TypeError, ValueError):
        return False
    if cap < 1:
        return False
    return current >= cap


def _whole(episode: dict, key: str) -> int:
    try:
        return int(episode.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def rank_completion(episodes: list[dict]) -> dict | None:
    """Verified completion outranks every failure.

    Among successes, fewer frames wins. Among failures, greater progress wins.
    That second order is diagnostic. It must not promote a failure over a success,
    and a fast failure does not beat a slow success.
    """
    good = [
        episode
        for episode in episodes
        if isinstance(episode, dict) and not episode.get("failed")
    ]
    if not good:
        return None
    successes = [episode for episode in good if episode.get("success")]
    if successes:
        return min(successes, key=lambda episode: _whole(episode, "frames"))
    return max(good, key=lambda episode: _whole(episode, "score"))


def explicit_init_allowed(source: dict | None, expected: dict | None) -> bool:
    """Weights may initialize a different objective when the controls and the
    observation width match. A missing stamp, or a different action list or
    width, may not. Matching here does not make the source a champion of the
    new objective.
    """
    if not isinstance(source, dict) or not isinstance(expected, dict):
        return False
    for key in ("actions", "ram", "objective"):
        if key not in source:
            return False
    for key in ("actions", "ram"):
        if key not in expected:
            return False
    return source.get("actions") == expected.get("actions") and source.get("ram") == expected.get("ram")
