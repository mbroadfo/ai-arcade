"""Generic engine modules do not import a game.

The composition root and the Mario adapter may name Super Mario Bros.
Everything else under games/lab that is not a Mario tool or a test may not.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {
    ROOT / "integrations" / "__init__.py",
    ROOT / "integrations" / "smb_1_1.py",
}
# experiments/ measures one game. It is not an engine module.
SKIP = {"mario", "tests", "experiments", "__pycache__"}
TOKENS = re.compile(
    r"\bsmb_1_1\b"
    r"|\bSMB_ACTIONS\b"
    r"|\bSMB_SHA1\b"
    r"|\bSMB_SHA256\b"
    r"|\bCLEAR_X\b"
    r"|\bpinned_smb\b"
    r"|\bstore_smb\b"
    r"|\breached_warp\b"
    r"|games\.lab\.mario"
    r"|games\.lab\.integrations\.smb_1_1"
)


def engine_sources() -> list[Path]:
    found = []
    for path in sorted(ROOT.rglob("*.py")):
        parts = path.relative_to(ROOT).parts
        if any(part in SKIP for part in parts):
            continue
        if path in ALLOWED:
            continue
        found.append(path)
    return found


def test_generic_engine_modules_do_not_name_a_game():
    hits = []
    for path in engine_sources():
        text = path.read_text(encoding="utf-8")
        for match in TOKENS.finditer(text):
            hits.append(f"{path.relative_to(ROOT)}:{match.group(0)}")
    assert hits == []


def test_the_training_path_does_not_assume_a_mario_life():
    env_text = (ROOT / "env.py").read_text(encoding="utf-8")
    for token in ("x_pos", "flag_get", "game_over"):
        assert token not in env_text
    assert 'info["world"]' not in env_text
    worker_text = (ROOT / "worker.py").read_text(encoding="utf-8")
    assert "peak_world = 1" not in worker_text
    assert "peak_stage = 1" not in worker_text
    assert 'info.get("world") or 1' not in worker_text
    assert 'info.get("stage") or 1' not in worker_text


def test_only_the_composition_root_imports_the_mario_adapter():
    root_text = (ROOT / "integrations" / "__init__.py").read_text(encoding="utf-8")
    assert "games.lab.integrations.smb_1_1" in root_text
    outsiders = []
    for path in engine_sources():
        text = path.read_text(encoding="utf-8")
        if "smb_1_1" in text or "games.lab.mario" in text:
            outsiders.append(str(path.relative_to(ROOT)))
    assert outsiders == []
