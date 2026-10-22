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

## Next

1. A client in this folder (Python) that speaks to the bridge, plus a state description for the model.
2. First honest baseline: no-flipper (nothing pressed) and a labelled code control (flip when the ball is at a flipper) for comparison.
3. The model-in-the-loop modes: paused/stepped ("thinking time", labelled as such), then real time with the model choosing goals and timing windows.
