# Games

Every game the arcade can play lives in `games/<system>/<name>/`, where `<system>` is the
EmulationStation system folder name (`arcade`, `nes`, `atari2600`, `snes`, ...) and `<name>` is the
ROM set. This is also where the ROM lives on the Pi: `/home/pi/RetroPie/roms/<system>/`.

**The rule:** `tools/` holds only what works for any game. Anything that knows one game's RAM,
maze, rules or scoring lives in that game's folder. Game packages never import from `tools/`;
tools reach a game only through `tools/gamelib.py` (`load_game("arcade/pacman")`).

```
games/arcade/pacman/
  __init__.py       the adapter (below)
  profile.json      ROM set, controls, hiscore/cheat RAM (tools/game_profile.py writes it)
  discovered.json   RAM found automatically (tools/discover_state.py writes it)
  RAM_MAP.md        hand-validated notes
  state.py maze.py ghosts.py features.py knowledge.py deciders.py player.py
  scripts/          one-off tools for this game (validation, Pi experiments); import _bootstrap first
  tests/            unit tests and fixtures; pytest runs them with the rest
```

## What a game package provides

| Name | Used by |
|---|---|
| `AGENT_REGIONS` | `tools/start_pi_game.py` (what the Pi exports and streams) |
| `decode(image)` | `tools/state_client.py` |
| `score_option(goal, option)` | the mock model in `tools/systemone.py` |
| `deciders.RuleDecider`, `deciders.SystemOneDecider(client)` | `tools/play.py` |
| `knowledge.LEVELS`, `knowledge.build_state_text(...)` | the ablation rungs |
| `player.Player(stream, broker, worker, strategy, log, knowledge=, lookahead=)`, `player.RuleStrategy` | `tools/play.py` |

`Player.tick()` returns a result dict (`game`, `score`, `level`, `seconds`) when a game ends.

## Adding a game

1. `python tools/game_profile.py <romset> --system <system>` (controls, score RAM)
2. `python tools/discover_state.py <romset> --system <system>` (RAM discovery)
3. Copy the adapter shape from `games/arcade/pacman/` and fill in the game's own decode and rules.
4. `python tools/start_pi_game.py --game <system>/<name>` then `python tools/play.py --game <system>/<name>`
