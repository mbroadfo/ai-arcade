"""What a finished round is allowed to keep on disk."""
from __future__ import annotations

from pathlib import Path


def finalize(run_dir: Path) -> list[Path]:
    """Delete rollout captures. The winner video, checkpoints, and result files stay.

    Returns the paths removed.
    """
    removed = []
    for path in run_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.name in {"latest.jpg", "latest.jpg.tmp"} or path.suffix == ".part":
            path.unlink()
            removed.append(path)
    return removed
