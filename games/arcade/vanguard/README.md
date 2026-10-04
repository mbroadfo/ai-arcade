# Vanguard

SNK, 1981; MAME romset `vanguard` (0.251). Rotated 90 degrees: the screen is 224 x 256 upright. A horizontally scrolling
ship fights through zones; four fire buttons shoot in four directions at no cost, so shooting is never a trade-off.
The goal of this project: S1M becomes a champion alone (every move and every shot is S1M's; code supplies state and
executes, docs/GAME_WORKSHOP.md).

## Workshop stages

| Stage | Status |
|---|---|
| 0 Feasibility | not measured |
| 1 Controls | `profile.json`: stick (8-way) and four buttons, coin, start. Checked on the screen, 4 October 2026: **button 1 fires left, 2 right, 3 down, 4 up** (`scripts/shots.py`). On the keyboard (MAME's Input Assignments, read with `tools/mame_seq_probe.lua`): arrows move, **Left Ctrl** = button 1 (left), **Left Alt** = 2 (right), **Space** = 3 (down), **Left Shift** = 4 (up), `5` coin, `1` or Enter start. Default coinage is 2 coins a play (`SETTINGS` makes it 1; the board has no free play). MAME's driver is "imperfect", so it opens on a warning screen that holds every script until a key: the start-up tools tap button 1 (`controller_client.dismiss_warning`) |
| 2 State | candidates only (below); `state.py` decodes them raw |

## RAM found so far (work RAM `$0000-$03FF`; candidates, not validated)

| Address | What | Evidence |
|---|---|---|
| `$40` | fire buttons held: button 1 `08`, 2 `04`, 3 `01`, 4 `02` | latches exactly with each press (`scripts/probe.py`) |
| `$42-$43` | the ship's position (16 bits) | UP/DOWN step it by 1, RIGHT by `$20` |
| `$2B`, `$02E1` | credits | discovery |
| `$BE` | spare ships (the HUD shows it + 1); `$FF` when the game is over | matches the displayed 3, 2, 1 across a game and the MAME cheat list's "Infinite Lives" address |
| `$50` | the THE END countdown: 14, 4, 3, 2, 1, 0, `$FF` | timed against the video |
| `$25-$27` | the HI-SCORE (BCD, 3 bytes: `00 10 00` is the 10000 shown), not the player's score | hiscore.dat and the screen |
| `$A9`, `$C4` | not lives (they stayed at 4 and 7 while the HUD lives fell); unknown | |

**Firing:** a held fire button fires one shot; the ship must be pulsed (press, release, again). The player's score has not been found yet: two scripted games (`scripts/drive.py`, `scripts/record.py`) never hit anything. The HUD also shows `COIN`, `ROUND` and the lives.

The screen: the ship sits near x = 105 and the world scrolls past; white ships fly in from the right; energy depots sit on
the ground (fuel is a timer: the energy bar drains).

## Tools

    python tools/start_pi_game.py --game arcade/vanguard          # ends EmulationStation, starts the game
    python games/arcade/vanguard/scripts/probe.py                 # one control at a time, RAM sampled, saved
    python games/arcade/vanguard/scripts/shots.py OUT.png --press 1.BUTTON_2   # frames around a press, one sheet
