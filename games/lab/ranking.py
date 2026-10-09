"""Who won the round. The higher score wins. For Mario that score is distance to the right."""
from __future__ import annotations


def winner(rows: list[dict]) -> dict:
    """rows need seat (int) and score (number). Ties go to the lower seat."""
    if not rows:
        raise ValueError("a round with no seats has no winner")

    def key(row: dict) -> tuple:
        return (row.get("score") or 0, -int(row["seat"]))

    return max(rows, key=key)
