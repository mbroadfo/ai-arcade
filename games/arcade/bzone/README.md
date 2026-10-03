# Battlezone

The third game, and the test of breadth (docs/REFACTOR_PLAN.md, phase 5): a first-person tank in a continuous world,
two tread sticks used together, decisions on a beat instead of at junctions.

## Workshop stages (docs/GAME_WORKSHOP.md)

| Stage | Status |
|---|---|
| 0 Feasibility | done: 100% speed on the Pi 5 (MAME 0.251) with no exporter and with all 1 KB of work RAM exported every frame (`mame_speed_test.py`); unthrottled with no display 1,350% |
| 1 Controls | `profile.json` written. Left tread on Player 1's stick (up = forward), right tread on Player 2's, fire on Player 1's button 1, coin, start: the `bzone` section of `tools/configure_mame_controller.py`. All checked to reach the game (`tools/mame_inputs_probe.lua`); the broker needs no change. Default coinage is 2 coins, 1 play. Press-to-effect latency not measured yet |
| 2 State | done for what the lab needs: Atari's own RAM names (RAM_MAP.md), the decoder (`state.py`) tested on a scripted recording (`tests/`), and in live runs: credits, lives, attract flag, heading, position, score (hits), hits taken, death counter |
| 3 Decision | on a beat: the real-time lab (below). Facts (`facts.py`) are what a player sees: the screen's left/right/rear warning always; bearing, distance and whether a shot would hit only while the enemy is on the radar, which shows it only within firing range |
| 4-8 | not started: no model plays yet |

## The real-time lab

`scripts/lab.py` runs a diagnostic policy (`policies.py`: code choosing, a control, never AI play) on a fixed-rate
clock (`arcadekit/clock.py`) and logs every tick: when it ran and how late, the snapshot it saw and how old it was when
the command went out, the decoded state, the facts, what the policy held and why, what was pressed and released, and
what changed. `scripts/explain.py` reads a run back tick by tick; `scripts/summarize.py` gives one line per run.

    python tools/start_pi_game.py --game arcade/bzone --speed 1.0
    python games/arcade/bzone/scripts/lab.py --policy track_and_fire --hz 10

Found on 2 October 2026:
- The 10 Hz clock held to within 0.6 ms; observations were about 13 ms old; a command shows in the state 100-200 ms
  later. The game's frame counter runs at about 41 a second.
- A shell hits only within 224-320 world units of the enemy (the game's SHRTCK), about +-0.6 degrees at 25,000 units,
  finer than the heading's step: aiming by angle (4 degrees) gave 1 kill in a game, aiming by where the shot would pass
  gave 8 (`track_and_fire`, 10 Hz).
- The video export showed nothing for Battlezone: it copied MAME's screen bitmap, and a vector game does not draw into
  it. Vector screens now use MAME's rendered snapshot (`tools/mame_video_export.lua`): 640 x 480, about 6 ms a capture,
  10.6 frames a second to the Observatory at 17 KB a frame (3 October 2026).

## Getting the ROM

The collection's `bzone.zip` matches an older MAME and lacks 8 lookup chips. A newer `bzone.zip` was added with
`python tools/add_rom_files.py PATH/bzone.zip --sets bzone bzonea` (docs/PI_SETUP.md): MAME 0.251 verified both
revisions. Human mode still plays the collection's copy in AdvanceMAME.
