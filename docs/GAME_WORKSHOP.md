# Game Workshop: from a ROM to a measured AI player

How a new arcade game is brought into AI Arcade, step by step, with what each step must produce before the next one
starts. Pac-Man is the worked example throughout.

The code layout this assumes is the one in `docs/REFACTOR_PLAN.md`. Where something only exists after a phase of that
plan, it says so (for example "phase 2").

## The question the project asks

Can a small, fast model play an arcade game from the same kind of information a human player has?

The answer is only meaningful if we can say, for every move, whether the model made it. So two things are fixed for
every game:

1. **The model decides.** Every choice of where to go or what to do comes from the model, given facts we compute.
2. **Every move is booked.** Who proposed it, who executed it, how old the answer was, and whether code changed it.

## What code may and may not do

Code may:

- **compute facts** a human would see or feel: distances, threats, which way something is coming from, how long a
  power-up lasts, where an enemy is headed. Facts describe the situation; they do not recommend a move.
- **decide when to ask** the model, and keep answers ready in time (the timing switches below).
- **execute** the model's choice: hold the joystick, follow a corridor, press fire.
- **make purely mechanical moves**: a corridor or corner with only one way on, inserting a coin, pressing start.

Code may not choose between real options, except in two labelled situations:

- **The control.** The rule decider plays the same game with the same facts and no model. It is how we know what the
  facts alone are worth. It is never reported as AI play.
- **A measured helper.** A reflex, a late default or a skill may run in an experiment if it is a switch, it is off in
  the "model alone" runs, and every move it makes is booked against it.

The test for any piece of code: does it change who chooses? If yes, it is an `override` or a `skill` and must be
switchable and booked.

## Where things live

```text
Pi           MAME 0.206 runs the game. Exports chosen RAM regions each frame, streams them, accepts controls.
             Decides nothing. Human mode (EmulationStation) is untouched.
arcadekit/   shared library: answers, ledger, switches, outcomes, report, model clients   (phase 1-2)
  kits/      genre kits shared by games of one kind, e.g. maze games                       (phase 4)
games/<system>/<name>/
             one game: RAM map and decode, facts, knowledge rungs, goals, the play loop, game skills
tools/       command-line programs: start the Pi side, profile, discover, play, compare runs
```

Shared from the start: anything that measures (ledger, report, manifest, outcomes) and the decision runtime (asking,
storing answers, lateness). These must be identical across games or the numbers are not comparable.

Shared later: a genre kit once a second game of that genre exists; a shared play loop only after the third game.

Never shared: one game's enemies, rules, scoring and skills.

## The stages

Each stage has an exit check. Do not start the next stage until it passes; most wasted time comes from building
decisions on state that was never validated.

### Stage 0: feasibility

Questions: does the game run at full speed on the Pi 3 under MAME 0.206, and how fast must a player decide?

- Run the speed test: `python tools/mame_speed_test.py --game <system>/<name>` (stops MAME; not during a game).
- Estimate the decision cadence: how often a real choice comes up, and how much warning there is. Compare it with the
  model's latency: about 80 ms for `tev1:0.8b`, about 250 ms for `nimble` (v13 medians, one request at a time on our
  Ollama server, port 11435).

Exit: full speed, and a written estimate of decisions per second and the warning before each.

Pac-Man: the Pi 3 runs it at about 85% speed (51.4 emulated frames a second against the arcade's 60.6, from the
v3 recording; `play.py` now records `emulated_fps` in every manifest). A junction comes up every few tiles at about 7.6 tiles a second, often only 1 to 3 tiles after the
previous one, so the warning can be under 200 ms. That single fact explains most late answers (`seen_too_late`).

### Stage 1: controls

Questions: what can the player do, and does each action work through the broker?

- `python tools/game_profile.py <romset> --system <system>` writes `profile.json`: controls from MAME's own port list,
  score RAM from hiscore.dat, named variables from cheat.dat.
- Exercise every control through the broker, with no AI involved.
- Measure press-to-effect latency: `python tools/state_client.py --measure` (needs stage 2's decode for the credit
  counter, or any RAM byte that changes on the press).
- Note what the game needs that the broker lacks: two sticks at once, hold-fire-while-moving (the held-set operation,
  phase 3), analog input (not built).

Exit: every control works, and latency is measured.

Pac-Man: four directions, coin, start. One direction is held at a time. Holding a direction into a wall stops
Pac-Man there, which is how he can wait.

### Stage 2: game state

Questions: what can the player observe, and can we read it reliably?

Three layers, kept separate:

| Layer | What it is | Pac-Man |
|---|---|---|
| Raw | bytes in emulated memory | `0x4000..0x4FFF`; the agent export is about 1 KB a frame (`AGENT_REGIONS`) |
| Decoded | what the game itself holds, as named fields | `state.py`: positions, tiles, directions, frightened and eyes flags, score, lives, level, mode |
| Derived | what our code concludes | `features.py`, `ghosts.py`: maze distances, threats per exit, room, ghost targets and routes |

Steps:

1. `python tools/discover_state.py <romset> --system <system>` finds candidates for credits, lives, score and
   position by scripted experiment. Treat position as a shortlist; enemies that chase the player correlate with it.
2. Write the RAM map with a provenance for every field: `source` (original source code), `disassembly`, `mame` (the
   driver), `observed` (validated by experiment), `inferred` (believed, not checked). Never let `inferred` pass as
   fact. Today that is `RAM_MAP.md`; from phase 4 it is `ram_map.json`, and the simple fields are decoded from it.
3. Decode the game's mode: attract, coin, playing, dying or between boards, game over. The play loop and the outcome
   stats depend on it.
4. Decode the outcome fields every game reports: score, level, lives.
5. Validate against recorded play (`tools/record_stream.py`), not only against made-up examples.

Exit: a validation script passes on a recording (Pac-Man: `scripts/validate_pacman_state.py`,
`scripts/validate_ghosts.py`).

Rule from Pac-Man: **every failure found in live play becomes a recorded state and a test.** The head-on deaths were
fixed only after the exact RAM was captured (`tests/fixtures/pacman_headon_ram.bin`).

### Stage 3: the decision

Questions: when does a real choice come up, what are the options, and what facts describe each option?

- **Decision points.** Either events (Pac-Man: a junction tile with more than one way on) or a regular beat (Battlezone:
  every N ms). Everything between decision points is mechanical, and executed by code.
- **Options.** Name them in the game's own terms (`UP`, `LEFT`; for a tank, perhaps `TURN_LEFT`, `FIRE`).
- **Facts per option.** Human-like and measurable: how far the food is, how near and from which side the nearest
  threat is, how much room there is, whether it reverses. A fact never says "best" or "safe to take".
- **Urgent questions.** If something can change the right answer between decision points, ask an extra question then,
  rather than letting code react. Pac-Man's danger query asks "carry on or turn back?" mid-corridor when a ghost is
  close.

Exit: for recorded situations, the facts printed for each option are what a good human would notice, and nothing more.

### Stage 4: knowledge rungs

Questions: how much do we tell the model about the game, and does each addition help?

The rungs are the same for every game; their content is the game's own.

| Rung | Adds | Pac-Man content |
|---|---|---|
| L0 | the current situation only | positions, the options |
| L1 | the rules | scoring, death, energizers, fruit |
| L2 | situation awareness: derived facts | steps to food, threat steps per exit, room |
| L3a | how other actors behave | ghost targeting, scatter and chase |
| L3b | short predictions from those rules | each ghost's target and next 10 tiles |

Knowledge is information. It is not a goal and not a decision.

Exit: the exact text the model receives at each rung can be printed for a recorded state
(`python -m games.arcade.pacman.knowledge`).

### Stage 5: the control player

The rule decider plays with the same facts and goals, with no model. Run it before any model run. It answers two
questions: are the facts good enough to play on, and what is the score to beat?

Exit: a control batch, reported in the standard format (stage 8).

Pac-Man: rule-decider batches scored 3,700 to 7,200 on average across versions; v10 reached level 4 in one game.

### Stage 6: the model player

The model answers the decision questions. Start with every `override` and `skill` switch on, as in the control, then
turn them off one at a time.

Timing work comes first, because a late answer is not the model's move. Tools for it, all `timing` switches that
never choose:

- **Ask ahead**: query a decision point before arriving (Pac-Man: `--lookahead 8` tiles).
- **Chain**: when an answer arrives, ask about the decision point it leads to (`--chain 2`).
- **Urgent lane**: questions whose answer is worthless a moment later jump the queue (`--danger-query`).
- **Check the decision points first.** In Pac-Man most "late" answers were corners seen mid-turn and mistaken for
  junctions; no amount of asking ahead could have caught them. Count late decisions by tile type before tuning timing.
- **Measure timing offline.** The replay (`tests/replay.py`) can answer with a serial server's latency, so a timing
  idea is measured in seconds, not in a batch of games. An answer queue along every branch was tried that way and
  dropped: no gain at 40-80 ms, a small loss at 200-250 ms.
- **Late default**: `--late rule` lets the rule decide; `--late keep` changes nothing and waits for the model, which
  with the reflex off is the model alone.

Choose the model for the cadence. In v13, `tev1:0.8b` (80 ms) made 69% of Pac-Man's junction decisions itself (86%
of the real junctions once corners are left out); `nimble` (250 ms) made 31%, because 67% of its answers were late.
To judge a slow model's choices without the latency handicap, run the game slower (`start_pi_game.py --speed 0.5`).

Exit: a model batch and a "model alone" batch (every `override` and `skill` off), both in the standard format.

### Stage 7: the slow layer (optional)

A second, slower question: what to aim for (the goal) and how to play (the stance: caution, chase, greed). Asked
about once a second, held for a few seconds, never blocking the fast loop. The game supplies the schema and a text
summary of the situation; `arcadekit/strategist.py` (today `tools/strategist.py`) asks and validates.

Strategy is a decision layer, not knowledge. A run where only the slow layer is a model must be reported as exactly
that: "the model set goals; the rule decider chose every direction".

### Stage 8: evaluation

Every run writes:

- **a manifest**: commit (and whether the tree was dirty), game, decider and model with its digest, knowledge rung,
  strategist, every switch with its kind, seed, games asked for and completed;
- **a decisions log**: one line per question, answer and executed move, with the frame number so it lines up with a
  recording;
- **game results**: outcome fields, per-life seconds and score, and the game's own metrics.

Reported for every batch:

| Group | Contents |
|---|---|
| Outcome | score per game, mean and spread, level reached, boards cleared, seconds and score per life |
| Agency | moves by `by` (below), **the model's own %**, late reasons |
| Feasibility | median and maximum model latency, answers per second |
| Game skills | the game's declared metrics (Pac-Man: ghosts per energizer, fruit, reflex firings, parks, refuges) |

`tools/compare_runs.py` (phase 2) puts batches side by side.

## The switches

Every switch a game offers has one kind (`arcadekit/options.py`, phase 2):

| Kind | May | Pac-Man |
|---|---|---|
| `facts` | change what the model is told | `--knowledge`, the stance text |
| `timing` | change when the model is asked; never choose | `--lookahead`, `--chain`, `--danger-query` |
| `override` | change or replace a proposed move | reflex (`--no-reflex` turns it off), `--revise`, late default (`--late`, phase 2) |
| `skill` | steer several moves on its own | `--park`, `--refuge` |

Every `override` and `skill` has an off position. Defaults are documented in `docs/AI_MODE.md`.

## Who made a move

| `by` | Meaning | The model's own |
|---|---|---|
| `model` | the model's answer, executed as given | yes |
| `rule` | the rule decider, in a control run | no |
| `code-late` | no answer in time; the late default decided | no |
| `code-fallback` | the model failed or was unsure; code decided | no |
| `code-override` | code changed a proposal (`via` says which: `reflex`, `revise`) | no |
| `code-skill` | a code skill steered (`via`: `park`, `refuge`) | no |

Mechanical moves are not booked. Today's labels (`reflex-override`, `code-hold`, `model-danger`) map onto these one
to one; see `docs/REFACTOR_PLAN.md`.

## Running experiments

- **Change one thing per batch.** A new model, rung, switch or game version, not two.
- **Batch size.** Three games is enough to spot a large effect, not a small one. Pac-Man scores within one batch
  ranged from 2,860 to 4,770. Report the spread, not only the mean, and say how many games.
- **Same model server, same load.** One model loaded at a time on our Ollama (port 11435); answers are served one at
  a time (about 12 a second for `nimble`). Do not run another model workload during a batch.
- **Say exactly what played.** Not "the AI scored 4,000". Instead: "`tev1:0.8b` chose junction directions at L2;
  code set goals; the survival reflex was on and changed 7% of moves; the model's own: 69%; mean 4,023 over 3 games
  (2,860 to 4,770)."

## Pac-Man: what the reference taught us

| Lesson | Evidence |
|---|---|
| Runs labelled "AI" can be entirely code | v2 to v12 used the rule decider; provenance was added to stop that happening silently |
| Check what counts as a decision before blaming latency | 83% of `tev1:0.8b`'s late decisions in v13 were corners mistaken for junctions |
| Latency, not judgment, is the first wall for a slow model | `nimble`: 67% of junction decisions late in v13 (45% of those were corners) |
| A smaller, faster model can beat a bigger one in real time | `tev1:0.8b` made 69% of its own moves vs 31% for `nimble`, at a similar score |
| The reflex was doing much of the surviving | the same model with the reflex off: mean 2,373 vs 4,023 (v14 vs v13) |
| Being asked is not the same as understanding | danger query, reflex off: asked 65 times, turned back once, carried on 47 times; no score gain |
| Without the reflex, the first life ended the same way every game | v14: all six games lost the first life at 9 s with 160 points; a deterministic ghost route, worth a recorded fixture |
| A "safe spot" needs its real conditions in the facts | refuge: 3 entries, 3 deaths (v12). It only works if no ghost is already routed into it and Pac-Man arrives facing up |
| Bugs from live play make the best tests | head-on deaths, junction flip-flop and stale answers were each fixed from a captured state |

## Checklist for a new game

- [ ] Stage 0: full speed on the Pi; cadence estimate written down
- [ ] Stage 1: `profile.json`; every control exercised; latency measured
- [ ] Stage 2: RAM map with provenance; decode; mode detection; outcome fields; validated on a recording
- [ ] Stage 3: decision points, options and facts; printed for recorded situations
- [ ] Stage 4: rungs L0 to L2 at least; prompt printable
- [ ] Stage 5: control batch reported
- [ ] Stage 6: model batch and model-alone batch reported, with the model's own %
- [ ] Stage 7 (optional): slow layer, reported as such
- [ ] Stage 8: manifest, decisions log and results for every batch; compared with `compare_runs.py`
- [ ] Shared code used, not copied: answers, ledger, switches, outcomes, report
- [ ] The game's cost recorded: new lines, reused lines, days (feeds the next genre kit decision)

## Next games

1. **Ms. Pac-Man**: same hardware family. Measures the cost of a sibling game, and is when the maze kit gets
   extracted (phase 4).
2. **Battlezone**: two tank sticks, a continuous world, decisions on a beat. Tests how far the workshop stretches
   (phase 5).
