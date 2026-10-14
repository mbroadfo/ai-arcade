"""Who won the round. The higher score wins. For Mario that score is distance to the right."""
from __future__ import annotations


def winner(rows: list[dict]) -> dict:
    """rows need seat (int) and score (number). Ties go to the lower seat."""
    if not rows:
        raise ValueError("a round with no seats has no winner")

    def key(row: dict) -> tuple:
        return (row.get("score") or 0, -int(row["seat"]))

    return max(rows, key=key)


def generation_rank(seats: list[dict], parent_score) -> list[dict]:
    """Highest score first. The change is against the score the generation started from."""
    try:
        parent = None if parent_score is None else int(parent_score)
    except (TypeError, ValueError):
        parent = None
    rows = []
    for index, seat in enumerate(seats):
        if not isinstance(seat, dict):
            continue
        try:
            score = int(seat.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        try:
            seat_index = int(seat["seat"]) if seat.get("seat") is not None else index
        except (TypeError, ValueError):
            seat_index = index
        rows.append({
            "rank": 0,
            "seat": seat_index,
            "name": seat.get("name") or "",
            "model": seat.get("model") or "",
            "color": seat.get("color") or "",
            "score": score,
            "delta": None if parent is None else score - parent,
            "record": "training",
        })
    rows.sort(key=lambda row: (-row["score"], row["seat"]))
    for place, row in enumerate(rows, start=1):
        row["rank"] = place
    return rows
