# AI Arcade Architecture

AI Arcade separates game content, emulator integration, game semantics, and intelligence.

## Layers

### Arcade Director

Chooses games, launches them, tracks sessions, and hands control to the matching adapter.

### Emulator Adapter

Provides emulator-specific capabilities such as launch/stop, controller injection, framebuffer access, emulated memory access, and timing.

### Game Adapter

Translates raw emulator state into semantic state such as player position, enemies, collectibles, map state, score, lives, legal actions, and events.

### Intelligence Framework

Consumes normalized state and combines fast constrained decision layers with slower supervisory reasoning. Implementations may include deterministic algorithms, Jev/System-One style models, CLMs, local open models, and reasoning LLMs.

### Observatory

Captures inputs, outputs, rankings, confidence, latency, decisions, state transitions, failures, and model escalations in real time.

## Content boundary

No adapter should require game ROMs to be stored in or copied into the source tree. Adapters may identify supported game revisions using hashes and may depend on locally configured game paths.
