"""tools/new_game.py and tools/board_families.py: the parts that need no Pi."""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools")]

import board_families as bf  # noqa: E402
import new_game as ng  # noqa: E402

KITS = bf.load_kits()


def test_a_games_name_loses_its_notes():
    assert ng.short_name("Puck Man (bootleg set 1)") == "Puck Man"
    assert ng.short_name("Pac-Man Plus") == "Pac-Man Plus"
    assert ng.short_name("Space Invaders / Space Invaders M (Midway)") == "Space Invaders"


def test_the_pacman_kit_covers_the_pacman_driver_file_and_nothing_else_claims_it():
    name, kit = ng.find_kit("pacman/pacman.cpp", KITS)
    assert name == "pacman_board" and kit["template"] == "arcade/pacman"
    assert ng.find_kit("galaxian/galaxian.cpp", KITS) == (None, None)  # no kit yet: the report says so
    assert (ROOT / "games" / kit["template"] / "spec.py").exists() and (ROOT / kit["validate"][0]).exists()


def test_the_generated_files_are_valid_python_that_binds_the_kit_and_derives_the_templates_spec():
    kit = KITS["pacman_board"]
    init = ng.render_init((ROOT / "games/arcade/pacman/__init__.py").read_text(encoding="utf-8"), "Pac-Man Plus", "pacplus",
                          "arcade/pacman", "pacman/pacman.cpp")
    spec = ng.render_spec("arcade/pacman", "Pac-Man (Midway)", "Puck Man (bootleg set 1)", "puckmanb", kit["spec_fields_with_name"])
    for text in (init, spec):
        ast.parse(text)
    assert init.startswith('"""Pac-Man Plus (MAME set "pacplus")') and "from arcadekit.kits.pacman_board.bind import bind" in init
    assert 'NAME = "Puck Man"' in spec and "from games.arcade.pacman.spec import SPEC as BASE" in spec
    assert all(f"{f}=BASE.{f}.replace(BASE.name, NAME)" in spec for f in kit["spec_fields_with_name"])


def test_validation_and_play_output_are_read():
    v = ng.parse_validation("== a\n  [PASS] one\n  [FAIL] two (x)\n  [PASS] three\nFAILED: two")
    assert v == {"passed": 2, "failed": ["two (x)"]}
    s = ng.parse_play_summary("GAME 1/2 over: score=3080 level=1\nGAME 2/2 over: score=3750 level=2\nThe model's own: 83%.")
    assert s == {"scores": [3080, 3750], "games": 2, "model_share": 83}
    assert ng.parse_play_summary("nothing")["model_share"] is None


def test_the_readme_records_what_was_found():
    text = ng.render_readme("Puck Man", "puckmanb", "pacman/pacman.cpp", "pacman_board", "arcade/pacman", ["on the Pi", "ASK: x"], "21 October 2026")
    assert "## Onboarding status (21 October 2026)" in text and "- ASK: x" in text


def test_the_family_table_groups_by_driver_file_and_marks_kit_and_ai_coverage():
    games = [{"zip": "pacman", "mame_name": "pacman", "title": "Pac-Man", "year": "1980", "emulator": "mame-0.251"},
             {"zip": "pacplus", "mame_name": "pacplus", "title": "Pac-Man Plus", "year": "1982", "emulator": "mame-0.251"},
             {"zip": "frogger", "mame_name": "frogger", "title": "Frogger", "year": "1981", "emulator": "mame-0.251"}]
    machines = {"pacman": {"source": "pacman/pacman.cpp"}, "pacplus": {"source": "pacman/pacman.cpp"}, "frogger": {"source": "galaxian/galaxian.cpp"}}
    rows = bf.build(games, machines, KITS, {"pacman"})
    assert rows[0]["source"] == "pacman/pacman.cpp" and rows[0]["kit"] == "pacman_board" and rows[0]["ai_games"] == ["pacman"]
    assert rows[1]["kit"] is None
    assert "pacman/pacman.cpp" in bf.markdown(rows)


def test_the_saved_family_table_is_consistent_with_the_catalog():
    families = json.loads((ROOT / "docs/data/board-families.json").read_text(encoding="utf-8"))["families"]
    assert sum(len(f["games"]) for f in families) == len(json.loads((ROOT / "docs/data/cabinet-controls-catalog.json").read_text(encoding="utf-8"))["games"])


def test_a_step_that_runs_too_long_is_stopped_and_reported_as_timed_out():
    out, code = ng.run_tool(["-c", "import time; print('partial', flush=True); time.sleep(30)"], 1)
    assert code == ng.TIMED_OUT
    assert ng.run_tool(["-c", "print('fine')"], 20) == ("fine\n", 0)
