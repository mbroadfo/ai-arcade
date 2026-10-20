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
            from games.lab.contract import ordered
            from games.lab.registry import owner_of
            from games.lab.contract import sense_of
            sense = rnd.get("sense") if rnd.get("sense") in ("maximize", "minimize") else sense_of(owner_of(rnd))
            if sense is None:
                seat = min(seats, key=lambda item: int(item.get("seat") or 0))
            else:
                seat = max(seats, key=lambda item: ordered(sense, int(item.get("score") or 0), int(item.get("seat") or 0)))
        score = int(seat.get("score") or 0)
        previous = rows[-1]["score"] if rows else None
        episodes = int(seat.get("episodes") or seat.get("deaths") or 0)
        steps = int(seat.get("steps") or 0)
        from games.lab.contract import sense_of
        from games.lab.registry import owner_of
        sense = rnd.get("sense") if rnd.get("sense") in ("maximize", "minimize") else sense_of(owner_of(rnd))
        if previous is None or sense is None:
            delta = None
        elif sense == "minimize":
            delta = previous - score
        else:
            delta = score - previous
        rows.append({
            "generation": len(rows),
            "id": rnd.get("id"),
            "winner": seat.get("seat"),
            "winner_name": seat.get("name"),
            "model": seat.get("model"),
            "score": score,
            "deaths": int(seat.get("deaths") or 0),
            "life": int(steps / episodes) if episodes else 0,
            "delta": delta,
            "sense": sense,
            "game": rnd.get("game"),
            "objective": rnd.get("objective"),
            "record": "training",
        })
    return rows


def champion(root: Path, model: str, stamp: dict | None = None, *, sense: str) -> dict | None:
    """The best.zip this metric prefers. A tie keeps the lower seat.

    sense comes from the adapter. A stamp limits the search to weights that used
    the same buttons and score. A different stamp stays on disk and does not
    parent the next round.
    """
    from games.lab.contract import training_prefers
    from games.lab.stamp import matches
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
            if not zip_path.is_file() or not matches(zip_path, stamp):
                continue
            score = int(seat.get("score") or 0)
            if training_prefers(sense, score, index, best):
                best = {
                    "path": zip_path,
                    "score": score,
                    "name": seat.get("name"),
                    "seat": index,
                    "run_id": path.name,
                    "model": model,
                }
    return best


def promoted_parent(root: Path, model: str, stamp: dict | None = None, *, protocol: dict | None = None) -> dict | None:
    """A zip whose independent evaluation matches these exact weights and this experiment.

    A training score does not promote. Without a protocol there is no experiment
    to match, so there is no parent. A missing file, a failed or incomplete
    evaluation, an assisted record, a different scenario or seed list, or a hash
    that does not match the zip leaves no parent. Two different ROM or core
    hashes are not ranked against each other. The higher success rate wins.
    A tie breaks on the protocol metric, in the protocol's sense, then the lower seat.
    """
    from games.lab.eval import accept_eval, read_eval
    from games.lab.stamp import matches
    if not isinstance(protocol, dict) or not protocol.get("name"):
        return None
    candidates: list[dict] = []
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
            index = int(seat.get("seat") or 0)
            zip_path = path / "seats" / str(index) / "best.zip"
            if not zip_path.is_file() or not matches(zip_path, stamp):
                continue
            evaluation = read_eval(zip_path.with_suffix(".eval.json"))
            if not accept_eval(evaluation, zip_path, protocol=protocol, model=model):
                continue
            furthest = evaluation.get("furthest") or {}
            sense = protocol.get("sense")
            metric = protocol.get("metric") or "score"
            if sense not in ("maximize", "minimize"):
                continue
            try:
                score = int(furthest.get(metric) or 0)
                rate = float(evaluation.get("success_rate") or 0)
            except (TypeError, ValueError):
                continue
            if protocol.get("require_success") and rate <= 0:
                continue
            ranked = score if sense == "maximize" else -score
            candidates.append({
                "_rank": (rate, ranked, -index),
                "_env": (evaluation.get("rom_sha1"), evaluation.get("core_sha1")),
                "path": zip_path,
                "score": score,
                "success_rate": rate,
                "name": seat.get("name"),
                "seat": index,
                "run_id": path.name,
                "model": model,
                "record": "independent",
            })
    environments = {item["_env"] for item in candidates}
    if len(environments) != 1:
        return None
    best = max(candidates, key=lambda item: item["_rank"])
    best.pop("_rank", None)
    best.pop("_env", None)
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
