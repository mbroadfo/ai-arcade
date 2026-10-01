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

### Ablation switches

Code that overrules or helps the decider must be switchable, so a model run is not credited for moves the code made.
The switches are written into the run's file names.

| Switch | Default | Meaning |
|---|---|---|
| `--revise` | off | re-check each stored answer against fresh facts and replace it if another exit scores 2.5+ better. Code overruling the decider: label any run that uses it |
| `--no-reflex` | reflex on | turn the survival instinct off |
| `--chain N` | 2 | after an answer, also ask about the junction it leads to, N deep (N+2 during the ghost-eaten pause); 0 = off |
| `--lookahead N` | 8 | start asking about a junction this many tiles ahead |
| `--park` | off | ambush only: wait against a wall near the energizer instead of pacing back and forth (below) |
| `--refuge` | off | hide at the game's safe spot when a ghost is close and he can get there first (below) |
| `--strategist code\|mock\|ollama` | code | who sets the goal and stance (below). `mock` repeats the code's choice after a delay, to separate the cost of latency from the model's judgment |

The run summary also says why answers were late: `seen_too_late` (the junction first came into view 0-1 tiles ahead:
junctions are often 1-3 tiles apart, so no model could have answered in time), `in_flight` (asked, not back yet),
`other_arrival` (answered under a different arriving direction) or `not_asked`.

Each game's result also carries what the goals are about: `ghosts_eaten`, `fruit_eaten`, `fruit_shown`,
`energizers`, `feasts` (ghosts eaten per energizer; a full feast is 4, worth 3000), `deaths`, `reflexes` and
seconds spent per goal.

### Waiting without a wait button (`--park`, `--refuge`)

Pac-Man stops only when his heading runs into a wall, and holding that heading keeps him there. Two separate ideas use it
(`park.py`). While held, the survival reflex does not steer: the point is to stay put, and the log says what happened.

- **`--park`: wait near an energizer.** During `ambush` he used to pace back and forth near the pellet, losing time and nearness.
  Now the option scoring pulls him to a wall-stop tile 3-8 steps from the pellet (a tile with a wall straight ahead, a way in
  and a way out; never a dead end) and he holds there. He goes for the pellet when ghosts have gathered (the usual ambush
  rule), after 10 s, or when the goal changes.
- **`--refuge`: hide at the safe spot.** With all four ghosts out of the house there is a corner he can hide in, tile (53, 44),
  the top of the stub to the right of the block above his start, holding UP into the wall. It earns nothing: it is a quick
  hideaway. Any goal except hunting: when a normal ghost is within 8 steps, the spot is within 12, and no ghost can be on his
  route or at the spot before him (2-step margin), he runs there. He waits until no ghost is within 12 steps of the spot
  (or 15 s), then leaves by the best exit and does not run back for 8 s.

Per game: `parks`, `parked_seconds`, `park_deaths`, `refuges`, `refuge_seconds`, `refuge_deaths` (a life lost while held or on the
way to the refuge). The decision log has `park` and `refuge` events (`start`, `run`, `waiting`, `leave` with why, `died`) with
the normal ghosts' step distances. The tile was named by the player; the refuge counters say whether it holds up. The
knowledge rungs do not describe either yet.

### The slow layer: goal and stance

`--strategist` lets a System One model pick the goal and a *stance* once a second or so, while code still chooses
every direction. The stance is three named dials, each with three levels, each level scaling some weights in
`score_option` (`goals.STANCE`): `caution` (threat and room), `chase` (blue ghosts), `greed` (dots). The model
never sees or sets a raw number, and the scale is bounded.

- General part: `tools/strategist.py` asks one choice question per goal and per dial, validates the answers, never
  blocks the control loop, and leaves the previous advice in force on a timeout, nonsense or low confidence.
- Pac-Man part: `games/arcade/pacman/strategy.py` holds the schema, the situation summary and `ModelGoalManager`.
  The code's own `GoalManager` keeps running underneath: it is the fallback before the first answer, after an
  answer has gone 8 s without renewal, and when the model's goal has nothing to aim at (hunt with no blue ghost,
  fruit with none on screen, ambush with no energizer left). A model goal is held at least 3 s.
- Every answer is logged as an `advice` event beside the goal the code would have chosen and what became of it
  (`taken`, `held`, `gated`); the run summary counts them, including how often the model agreed with the code.
- Survival still overrides everything.

Label results by what the model did: with `--strategist ollama` and the rule decider, the model sets parameters
and code picks every direction (not the S1M playing); with `--decider ollama` as well, a model does both.

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
| `tools/strategist.py` | the slow layer: asks a model for the goal and stance, validates, never blocks |
| `tools/state_client.py` | read the stream; `--measure` times stream and control latency |
| `tools/record_stream.py` | record raw snapshots for offline analysis |
| `tools/game_profile.py`, `tools/discover_state.py` | build a new game's profile and find its RAM (`docs/GAME_STATE_STRATEGY.md`) |
| `tools/probe_mame_input.py` | verify MAME sees the cabinet controls; also the shared SSH helper |
| `tools/configure_mame_controller.py` | one-time controller profile |

Game-specific code and scripts live under `games/<system>/<game>/` (see `games/README.md`).
