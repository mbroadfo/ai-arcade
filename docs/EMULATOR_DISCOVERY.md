# Emulator discovery and observation

Build reusable emulator adapters and separate game decoders, following
[ARCHITECTURE.md](ARCHITECTURE.md). Discover the running executable, core,
version, content identity, and effective configuration before choosing an
observation method. An ES system's default emulator may differ from the
per-game selection.

An emulator adapter should expose its supported observation capabilities and
raw state with session identity, sequence/frame information, and freshness.
Game decoders interpret that state for a verified game revision. Unsupported
fields remain unknown; controller acknowledgments do not prove game effects.
Prefer internal state and memory over screen capture for this work.

Inspect the complete input chain: broker action, installed controller profile,
frontend remap, and emulator/game input configuration. Keep the public actions
semantic (`COIN`, `START`, directions). Legacy remaps must not silently redefine
those actions for every game. Persistent fixes belong in tested, repeatable
installation automation with backups, not manual Pi edits.

## Pac-Man investigation, 2026-09-30

- Live launch: `arcade/pacman.zip` through RetroArch and `lr-mame2003`.
  The per-game emulator override takes precedence over Arcade's MAME4ALL default.
- Installed core source revision: `3eb27d5f161522cf873c0642f14b8e2267b3820f`.
  Its `src/mame2003/mame2003.c` memory data and size callbacks return zero.
  A useful memory exporter is not implemented yet. Save-state serialization is
  present, but a validated observation reader/decoder is still needed.
- Installed controller profile maps broker `COIN` to RetroPad Select (button 8)
  and `START` to RetroPad Start (button 9).
- `/opt/retropie/configs/arcade/MAME 2003 (0.78)/MAME 2003 (0.78).rmp`
  contains `input_player1_btn_select = "3"` and
  `input_player1_btn_start = "2"`: a Select/Start swap (RetroPad IDs 2/3).
  This explains why the normal semantic input sequence can fail. The same
  remap also changes action buttons; inspect it before normalizing anything.
- The user confirmed a credit appeared after the first input trial, but the
  game did not start. A subsequent trial used broker `COIN` as the remapped
  Start. The user then confirmed the game started and Pac-Man moved left into
  a wall. A further trial used the remaining credit and sent Left, Up, Right,
  Down for 1.2 seconds each, then released all controls. The broker acknowledged
  every input; confirmation of the other three directions is pending. A wall
  blocking movement must not be mistaken for an input failure.

Next validation: confirm effective Start and joystick behavior, then automate
mapping corrections without overwriting unrelated game-specific mappings.
For observation, export coherent, read-only emulator state and decode Pac-Man
separately; do not place Pac-Man RAM offsets in the generic controller broker.

The Pac-Man decoder must provide a traversable maze/wall grid, remaining dots
and power pellets, player position/direction, and each ghost's position and
mode (including frightened/returning states). Include game phase, lives, score,
and level so controllers can distinguish attract mode, ready, play, and death.
These are requirements, not fields currently available. Validate coordinate
alignment and tile/entity meanings against the loaded ROM revision before
using them to plan movement. Preserve the raw snapshot and unknown values so
an incorrect decoder cannot silently invent a safe route.
