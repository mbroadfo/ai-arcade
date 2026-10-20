# Gate A — what the current Mario reward is paying for

Read-only diagnosis on 2026-10-14. No training. The champion zip and the paused generation were not modified. Generation 145 stayed paused.

## Setup

- Game: Super Mario Bros., World 1-1, adapter `smb_1_1`, objective `progress`.
- Algorithm: PPO / Nature CNN, deterministic unless a row says otherwise. Frame skip 4. Twelve button chords. No shared tape, no hint, no demonstration. `reset_assisted` was false.
- Checkpoints, read only:
  - Champion `C:/Users/Mike/mario-runs/20261012T011344Z/seats/0/best.zip`, sha256 `0d31d9fd5ae3cdab1531f72e33938a584e93f7549061e9de49ed26b2a18cf7ec`.
  - Generation 145 Red `C:/Users/Mike/mario-runs/20261014T175707Z/seats/0/best.zip`, sha256 `e3c1a3f91547c137155f40290870277f52c5af81a5eccf239c06d5325f27d7c6`.
- Starts: the normal title entry (x=40, y=79), and `state.bin` in this folder (x=197, y=79). That state is 21 decisions of RIGHT+B after the title, on the way to the first pipe. Core state is 13758 bytes, sha256 `72c3ea8bd337c489e2a0c1adb3253de22457c8617c8162816dfbd25ae014a97e`.
- Reward components were recomputed with the production formula. They matched the environment reward within 0.000006.

The two checkpoints have different bytes and produced the same buttons on both starts.

## What the episodes did

From the title, both policies pressed RIGHT+A+B for all 37 decisions (148 emulator frames). Mario jumped once (y 79 up to 145, back to 79 by decision 14) and then ran on the ground. A goomba (enemy id 6) was on screen from decision 22. Mario died at x=313. Score stayed 0.

| Component | Total |
|---|---|
| Progress reward | 543.01 |
| Stall penalty | 1.00 |
| Death penalty | 256.00 |
| Episode return | 286.01 |

From `state.bin`, both policies pressed RIGHT+A+B for all 180 decisions (720 emulator frames) and hit the step limit alive. One jump at the start, then the ground. Mario stomped the goomba (score became 100) and stopped at x=434, against the left side of the first green pipe. The next 150 decisions (600 emulator frames) gained no x. y stayed 79, physics stayed `ground`, y speed stayed 0.

| Component | Total |
|---|---|
| Progress reward | 470.04 |
| Stall penalty | 151.00 |
| Death penalty | 0 |
| Episode return | 319.04 |

The pipe stall itself returned −150. The earlier distance in the same life returned +470, so the life was still a gain.

## The pipe is visible, and a new press of A clears it

At x=434 the 256×240 frame shows Mario on the ground beside the pipe. The 84×84 grayscale frame the Nature CNN receives still shows that pipe as its own column. The 9-float RAM vector has position, time, state, death, flag, coins, world, and stage. It has no pipe and no enemy. `diagnose()` saw the goomba, and that reading stays out of the policy vector.

A separate button probe, not a policy action, released A for 3 decisions (RIGHT+B) and pressed RIGHT+A+B again. Mario left the ground immediately (y 79 to 95, y speed −4) and landed on top of the pipe at x=458. The pipe does not require a special button. It requires a new press of A.

SMB starts a jump when A goes down. Holding A does not start another jump. The deterministic policy never releases A, so it gets one jump per life and then pushes into the pipe.

A seeded stochastic sample (seed 0, 120 decisions, the training distribution) pressed something other than RIGHT+A+B on 20 decisions and left the ground 25 times. It was at x=594 when the sample stopped, still in World 1-1. Training can look like repeated jumping because entropy sometimes releases A. Independent deterministic evaluation does not.

## What the current objective is incentivizing

Positive reward is new maximum progress, multiplied by `1 + time/400`. Early in 1-1 that is about two points per new pixel. A running step in this trace gained about 8–10 pixels and paid about 15–20. A jump has no reward term. A step with no new maximum pays −1 while Mario is alive. A death pays −256.

Those numbers train a single chord, RIGHT+A+B. It is the chord that moves right. Once A is held, the chord stops producing jumps, and the pipe stall pays −1 per decision until the step limit. One running step covers about fifteen of those penalties, and the distance before the pipe already outweighs the whole stall. The life is a successful training return that never crosses the pipe.

The early death is the same shape. The approach pays +543 and the death costs 256, so the return stays positive. The goomba is on screen. The learned chord does not change when it appears.

This is a combination:

- Action timing. The argmax action holds A, and a held A cannot start the second jump that lands on the pipe.
- Reward design. Distance before the obstacle pays more than a long stall or this death costs. Nothing ends the stall. Actual NES points are read and then ignored.
- Observation. The CNN does receive the pipe. The failure at the pipe is not a missing pixel. The RAM vector would be blind to it. The goomba is a 16×16 sprite, a few pixels after the 84×84 resize.
- Exploration. Stochastic samples sometimes release A and get past the pipe. The saved deterministic policy does not.

## Proposed profiles

No new framework. An experiment names a profile. The profile's id is the stamp `objective`. `champion()` already requires an exact stamp, so `progress`, `smb-1-1-speed`, and `smb-points` cannot parent each other.

Two profiles to implement after this report. Both version 1.

**`smb-1-1-speed`.** Complete World 1-1. The completion event is the existing `clear-1-1-flag` latch. Among completed attempts, fewer emulator frames wins. A failed attempt is ranked by its furthest x, in a separate list. A short death cannot beat a slower success, and it cannot beat a longer failure.

Reward per decision, scaled for PPO and DQN:

- New maximum x pays `min(2, pixels/16 * clock)`, where `clock` is 1 at time 0 and 2 at time 400. A body-length of new ground is about one point. A single step cannot pay more than 2.
- The flag latch pays +8 once.
- A decision with no new maximum pays −0.05.
- Twenty-four consecutive decisions with no new maximum end the life as a stall (96 emulator frames). A scenario can set `wait_allowed` when waiting is the skill, as on the ceiling. The World 1-1 pipe does not.
- Death pays −2 and the attempt is a failure.

There is no jump bonus. The pipe is solved by gaining x after a new press of A. A jump bonus would pay for hopping in place.

**`smb-points`.** Maximize the NES score already read from RAM at `0x07DE`. Completion is not required. The metric is that score.

- Each decision pays `clip(delta_points / 100, -1, 5)`. A coin or a stomp is about +1.
- Death pays −2.
- No progress term. Distance and score stay different objectives.

Planned until the event itself is measured, and not offered as a selectable objective yet:

- Enemy defeats. A slot and an id are visible. A defeat is not.
- Distinct question blocks. A coin or a score change does not identify which block broke.
- Shortcuts. No shortcut event is measured.

## What the comparison should measure later

Same PPO/CNN, same champion weights as the starting point, same emulator, one small frame budget, disposable directories. Evaluate both reward profiles with no tape and no overrides, on the title start, on `state.bin`, and on one held-out start beyond the first pipe. Report completion rate, pipe crossing, median emulator frames among clears, furthest x on failures, deaths, stalls, and simulated training frames. A higher training return is not evidence that the policy learned the objective.
