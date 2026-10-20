# Can the policy tell that A is already held?

Measured before the reward comparison. The 12 button chords were not changed. Nothing was added to the observation.

The pipe-approach state is `state.bin`. Holding RIGHT+A+B from there reaches the first pipe and stops at x=434, y=79, on the ground. That savestate is the branch point. From it, 8 emulator frames of RIGHT+A+B and 8 frames of RIGHT+B both stay at x=434, y=79, physics `ground`, both speeds 0.

The 84×84 grayscale the CNN would see is the same for those two futures. Mean absolute difference 0, maximum difference 0. `frames/edge-held.png` and `frames/edge-released.png` are the full frames. The 9-float RAM vector is also the same: x, y, the timer, player state, not dying, no flag, no coins, world 1, stage 1.

Four raw RAM bytes differ, and those four do not differ when the same held chord simply runs from 4 frames to 8 frames:

| Address | Held RIGHT+A+B | Released RIGHT+B |
|---|---:|---:|
| 10 (0x000A) | 192 | 64 |
| 13 (0x000D) | 192 | 64 |
| 1788 (0x06FC) | 193 | 65 |
| 1866 (0x074A) | 193 | 65 |

Each released value is exactly 128 below the held value. 193 is A+B+Right and 65 is B+Right when A is bit 0x80, B is bit 0x40, and Right is bit 0x01. That is the chord this probe sent. None of those bytes is in the 9-float vector, and the pixels do not change. At the decision, the network is looking at the savestate image from before the button runs. It has no channel that says the jump button is already down.

Releasing A for 3 decisions and pressing RIGHT+A+B again does start a jump (`y_speed` −4). Mario lands on the pipe at x=472, y=111 (`frames/on-pipe.png`), then on the ground past it at x=505, y=79 (`frames/past-pipe.png`, between the two green pipes). A later held-out state is x=594, y=79. Training does not reset from any of these. The title entry remains the only training reset.

This is the observation finding. The reward comparison keeps the current 12 actions and does not feed these bytes back in.
