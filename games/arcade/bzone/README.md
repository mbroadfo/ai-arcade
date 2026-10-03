# Battlezone

The third game, and the test of breadth (docs/REFACTOR_PLAN.md, phase 5): a first-person tank in a continuous world,
two tread sticks used together, decisions on a beat instead of at junctions.

## Workshop stages (docs/GAME_WORKSHOP.md)

| Stage | Status |
|---|---|
| 0 Feasibility | done: 100% speed on the Pi 5 (MAME 0.251) with no exporter and with all 1 KB of work RAM exported every frame (`mame_speed_test.py`); unthrottled with no display 1,350% |
| 1 Controls | `profile.json` written. Left tread on Player 1's stick (up = forward), right tread on Player 2's, fire on Player 1's button 1, coin, start: the `bzone` section of `tools/configure_mame_controller.py`. All checked to reach the game (`tools/mame_inputs_probe.lua`); the broker needs no change. Default coinage is 2 coins, 1 play. Press-to-effect latency not measured yet |
| 2 State | under way: Atari's own RAM names (RAM_MAP.md); credits, lives, attract flag, tank angle, tank position, score and shell checked by experiment. Next: the decoder (`state.py`), the enemy's position checked, a validation script on a recording |
| 3-8 | not started |

## Getting the ROM

The collection's `bzone.zip` matches an older MAME and lacks 8 lookup chips. A newer `bzone.zip` was added with
`python tools/add_rom_files.py PATH/bzone.zip --sets bzone bzonea` (docs/PI_SETUP.md): MAME 0.251 verified both
revisions. Human mode still plays the collection's copy in AdvanceMAME.
