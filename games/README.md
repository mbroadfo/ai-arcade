# Games

Every game the arcade can play lives in `games/<system>/<name>/`, where `<system>` is the
EmulationStation system folder name (`arcade`, `nes`, `atari2600`, `snes`, ...) and `<name>` is the
ROM set. This is also where the ROM lives on the Pi: `/home/pi/RetroPie/roms/<system>/`.

**The rule:** `tools/` holds only command-line programs that work for any game, and `arcadekit/` the shared library
(answers, ledger, options, outcome, report, model clients). Anything that knows one game's RAM, maze, rules or scoring
lives in that game's folder. Game packages may import `arcadekit` but never `tools/`; tools reach a game only through
`tools/gamelib.py` (`load_game("arcade/pacman")`). See `docs/REFACTOR_PLAN.md` and `docs/GAME_WORKSHOP.md`.

```
games/arcade/pacman/
  __init__.py       the adapter (below)
  profile.json      ROM set, controls, hiscore/cheat RAM (tools/game_profile.py writes it)
  discovered.json   RAM found automatically (tools/discover_state.py writes it)
  RAM_MAP.md        hand-validated notes
  spec.py           the game's own facts; the player, features, knowledge and the rest are shared by the games on
                    Pac-Man's board (arcadekit/kits/pacman_board) and bound to the spec in __init__.py
  state.py maze.py  thin re-exports of the shared decoder and maze reader
  scripts/          one-off tools for this game (validation, Pi experiments); import _bootstrap first
  tests/            unit tests and fixtures; pytest runs them with the rest
```

## What a game package provides

| Name | Used by |
|---|---|
| `AGENT_REGIONS`: `(start, end, every [, cpu, space])` | `tools/start_pi_game.py`, `tools/mame_speed_test.py` (what the Pi exports and streams; cpu/space default `:maincpu`/`program`) |
| `IMAGE`: `(base, size)` | `tools/state_client.py`, `tools/record_stream.py` (the RAM window the streamed regions are placed in) |
| `decode(image)` | `tools/state_client.py` |
| `score_option(goal, option)` | the mock model in `arcadekit/systemone.py` |
| `deciders.RuleDecider`, `deciders.SystemOneDecider(client)` (built on `arcadekit.decisions.ChoiceDecider`) | `tools/play.py` |
| `knowledge.LEVELS`, `knowledge.build_state_text(...)` | the ablation rungs |
| `goals.GOALS`, `goals.MISSIONS`, `goals.GoalManager(mission)` | `tools/play.py --goal` |
| `strategy.SCHEMA`, `strategy.ModelGoalManager(strategist, goal_manager)`, `strategy.code_chooser` | `tools/play.py --strategist` (optional: a game without it just has no slow model layer) |
| `player.Player(stream, broker, worker, goal_manager, log, knowledge=, **switches)` with `.stats`, `.ledger` (`arcadekit.ledger`), `.latencies` | `tools/play.py` |
| `experiment.OPTIONS` (switches, each an `arcadekit.options.Option` with a kind), `experiment.METRICS`, `experiment.player_kwargs(values, new_worker)`, `experiment.report_lines(player, results)` | `tools/play.py` builds its game switches, run label, manifest and summary from these (optional: without it a game has no switches) |

`Player.tick()` returns a result dict when a game ends: `game`, `score`, `level`, `seconds`, the outcome block every
game shares (`arcadekit.outcome.OutcomeStats`: `deaths`, `boards_cleared`, `lives`), and the game's own metrics (for
Pac-Man ghosts and fruit eaten, energizers, feasts, reflexes, parks, refuges).

Compare runs with `python tools/compare_runs.py <label parts>`.

## Adding a game

1. `python tools/game_profile.py <romset> --system <system>` (controls, score RAM)
2. `python tools/discover_state.py <romset> --system <system>` (RAM discovery)
3. Copy the adapter shape from `games/arcade/pacman/` and fill in the game's own decode and rules.
4. `python tools/start_pi_game.py --game <system>/<name>` then `python tools/play.py --game <system>/<name>`
