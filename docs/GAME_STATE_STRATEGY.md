# Automatic game-state and control mapping (any MAME romset)

Goal: onboard a new arcade ROM without hand-reverse-engineering. Each layer is automatic
and says how much it can be trusted. Run `python tools/game_profile.py <romset>` for layers 0-1.

## Layer 0 - Controls (fully automatic)

MAME knows every port a game defines. `tools/mame_ports_probe.lua` enumerates them
(`manager:machine():ioport().ports`), and `game_profile.py` maps field names (`P1 Up`, `P1 Button 2`,
`Coin 1`, `1 Player Start`) to the broker's canonical controls. Analog inputs (paddles, dials,
trackballs) are listed separately because the broker has no analog path yet.
The `aiarcade` controller profile uses MAME's standard input types, so it applies to every game.

## Layer 1 - Named RAM anchors from community databases (automatic, partial)

- `hiscore.dat` (MAME plugin, ~11.8k entries): where MAME itself persists the **high score** (not the live score).
- `cheat.dat` (MAME 0.78-era, ~27.5k rows): named variables such as lives, energy, timers, level skip.
Both are on the Pi already. Pac-Man check: cheat.dat `4E14`/`4E15` = lives and `4E0E=F4` = level complete, hiscore `4E88` = high score,
all matching our independent validation. Caveats: coverage varies by game; cheat.dat targets older MAME drivers,
so addresses should be re-validated on 0.206; it rarely names positions or enemies.

## Layer 2 - Experiment-driven discovery (built: `tools/discover_state.py`)

`python tools/discover_state.py <romset>` runs a scripted session through the broker (attract idle, coin, start,
4x each direction hold, then idle until lives are lost) while `mame_snapshot_service.lua` dumps the whole
address space on request (about one snapshot per second, no per-frame cost). It then ranks candidates:

| Signal | Rule | Pac-Man result (known truth) |
|---|---|---|
| Credits | stable in attract, rises on coin, drops by 1 on start | found `4E6E` + 3 false positives |
| Lives | starts 1-9, steps down by exactly 1 (mod 256) before it first rises | found `4E14`, `4E15` (+ 5 false positives); cheat.dat names both |
| Score / progress | constant while idle, changes in 3+ play intervals, mostly upward (binary or BCD) | found `4E80/81`, `4E88/89`, `4E0E`, and on-screen score digits |
| Position | byte deltas flip sign between opposite holds; low on the other axis | truth (`4D09` `4D3A` horizontal, `4D08` `4D39` vertical) is in the top 12, mixed with ghost and sprite bytes |

Notes learned from running it:
- Hardware mirrors RAM (`4Cxx`=`6Cxx`=`CCxx`=`ECxx`); candidates are collapsed only when the bytes around them match in every snapshot.
- Position is the weakest signal: ghosts chase the player, so their bytes correlate with the input.
  Treat position output as a shortlist to confirm, not an answer.
- Cheat-DB anchors are attached to candidates automatically when present.
- `--save`/`--load` keep the raw snapshots so heuristics can be tuned offline without replaying the game.
- Assumes a game with coin/start and a directional controller; games needing other inputs need a different script.

## Layer 3 - Fallback: pixels

When RAM semantics are unknown, MAME can still provide frames, plus layer-1 score/lives, for a vision-based agent.

## Pac-Man status

Layers 0, 1 and a full hand-validated decoder (`tools/pacman_state.py`, `docs/PACMAN_RAM_MAP.md`) pass
`tools/validate_pacman_state.py`. Pac-Man is the reference for checking that layer 2 finds the same answers.
