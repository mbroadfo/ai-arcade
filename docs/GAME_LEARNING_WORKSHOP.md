# AI Arcade: Build the Game Learning Workshop

We are reaching the point where Pac-Man should stop defining the architecture.

The next step is to turn what we have learned into a reusable **Game Learning Workshop** for adding and evaluating new arcade games.

The workshop should be organized around four first-class concerns:

# Controls → Game State → Knowledge → Evaluation

The goal is not to create a giant universal game abstraction.

The goal is to make adding a new game disciplined, repeatable, measurable, and understandable.

Pac-Man is the reference implementation.

Battlezone will be the first serious test of whether the workshop generalizes.

---

# 1. Controls

## Question

> What can the player do?

Controls define the game's **action space**.

The generic runtime should work with semantic actions rather than physical joystick/button numbers.

Examples:

Pac-Man:

    UP
    DOWN
    LEFT
    RIGHT
    COIN
    START

Battlezone might expose actions such as:

    LEFT_TRACK_FORWARD
    LEFT_TRACK_REVERSE
    RIGHT_TRACK_FORWARD
    RIGHT_TRACK_REVERSE
    FIRE
    COIN
    START

Do not force radically different games into Pac-Man's directional abstraction.

The game package should define:

- semantic actions
- valid simultaneous actions
- mutually exclusive actions
- tap versus hold behavior
- analog versus digital controls
- special controls such as fire
- coin/start behavior
- mapping to MAME inputs
- expected control latency

## Workshop requirement

A new game should have a clear Controls artifact/configuration describing its action space.

There should also be a validation procedure proving that every declared control actually affects the running game correctly.

Ideally the workflow becomes something like:

    describe controls
          ↓
    map semantic actions to MAME
          ↓
    execute automated/manual control test
          ↓
    measure action-to-state latency
          ↓
    mark Controls validated

Do not mix control validation with AI logic.

---

# 2. Game State

## Question

> What does the player know about what is happening?

Game State defines the game's **observation space**.

We need to preserve a strong separation between three layers.

## A. Raw State

What the emulator actually exposes.

Possible sources include:

- CPU RAM
- video RAM
- sprite/object tables
- vector RAM
- memory-mapped devices
- registers
- coprocessor state
- game-mode flags

Raw state should retain provenance.

For every important memory field, we should be able to say how we know what it means:

    original source
    map/symbol file
    disassembly
    MAME
    direct observation
    inference

Inference should never silently become fact.

---

## B. Decoded State

Raw emulator state translated into named game concepts.

For Pac-Man:

    pacman.position
    pacman.direction
    ghost positions
    frightened flags
    score
    level
    lives
    dots eaten

For Battlezone this may become:

    player heading
    player motion
    object records
    enemy type
    enemy position
    enemy heading
    projectile state
    score
    lives

Decoded State should represent facts that are directly present in, or directly recoverable from, the game's internal state.

The decoder should be independently testable.

The generic pipeline should conceptually be:

    emulator state
         ↓
      decode()
         ↓
    semantic GameState

Do not require the AI player in order to validate the decoder.

---

## C. Derived State / Features

This is information computed from decoded state.

Pac-Man examples:

    path distance to ghost
    nearest food
    available exits
    threat direction
    junction structure

Battlezone examples:

    relative bearing
    target range
    closing rate
    firing alignment
    obstacle sector
    threat ranking

This distinction is important:

> Decoded State is what the game knows.

> Derived State is what our workshop computes from what the game knows.

Do not collapse them into one opaque blob.

---

# 3. Knowledge

## Question

> What are we teaching the player about how the game works?

Knowledge must remain separate from current Game State.

State answers:

> What is happening now?

Knowledge answers:

> What does it mean and how does the game work?

Pac-Man has already established the beginning of a useful experimental model.

Formalize that idea as reusable **knowledge rungs**.

The exact information will differ by game, but the meaning of the rungs should remain reasonably consistent.

---

## L0 — State Only

Give the model the minimum semantic observation.

Coordinates, flags, available actions, current state.

No game instruction beyond what is required to interpret the values.

Question:

> What can a fast model learn or infer almost entirely from current state?

---

## L1 — Rules

Add static game knowledge:

- objective
- scoring
- death conditions
- level completion
- important objects
- special mechanics
- control meaning

Question:

> How much improvement comes simply from explaining the game?

---

## L2 — Situation Awareness

Add derived perception.

This should generally be egocentric and decision-oriented, but not strategy.

Examples:

Pac-Man:

    ghost 4 steps ahead
    nearest food through LEFT
    UP leads toward danger
    RIGHT is a reversal

Battlezone:

    tank 25 degrees left
    range 380
    projectile closing from front-right
    obstacle immediately behind target

Question:

> How much does code-derived perception help the model make good reactive choices?

---

## L3a — Behavioral Knowledge

Add known behavior of other game actors or game mechanics.

Pac-Man:

    ghost targeting rules

Battlezone:

    enemy movement or firing behavior, if documented

Question:

> Does knowing how the world behaves improve decisions?

---

## L3b — Prediction

Add state-derived short-horizon forecasts.

Pac-Man:

    ghost target
    predicted ghost route

Battlezone:

    estimated enemy trajectory
    projected collision
    firing opportunity
    projected threat sector

Question:

> Is prediction worth the additional complexity?

---

## L4 — Expert / Rule Baseline

L4 is not knowledge supplied to a model.

It is the deterministic control player.

Its purpose is to answer:

> How close does the learned/model-based player get to a hand-coded expert?

Do not blur L4 into the model experiments.

---

# 4. Evaluation

## Question

> How well did the player perform, and who was actually responsible for that performance?

Evaluation needs to become a first-class part of every game package.

Score alone is not enough.

There should be three layers of evaluation.

---

## A. Outcome Metrics

What happened in the game?

Examples:

- score
- level/wave reached
- boards completed
- progress toward level completion
- survival time
- objective completion

These should be mostly game-specific.

---

## B. Skill Metrics

Did the player demonstrate the skills the game rewards?

Pac-Man examples:

- dots eaten
- total maze progress
- fruit shown/eaten/missed
- ghosts eaten
- ghosts eaten per energizer
- score per life
- dots per life

Battlezone examples might include:

- tanks destroyed
- super tanks destroyed
- missiles destroyed
- hit rate
- shots fired
- survival time
- average threat distance
- deaths from projectile vs collision

The game package should define these.

---

## C. Agency / Decision-System Metrics

This is critical.

We need to know not only how well the whole system performed, but whether the **model itself** was responsible.

The Pac-Man runs already show why.

A System One player may achieve a good score while:

- model answers arrive late
- a rule fallback chooses instead
- stale plans are revised
- a survival reflex vetoes the model
- control code follows corridors automatically

Without agency metrics, a strong safety layer can make a weak model look good.

Every meaningful decision should therefore preserve provenance.

Conceptually:

    observation
        ↓
    model proposal
        ↓
    possible fallback
        ↓
    possible revision
        ↓
    possible safety/reflex override
        ↓
    executed action

A decision record should make this lineage clear.

For example:

    junction / decision point
    current goal
    available actions

    proposed action
    proposal source
    confidence
    model latency

    fallback action, if any
    revision, if any
    safety override, if any

    final executed action

From this we should be able to calculate:

- model autonomy %
- model action executed unchanged %
- late decision %
- fallback %
- safety/reflex override %
- stale-plan revision %
- median decision latency
- max decision latency
- confidence distribution
- control latency

This distinction is essential for evaluating L0/L1/L2/L3 fairly.

---

# Run Manifest

Every experiment should persist enough information that we can understand it months later without decoding the filename.

Each run should produce a manifest containing at least:

    timestamp
    game
    ROM set
    git commit SHA
    MAME version if practical

    decider type
    model
    knowledge level
    goal mode

    lookahead / timing parameters
    confidence threshold
    random seed if relevant

    requested game count
    completed game count

    any significant game/player configuration

Do not rely on names such as:

    v2
    v3
    trial
    tev1small2

to preserve experimental meaning.

---

# Workshop Output Structure

A game package should eventually make these four areas visible.

Conceptually:

    games/<system>/<game>/

        controls
            semantic action definition
            mappings
            validation

        state
            exported regions
            decoder
            state schema
            provenance
            validation

        knowledge
            L0
            L1
            L2
            L3a
            L3b

        evaluation
            game metrics
            event detection
            result summary

        player
            optional game-specific interaction loop
            rule/expert baseline

Exact filenames and modules are up to you.

Do not reorganize purely for aesthetic consistency if the current package already has sensible boundaries.

The conceptual contract matters more than directory purity.

---

# Pac-Man Wrap-Up Task

Use Pac-Man to make the workshop concrete.

Do not spend the next phase primarily making Pac-Man play better.

Instead review the existing Pac-Man package and current run logs and ask:

## Controls

- Is the action space explicitly defined?
- Can each control be independently validated?
- Are semantic actions clearly separated from MAME mappings?

## Game State

- Is raw vs decoded vs derived state clear?
- Is field provenance documented?
- Is decoder validation sufficient?
- Is anything in generic tooling secretly Pac-Man-specific?

## Knowledge

- Are L0/L1/L2/L3a/L3b clearly reproducible?
- Can we print exactly what a model receives?
- Can the same run be repeated with only the knowledge rung changed?

## Evaluation

- Are outcome metrics persisted?
- Are Pac-Man-specific skill metrics persisted?
- Are decision-system metrics persisted?
- Can we distinguish proposed actions from executed actions?
- Can we determine how often the rule player or reflex layer rescued the model?
- Is experiment configuration stored in a manifest?

Fix gaps that materially affect the workshop.

Avoid polishing unrelated Pac-Man strategy.

---

# Current Pac-Man Evaluation Findings To Consider

Recent run analysis exposed several useful lessons.

We are already persisting useful game statistics such as:

- score
- level
- dots
- duration
- ghosts eaten
- energizers
- feast sizes
- fruit shown/eaten/missed
- reflex events
- goal time

Decision logs also include:

- chosen direction
- source
- confidence
- latency
- probabilities
- chain depth
- late fallbacks
- revisions
- reversals
- reflexes

However, some run-level system metrics are still primarily console output rather than durable structured experiment metadata.

Also, the current `revised` count can overcount the same logical revision across repeated ticks near one decision point.

Treat this as a logging-semantic issue:

> decide whether the metric means “frames overridden” or “logical decisions revised.”

Prefer logical decision/event counts for experiment comparison.

Most importantly, preserve **final executed-action provenance** so a model's actual autonomy can be measured.

---

# Battlezone As Workshop Validation

Once Pac-Man makes the workshop contract clear, add Battlezone.

The goal is not initially to build a strong Battlezone bot.

The goal is to determine whether the same four-part workshop applies cleanly to a radically different game.

Battlezone challenges assumptions because it has:

- different controls
- continuous rather than tile-based geometry
- vector graphics
- 6502 plus Mathbox hardware
- world/object state rather than a maze
- firing decisions as well as movement decisions

Use the workshop in order:

    Controls
        ↓
    Game State
        ↓
    Knowledge
        ↓
    Evaluation

Do not begin with strategy.

---

# Battlezone Stage 1 — Controls

Identify and validate its semantic action space.

Do not force it into Pac-Man abstractions.

Document control combinations and timing.

Confirm that generic broker/control infrastructure is sufficient.

---

# Battlezone Stage 2 — Game State

Use the unusually strong Battlezone documentation:

- original Atari source
- MAP/DOC files
- schematics
- modern disassembly
- MAME implementation

Build a provenance-backed decoder.

Start with high-confidence state only.

Do not require complete vector-display decoding before creating useful semantic state.

---

# Battlezone Stage 3 — Knowledge

Build L0/L1/L2 first.

Only add behavioral prediction once basic state and evaluation are trusted.

The initial Battlezone System One experiment should be simple enough that we can understand why it succeeds or fails.

---

# Battlezone Stage 4 — Evaluation

Define Battlezone-specific outcome and skill metrics.

Reuse the generic decision-provenance / agency instrumentation.

If Pac-Man and Battlezone can share the same experiment/run-analysis framework while having radically different state and controls, the workshop abstraction is succeeding.

---

# Architectural Rule

Be conservative about moving concepts into generic infrastructure.

When Battlezone disagrees with Pac-Man, first ask:

> Is this a missing universal abstraction?

or:

> Is this simply how Battlezone works?

Only generalize when at least two games demonstrate the same underlying concept.

Pac-Man gives us one example.

Battlezone gives us the first challenge.

A third game will tell us which abstractions are truly general.

---

# Definition of Success

The workshop is successful when adding a game feels like answering four sets of questions:

## Controls

What can I do?

## Game State

What can I observe?

## Knowledge

What do I know about how this world works?

## Evaluation

How do I know whether this player is good, and how much of that performance came from the player itself?

The generic AI Arcade runtime should orchestrate those pieces without knowing whether the game is Pac-Man, Battlezone, Robotron, Asteroids, or something else.

For the next step, please review the current repository against this model and propose the **smallest set of concrete changes needed to make Pac-Man the reference Game Learning Workshop implementation before beginning Battlezone**.

Do not redesign the project wholesale.

Preserve working code.

Prefer explicit contracts, durable experiment metadata, and measurable behavior over abstraction for abstraction's sake.