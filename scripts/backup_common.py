"""Dependency-free helpers shared by AI Arcade backup tools."""
from __future__ import annotations

import fnmatch
import posixpath


def excluded(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def s3_key(prefix: str, rel_path: str) -> str:
    prefix = prefix.strip("/")
    return posixpath.join(prefix, rel_path) if prefix else rel_path
