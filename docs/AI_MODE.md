# AI mode

AI mode runs a game in **standalone MAME** on the Pi so an AI can play it. Human mode (EmulationStation,
RetroArch, lr-mame2003) is untouched and stays the way people play.

## How it fits together

```
Pi (only runs the game)                         PC (all the thinking)
  MAME + tools/mame_state_export.lua  --state-->  tools/state_client.py   port 8766, newest snapshot wins
  pi/state_server.py                              games/<system>/<game>/  decode, features, knowledge
  pi/controller_broker.py  <------controls-----   tools/broker_link.py    port 8765, tap/press/release
                                                  tools/systemone.py      fast model (Ollama /v1/systemone) or mock
```

- The Pi decides nothing. It exports a small set of RAM regions each frame and accepts controls.
- Nothing needs SSH while a game is being played. SSH is only used to set up and start.
- Fast decisions come from a System One model (local Ollama, model `nimble` by default). A slower goal
  chooser sets the strategy. The rule decider is the non-AI control.

## One-time Pi setup

1. `python tools/install_pi.py` installs the controller broker (see `docs/PI_SETUP.md`).
2. `python tools/configure_mame_controller.py` writes the MAME controller profile (`aiarcade.cfg`).

## Run a game

```
python tools/start_pi_game.py --game arcade/pacman      # MAME + exporter + state server, audio on
python tools/play.py --game arcade/pacman --decider rule --games 3
python tools/play.py --game arcade/pacman --decider ollama --model nimble --knowledge L2 --games 10
```

`--decider` is `rule` (control), `mock` (simulated model latency) or `ollama`. Each run writes
`runs/<time>-<game>-<decider>-<knowledge>-decisions.jsonl` and `...-games.jsonl` (git-ignored).

## What the model is told (ablation rungs)

Set with `--knowledge`. Each rung is cumulative, so a result can be labelled by the help it had:

| Rung | Adds |
|---|---|
| L0 | raw coordinates and flags |
| L1 | the game's rules as text |
| L2 | a situation report in the player's own frame: path distances, danger bands, which exit each threat uses |
| L3a | how each ghost chooses its target (text) |
| L3b | each ghost's current target and its route |
| L4 | code picks the action: the rule decider, the control (not a rung) |

Print exactly what a model would see: `python -m games.arcade.pacman.knowledge --level L3b`.

## Tools

| Tool | Purpose |
|---|---|
| `tools/start_pi_game.py` | start MAME, the exporter and the state server for a game |
| `tools/play.py` | the player loop for any game package |
| `tools/state_client.py` | read the stream; `--measure` times stream and control latency |
| `tools/record_stream.py` | record raw snapshots for offline analysis |
| `tools/game_profile.py`, `tools/discover_state.py` | build a new game's profile and find its RAM (`docs/GAME_STATE_STRATEGY.md`) |
| `tools/probe_mame_input.py` | verify MAME sees the cabinet controls; also the shared SSH helper |
| `tools/configure_mame_controller.py` | one-time controller profile |

Game-specific code and scripts live under `games/<system>/<game>/` (see `games/README.md`).
