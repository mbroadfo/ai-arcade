"""One round: six seats. Each seat keeps the life that went furthest right."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from games.lab.catalog import by_id, default_catalog_path, games_from, load_path
from games.lab.integrations import get
from games.lab.lineage import champion, collapsed_history, load_rows, promoted_parent, save_rows, seats_for_generation
from games.lab.models import registry
from games.lab.publish import finalize
from games.lab.ranking import winner
from games.lab.roms import ssh_command, store_game, store_smb
from games.lab.paths import chain_followup, pause_requested, runs_root, stop_requested
from games.lab.seats import SEATS
from games.lab.worker import atomic_json


def load_catalog() -> list:
    if os.environ.get("LAB_CATALOG"):
        return load_path(Path(os.environ["LAB_CATALOG"]))
    try:
        raw = subprocess.check_output(
            ssh_command("python3 /home/pi/ai-arcade/cabinet/cabinet.py catalog"),
            timeout=30,
        )
        return games_from(json.loads(raw.decode()))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        path = default_catalog_path()
        if path is None:
            raise RuntimeError("no cabinet catalog: SSH failed and .manifests/es-catalog is empty")
        return load_path(path)


def materialize(game) -> Path:
    if game.integration == "smb_1_1":
        return store_smb()
    suffix = Path(game.path).suffix.lower() or ".rom"
    if suffix == ".zip":
        suffix = ".nes" if game.system == "nes" else ".a26"
    return store_game(game.system, game.path, f"{game.id.replace('/', '-')}{suffix}")


def _alive(pid: int) -> bool:
    """Process exists. On Windows os.kill(pid, 0) is Ctrl+C, so do not use it."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return kernel.GetLastError() == 5  # ERROR_ACCESS_DENIED: it exists
        code = ctypes.c_ulong()
        ok = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def round_running() -> bool:
    current = runs_root() / "current.json"
    if not current.is_file():
        return False
    try:
        data = json.loads(current.read_text(encoding="utf-8"))
        state = json.loads((Path(data["path"]) / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError):
        return False
    return state.get("status") in {"running", "recording"} and _alive(int(state.get("pid") or 0))


def read_chain() -> dict | None:
    path = runs_root() / "chain.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def chain_running() -> bool:
    chain = read_chain()
    return bool(chain) and chain.get("status") == "running" and _alive(int(chain.get("pid") or 0))


class _Paused(Exception):
    """The seats saved their checkpoints. The generation is not finished."""

    def __init__(self, run_dir: Path):
        super().__init__(run_dir.name)
        self.run_dir = run_dir


def _budget_met(seat_dir: Path, steps: int) -> bool:
    """A paused seat can say finished when its process exited. The budget is the step count."""
    path = seat_dir / "status.json"
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return int(data.get("steps") or 0) >= int(steps)


def read_pause() -> dict | None:
    path = runs_root() / "pause.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_pause(game_id: str, seats: list[dict], steps: int, generation: int, run_id: str | None,
                 phase: str, parent_score, parent_name: str | None) -> None:
    atomic_json(runs_root() / "pause.json", {
        "game_id": game_id,
        "seats": seats,
        "steps": steps,
        "generation": generation,
        "run_id": run_id,
        "phase": phase,
        "parent_score": parent_score,
        "parent_name": parent_name,
    })


def abandon_pause() -> None:
    """Stop, while nothing is training, drops the frozen generation."""
    for name in ("pause.json", "pause.request", "stop.request"):
        path = runs_root() / name
        if path.is_file():
            path.unlink()
    chain = read_chain()
    if chain and chain.get("status") == "paused":
        _set_chain("stopped", "stopped", int(chain.get("generation") or 0), chain.get("parent_score"), chain.get("parent_name"))


def _set_chain(status: str, phase: str, generation: int, parent_score, parent_name: str | None) -> None:
    atomic_json(runs_root() / "chain.json", {
        "status": status,
        "pid": os.getpid(),
        "phase": phase,
        "generation": generation,
        "parent_score": parent_score,
        "parent_name": parent_name,
    })


def _finished_rounds(root: Path) -> list[dict]:
    found = []
    if not root.is_dir():
        return found
    for path in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name, reverse=True):
        results = path / "results.json"
        if not results.is_file():
            continue
        try:
            data = json.loads(results.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        data["id"] = path.name
        found.append(data)
    return found


def _game_stamp(game_id: str) -> dict | None:
    game = by_id(load_catalog())[game_id]
    integration = get(game.integration)
    stamp = getattr(integration, "stamp", None)
    return stamp() if stamp else None


def _seed_sources(seats: list[dict], stamp: dict | None = None) -> list[dict | None]:
    """Training-score zips. They set the practice floor. They do not parent weights."""
    cache: dict[str, dict | None] = {}
    sources = []
    for seat in seats:
        model = seat["model"]
        if model not in cache:
            cache[model] = champion(runs_root(), model, stamp)
        sources.append(cache[model])
    return sources


def _weight_sources(seats: list[dict], stamp: dict | None = None) -> list[dict | None]:
    """Independent evaluations. A training score alone does not seed the next generation."""
    cache: dict[str, dict | None] = {}
    sources = []
    for seat in seats:
        model = seat["model"]
        if model not in cache:
            cache[model] = promoted_parent(runs_root(), model, stamp)
        sources.append(cache[model])
    return sources


def run_round(
    game_id: str,
    seats: list[dict],
    steps: int,
    *,
    generation: int = 0,
    seed_sources: list[dict | None] | None = None,
    parent_score: int | None = None,
    parent_name: str | None = None,
    chained: bool = False,
    resume_dir: Path | None = None,
) -> Path:
    continuing = resume_dir is not None
    if continuing:
        run_dir = resume_dir
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        run_id = str(manifest["id"])
        game_id = manifest["game_id"]
        steps = int(manifest["steps"])
        generation = int(manifest.get("generation") or generation)
        parent_score = manifest.get("parent_score")
        parent_name = manifest.get("parent_name")
        seats = [{"model": seat["model"], "seed": int(seat["seed"])} for seat in manifest["seats"]]
    games = by_id(load_catalog())
    if game_id not in games:
        raise KeyError(f"unknown game {game_id}")
    game = games[game_id]
    if not game.selectable:
        raise ValueError(game.reason or "that game cannot be started")
    if len(seats) != 6:
        raise ValueError("a round has six seats")
    integration = get(game.integration)
    for seat in seats:
        registry.check(seat["model"], integration)

    if not continuing:
        run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        run_dir = runs_root() / run_id
        run_dir.mkdir(parents=True)
        try:
            rom = materialize(game)
        except Exception as exc:
            atomic_json(run_dir / "state.json", {"status": "failed", "pid": os.getpid(), "error": str(exc), "id": run_id})
            atomic_json(runs_root() / "current.json", {"id": run_id, "path": str(run_dir)})
            raise
        objective = integration.objective if integration is not None else "steps"
        manifest = {
            "id": run_id,
            "game_id": game.id,
            "game": game.name,
            "system": game.system,
            "grade": game.grade,
            "objective": objective,
            "steps": steps,
            "rom": str(rom),
            "generation": generation,
            "parent_score": parent_score,
            "parent_name": parent_name,
            "seats": [
                {**SEATS[index], "seat": index, "model": seats[index]["model"], "seed": int(seats[index]["seed"])}
                for index in range(6)
            ],
        }
        atomic_json(run_dir / "manifest.json", manifest)
    else:
        rom = Path(manifest["rom"])
        if not rom.is_file():
            rom = materialize(game)
        objective = manifest.get("objective") or (integration.objective if integration is not None else "steps")
    atomic_json(run_dir / "state.json", {"status": "running", "pid": os.getpid(), "id": run_id})
    atomic_json(runs_root() / "current.json", {"id": run_id, "path": str(run_dir)})
    if chained:
        _set_chain("running", "training", generation, parent_score, parent_name)
    if seed_sources and not continuing:
        for index, source in enumerate(seed_sources):
            if not source:
                continue
            seat_dir = run_dir / "seats" / str(index)
            seat_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source["path"], seat_dir / "seed.zip")
            stamp_file = source["path"].with_suffix(".stamp.json")
            if stamp_file.is_file():
                shutil.copyfile(stamp_file, seat_dir / "seed.stamp.json")
    if not continuing:
        from games.lab.actions import for_system
        from games.lab.tape import seed_run
        if integration is not None and getattr(integration, "actions", None):
            n_actions = len(integration.actions)
        else:
            n_actions = len(for_system(game.system))
        seed_run(run_dir, runs_root(), n_actions, objective, int(parent_score or 0))

    child_env = os.environ.copy()
    child_env["OMP_NUM_THREADS"] = "1"
    child_env["MKL_NUM_THREADS"] = "1"
    child_env["SDL_AUDIODRIVER"] = "dummy"
    procs: dict[int, subprocess.Popen] = {}
    attempts = {index: 0 for index in range(6)}
    pending = {
        index for index in range(6)
        if not (continuing and _budget_met(run_dir / "seats" / str(index), steps))
    }
    failed = None

    def start(index: int) -> None:
        seat = manifest["seats"][index]
        seat_dir = run_dir / "seats" / str(index)
        seat_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable, "-m", "games.lab.worker",
            "--system", game.system,
            "--rom", str(rom),
            "--integration", game.integration or "",
            "--model", seat["model"],
            "--seed", str(seat["seed"]),
            "--steps", str(steps),
            "--seat-dir", str(seat_dir),
            "--seat", str(index),
            "--name", seat["name"],
            "--color", seat["color"],
            "--objective", objective,
        ]
        checkpoint = seat_dir / "checkpoint.zip"
        seed_file = seat_dir / "seed.zip"
        if checkpoint.is_file() and (attempts[index] or continuing):
            cmd.append("--resume")
        elif seed_file.is_file():
            cmd.extend(["--seed-from", str(seed_file)])
        elif attempts[index]:
            raise RuntimeError(f"seat {index} stopped before saving a checkpoint")
        procs[index] = subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parents[2]), env=child_env)

    try:
        while pending or procs:
            for index in list(pending):
                start(index)
                pending.discard(index)
            finished = []
            for index, proc in procs.items():
                code = proc.poll()
                if code is None:
                    continue
                finished.append(index)
                if code != 0:
                    attempts[index] += 1
                    # Stop or Pause already asked the seats to leave. Relaunching would keep training.
                    if attempts[index] < 2 and not stop_requested() and not pause_requested():
                        pending.add(index)
                    else:
                        failed = f"seat {index} exited {code}"
            for index in finished:
                procs.pop(index)
            if failed:
                break
            if procs or pending:
                time.sleep(0.2)
        if failed:
            raise RuntimeError(failed)
        if chain_followup(stop_requested(), pause_requested()) == "pause":
            atomic_json(run_dir / "state.json", {"status": "paused", "pid": os.getpid(), "id": run_id})
            raise _Paused(run_dir)

        rows = []
        for index in range(6):
            status_path = run_dir / "seats" / str(index) / "status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            rows.append(status)
        best = winner(rows)
        # best.gif beside each seat is the life that set the distance record.
        # Replaying checkpoint.zip is the final policy, which can walk left.
        finalize(run_dir)
        results = {
            "id": run_id,
            "game_id": game.id,
            "game": game.name,
            "objective": objective,
            "grade": game.grade,
            "winner": best["seat"],
            "seats": rows,
        }
        atomic_json(run_dir / "results.json", results)
        atomic_json(run_dir / "state.json", {"status": "done", "pid": os.getpid(), "id": run_id})
        return run_dir
    except _Paused:
        raise
    except Exception as exc:
        atomic_json(run_dir / "state.json", {"status": "failed", "pid": os.getpid(), "error": str(exc), "id": run_id})
        for proc in procs.values():
            if proc.poll() is None:
                proc.terminate()
        raise
    finally:
        for proc in procs.values():
            if proc.poll() is None:
                proc.terminate()


def _remember(run_dir: Path, generation: int) -> dict:
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    seat = next(item for item in results["seats"] if item["seat"] == results["winner"])
    return {
        "generation": generation,
        "id": results["id"],
        "winner": seat["seat"],
        "winner_name": seat["name"],
        "model": seat["model"],
        "score": int(seat.get("score") or 0),
        "deaths": int(seat.get("deaths") or 0),
        "life": int(int(seat.get("steps") or 0) / int(seat.get("episodes") or seat.get("deaths") or 1)),
        "game": results.get("game"),
        "objective": results.get("objective"),
        "record": "training",
    }


def run_chain(
    game_id: str,
    seats: list[dict],
    steps: int,
    *,
    start_generation: int | None = None,
    resume_dir: Path | None = None,
) -> None:
    """Keep training. The practice floor is the training score. Weights need an independent eval."""
    if resume_dir is None:
        for name in ("stop.request", "pause.request"):
            path = runs_root() / name
            if path.is_file():
                path.unlink()
    rows = load_rows(runs_root())
    if not rows:
        rows = collapsed_history(_finished_rounds(runs_root()))
        save_rows(runs_root(), rows)
    generation = (int(rows[-1]["generation"]) + 1) if rows else 0
    if start_generation is not None:
        generation = start_generation
    stamp = _game_stamp(game_id)
    pending_resume = resume_dir
    try:
        while True:
            weights = None if pending_resume is not None else _weight_sources(seats, stamp)
            training = None if pending_resume is not None else _seed_sources(seats, stamp)
            present = [source for source in (training or []) if source]
            parent_score = max((source["score"] for source in present), default=None)
            weight_present = [source for source in (weights or []) if source]
            same_parent = len(weight_present) == 6 and len({str(source["path"]) for source in weight_present}) == 1
            parent_name = weight_present[0]["name"] if same_parent else None
            if pending_resume is None and pause_requested():
                _write_pause(game_id, seats, steps, generation, None, "between", parent_score, parent_name)
                _set_chain("paused", "paused", generation, parent_score, parent_name)
                return
            _set_chain("running", "between", generation, parent_score, parent_name)
            try:
                run_dir = run_round(
                    game_id,
                    seats_for_generation(seats, generation),
                    steps,
                    generation=generation,
                    seed_sources=weights,
                    parent_score=parent_score,
                    parent_name=parent_name,
                    chained=True,
                    resume_dir=pending_resume,
                )
            except _Paused as paused:
                _write_pause(game_id, seats, steps, generation, paused.run_dir.name, "training", parent_score, parent_name)
                _set_chain("paused", "paused", generation, parent_score, parent_name)
                return
            pending_resume = None
            pause_file = runs_root() / "pause.json"
            if pause_file.is_file():
                pause_file.unlink()
            row = _remember(run_dir, generation)
            previous = rows[-1]["score"] if rows else None
            row["delta"] = None if previous is None else row["score"] - previous
            rows.append(row)
            save_rows(runs_root(), rows)
            if chain_followup(stop_requested(), pause_requested()) == "stop":
                _set_chain("stopped", "stopped", generation, parent_score, parent_name)
                return
            if chain_followup(stop_requested(), pause_requested()) == "pause":
                _write_pause(game_id, seats, steps, generation + 1, None, "between", parent_score, parent_name)
                _set_chain("paused", "paused", generation + 1, parent_score, parent_name)
                return
            generation += 1
    except Exception:
        _set_chain("failed", "failed", generation, None, None)
        raise


def resume_chain() -> None:
    """Continue the frozen generation, then keep the chain going."""
    data = read_pause()
    if data is None:
        raise RuntimeError("nothing is paused")
    for name in ("pause.request", "stop.request"):
        path = runs_root() / name
        if path.is_file():
            path.unlink()
    resume_dir = None
    run_id = data.get("run_id")
    if run_id:
        folder = runs_root() / str(run_id)
        if (folder / "manifest.json").is_file():
            resume_dir = folder
    run_chain(
        data["game_id"],
        list(data["seats"]),
        int(data["steps"]),
        start_generation=int(data.get("generation") or 0),
        resume_dir=resume_dir,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one lab round, or keep training")
    parser.add_argument("--game")
    parser.add_argument("--steps", type=int, default=200_000)
    parser.add_argument("--seats", help="JSON list of {model, seed}")
    parser.add_argument("--chain", action="store_true")
    parser.add_argument("--resume-chain", action="store_true")
    args = parser.parse_args(argv)
    if args.resume_chain:
        resume_chain()
        return 0
    if not args.game or args.seats is None:
        parser.error("--game and --seats are required")
    seats = json.loads(args.seats)
    if args.chain:
        run_chain(args.game, seats, args.steps)
    else:
        run_round(args.game, seats, args.steps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
