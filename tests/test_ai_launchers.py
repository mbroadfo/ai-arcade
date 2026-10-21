"""Every tool that starts MAME for the AI's controller (the aiarcade controller file) must show MAME only the AI pads."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_every_launcher_that_uses_the_aiarcade_controller_file_hides_the_other_pads():
    offenders = []
    sources = list((ROOT / "tools").glob("*.py")) + list((ROOT / "games").glob("*/*/scripts/*.py"))
    for path in sources:
        text = path.read_text(encoding="utf-8")
        if "-ctrlr aiarcade" in text and "AI_PADS_ENV" not in text and "ONLY_AI_PADS" not in text:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, f"these start MAME for the AI without AI_PADS_ENV (gamelib): {offenders}"
