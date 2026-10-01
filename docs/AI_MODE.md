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

## Goals and survival

A **goal** is a standing objective, chosen slowly and held. Pac-Man's goals (`games/arcade/pacman/goals.py`):

| Goal | Try to |
|---|---|
| `clear_dots` | eat every dot (default) |
| `hunt_ghosts` | eat as many ghosts as possible: energizer, then chase the blue ones |
| `ambush` | lure ghosts close near an energizer, eat it, then eat the ghosts: 200, 400, 800, 1600 |
| `pacifist` | eat dots but never a ghost, not even a blue one |
| `eat_fruit` | eat the bonus fruit whenever it appears |

`--goal NAME` pins a goal for the whole game. `--goal auto` (default) follows this policy, highest first:

1. **Feast:** blue ghosts we can still reach before they turn back (the blue window is measured in emulated
   frames, 360 on level 1, shorter on later levels) go to `hunt_ghosts`.
2. **Fruit:** bonus fruit on screen within reach goes to `eat_fruit`.
3. **Ambush:** an energizer within 20 steps and 2+ ghosts chasing goes to `ambush`: hold about 4 steps from the
   energizer until 2+ ghosts are within 9 steps (or one is within 4), then eat it. Time-boxed to 20 s, then a
   15 s cooldown.
4. Otherwise `clear_dots`, the long-term objective.

A higher-ranked goal takes over at once; otherwise a goal is held at least 4 s, and it ends early when its
trigger disappears. Ghosts that are not blue are never chased. A slow LLM can replace the chooser later.

The **survival instinct** (`survival.py`) sits above every goal and every decider: if the chosen way leads
to a normal ghost within 3 steps and another way is at least 2 steps safer, it overrides the choice, at
junctions and in corridors. Overrides are logged as `reflex` events and counted per game.

Each game's result also carries what the goals are about: `ghosts_eaten`, `fruit_eaten`, `fruit_shown`,
`energizers`, `feasts` (ghosts eaten per energizer; a full feast is 4, worth 3000), `deaths`, `reflexes` and
seconds spent per goal.

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
