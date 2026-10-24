# 3D Pinball for Windows - Space Cadet (AI project, spike)

Goal: the S1M model plays Space Cadet, with the model making the decisions (see `docs/AI_MODE.md`).

## What is here

- `bridge/` - a small socket added to a **private copy** of the open-source SpaceCadetPinball 2.1.0 source on the cabinet Pi
  (`~/ai-arcade-pinball`; the install in `~/RetroPie/ports/space-cadet-pinball` that the retropie-pinball project owns is not touched).
  - `AgentBridge.cpp/.h` - line-based JSON on 127.0.0.1, enabled only when `SCP_AGENT_PORT` is set. Commands: `state`, `input`
    (left, right, plunger, nudge_left, nudge_right, nudge_up, new_game), `mode` (step / real time), `step` (N fixed 10 ms frames).
    Inputs go through the game's own key path, so tilt, nudge and launch rules apply.
  - `apply.py` - copies the bridge into a source tree and makes the three small edits (CMake list, `Init`, `Poll`).
  - `probe.py` - the feasibility probe.
- Original game data (`PINBALL.DAT`, sounds) stays on the Pi under the retropie-pinball project and is not in this repo.

## Build (on the Pi)

    cp -r ~/RetroPie/ports/space-cadet-pinball/source ~/ai-arcade-pinball/source && rm -rf ~/ai-arcade-pinball/source/bin
    python3 bridge/apply.py ~/ai-arcade-pinball/source bridge
    cmake -S ~/ai-arcade-pinball/source -B ~/ai-arcade-pinball/build -DCMAKE_BUILD_TYPE=Release
    cmake --build ~/ai-arcade-pinball/build --parallel 3     # about 3 minutes

## Spike findings (2026-10-21)

- Runs headless (`SDL_VIDEODRIVER=dummy`, `SDL_AUDIODRIVER=dummy`), so no display and no need to stop EmulationStation.
- The state is rich: score, ball number, tilt, multiball, every ball's position/direction/speed, both flippers' angle,
  and the game's own message text (missions, "Player 1").
- Time can be paused and stepped: 5,000 frames (50 s of game time) in about 10 ms of wall time, so thinking time costs the game nothing.
- Plunger held 1.5 s then released launched the ball; a ball left alone for 50 s scored 31,000 and drained (ball 3 -> 2).
- Table units: x about -7 to +7 (plunger lane at x -7), y about -12 (top) to +12 (bottom, plunger at y 11.7). Flipper angle 0 (down) to 1.2152 rad (up).

## Table geometry (measured)

x runs to the screen's left, y runs down: the left flipper's pivot is at x +2.49, y 12.06 (tip at rest x +0.96, y 13.13); the
right flipper mirrors it at x -2.49. The plunger lane is at x -7.0 (screen right) and the ball waits at y 11.67. The table is
about x -7 to +6.6 and y -12.2 (top) to +13.8 (drain). A flipper swings 0 to about 1.215 rad. The game is deterministic: the
same inputs give the same game, so a code control gives one result, not a spread.

Two things the game does that a player must know: a ball that drains early is **re-deployed** ("Re-Deploy") without losing a
ball, and a plunger pull made before the ball has rolled down to rest (y about 11.67) jams the plunger.

## Playing it

    python -m games.ports.space_cadet.run --player model --model nimble     # S1M decides every window
    python -m games.ports.space_cadet.run --player reflex                   # CONTROL (code): flip when the ball is in reach
    python -m games.ports.space_cadet.run --player idle                     # CONTROL (code): never touch a flipper

`players.py` describes the table in words and numbers (where the ball is going, which flipper could hit it, how long a flipper
has been up, the tilt meter) and shows each choice with its effect; the model picks the flippers (neither, left, right, both),
a nudge, or the plunger pull. `run.py` presses what was chosen and steps 8 frames (80 ms). Runs are labelled **stepped
(thinking time)**; the log in `runs/` books every decision as model, fallback or code.

## First results (2026-10-21, nimble, window 8)

| Player | Score | Notes |
|---|---|---|
| idle (control) | 143,750 | one ball is mostly bumpers; the last ball jams, so it never finishes |
| reflex (control) | 155,000 | finishes a game in 57 s of game time |
| model (nimble) | 82,000 | 2,356 model decisions, 0 fallbacks, 0.2 to 0.4 s each; two balls lost, the last ball sat jammed at the right flipper's pivot for 20 minutes of wall time |

What this says: the loop works and the model answers fast enough to play in thinking time, but it plays worse than doing nothing
so far. It held the right flipper up with the ball resting on it until the facts said so in words (and in each option's effect);
it never chose a nudge, which is what frees a jammed ball. Score alone is a weak measure here because one launch already hits the bumpers.

## Next

1. Seeded batches (`--seed N`, a random 0 to 2 s wait before each launch) of the model and the controls, watched in the Observatory.
2. The same game with `tev1:latest` and `tev1:0.8b`.
3. Real-time mode (the model chooses goals and timing windows, skills do the milliseconds).

## In the Observatory

The game is listed in GAMES as "3D Pinball for Windows - Space Cadet" (system `ports`) and is started from the AI setup: choose
"AI plays", or one of the two controls. The package declares `own_screen`, so the Observatory starts no MAME and clears no
screen: it starts `run_lab.py`, which runs `run.py`. The run sends its own picture (`observe.py`: ball, path and flippers drawn
from the bridge's state, about five a second) and a status line with whose move it was; the timeline gets every launch, nudge,
lost ball and model fallback. The picture is not the game's screen (the game runs headless on the Pi), and time is stepped, so
it moves at the model's pace, not in real time.

The Observatory server needed two generic changes: it accepts `{"event": "frame", "png": ...}` from a player (a game with no
frame server), and a game package may declare `own_screen`. The player module is `players.py` because a submodule named
`player` would make the AI setup treat the package as a model-player game.

## What the model is asked, and when (2026-10-22)

First live use in the Observatory showed `nimble:latest` holding both flippers up for 250 of 284 windows, whatever the ball was
doing. Fixes, in the order they mattered:

- **One question per flipper** (raise or lower) and a separate nudge question, not "which flippers" with "both" among the answers.
  Alone this was not enough: the small models still raised a flipper with the ball out of its reach in 70 to 85 % of windows,
  nudged in about half, and three questions made each window take 1.2 s.
- **Ask only when it matters** (`--ask-when near`, a [timing] switch, on by default): a flipper question goes to the model only
  when the ball is within 4.5 of that flipper's pivot or will pass flipper height over it within 0.7 s; the nudge question only
  when the ball has stayed put 1.5 s or is heading for the gap. A window with nothing to ask is booked as `skipped` (the
  flippers rest), never as a model move. `--ask-when always` is the pure version. First try, one seed, 240 s wall: nimble:latest
  416,500 (350 model decisions, 857 skipped), nimble 373,000 (355, 707), against about 145,000 to 170,000 for the controls: not yet a
  comparison (one seed, game not finished), and the controls' flippers are also worth re-checking.
- Run logs no longer put a colon in the file name (`nimble:latest`): Windows made the rest a hidden stream, so the log looked empty.

## On the cabinet's screen

An AI run started from the Observatory takes the cabinet's screen (EmulationStation stops, as for MAME) and runs the game
itself fullscreen with its sound (`--show`; `cabinet_screen` in `LAB`); the Observatory still gets the drawn picture. Back to
menu in the Observatory brings EmulationStation back. Time is stepped, so the game on the screen moves in bursts at the model's pace.

## Nine seeded games each (2026-10-24, nimble, window 8, `--ask-when near`, stepped / thinking time)

Seeds 1 to 9 (`--seed N`), every game played to game over.

| Player | Median | Mean | Range | Scores by seed 1 to 9 |
|---|---|---|---|---|
| model (nimble) | 328,000 | 413,000 | 141,750 to 965,000 | 242,750 / 383,750 / 321,000 / 141,750 / 965,000 / 225,000 / 328,000 / 515,500 / 597,500 |
| reflex (control, code) | 227,000 | 235,000 | 158,000 to 405,000 | 173,250 / 256,000 / 158,000 / 171,500 / 227,000 / 322,750 / 235,750 / 405,000 / 168,250 |
| idle (control, code) | 137,750 | 151,000 | 86,500 to 345,500 | 146,750 / 345,500 / 111,500 / 144,750 / 86,500 / 137,750 / 108,000 / 109,000 / 170,750 |

The model scored higher than reflex on 7 of the 9 seeds and higher than idle on 8 of 9. A permutation test on the medians gives
p about 0.05 against reflex and 0.02 against idle: suggestive, not settled, with 9 games each and a very wide spread (the model's
own best game is 965,000, its worst 141,750).

Read it with these in mind:

- The model was **asked in a minority of windows**: in each game 40 to 55 % of windows were skipped (the ball far from both
  flippers), booked as `skipped`, where the flippers rest. "Model" below means the windows it answered: 230 to 1,930 a game
  (about 0.5 to 0.9 s each, up to 4 s; some timed out and were booked as `fallback`, 22 to 75 a game in the first three games).
- The reflex control is crude (flip while the ball is in reach, down after three windows); a better code control would be a fairer
  yardstick, and is worth building before any claim that the model "beats code".
- The run is stepped (thinking time): the game waits for each answer. Real-time play, where the model's delay costs the ball, is
  not tested.
- Seed 2's first try ended at the 15-minute wall limit with the ball still alive (it was not a jam); rerun with a 40-minute limit.
