"""One ladder for a game. Identical finished rounds are one generation, not extra halls."""
from __future__ import annotations

import json
from pathlib import Path

MIN_STEPS = 50_000


def seats_for_generation(seats: list[dict], generation: int) -> list[dict]:
    """Same six seats. The seed moves by six each generation so the rollouts diverge."""
    return [{**seat, "seed": int(seat["seed"]) + 6 * generation} for seat in seats]


def collapsed_history(rounds: list[dict]) -> list[dict]:
    """Oldest first. A repeated scoreboard is one row. Short diagnostic rounds are left out."""
    rows: list[dict] = []
    seen: set[tuple] = set()
    for rnd in reversed(rounds):
        seats = list(rnd.get("seats") or [])
        if not seats:
            continue
        if max(int(seat.get("steps") or 0) for seat in seats) < MIN_STEPS:
            continue
        signature = tuple(
            (
                seat.get("name"),
                seat.get("model"),
                int(seat.get("score") or 0),
                int(seat.get("deaths") or 0),
            )
            for seat in sorted(seats, key=lambda seat: int(seat.get("seat") or 0))
        )
        if signature in seen:
            continue
        seen.add(signature)
        winner_index = rnd.get("winner")
        seat = next((item for item in seats if item.get("seat") == winner_index), None)
        if seat is None:
            seat = max(seats, key=lambda item: (int(item.get("score") or 0), -int(item.get("seat") or 0)))
        score = int(seat.get("score") or 0)
        previous = rows[-1]["score"] if rows else None
        episodes = int(seat.get("episodes") or seat.get("deaths") or 0)
        steps = int(seat.get("steps") or 0)
        rows.append({
            "generation": len(rows),
            "id": rnd.get("id"),
            "winner": seat.get("seat"),
            "winner_name": seat.get("name"),
            "model": seat.get("model"),
            "score": score,
            "deaths": int(seat.get("deaths") or 0),
            "life": int(steps / episodes) if episodes else 0,
            "delta": None if previous is None else score - previous,
            "game": rnd.get("game"),
            "objective": rnd.get("objective"),
        })
    return rows


def champion(root: Path, model: str) -> dict | None:
    """The best.zip with the highest training score for this model. A tie keeps the lower seat."""
    best: dict | None = None
    if not root.is_dir():
        return None
    for path in root.iterdir():
        results_path = path / "results.json"
        if not path.is_dir() or not results_path.is_file():
            continue
        try:
            data = json.loads(results_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for seat in data.get("seats") or []:
            if seat.get("model") != model:
                continue
            if int(seat.get("steps") or 0) < MIN_STEPS:
                continue
            index = int(seat.get("seat") or 0)
            zip_path = path / "seats" / str(index) / "best.zip"
            if not zip_path.is_file():
                continue
            score = int(seat.get("score") or 0)
            if best is None or score > best["score"] or (score == best["score"] and index < best["seat"]):
                best = {
                    "path": zip_path,
                    "score": score,
                    "name": seat.get("name"),
                    "seat": index,
                    "run_id": path.name,
                    "model": model,
                }
    return best


def load_rows(root: Path) -> list[dict]:
    path = root / "lineage.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("rows")
    return list(rows) if isinstance(rows, list) else []


def save_rows(root: Path, rows: list[dict]) -> None:
    from games.lab.worker import atomic_json
    atomic_json(root / "lineage.json", {"rows": rows})
