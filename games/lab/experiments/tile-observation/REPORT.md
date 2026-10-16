# Tile observation validation

Accepted: False

On the approach frame the one-hot is window row 8. Column 0 is solid on window rows [9]. At the first pipe, solid cells ahead of column 0 are row 7 offsets [1, 2], row 8 offsets [1, 2], row 9 offsets [1, 2, 3, 4, 5, 6]. The acceptance rule looks above the one-hot, on rows 6 and 7. The goomba at x=228 on decision 28 is a -1 at window row 7, column offset 6. The two-high pipe is on the one-hot row and the row above it. The rule requires both rows above the one-hot, and the floor cell on the one-hot row is empty. The registered retries do not move that run. Width 10 was not run, because a short lead was not the only failure. No third grid was tried. Fixtures were not written.

Spec id: smb-tiles-v1
Width: 7
n: 80
Body parameters: 1500
Value parameters: 1313
Spec digest: 4f888ce33c2b611ef16d39f9ba7d5661511800664cb4149ced9711a259902ae1
Decoder: `{"enemy_x": "0x03AE", "enemy_y": "0x03B9", "x_bias": 12, "y_bias": 16}`
Lead decisions: None
Ground index: 8
Emulator frames: 499
Held versus released max abs: 0.0
Held versus released 84x84 gray MAE: 0.0

## Attempts

| Reason | Spec | Accepted | Frames | Failures |
|---|---|---|---|---|
| default | smb-tiles-v1 | False | 499 | approach_floor, contact_offset, lead |
| x_bias | smb-tiles-v1 | False | 499 | approach_floor, contact_offset, lead, pairwise |
| y_bias | smb-tiles-v1 | False | 499 | approach_floor, contact_offset, lead |

## Preconditions

- ROM SHA1: ea343f4e445a9050d4b4fbac2c77d0693b1d0922
- Core SHA1: e3d3a8436a3a0f3cc2c9164945dc4f87e616f243
- Approach state sha256: 72c3ea8bd337c489e2a0c1adb3253de22457c8617c8162816dfbd25ae014a97e

## Samples

```text
approach: x=197 y=79 viewport=1 screen=(112,176) anchor=(7,12) unbiased=(7,11) one_hot=8 pipes=[]
   0  0  0  0  0  0  0  0
   1  0  0  0  0  0  0  0
   2  0  0  0  0  0  0  0
   3  0  0  0  0  0  0  0
   4  0  0  0  0  0  0  0
   5  0  0  0  0  1  0  0
   6  0  0  0  0  0  0  0
   7  0  0  0  0  0  0  0
*  8  0  0  0  0  0  0  0
   9  1  1  1  1  1  1  1
enemies:
  slot 0 flag=1 id=6 page=1 0087=89 00CF=184 03AE=4 03B9=184 cell_03AE={'col': 0, 'row': 11, 'window_row': 7, 'col_offset': -7} cell_0087={'col': 5, 'row': 11, 'window_row': 7, 'col_offset': -2}
  slot 1 flag=0 id=0 page=2 0087=128 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -7} cell_0087={'col': 8, 'row': 0, 'window_row': -4, 'col_offset': 1}
  slot 2 flag=0 id=0 page=2 0087=128 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -7} cell_0087={'col': 8, 'row': 0, 'window_row': -4, 'col_offset': 1}
  slot 3 flag=0 id=0 page=2 0087=128 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -7} cell_0087={'col': 8, 'row': 0, 'window_row': -4, 'col_offset': 1}
  slot 4 flag=0 id=0 page=2 0087=128 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -7} cell_0087={'col': 8, 'row': 0, 'window_row': -4, 'col_offset': 1}
```

```text
title: x=40 y=79 viewport=1 screen=(40,176) anchor=(3,12) unbiased=(2,11) one_hot=8 pipes=[]
   0  0  0  0  0  0  0  0
   1  0  0  0  0  0  0  0
   2  0  0  0  0  0  0  0
   3  0  0  0  0  0  0  0
   4  0  0  0  0  0  0  0
   5  0  0  0  0  0  0  0
   6  0  0  0  0  0  0  0
   7  0  0  0  0  0  0  0
*  8  0  0  0  0  0  0  0
   9  1  1  1  1  1  1  1
enemies:
  slot 0 flag=0 id=0 page=1 0087=96 00CF=224 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -3} cell_0087={'col': 6, 'row': 14, 'window_row': 10, 'col_offset': 3}
  slot 1 flag=0 id=0 page=1 0087=96 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -3} cell_0087={'col': 6, 'row': 0, 'window_row': -4, 'col_offset': 3}
  slot 2 flag=0 id=0 page=1 0087=96 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -3} cell_0087={'col': 6, 'row': 0, 'window_row': -4, 'col_offset': 3}
  slot 3 flag=0 id=0 page=1 0087=96 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -3} cell_0087={'col': 6, 'row': 0, 'window_row': -4, 'col_offset': 3}
  slot 4 flag=0 id=0 page=1 0087=96 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -3} cell_0087={'col': 6, 'row': 0, 'window_row': -4, 'col_offset': 3}
```

```text
contact: x=434 y=79 viewport=1 screen=(116,176) anchor=(8,12) unbiased=(7,11) one_hot=8 pipes=[]
   0  0  0  0  0  0  0  0
   1  0  0  0  0  0  0  0
   2  0  0  0  0  0  0  0
   3  0  0  0  0  0  0  0
   4  0  0  0  0  0  0  0
   5  0  0  0  0  0  0  0
   6  0  0  0  0  0  0  0
   7  0  1  1  0  0  0  0
*  8  0  1  1  0  0  0  0
   9  1  1  1  1  1  1  1
enemies:
  slot 0 flag=0 id=0 page=2 0087=128 00CF=184 03AE=82 03B9=184 cell_03AE={'col': 5, 'row': 11, 'window_row': 7, 'col_offset': -3} cell_0087={'col': 8, 'row': 11, 'window_row': 7, 'col_offset': 0}
  slot 1 flag=0 id=0 page=2 0087=128 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -8} cell_0087={'col': 8, 'row': 0, 'window_row': -4, 'col_offset': 0}
  slot 2 flag=0 id=0 page=2 0087=128 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -8} cell_0087={'col': 8, 'row': 0, 'window_row': -4, 'col_offset': 0}
  slot 3 flag=0 id=0 page=2 0087=128 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -8} cell_0087={'col': 8, 'row': 0, 'window_row': -4, 'col_offset': 0}
  slot 4 flag=0 id=0 page=2 0087=128 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -8} cell_0087={'col': 8, 'row': 0, 'window_row': -4, 'col_offset': 0}
```

```text
goomba: x=228 y=79 viewport=1 screen=(112,176) anchor=(7,12) unbiased=(7,11) one_hot=8 pipes=[]
   0  0  0  0  0  0  0  0
   1  0  0  0  0  0  0  0
   2  0  0  0  0  0  0  0
   3  0  0  0  0  0  0  0
   4  0  0  0  0  0  0  0
   5  0  0  1  0  0  0  1
   6  0  0  0  0  0  0  0
   7  0  0  0  0  0  0 -1
*  8  0  0  0  0  0  0  0
   9  1  1  1  1  1  1  1
enemies:
  slot 0 flag=1 id=6 page=1 0087=82 00CF=184 03AE=223 03B9=184 cell_03AE={'col': 13, 'row': 11, 'window_row': 7, 'col_offset': 6} cell_0087={'col': 5, 'row': 11, 'window_row': 7, 'col_offset': -2}
  slot 1 flag=0 id=0 page=2 0087=128 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -7} cell_0087={'col': 8, 'row': 0, 'window_row': -4, 'col_offset': 1}
  slot 2 flag=0 id=0 page=2 0087=128 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -7} cell_0087={'col': 8, 'row': 0, 'window_row': -4, 'col_offset': 1}
  slot 3 flag=0 id=0 page=2 0087=128 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -7} cell_0087={'col': 8, 'row': 0, 'window_row': -4, 'col_offset': 1}
  slot 4 flag=0 id=0 page=2 0087=128 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -7} cell_0087={'col': 8, 'row': 0, 'window_row': -4, 'col_offset': 1}
```

```text
on-pipe: x=474 y=111 viewport=1 screen=(117,144) anchor=(8,10) unbiased=(7,9) one_hot=6 pipes=[]
   0  0  0  0  0  0  0  0
   1  0  0  0  0  0  0  0
   2  0  0  0  0  0  0  0
   3  0  0  0  0  0  0  0
   4  0  0  0  0  0  0  0
   5  0  0  0  0  0  0  0
*  6  0  0  0  0  0  0  0
   7  0  0  0  0  0  0  0
   8  0  0  0  0  0  0  0
   9  1  1  1  1  1  1  1
enemies:
  slot 0 flag=1 id=6 page=2 0087=134 00CF=184 03AE=32 03B9=184 cell_03AE={'col': 2, 'row': 11, 'window_row': 7, 'col_offset': -6} cell_0087={'col': 8, 'row': 11, 'window_row': 7, 'col_offset': 0}
  slot 1 flag=0 id=0 page=3 0087=96 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -8} cell_0087={'col': 6, 'row': 0, 'window_row': -4, 'col_offset': -2}
  slot 2 flag=0 id=0 page=3 0087=96 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -8} cell_0087={'col': 6, 'row': 0, 'window_row': -4, 'col_offset': -2}
  slot 3 flag=0 id=0 page=3 0087=96 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -8} cell_0087={'col': 6, 'row': 0, 'window_row': -4, 'col_offset': -2}
  slot 4 flag=0 id=0 page=3 0087=96 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -8} cell_0087={'col': 6, 'row': 0, 'window_row': -4, 'col_offset': -2}
```

```text
past: x=507 y=79 viewport=1 screen=(117,176) anchor=(8,12) unbiased=(7,11) one_hot=8 pipes=[6]
   0  0  0  0  0  0  0  0
   1  0  0  0  0  0  0  0
   2  0  0  0  0  0  0  0
   3  0  0  0  0  0  0  0
   4  0  0  0  0  0  0  0
   5  0  0  0  0  0  0  0
   6  0  0  0  0  0  0  1
   7  0  0  0  0  0  0  1
*  8  0  0  0  0  0  0  1
   9  1  1  1  1  1  1  1
enemies:
  slot 0 flag=1 id=6 page=2 0087=142 00CF=184 03AE=7 03B9=184 cell_03AE={'col': 0, 'row': 11, 'window_row': 7, 'col_offset': -8} cell_0087={'col': 8, 'row': 11, 'window_row': 7, 'col_offset': 0}
  slot 1 flag=0 id=0 page=3 0087=96 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -8} cell_0087={'col': 6, 'row': 0, 'window_row': -4, 'col_offset': -2}
  slot 2 flag=0 id=0 page=3 0087=96 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -8} cell_0087={'col': 6, 'row': 0, 'window_row': -4, 'col_offset': -2}
  slot 3 flag=0 id=0 page=3 0087=96 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -8} cell_0087={'col': 6, 'row': 0, 'window_row': -4, 'col_offset': -2}
  slot 4 flag=0 id=0 page=3 0087=96 00CF=0 03AE=0 03B9=0 cell_03AE={'col': 0, 'row': 0, 'window_row': -4, 'col_offset': -8} cell_0087={'col': 6, 'row': 0, 'window_row': -4, 'col_offset': -2}
```

Title x after each decision:

`40, 41, 42, 45, 47, 51, 55, 59, 64, 70, 76, 82, 88, 94, 102, 110, 118, 128, 138, 148, 158, 168, 178, 188, 198, 208, 218, 228, 238, 248, 258, 268, 278, 288, 298, 308, 313`

Scripted cross:

| Decision | Action | x | y | Grounded | One-hot |
|---|---|---|---|---|---|
| 1 | 3 | 434 | 79 | True | 8 |
| 2 | 3 | 434 | 79 | True | 8 |
| 3 | 3 | 434 | 79 | True | 8 |
| 4 | 4 | 434 | 95 | False | 7 |
| 5 | 4 | 434 | 108 | False | 6 |
| 6 | 4 | 436 | 119 | False | 5 |
| 7 | 4 | 438 | 128 | False | 4 |
| 8 | 4 | 440 | 136 | False | 4 |
| 9 | 4 | 444 | 141 | False | 4 |
| 10 | 4 | 447 | 144 | False | 3 |
| 11 | 4 | 452 | 145 | False | 3 |
| 12 | 4 | 457 | 143 | False | 4 |
| 13 | 4 | 462 | 133 | False | 4 |
| 14 | 4 | 468 | 117 | False | 5 |
| 15 | 4 | 474 | 111 | True | 6 |
| 16 | 4 | 481 | 111 | False | 6 |
| 17 | 4 | 489 | 104 | False | 6 |
| 18 | 4 | 498 | 91 | False | 7 |
| 19 | 4 | 507 | 79 | True | 8 |

## Checks

| Check | Pass |
|---|---|
| title_start | True |
| approach_one_hot | True |
| approach_pipe_empty | True |
| approach_floor | False |
| goomba | True |
| lead | False |
| contact_offset | False |
| contact_row | True |
| contact_air | True |
| on_pipe_delta | True |
| on_pipe_support | True |
| past_row | True |
| past_differs | True |
| past_not_early | True |
| held_released | True |
| script_cross | True |
| pairwise | True |
| held_out_differ | True |
| held_out_not_training | True |
| frame_cap | True |

## Fixtures

Checks did not accept a grid. No fixtures written.

## Out of scope

This run does not train, does not start a generation, and does not implement neuroevolution or `ppo_vector`.
