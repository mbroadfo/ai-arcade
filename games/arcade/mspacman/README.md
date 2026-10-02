# Ms. Pac-Man

The second game, and the test of reuse (docs/REFACTOR_PLAN.md, phase 4): a sibling of Pac-Man on the same board, so
most of Pac-Man should carry over, and what does not is what the shared code must make configurable.

## Workshop stages (docs/GAME_WORKSHOP.md)

| Stage | Status |
|---|---|
| 0 Feasibility | to run: `python tools/mame_speed_test.py --game arcade/mspacman` |
| 1 Controls | to run: `python tools/game_profile.py mspacman` writes `profile.json` |
| 2 State | decoder shared with Pac-Man (`arcadekit/kits/pacman_board`), per the disassembly; to run: `python games/arcade/pacman/scripts/validate_pacman_state.py --game arcade/mspacman`, then the checks in RAM_MAP.md |
| 3-8 | after stage 2. First probe: Pac-Man's own player on Ms. Pac-Man with no new code (`start_pi_game.py --game arcade/mspacman`, then `play.py --game arcade/pacman`), to see what carries over |

## Cost so far

New code: this package's `__init__.py` (one import). Moved to be shared: Pac-Man's decoder and maze reader
(`arcadekit/kits/pacman_board`). Found on the way: Pac-Man's blue flags were read one ghost off (fixed in `99d9bbb`).
