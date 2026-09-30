#!/usr/bin/env python3
"""Fail CI if likely game-content files appear in the repository."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BLOCKED_DIRS = {
    "roms", "bios", "chd", "saves", "states", "savestates",
    "games-private", "private-library",
}
BLOCKED_SUFFIXES = {
    ".nes", ".sfc", ".smc", ".gb", ".gbc", ".gba", ".n64", ".z64", ".v64",
    ".a26", ".a52", ".a78", ".sms", ".gg", ".32x", ".iso", ".chd", ".dsk",
    ".atr", ".xfd", ".cas", ".tap", ".tzx", ".woz", ".adf", ".ipf", ".g64",
    ".d64", ".t64", ".crt", ".z3", ".z4", ".z5", ".z6", ".z7", ".z8", ".ulx",
    ".7z", ".rar",
}
# ZIP is blocked unless explicitly kept under tests/fixtures and very small; safer default is no ZIP at all.
BLOCKED_SUFFIXES.add(".zip")
MAX_BINARY_BYTES = 25 * 1024 * 1024


def main() -> int:
    violations: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if ".git" in rel.parts or ".venv" in rel.parts:
            continue
        lower_parts = {p.lower() for p in rel.parts[:-1]}
        if lower_parts & BLOCKED_DIRS:
            violations.append(f"blocked directory: {rel}")
            continue
        if path.suffix.lower() in BLOCKED_SUFFIXES:
            violations.append(f"blocked game/archive extension: {rel}")
            continue
        if path.stat().st_size > MAX_BINARY_BYTES:
            # Large source/test data should be reviewed rather than silently committed.
            violations.append(f"file exceeds 25 MiB review threshold: {rel}")

    if violations:
        print("Repository hygiene check FAILED:\n")
        for item in violations:
            print(f" - {item}")
        print("\nKeep game content and private archives outside the Git repository.")
        return 1

    print("Repository hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
