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

    python -m games.pinball.space_cadet.run --player model --model nimble     # S1M decides every window
    python -m games.pinball.space_cadet.run --player reflex                   # CONTROL (code): flip when the ball is in reach
    python -m games.pinball.space_cadet.run --player idle                     # CONTROL (code): never touch a flipper

`player.py` describes the table in words and numbers (where the ball is going, which flipper could hit it, how long a flipper
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

1. A `--seed` (random settling time before the launch) so repeated runs differ and a comparison has a spread.
2. A "ball has not moved for N s" fact and clearer options for a jammed ball; then the same game with `tev1:latest`.
3. Observatory: a top-down view drawn from the state and a launcher, so it appears in the AI games list.
4. Real-time mode (the model chooses goals and timing windows, skills do the milliseconds).
