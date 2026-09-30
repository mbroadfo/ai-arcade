# AI Arcade Architecture

## 1. Purpose

AI Arcade is an experimental layered-intelligence platform for allowing AI systems to select, launch, observe, and play classic games running through emulation.

The project is not intended to build a single end-to-end game-playing model. Instead, it separates gameplay into distinct cognitive and engineering responsibilities so that each layer can be implemented, observed, benchmarked, and replaced independently.

The core research question is:

> Which parts of game-playing intelligence require deliberate reasoning, which are better handled by fast constrained decision models, and which should remain deterministic software?

AI Arcade should support many emulated systems over time, including arcade/MAME titles, NES, Sega, TRS-80, Z-machine games, and other platforms already available through the user's RetroPie/EmulationStation environment.

Pac-Man is the first reference game because it combines a tiny action space with rich problems in navigation, pursuit/evasion, prediction, risk, reward, strategy, and real-time control.

---

## 2. Architectural Principles

### 2.1 Layered intelligence

Do not ask one model to perform all gameplay reasoning.

The system should progressively answer questions such as:

1. What game is running?
2. What is objectively true about the current game state?
3. What aspects of that state are important right now?
4. What behavioral mode should dominate?
5. What strategic objective should be pursued?
6. What destination, enemy, item, or region should be targeted?
7. What immediate action best serves that objective?
8. What emulator/controller input realizes that action?
9. Did the action work?
10. Is the current approach making progress or should control escalate to a slower reasoning layer?

Different technologies should be used for different categories of problems.

### 2.2 Deterministic truth before AI inference

Whenever the emulator can provide exact state, use that exact state.

Do not ask an LLM or vision model to infer information such as position, score, lives, pellets, enemies, health, or inventory when the emulator can expose it directly.

AI inference should operate on top of reliable ground truth.

### 2.3 Selection before generation

Fast gameplay decisions should favor constrained selection among legal actions rather than open-ended text generation.

For Pac-Man, a controller should usually choose among:

- UP
- DOWN
- LEFT
- RIGHT
- NONE

rather than generate free-form instructions.

### 2.4 Escalation instead of constant deep reasoning

Most gameplay should be handled by fast controllers.

A slower reasoning LLM should be invoked only when:

- the system is stuck;
- repeated failures occur;
- a strategic objective needs revision;
- a novel situation appears;
- the current policy becomes uncertain;
- performance analysis indicates a recurring weakness.

### 2.5 Observatory-first design

Every meaningful decision should be observable.

The project should make it possible to understand not only what the AI did, but:

- what state it saw;
- what alternatives it considered;
- which model made the decision;
- what confidence or ranking it produced;
- what objective was active;
- why escalation occurred;
- what the outcome was.

### 2.6 Pluggable intelligence providers

Architectural roles should not be tied to a particular vendor or model.

Examples of possible providers include:

- deterministic rules;
- heuristic scoring;
- Jev;
- Jev-like constrained classifiers;
- Qwen constrained/logit-based selection;
- CLMs;
- dual encoders;
- embedding/reranking models;
- local LLMs;
- hosted reasoning LLMs.

The architecture should define the role first and choose the provider second.

---

## 3. Top-Level System

AI Arcade consists of several major subsystems:

### 3.1 Arcade Director

The Arcade Director operates above any individual game.

Responsibilities:

- discover installed games;
- maintain a catalog of games and supported adapters;
- choose a game to play;
- launch the game through EmulationStation or the emulator;
- recognize when the game has started;
- attach the correct Game Adapter;
- detect game-over or exit;
- return to the frontend;
- select the next game or retry;
- eventually decide what skill/game deserves additional practice.

The Arcade Director is the beginning of meta-level intelligence across games.

### 3.2 Emulator Adapter

The Emulator Adapter handles emulator-specific operations.

Responsibilities may include:

- launch a game;
- stop or pause a game;
- send controller inputs;
- capture framebuffer/screenshots;
- expose frame or tick timing;
- inspect emulator memory;
- inspect registers or memory regions;
- expose emulator events;
- interact with emulator scripting/debugger APIs.

Examples:

- MAME adapter;
- RetroArch adapter;
- FBNeo adapter;
- standalone emulator adapter.

The Emulator Adapter must not contain Pac-Man-specific or game-specific semantics.

### 3.3 Game Adapter

The Game Adapter translates emulator-specific state into game-specific meaning.

For Pac-Man, the adapter may decode:

- Pac-Man position;
- Pac-Man direction;
- ghost positions;
- ghost directions;
- ghost states;
- pellet map;
- power-pellet state;
- score;
- lives;
- level;
- fruit state;
- frightened timer.

The Game Adapter creates a normalized Canonical Game State consumed by the intelligence layers.

### 3.4 Intelligence Stack

The Intelligence Stack converts Canonical Game State into actions.

It contains both fast System-One-style components and slower reasoning components.

### 3.5 Controller Output

The Controller Output layer translates abstract actions into actual emulator input.

Examples:

- HOLD LEFT;
- PRESS FIRE;
- RELEASE UP;
- JOYSTICK NORTH;
- BUTTON A.

### 3.6 Observatory and Event Bus

All components publish their decisions and state changes through a common event/telemetry system.

This enables:

- live dashboard visualization;
- complete decision lineage;
- post-run analysis;
- comparison among models and architectures;
- failure attribution.

---

## 4. Game Catalog and Capability Model

AI Arcade may contain hundreds of games, but not every game will have the same level of instrumentation.

Each game should advertise capability levels.

### Level 0 — Launchable

The system can launch and exit the game.

### Level 1 — Controllable

The system can send controller inputs.

### Level 2 — Screen Observable

The system can capture the framebuffer.

### Level 3 — Basic Telemetry

Basic state such as score, lives, player position, or game-over state is available.

### Level 4 — Structured Game State

Rich state is available, including enemies, map information, objects, timers, and legal actions.

### Level 5 — Full Cognitive Adapter

The game exposes enough semantics to support layered tactical, strategic, risk, and progress models.

Pac-Man should be developed toward Level 5 first.

---

## 5. Canonical Game State

Every Game Adapter should expose a normalized state object.

The exact schema will evolve, but conceptually it should include:

### Session

- game identifier;
- platform;
- emulator/core;
- ROM/revision identifier;
- game tick/frame;
- elapsed time;
- score;
- level/stage;
- lives;
- game-over state.

### Player

- position;
- velocity if relevant;
- direction/facing;
- current movement state;
- health or equivalent resource;
- current weapon or capability if applicable.

### World

- static map/topology;
- obstacles;
- corridors;
- platforms;
- doors;
- hazards;
- legal transitions;
- known destinations.

### Dynamic entities

- enemies;
- hazards;
- projectiles;
- collectibles;
- bonuses;
- temporary power states;
- NPCs.

### Legal actions

The currently valid abstract actions.

### Events

Recent meaningful state changes such as:

- life lost;
- enemy destroyed;
- pellet consumed;
- score changed;
- level completed;
- item collected;
- damage taken;
- power state activated.

The Canonical Game State should be authoritative for downstream intelligence.

---

## 6. Observation Modes

Each game should eventually support one or more observation modes.

### Omniscient / Instrumented

Uses emulator memory and other internal state.

Best for architecture research because perception error is minimized.

### Vision-Only

Uses only framebuffer/screen information.

Closer to human-equivalent play.

### Hybrid

Uses vision plus limited telemetry such as score, lives, or controller state.

This allows AI Arcade to compare:

> How well does the same intelligence architecture perform with perfect state versus inferred state?

---

## 7. Pac-Man Reference Architecture

Pac-Man is the first target because the game state is compact, highly structured, and suitable for fast constrained decision-making.

### 7.1 Pac-Man Ground Truth

The adapter should expose:

#### Pac-Man

- current tile/node;
- pixel position if useful;
- direction;
- desired direction;
- movement state;
- lives.

#### Maze

- walls;
- corridors;
- junctions;
- tunnels;
- ghost house;
- static connectivity graph.

#### Pellets

- remaining normal pellets;
- remaining power pellets;
- pellet density by region.

#### Ghosts

For each ghost:

- position;
- direction;
- current graph node;
- mode/state;
- frightened state;
- returning-home state;
- projected path or likely movement if available.

#### Other

- score;
- level;
- fruit state;
- frightened timer;
- remaining board state.

---

## 8. Maze Graph

Pac-Man should not reason primarily in pixels.

The static maze should be converted into a graph consisting of:

- intersections;
- corners;
- tunnels;
- dead ends;
- important transition nodes;
- power-pellet locations;
- ghost-house entry/exit;
- strategic regions.

Most gameplay decisions should occur at decision points such as junctions.

This dramatically reduces the decision frequency and converts the problem into constrained graph navigation.

---

## 9. Situation Assessment Layer

The Situation Assessment Layer converts raw state into meaningful tactical concepts.

Examples:

- immediate ghost threat;
- low-risk corridor available;
- player approaching trap;
- high pellet density nearby;
- power pellet available;
- ghosts frightened;
- fruit opportunity;
- board nearly clear;
- escape routes limited;
- multiple ghosts converging.

This layer should favor fast classification/ranking models rather than narrative generation.

Possible providers:

- Jev;
- CLM;
- constrained local model;
- small classifier;
- heuristic baseline.

---

## 10. Behavioral Mode Controller

Before selecting a direction, the system should determine what type of behavior currently matters most.

Pac-Man modes may include:

### FORAGE

Efficient pellet collection.

### EVADE

Avoid dangerous ghosts while continuing useful movement.

### ESCAPE

Immediate survival takes precedence over reward.

### HUNT

Pursue frightened ghosts.

### POWER-PELLET APPROACH

Position for maximum value before consuming a power pellet.

### FRUIT PURSUIT

Temporarily divert toward a bonus fruit.

### LEVEL-CLEAR

Optimize collection of the remaining scattered pellets.

### REPOSITION

Move toward a more advantageous region.

The Behavioral Mode Controller should normally be a fast constrained selector.

---

## 11. Strategic Supervisor

The strategic LLM should not control the joystick.

Its job is to set longer-lived intent.

Examples:

- clear the upper-left pellet cluster;
- preserve the nearby power pellet until more ghosts converge;
- prioritize survival on the final life;
- improve score rather than simply clear the board;
- stop taking risky central crossings;
- avoid a region responsible for repeated deaths;
- focus on board completion rather than fruit.

Strategic decisions should occur:

- periodically;
- after major events;
- after repeated failures;
- when a level changes;
- when the progress monitor requests escalation.

The strategy should guide lower layers without micromanaging individual directions.

---

## 12. Objective Controller

Between the Strategic Supervisor and the Tactical Controller should be an Objective Controller.

Its purpose is to convert broad strategy into concrete local goals.

Examples:

Strategic intent:

> Clear the northwest quadrant.

Objective:

> Reach pellet cluster NW-3.

Strategic intent:

> Prepare to use the lower-left power pellet.

Objective:

> Approach staging junction LL-2 without consuming the pellet.

This layer narrows strategic intent into something the route planner and tactical controller can execute.

---

## 13. Route Planner

The Route Planner determines candidate paths to a selected objective.

Whenever possible, this should use deterministic graph algorithms.

AI should decide:

> Where should Pac-Man go?

Conventional algorithms should decide:

> What routes reach that destination?

Candidate routes can then be scored for:

- distance;
- pellet reward;
- ghost exposure;
- escape options;
- power-pellet opportunities;
- strategic alignment.

---

## 14. Ghost Trajectory Predictor

Ghost location alone is insufficient.

The system should estimate where ghosts are likely to be when Pac-Man reaches future junctions.

The predictor may use:

- current ghost position;
- current direction;
- ghost mode;
- maze connectivity;
- timing;
- known game rules;
- learned or observed motion patterns.

The goal is to estimate:

- likely interception points;
- dangerous junctions;
- safe corridors;
- trap probability;
- time-to-contact.

Initially this may be deterministic for classic Pac-Man.

Later, learned prediction models can be compared against rules.

---

## 15. Risk Controller

Risk should be a first-class architectural concept.

For each candidate route or action, estimate factors such as:

- distance to each ghost;
- time to likely interception;
- number of escape exits;
- dead-end risk;
- convergence risk;
- frightened-mode timing;
- tunnel accessibility;
- remaining lives;
- strategic value of the route.

The Risk Controller does not necessarily select the action.

It provides risk information to the tactical layer and may override other goals when survival becomes critical.

---

## 16. Reward and Opportunity Assessment

A separate assessment may rank possible actions according to reward.

Examples:

- pellet count;
- power-pellet value;
- ghost-eating opportunity;
- fruit value;
- board-clear progress;
- strategic-region progress.

Separating reward from risk makes decision lineage easier to understand.

A route may have:

- very high reward;
- very high risk;
- excellent strategic alignment.

The tactical selector can then make an explicit trade-off.

---

## 17. Tactical Action Selector

The Tactical Action Selector is the primary fast System-One controller.

Its job is:

> Given the current mode, objective, legal actions, predicted risk, reward, ghost trajectories, and recent history, which immediate action is best?

For Pac-Man the candidate set is usually tiny:

- UP;
- DOWN;
- LEFT;
- RIGHT;
- NONE.

The selector should produce:

- selected action;
- ranked alternatives;
- confidence or relative score where available.

Possible providers include:

- Jev;
- Qwen constrained logits;
- CLM;
- classifier;
- heuristic baseline.

The architecture should not depend on any single provider.

---

## 18. Motor Controller

The Motor Controller translates the abstract selected action into emulator input.

Responsibilities:

- press/hold/release directions;
- avoid unnecessary repeated input;
- account for emulator timing;
- maintain direction until a decision point if appropriate;
- expose actual input state to the Observatory.

This layer should remain deterministic.

---

## 19. Progress and Failure Monitor

The system must explicitly detect whether it is succeeding.

Possible signals:

- score growth;
- pellet reduction;
- distance to objective;
- movement through the map;
- repeated deaths in the same location;
- repeated route choices;
- repeated tactical oscillation;
- time spent without progress;
- strategy completion;
- level completion.

Classifications may include:

- progressing;
- temporarily stalled;
- strategically ineffective;
- tactically trapped;
- oscillating;
- repeatedly failing.

The Progress Monitor is the primary trigger for System-Two escalation.

---

## 20. System-Two Escalation

The reasoning LLM acts as coach, strategist, and diagnostician.

It should be invoked only when necessary.

Typical triggers:

- repeated deaths in the same region;
- poor score progression;
- tactical choices consistently produce high-risk outcomes;
- objective repeatedly fails;
- board completion stalls;
- a new level introduces behavior the existing strategy does not handle.

The LLM may respond with higher-level guidance such as:

- reduce risk weighting in one situation;
- increase escape priority;
- stop entering a particular corridor when ghosts converge;
- preserve a power pellet;
- change target region;
- change strategic objective.

After providing guidance, control returns to the fast loop.

---

## 21. Multi-Timescale Operation

Different layers should run at different frequencies.

### Emulator / motor loop

Runs at or near game frame rate.

Handles actual controller state and game interaction.

### Reflex/tactical loop

Runs at decision points or at a relatively high rate.

Handles immediate direction/action.

### Situation/risk loop

Runs less frequently.

Reassesses threat, reward, and behavior mode.

### Objective/route loop

Runs when an objective changes or a route becomes invalid.

### Strategic loop

Runs periodically or on major events.

### Reasoning escalation

Runs only when explicit conditions trigger it.

The system should avoid invoking slow models at frame rate.

---

## 22. Decision Lineage

Every meaningful action should be traceable through the full intelligence stack.

Example:

### Ground Truth

Pac-Man approaching junction J42.

Three directions legal.

Blinky approaching from east.

Power pellet remains to north.

### Situation Assessment

Threat: medium-high.

Escape quality: west high.

Reward opportunity: north high.

### Behavioral Mode

EVADE.

### Strategic Objective

Clear upper-right quadrant while preserving final life.

### Candidate Routes

North, West, East.

### Risk Assessment

North: 0.52  
West: 0.08  
East: 0.79

### Tactical Selector

West: 0.71  
North: 0.24  
East: 0.05

### Motor Output

LEFT/WEST.

### Outcome

Pac-Man escapes convergence and consumes four pellets.

This lineage should be persisted and visible live.

---

## 23. Observatory Dashboard

The dashboard should be treated as a core product feature rather than a debugging afterthought.

### Live Game Panel

- framebuffer/game display;
- current frame/tick;
- score/lives/level.

### Ground Truth Panel

- player state;
- entities;
- collectibles;
- map position;
- game-specific state.

### Strategy Panel

- current strategic objective;
- age of objective;
- reason selected.

### Behavioral Mode Panel

- current mode;
- ranked alternative modes;
- confidence.

### Objective and Navigation Panel

- local target;
- route;
- progress toward target;
- alternative routes.

### Threat/Risk Panel

- nearest threats;
- predicted intercepts;
- candidate route risk.

### Reward Panel

- pellet density;
- fruit opportunity;
- power-pellet opportunity;
- board completion.

### Tactical Decision Panel

- candidate actions;
- rankings;
- selected action;
- provider/model;
- latency.

### System-Two Panel

- escalation state;
- reason for escalation;
- supervisor input;
- supervisor recommendation.

### Progress Panel

- current progress classification;
- stuck/oscillation indicators;
- repeated-failure metrics.

### Performance Panel

- model calls;
- inference latency;
- tokens;
- CPU/GPU usage where available;
- decisions per second.

---

## 24. Event and Telemetry Model

Every intelligent component should emit standardized events.

At minimum, capture:

- event timestamp;
- game tick;
- component name;
- component role;
- provider/model;
- model configuration/version;
- input state reference;
- candidates;
- retrieved context;
- output;
- ranked alternatives;
- confidence/probabilities;
- latency;
- reason for invocation;
- reason for escalation;
- action selected;
- game outcome;
- resulting state delta.

This telemetry should support both:

- real-time visualization;
- post-run analysis.

---

## 25. Provider Abstraction

Each cognitive role should expose a stable interface independent of implementation.

Example interchangeable providers:

### Situation Assessment

- rules;
- small classifier;
- Jev;
- CLM.

### Tactical Selection

- heuristic;
- Qwen logits;
- Jev;
- CLM.

### Risk

- deterministic scoring;
- classifier;
- learned model.

### Strategy

- local LLM;
- hosted reasoning LLM;
- scripted baseline.

### Trajectory Prediction

- deterministic game rules;
- learned model.

This allows direct controlled comparisons.

---

## 26. Baselines

Every advanced controller should be compared against simple baselines.

Recommended baseline modes:

### Random

Choose randomly among legal actions.

### Simple heuristic

Basic safety/reward rules.

### Deterministic graph policy

Shortest path or pellet-density policy.

### Single-model controller

One LLM or local model making all decisions.

### Layered architecture

Full fast/slow stack.

Without baselines, added architectural complexity cannot be justified scientifically.

---

## 27. Experimental Metrics

AI Arcade should measure more than raw score.

### General

- score;
- survival time;
- levels completed;
- lives lost;
- game-over frequency;
- action frequency;
- inference latency;
- model calls;
- tokens;
- compute usage.

### Pac-Man-specific

- pellets collected;
- power pellets collected;
- ghosts eaten;
- fruit collected;
- board-clear time;
- deaths per region;
- average route risk;
- high-risk choices;
- successful escapes;
- junction decisions;
- route efficiency;
- score per life;
- score per minute;
- repeated-death patterns;
- System-Two escalations.

### Architectural

- percentage of decisions handled by fast controller;
- percentage escalated;
- confidence calibration;
- intervention effectiveness;
- strategy changes;
- stuck episodes;
- recovery rate after escalation.

---

## 28. Multi-Game Expansion

Pac-Man should be the first adapter, but the framework should support many games.

Potential follow-on games:

### Frogger

Primary challenges:

- trajectory prediction;
- timing;
- moving hazards;
- safe path planning.

### Galaga

Primary challenges:

- target selection;
- firing;
- projectile avoidance;
- movement prediction.

### Donkey Kong

Primary challenges:

- platform navigation;
- timing;
- hazard avoidance;
- route planning.

### Space Invaders

Primary challenges:

- target prioritization;
- projectile avoidance;
- firing timing.

### Asteroids

Primary challenges:

- continuous geometry;
- momentum;
- aiming;
- collision prediction.

### Dig Dug

Primary challenges:

- pursuit;
- path planning;
- spatial defense.

Each game should reuse the same overall architecture while stressing different cognitive capabilities.

---

## 29. Arcade Director and Cross-Game Learning

Eventually the Arcade Director should become intelligent enough to choose what the AI should practice.

It may consider:

- recent game performance;
- untried games;
- weak skills;
- repeated failure patterns;
- newly available adapters;
- experimental goals.

Example decisions:

- Pac-Man performance is improving; move to Frogger.
- Frogger still produces repeated timing failures; practice it again.
- A new Galaga adapter is available; test it.
- Compare Jev and Qwen tactical providers on the same game.

This creates a meta-learning layer above individual games.

---

## 30. Repository and Content Boundary

The GitHub repository must contain no copyrighted game content.

The repository may contain:

- AI Arcade source code;
- emulator integration;
- adapter logic;
- memory-map definitions created from public/reverse-engineered knowledge;
- canonical schemas;
- static structural metadata created by the project;
- hashes/checksums;
- test fixtures containing synthetic data;
- documentation;
- metrics and experiment results.

The repository must not contain:

- ROM images;
- BIOS files;
- CHDs;
- disk images;
- commercial game assets;
- copied artwork;
- save states containing copyrighted game data unless explicitly excluded from publication.

Game content remains external and user-supplied.

---

## 31. Recommended Initial Implementation Sequence

### Phase 1 — Infrastructure and architecture

- finish repository structure;
- define Emulator Adapter interface;
- define Game Adapter interface;
- define Canonical Game State;
- define event/telemetry contract;
- define controller action interface.

### Phase 2 — Pac-Man vertical slice

- launch Pac-Man;
- read emulator state;
- decode Pac-Man position;
- decode ghost positions;
- decode pellets;
- send joystick input;
- display canonical state.

No AI yet.

### Phase 3 — Deterministic baseline

- build maze graph;
- identify legal actions;
- implement simple rule-based controller;
- collect benchmark telemetry.

### Phase 4 — Fast tactical intelligence

- add constrained action selector;
- begin with local model or heuristic comparison;
- expose rankings/confidence.

### Phase 5 — Risk and prediction

- ghost trajectory prediction;
- route risk;
- escape analysis;
- behavioral modes.

### Phase 6 — Strategic supervisor

- add slow LLM;
- define strategic objective contract;
- invoke only periodically or on escalation.

### Phase 7 — Observatory dashboard

- show full decision lineage;
- add live model/component panels;
- support replay/post-run analysis.

### Phase 8 — Additional games

- Frogger;
- Galaga;
- Donkey Kong or another contrasting game.

---

## 32. Long-Term Research Goal

AI Arcade should become one environment in a broader family of layered-intelligence experiments.

### Zork Observatory

Tests symbolic, language-heavy, slow reasoning.

### Doom-Slayer

Tests continuous tactical and perceptual intelligence.

### AI Arcade

Tests fast constrained decision-making, real-time control, prediction, risk, and cross-game adaptation.

All three should share the same architectural ideas:

- authoritative ground truth;
- specialized fast intelligence;
- slower strategic reasoning;
- escalation;
- memory;
- progress monitoring;
- confidence;
- model interchangeability;
- decision lineage;
- observability.

The larger goal is not merely to make AIs play games.

It is to build a reusable experimental framework for understanding:

> how layered System-One/System-Two intelligence should be assembled, observed, measured, and improved across radically different environments.
