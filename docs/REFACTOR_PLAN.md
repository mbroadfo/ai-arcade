# Refactor plan: from one game to many

Status, 2026-10-01: phase 0 done (`0cea045`); phase 1 done (`1dcfc91`, `43f8e04`, `15e08f0`) except `OutcomeStats`,
which moves with the report in phase 2. `player.py` is 490 lines after phase 1, not the 300 estimated: what remains
is mostly Pac-Man's own (holds, the danger query, the reflex).

## Why now

Pac-Man was built as the prototype, so the shared parts and the Pac-Man parts grew up in the same files. That was the
right way to start. It stops being right the moment a second game is added: whatever is shared but lives inside
`games/arcade/pacman/` gets copied, the copies drift, and every later game adds another copy to keep in step. The cost
of that grows with every game.

The thing that must not drift is the measurement. The project's question is "how much of the play is the model's own?"
That answer is only comparable across games if every game books its moves with the same code, the same labels and the
same late reasons. Today that code lives in `games/arcade/pacman/player.py`.

The goal of this plan is more reuse where it is safe and clearly pays, and no generalising on speculation.

## What is already shared and stays as it is

These know nothing about Pac-Man and need no change beyond the small gaps listed in phase 3:

| Part | File |
|---|---|
| RAM export on the Pi (any regions, refreshed every N frames) | `tools/mame_state_export.lua` |
| State stream, Pi to PC (raw bytes, newest snapshot wins) | `pi/state_server.py`, `tools/state_client.py` |
| Controller broker and its PC link (named actions) | `pi/controller_broker.py`, `tools/broker_link.py` |
| Finding and loading a game package | `tools/gamelib.py` |
| Profile from MAME's ports, hiscore.dat and cheat.dat | `tools/game_profile.py` |
| RAM discovery by scripted experiment | `tools/discover_state.py` |
| Model client (Ollama `/v1/systemone`) and the mock | `tools/systemone.py` |
| Answers off the control loop, with an urgent lane | `tools/decision_worker.py` |
| The slow layer (goal and stance), given a game's schema | `tools/strategist.py` |
| Run manifest (commit, models and digests, switches) | `tools/run_manifest.py` |

## Where Pac-Man and shared code are mixed

| Problem | Where | Cost if left |
|---|---|---|
| The decision runtime (ask ahead, store answers, drop stale ones, use each once, classify late answers, the urgent lane) is inside the Pac-Man player | `games/arcade/pacman/player.py`, about half of its 508 lines | copied into every game's player; drifts |
| Move booking (`_book_move`, `MOVE_LABELS`, `stats["moves"]`) is inside the Pac-Man player | same | provenance labels differ per game; "the model's own %" stops being comparable |
| The generic part of the model decider (ask a choice question, fall back on error or low confidence) is mixed with Pac-Man's question text | `games/arcade/pacman/deciders.py` | copied per game |
| Shared code has no home that games may import (`games/README.md`: games never import from `tools/`) | repository layout | every reuse becomes a copy |
| `play.py` has Pac-Man flags: `--park`, `--refuge`, `--danger-query`, `--chain` | `tools/play.py` | every game adds flags to the shared tool |
| The manifest's `SWITCHES` names Pac-Man switches | `tools/run_manifest.py` | same |
| The run summary prints Pac-Man metrics (`feasts`, `ghosts_eaten`, `energizers`, `parks`...) | `tools/play.py` | same |
| The RAM image defaults to Pac-Man's window, 0x4000..0x4FFF | `tools/state_regions.py` `expand()`, called with defaults by `state_client.py` and `record_stream.py` | a second game silently gets a wrong image |
| The exporter reads only `:maincpu` program space | `tools/mame_state_export.lua`, `tools/mame_snapshot_service.lua` | games whose state is on another CPU or address space cannot be read |
| The broker link holds exactly one direction | `tools/broker_link.py` `steer()` | games with two sticks (Battlezone) or fire-while-moving cannot be played |
| The rule filling in for a late answer has no off switch | `player.py`, the `steps == 0` branch | the largest helper of all (67% of `nimble`'s junction decisions in v13) cannot be ablated |
| "Game over / attract / playing / dying" is read from a raw Pac-Man address inside the player loop | `player.py` `image[0x4E04 - 0x4000]` | fine inside Pac-Man; a generic loop would need it from the game |
| Run comparison is done by hand, grepping `.out` files | none | slow, and error-prone once there are many games |

## The target layout

```text
pi/                     unchanged: runs MAME, exports RAM, streams state, accepts controls
tools/                  command-line programs only (play, start_pi_game, discover_state, game_profile, compare_runs, ...)
arcadekit/              NEW: the shared library. Games and tools may import it. It never imports a game.
  decisions.py            Decision, DecisionWorker (moved from tools/), ChoiceDecider
  answers.py              AnswerBook: ask ahead, store, single use, max age, late reasons, urgent questions
  ledger.py               who made each move: the fixed vocabulary, booking, summary, "the model's own %"
  options.py              Option: how a game declares its switches and what kind each is
  outcome.py              OutcomeStats: score, level, lives, seconds and score per life, boards
  report.py               the run summary from a ledger, outcomes and the game's declared metrics
  manifest.py             build_manifest (moved from tools/run_manifest.py)
  strategist.py           moved from tools/
  systemone.py            moved from tools/
  kits/                   genre kits, created only when a second game of the genre exists (phase 4)
games/<system>/<name>/  one game: RAM map, decode, facts, knowledge, goals, the game's player loop, skills
```

Import rules:

- `arcadekit` imports nothing from `games/` or `tools/`.
- A game imports from `arcadekit` and from its own package only.
- `tools/` imports `arcadekit` and loads games through `gamelib.load_game()`.

The moved modules keep a one-line re-export in `tools/` for one release so nothing breaks while the change settles,
then the re-exports go.

### Library, not framework

The game keeps its own play loop and calls the shared pieces. There is no generic `Player` base class yet.

Pac-Man's loop is shaped by junctions and corridors. Battlezone's will be shaped by a regular beat, and we have not
seen a third game. A shared loop written now would be shaped like Pac-Man and would need retrofitting. The rule:
**extract a shared loop after the third game, when there are three real loops to compare.** The pieces it would be
made of (answer book, ledger, worker, decider) are shared from the start, so that later extraction is small.

## The fixed vocabularies

These are the contract that makes games comparable. They live in `arcadekit` and a game cannot add to them without
changing the library (and its tests).

### Who made a move (`ledger.py`)

Every executed decision is booked once with `by` and `via`:

| `by` | Meaning | Counts as the model's |
|---|---|---|
| `model` | the model's answer, executed as given | yes |
| `rule` | the rule decider, in a control run | no (it is the control) |
| `code-late` | no answer in time; the late default decided | no |
| `code-fallback` | the model failed or was unsure; code decided | no |
| `code-override` | the model (or rule) proposed, code changed it | no |
| `code-skill` | a code skill steered on its own (wait, hide) | no |

`via` names the question or helper: `junction`, `danger`, `reflex`, `revise`, `park`, `refuge`, and so on. A game
may add `via` names; it may not add `by` values. Forced single-exit moves and coin/start are mechanical and not booked.

Today's labels map one to one, so v13/v14 logs stay comparable:

| Today | New |
|---|---|
| `model` | `by=model via=junction` |
| `model-danger` | `by=model via=danger` |
| `rule` | `by=rule via=junction` |
| `code-late` | `by=code-late via=junction` |
| `code-fallback` | `by=code-fallback via=junction` |
| `reflex-override` | `by=code-override via=reflex` |
| `code-revise` | `by=code-override via=revise` |
| `code-hold` | `by=code-skill via=park` or `via=refuge` |

The headline number stays "The model's own: N%" = `by=model` over all booked moves.

### What a switch does (`options.py`)

Each game declares its switches. Each switch has exactly one kind, chosen by the question "does it change who chooses?":

| Kind | What it may do | Pac-Man examples | Booking |
|---|---|---|---|
| `facts` | change what the model is told | `--knowledge L0..L3b`, the stance text | none |
| `timing` | change when or how often the model is asked; never chooses | `--lookahead`, `--chain`, `--danger-query`, the future answer queue (NBA) | the model's answers are booked as `model` |
| `override` | change or replace a proposed move | `--reflex`, `--revise`, `--late rule` | `code-override` or `code-late` |
| `skill` | steer several moves on its own | `--park`, `--refuge` | `code-skill` |

`play.py` builds its command line from these declarations, passes them to the game's player, and the manifest records
each switch with its kind. Every `override` and `skill` switch must have an off position, which is what makes a "model
alone" run possible.

## Phases

Each phase ends with all tests passing and Pac-Man behaving the same, unless the phase says otherwise.

### Phase 0: a safety net that proves "nothing changed"

The 192 tests check pieces. A refactor of the play loop needs a check of the whole.

1. Give `Player` an injectable clock (`clock=time.time`), so a replay can run with recorded time.
2. Add a replay test: feed a recorded stream through the Pac-Man player with the rule decider answering at once, and
   compare the resulting move log with a stored one. Source: a trimmed piece of `runs/v3.pkl` (only the agent regions,
   so about 1 KB a frame; 60 seconds is about 3.8 MB before compression), stored as a fixture.
3. Record the stored log before phase 1 starts. Any later difference is either a bug or a deliberate change that
   updates the stored log in the same commit, with the reason.

Done when: the replay test passes on the current code and fails if a decision rule is changed.

### Phase 1: a home for shared code; move the decision runtime and ledger

Behaviour-preserving. No new features.

1. Create `arcadekit/` and add it to `pytest.ini`'s paths.
2. Move `decision_worker.py`, `systemone.py`, `strategist.py`, `run_manifest.py` into it (re-exports left in `tools/`).
3. `Decision` moves to `arcadekit/decisions.py`, with `choice` in place of `direction` (a direction is Pac-Man's word).
   Pac-Man's code and tests are renamed mechanically.
4. `ChoiceDecider(client, question, fallback)`: the generic half of `SystemOneDecider`. Pac-Man supplies `question(facts,
   goal)`, which returns its instructions and option descriptions.
5. `AnswerBook`: the plan store, max age, single use, the urgent lane and the late reasons (`seen_too_late`,
   `in_flight`, `other_arrival`, `not_asked`), moved out of `player.py`. The chain stays in Pac-Man, as a hook the
   book calls ("an answer arrived; what should be asked next?"), because what follows a junction is maze knowledge.
6. `Ledger`: `_book_move`, the vocabularies above, and the per-run move counts, moved out of `player.py`.
7. `OutcomeStats`: the game-independent half of `GameStats` (score, level, deaths, per-life log, boards). Pac-Man's
   `GameStats` keeps ghosts, fruit, energizers, feasts, parks, refuges and adds the outcome block.

Done when: tests and the replay check pass unchanged; `player.py` is mostly Pac-Man.

### Phase 2: games declare their switches and metrics; `play.py` becomes generic

1. Pac-Man declares `OPTIONS` (switches with kinds) and `METRICS` (result keys with a short description).
2. `play.py` builds its game-specific arguments from `OPTIONS` (in a group named after the game) and its summary from
   `arcadekit/report.py`. The Pac-Man flags keep their names and defaults, so existing commands still work.
3. The manifest records every switch with its kind instead of the fixed `SWITCHES` list.
4. New switch: `--late rule|keep` (kind `override`). `rule` is today's behaviour and stays the default. `keep` makes
   the late default "carry on the way you are going", a non-choice, so a model-alone run is possible. This changes
   behaviour only when used.
5. `tools/compare_runs.py`: reads manifests and game results and prints a comparison table (mean, spread, the model's
   own %, late reasons, median latency, per-life seconds), replacing grepping `.out` files.

Done when: `play.py` contains no Pac-Man names; the v13/v14 runs can be compared with `compare_runs.py`.

### Phase 3: MAME and transport gaps

1. Regions may name a device and address space (`(start, end, every, ":maincpu", "program")`, defaults as today).
   The exporter and snapshot service read per region.
2. The RAM image window comes from the game (`IMAGE = (base, size)`), not from `expand()`'s defaults. The defaults are
   removed so a game that forgets fails loudly.
3. The broker gets a held-set operation (`{"op": "hold", "actions": [...]}`: press exactly these, release the rest).
   `BrokerLink.hold(set)` replaces `steer()` in shared code; Pac-Man's single direction becomes `hold({d})`.
   This changes the Pi: it goes through `tools/install_pi.py`, per the README's development rule, and needs your
   go-ahead before it is deployed.
4. `mame_speed_test.py` moves from `games/arcade/pacman/scripts/` to `tools/`: any game's emulation speed on the
   Pi 3 under MAME 0.206 is the first feasibility check.

Done when: Pac-Man plays as before through the new paths; a two-direction hold works in the controller test.

### Phase 4: a sibling game measures the cost of a new game (Ms. Pac-Man)

Ms. Pac-Man is the cheapest real test of reuse: same hardware family, different mazes, RAM and ghost behaviour.

1. Bring it up through the workshop (`docs/GAME_WORKSHOP.md`).
2. Only now extract `arcadekit/kits/maze/`: the tile maze (BFS, exits, the walk to the next decision point), the
   ask-ahead chain, and the per-option facts that both games share. Pac-Man is changed to use it, and the replay
   check proves it unchanged.
3. Trial a declarative RAM map: a `ram_map.json` per game with each field's address, type and provenance (`source`,
   `disassembly`, `mame`, `observed`, `inferred`), from which the simple fields are decoded. Derived facts stay code.
4. Record the cost: new lines, reused lines, days. That is the number that says whether hundreds of games are
   realistic, and which kit is worth building next.

Done when: Ms. Pac-Man has a control run and a model run reported with the model's own %, and the cost is recorded.

### Phase 5: Battlezone tests the breadth

Battlezone breaks the most Pac-Man assumptions: a continuous world, two tank sticks used together, decisions on a
regular beat instead of at junctions, vector rendering, a math co-processor.

1. Feasibility first: full speed on the Pi 3, both sticks through the broker's held set.
2. A decision on a beat: the answer book is asked on a timer instead of at junction tiles. If that needs a change to
   `AnswerBook`, that is the finding.
3. Its own facts (bearing, range, closing speed, firing alignment), knowledge rungs and metrics, through the same
   ledger and report.

Done when: Battlezone has a control run and a model run in the same report format as Pac-Man.

### After the third game

Compare the three play loops. Extract a shared loop only if they share a real shape.

## Sequencing with the model-first work

The model-first work (keeping the model from being late, park and hide and chase as model choices, the
reflex as a measured option) would otherwise be built inside `player.py` and then moved. Doing phases 0 to 2 first puts
it in the right place from the start: asking ahead belongs in `AnswerBook`, and new model choices are booked through
the `Ledger`. Phases 3 to 5 can interleave with it.

Measured since: most late decisions were corners mistaken for junctions (fixed in `18371ae`). After that fix the
replay with a serial model server answers 96-97% of junctions in time at 40-80 ms. An answer queue that asks ahead
along every branch gained nothing there and slightly hurt at 200-250 ms (it loads the one-at-a-time server), so it
was not kept. `--late keep` (`5e21701`) makes a model-alone run possible.

## What we deliberately do not build

- **A canonical game state.** Each game keeps its own state dataclass. Only the outcome fields (score, level, lives,
  mode) are standardised, because the report needs them. A universal state schema would be shaped by the first two
  games and wrong for the third.
- **A shared play loop**, until the third game (above).
- **Generic enemy prediction.** Ghost targeting and tank behaviour have nothing in common.
- **Analog input.** Added when a game needs it (Tempest, Star Wars), not before.
- **Moving Pac-Man's skills into the library.** Park and refuge are Pac-Man's, and the aim is for them to become model
  choices anyway.

## Risks

| Risk | Guard |
|---|---|
| A refactor changes play without anyone noticing | phase 0 replay check, run on every phase |
| Old logs become unreadable | log field names stay; the label mapping table above; `compare_runs.py` reads both |
| Import churn breaks scripts | re-exports in `tools/` for one release |
| Pi change breaks human mode or the controller | phase 3 broker change goes through the installer and the existing controller tests, with your go-ahead |
| Generalising too early | the rule: shared from the start only what is already proven common (measurement and the decision runtime); everything else at the second or third game |

## Documents

- `docs/GAME_WORKSHOP.md` (new) replaces `docs/GAME_LEARNING_WORKSHOP.md`, and is written against this layout.
- `games/README.md` (the adapter contract table) is updated in phases 1 and 2 as the contract changes.
- `docs/AI_MODE.md` stays the operator's guide to running Pac-Man; the provenance and switch sections move to the
  workshop doc in phase 2 and are linked from there.
- `docs/AI_ARCADE_ARCHITECTURE.md` (1,295 lines, from the first scaffold) describes a director, a canonical state and
  layers that this plan deliberately does not build. It should be cut down to what is true or retired; that is your
  call.
