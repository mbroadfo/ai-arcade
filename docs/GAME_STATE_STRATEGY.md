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

## Layer 2 - Experiment-driven discovery (semi-automatic, to build)

For anything unnamed, drive scripted actions through the broker and watch RAM (`mame_state_export.lua`
streams any regions listed in `regions.lua`; `ram_experiment.py` shows the change-diff idea):
- coin -> a byte that increments (credits), start -> credits decrement, mode byte changes;
- hold a direction -> byte pairs that change monotonically with direction sign (player position);
- repeat idle runs to subtract noise; keep only candidates stable across runs.
Output candidates with a confidence score; a human or LLM confirms and the result is saved as a profile.

## Layer 3 - Fallback: pixels

When RAM semantics are unknown, MAME can still provide frames, plus layer-1 score/lives, for a vision-based agent.

## Pac-Man status

Layers 0, 1 and a full hand-validated decoder (`tools/pacman_state.py`, `docs/PACMAN_RAM_MAP.md`) pass
`tools/validate_pacman_state.py`. Pac-Man is the reference for checking that layer 2 finds the same answers.
