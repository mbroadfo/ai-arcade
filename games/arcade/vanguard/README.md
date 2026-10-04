# Vanguard

SNK, 1981; MAME romset `vanguard` (0.251). Rotated 90 degrees: the screen is 224 x 256 upright. A horizontally scrolling
ship fights through zones; four fire buttons shoot in four directions at no cost, so shooting is never a trade-off.
The goal of this project: S1M becomes a champion alone (every move and every shot is S1M's; code supplies state and
executes, docs/GAME_WORKSHOP.md).

## Workshop stages

| Stage | Status |
|---|---|
| 0 Feasibility | not measured |
| 1 Controls | `profile.json`: stick (8-way) and four buttons, coin, start. Checked on the screen, 4 October 2026: **button 1 fires left, 2 right, 3 down, 4 up** (`scripts/shots.py`). Default coinage is 2 coins a play. MAME's driver is "imperfect", so it opens on a warning screen that holds every script until a key: the start-up tools tap button 1 (`controller_client.dismiss_warning`) |
| 2 State | candidates only (below); `state.py` decodes them raw |

## RAM found so far (work RAM `$0000-$03FF`; candidates, not validated)

| Address | What | Evidence |
|---|---|---|
| `$40` | fire buttons held: button 1 `08`, 2 `04`, 3 `01`, 4 `02` | latches exactly with each press (`scripts/probe.py`) |
| `$42-$43` | the ship's position (16 bits) | UP/DOWN step it by 1, RIGHT by `$20` |
| `$2B`, `$02E1` | credits | discovery |
| `$A9`, `$C4` | lives or a zone counter | both drop on a death and reset on the next life; not yet told apart |
| `$25-$27` | the score (BCD, 3 bytes) | hiscore.dat |

The screen: the ship sits near x = 105 and the world scrolls past; white ships fly in from the right; energy depots sit on
the ground (fuel is a timer: the energy bar drains).

## Tools

    python tools/start_pi_game.py --game arcade/vanguard          # ends EmulationStation, starts the game
    python games/arcade/vanguard/scripts/probe.py                 # one control at a time, RAM sampled, saved
    python games/arcade/vanguard/scripts/shots.py OUT.png --press 1.BUTTON_2   # frames around a press, one sheet
