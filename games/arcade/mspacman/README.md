# Ms. Pac-Man

The second game, and the test of reuse (docs/REFACTOR_PLAN.md, phase 4): a sibling of Pac-Man on the same board, so
most of Pac-Man should carry over, and what does not is what the shared code must make configurable.

## Workshop stages (docs/GAME_WORKSHOP.md)

| Stage | Status |
|---|---|
| 0 Feasibility | done: 99.55% speed with no exporter, 91.07% with the agent export, 42.79% with the full 4 KB export (Pi 3, MAME 0.206) |
| 1 Controls | `profile.json` written: 4-way stick, coin, start, as Pac-Man; cheat.dat names lives, dots and the four blue flags |
| 2 State | done for maze 1: Pac-Man's decoder passes all 16 validation checks (`validate_pacman_state.py --game arcade/mspacman`); maze 1 reads with Pac-Man's tile codes (220 dots + 4 energizers, 36 junctions). Mazes 2-4, the tunnels and the wandering fruit still to check (RAM_MAP.md) |
| 3-8 | first probe (v20): Pac-Man's own player on Ms. Pac-Man with no new code. Rule decider: mean 3,907 (2,550-5,350), level 2 twice. nimble L2: mean 6,033 (4,900-7,110), level 2 in all three, the model's own 59%. Next: move the player, features and knowledge into a family kit; Ms. Pac-Man supplies ghost behaviour, mazes, tunnels and knowledge text |

## Cost so far

New code: `spec.py` (the name, ghost knowledge and tunnels; about 60 lines, mostly the L1/L3a texts) and the binding
in `__init__.py`. Moved to be shared: everything else Pac-Man had, into `arcadekit/kits/pacman_board`. Found on the way: Pac-Man's blue flags were read one ghost off (fixed in `99d9bbb`).
