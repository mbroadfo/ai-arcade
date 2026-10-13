"""Where the lab keeps things. Code stays in the repo. ROMs, cores, and runs do not."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def lab_home() -> Path:
    return Path(os.environ.get("LAB_HOME", Path.home() / "mario-lab"))


def runs_root() -> Path:
    return Path(os.environ.get("LAB_RUNS", Path.home() / "mario-runs"))


def stop_requested() -> bool:
    """The page writes this file. Seats leave and the chain ends."""
    return (runs_root() / "stop.request").is_file()


def pause_requested() -> bool:
    """The page writes this file. Seats save checkpoints and the generation waits."""
    return (runs_root() / "pause.request").is_file()


def hold_requested() -> bool:
    """Either button asks the seats to leave the current learn() call."""
    return stop_requested() or pause_requested()


def chain_followup(stop: bool, pause: bool) -> str:
    """Stop closes the chain. Pause freezes this generation. Otherwise training continues."""
    if stop:
        return "stop"
    if pause:
        return "pause"
    return "continue"


def cores_dir() -> Path:
    return lab_home() / "cores"


def roms_dir() -> Path:
    return lab_home() / "roms"


def assert_outside_repo(path: Path) -> None:
    resolved = path.resolve()
    root = REPO_ROOT.resolve()
    if resolved == root or root in resolved.parents:
        raise RuntimeError(f"{resolved} is inside the repository; the lab does not store games there")
