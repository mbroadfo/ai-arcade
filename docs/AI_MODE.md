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
  tools/mame_video_export.lua --video-->          tools/observatory.py    port 8767, the dashboard (see below)
  pi/frame_server.py
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

## The Observatory (control panel and dashboard)

`python tools/observatory.py`, then open http://localhost:8780/. It is the cabinet's control panel: pick any game the
cabinet has and play it, or, for a game with an AI package, set up an AI run and watch it. One-time setup:
`python tools/install_cabinet.py` (the cabinet controls, pi/cabinet/, and a hook in RetroPie's autostart).

What the page shows follows what is on the cabinet's screen (polled every two seconds):

| On the screen | The page | The header's action |
|---|---|---|
| the menu | home: what's next, the games the AI can play, recently played | GAMES |
| a person's game (from the menu or the page) | home: what is playing, its emulator | STOP GAME |
| an AI run starting | its steps: screen cleared, MAME and streams, player | – |
| an AI run | the dashboard below | STOP AI (the player writes its results first) |
| AI mode's MAME, no player (a run ended) | the dashboard's last state | RUN AGAIN, BACK TO MENU |
| nothing / cabinet unreachable | what is wrong, retrying | BACK TO MENU |

GAMES opens the picker (search, systems, "AI can play"); a game's PLAY starts it for a person as EmulationStation would
(its own emulator), AI PLAYS… opens the AI setup. The setup is read from the game package (tools/ai_setup.py): who
decides (a model from this PC's Ollama, the rule as the control, or the mock), what the model is told (the knowledge
levels with the game's own descriptions), the goal, who sets the goal and stance, standing orders, how many games, and
the game's switches grouped by kind (overrides and skills marked: they change who makes the moves). It remembers the
last setup per game and shows the play.py command it will run. Links: `#games` opens the picker, `#setup=arcade/pacman`
a game's setup. `--watch-only` leaves the controls out; `--listen 0.0.0.0` lets anyone on the LAN watch and control.

Game speed: AI mode runs at 85 % by default (`start_pi_game.py --speed`), the Pi 3's pace (about 51 frames a second),
which the model's answer times were tuned on; at the Pi 5's full 60 most answers arrived after Pac-Man had passed the
junction. The setup has a speed slider and the dashboard one under the video, which changes it during the run
(tools/mame_speed_control.lua sets MAME's throttle rate). The player measures the speed it actually gets every three
seconds and logs each change as a `speed` event; the manifest lists them (`speeds`).

The dashboard: the game's video beside what the player is doing.
Drawn over the video: a line from Pac-Man to each ghost with its distance in steps along the maze, the junction just
decided (every option sized by the model's probability, the executed way in the colour of who made the move, a
proposal code overruled in red), and the answers already waiting at junctions ahead. Beside it: the goal and stance,
the last decision as a compass with the joystick, who made the run's moves (the model's own share first), each finished
game, and a timeline of the logged events. The header says whether the run is live, between games or ended. Start it before or after `play.py`; each reconnects to the other, and the video
reconnects to the Pi. `--listen 0.0.0.0` lets a phone or another PC on the LAN watch.

- Video: `start_pi_game.py` loads `tools/mame_video_export.lua` beside the state exporter (through `autoboot.lua`). It
  copies MAME's screen bitmap 15 times a second (`--video-fps`) to `/dev/shm`, and `pi/frame_server.py` (port 8767)
  sends each frame zlib-compressed: a Pac-Man frame is 252 KB raw, a few KB on the wire. The PC turns frames upright and
  into PNGs; the Pi encodes nothing. `--no-video` leaves it out.
- Measured on the Pi 5 (2 October 2026): a capture costs 0.4 ms of MAME's frame; with video streaming, Pac-Man runs at
  60.7 emulated frames a second and press-to-effect is 69 ms median (66 ms without).
- Events: `play.py` hands the player an `arcadekit.observatory.EventSink` as its decisions log. Every line still goes
  to the file; a copy goes to the dashboard (port 8770) from a background thread that never blocks the player and
  drops lines when no dashboard is listening. Five times a second it also sends a `status` line (the player's
  `observe()`: facts read from the stream, with screen positions from the kit's `screen.py`; it decides nothing).
  `--observatory none` sends nothing.
- The dashboard decides nothing and knows no game: it shows the standard events whatever the game. What it shows of a
  game (the facts, the lines over time, the marks on the screen) comes from that game's `observe()` (games/README.md);
  a test keeps game words out of the page, the server and the shared modules.
- Game state: the facts the game picks (Pac-Man: phase, blue ghosts, food and energizers left, Cruise Elroy, fruit),
  60-second lines (nearest ghost with an alarm under 8 steps, nearest blue ghost, score; and from the answers, the
  model's confidence and latency) and who is where.
- What the model was asked: the last request of each asker exactly as it was sent (standing orders, question, options
  with the answer marked, then the state text), captured where it is sent. "hold" freezes it to read.

### Standing orders

Plain words from the operator, put in front of every question a model is asked (`arcadekit/orders.py`): set at the start
with `--orders "..."` (repeat for several) or typed into the Observatory during the run (it shows the game's own example,
`ORDERS_EXAMPLE`). No code reads them; whether the model follows them, and whether that helps, is what a run measures.
A rule decider or a mock model never sees text, so the page says when no model reads them.

Every change is an `orders` event with a version; each `decision`, `move` and `advice` record carries the version it was
asked under; the manifest has the history and how many questions went out under each version. Measured 2 October 2026
(nimble, L2): an order changed from the page took effect within the run (19 answers under version 1, then 23 under 2).
Whether `nimble` follows a given order is not yet measured: compare runs with and without it.

## Goals and survival

A **goal** is a standing objective, chosen slowly and held. Pac-Man's goals (`arcadekit/kits/pacman_board/goals.py`, shared with Ms. Pac-Man):

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

### The danger query (`--danger-query`)

The model is normally asked only at junctions, so mid-corridor the survival reflex (code) was the only thing that could turn
Pac-Man round: in a live `tev1:0.8b` game 26 of its 47 reflex firings were corridor turn-backs. With the switch on, a ghost
within 8 steps along the way ahead (or 3 behind) in a plain corridor makes the player ask the model the one choice a corridor
has, carry on or turn back, with the threat data. The question jumps the queue; code only decides *when to ask* and drops answers
older than 0.4 s or for a spot he has left. The model's turn-backs are booked as `model-danger` in the provenance counts and
logged as `danger` events; the summary prints asked / answered / dropped / turned_back / carried_on. Run it with `--no-reflex`
to see the model alone, and without `--danger-query` to see what the reflex contributes.

### Who made each move (provenance), the run manifest, per-life stats

A result can only be claimed for the AI if the AI made the moves. Every run therefore records, per junction decision, who
proposed the direction and who executed it (forced single-exit corners are mechanical and not counted):

| `by` | `via` | Meaning |
|---|---|---|
| `model` | `junction`, `danger` | the model's answer, executed as given |
| `rule` | `junction` | the rule decider (the control, L4) |
| `code-fallback` | `junction`, `danger` | the model failed or was unsure, the rule decided |
| `code-late` | `junction` | no answer in time, the rule decided; `late` says why (`seen_too_late`, `in_flight`, `other_arrival`, `not_asked`) |
| `code-override` | `reflex`, `revise` | code changed the proposed direction |
| `code-skill` | `park`, `refuge` | a park or the refuge (code-triggered until the model gets those choices) |

The vocabulary is `arcadekit/ledger.py`, shared by every game. Logs written before it (up to v15) used `reflex-override`,
`code-revise`, `code-hold` and `model-danger`; `OLD_LABELS` there maps them. The decision log has one `move` event per
decision (proposed, source, confidence, latency, the answer's age when used, executed, `by`, `via`, `late`), and every log line carries the `frame` so it lines up with a recording. The run summary prints
the counts and "The model's own: N%". Each run also writes `<label>-manifest.json`: git commit and whether the tree was
dirty, game, decider and model (with the Ollama digest), knowledge rung, goal, strategist, every switch, seed, games asked.
Each game's result carries `lives` (seconds, score earned and dots for every life), `boards_cleared`, `dots_total` and
`board_dots`.

First model-decider run with the full stack (nimble, L2, one game, 1 Oct 2026): score 5770, but the model's own moves were
31% of 233 junction decisions (72); the late rule fill-in made 154 (66%) and the reflex changed 7 (3%). The model's median
answer took 244 ms; answers were late because they were still in flight (79), the junction was seen too late (64) or was
answered under another arriving direction (11).

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
| `--danger-query` | off | in a corridor with a ghost close, ask the model carry on or turn back (urgent, at the front of the queue) and execute its answer (below). `--danger-model M` sends it to a separate, faster model |
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
- Pac-Man part: `arcadekit/kits/pacman_board/strategy.py` holds the schema, the situation summary and `ModelGoalManager` (shared by the games on Pac-Man's board; the player's name comes from the game's spec).
  The code's own `GoalManager` keeps running underneath: it is the fallback before the first answer, after an
  answer has gone 8 s without renewal, and when the model's goal has nothing to aim at (hunt with no blue ghost,
  fruit with none on screen, ambush with no energizer left). A model goal is held at least 3 s.
- Every answer is logged as an `advice` event beside the goal the code would have chosen and what became of it
  (`taken`, `held`, `gated`); the run summary counts them, including how often the model agreed with the code.
- Only the goals with something to aim at are offered (no hunting with no blue ghost, and so on): which goals are
  possible is a fact about the board, which to pursue is still the model's. The gate stays, for a board that changes
  while the question is out.
- Survival still overrides everything.
- When it asks (`--strategy-timing`, a timing switch). The model server answers one question at a time, so the slow
  layer's questions and the junction questions wait for each other. `events` (the default): the goal alone on a game
  event (energizers, ghosts turning blue or back, fruit, a life, a level), at once; otherwise every 5 s the goal with
  one stance setting, in turn (caution, chase, greed: each renewed every 15 s, in smaller pieces than
  the 665 ms of all three, which held up junction questions arriving behind it); heartbeats only when no junction
  question waits or is being answered. A stance not renewed in 30 s lapses to normal. `always`: goal and stance as often as answers come (the behaviour before 2 October 2026). Each
  `advice` record says why it was asked. Measured on nimble with an idle server: the goal alone 95 ms, goal and stance
  665 ms; with `always`, one Ms. Pac-Man run kept the server busy 78% of the time and junction answers took a median
  1.9 s, so code's late default made 98% of the moves.
- The code's goal (`GoalManager`, the default without `--strategist`) is a hand-tuned policy: it reads only what a
  player can see or know (path distances, blue time from the Pac-Man Dossier's table), but its thresholds are code's
  judgement, and the goal it picks is in every junction question. A run with code's goal is "the model picks
  directions under code's strategy".

Label results by what the model did: with `--strategist ollama` and the rule decider, the model sets parameters
and code picks every direction (not the S1M playing); with `--decider ollama` as well, a model does both.

### Model server

ai-arcade runs its own Ollama (`tools/ollama/`, port 11435), separate from the Zork project's. Measured throughput: about
12 answers a second in total, one request at a time; parallel slots do not apply to `nimble` (architecture `qwen35`). Plan the
lookahead around about 4-5 questions per junction transition. Details, setup and the numbers: `tools/ollama/README.md`.

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

Print exactly what a model would see: `python tools/show_prompt.py --game arcade/pacman --level L3b --image games/arcade/pacman/tests/fixtures/pacman_play_ram.bin`.

## Tools

| Tool | Purpose |
|---|---|
| `tools/start_pi_game.py` | start MAME, the exporter and the state server for a game |
| `tools/play.py` | the player loop for any game package |
| `tools/observatory.py` | the dashboard: video, intent, moves and events in the browser |
| `tools/strategist.py` | the slow layer: asks a model for the goal and stance, validates, never blocks |
| `tools/state_client.py` | read the stream; `--measure` times stream and control latency |
| `tools/record_stream.py` | record raw snapshots for offline analysis |
| `tools/game_profile.py`, `tools/discover_state.py` | build a new game's profile and find its RAM (`docs/GAME_STATE_STRATEGY.md`) |
| `tools/probe_mame_input.py` | verify MAME sees the cabinet controls; also the shared SSH helper |
| `tools/configure_mame_controller.py` | one-time controller profile |

Game-specific code and scripts live under `games/<system>/<game>/` (see `games/README.md`).
