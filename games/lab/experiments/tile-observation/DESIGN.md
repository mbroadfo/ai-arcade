# Tile observation, slice 1

Acceptance contract for `smb-tiles-v1`. The reviewed design was approved for this slice only. The genetic algorithm, the `ppo_vector` model, and any training run are later slices. They are not in this branch.

The lab sees an observation specification: `id`, `dtype`, `shape`, `low`, and `high`. Mario addresses and cell rules stay in `games/lab/integrations/smb_1_1.py`. `games/lab/observations.py` checks the document and hashes it. It does not name a game.

## What this slice preserves

- `ram_vector` stays nine floats.
- `SMB_ACTIONS` stays the twelve chords. START and SELECT stay out.
- `stamp()` and `stamp("smb-1-1-speed")` stay the progress and speed stamps: same actions, `ram` 9, no `observation` key.
- Passing an observation id sets `ram` to that spec's length and adds `observation`.
- Historical checkpoints, tapes, the champion zip, and the speed comparison are not rewritten.
- `diagnose()` stays out of the policy vector.

## Specification

| Id | Shape | Cells | Row one-hot |
|---|---|---|---|
| `smb-tiles-v1` | `(80,)` float32, low −1, high 1 | 70 values in {−1, 0, 1} | 10 values in {0, 1} |
| `smb-tiles-v1w10` | `(110,)` | 100 | 10 |

`motion` (length 2) and `previous_action` (length 12) are recorded on the spec and omitted from the vector. Enabling either one requires a new spec id.

`spec_digest` is the SHA-256 of `json.dumps(require_spec(spec), sort_keys=True, separators=(",", ":"))`. The hashed object includes `layout`, `grid`, and `decoder`. Python `json.dumps(-1.0)` emits `-1.0`.

Parameter counts are recorded for the next slice and are not trained here.

- `body_parameters(n) = (n + 1) * 16 + (16 + 1) * 12`
- `value_parameters(n) = n * 16 + 16 + 16 + 1`
- n = 80 → body 1500, value 1313
- n = 110 → body 1980, value 1793

## Grid

| Parameter | Value |
|---|---|
| `start_row` | 4, from the top of the 240 px screen |
| `width` | 7, or 10 only as the lead-time fallback |
| `height` | 10, screen rows 4 through 13 |
| `cell_px` | 16 |
| anchor | the player's column, then columns to the right |
| flatten | row-major `(row - start_row) * width + (column - anchor_column)` |

The anchor column keeps the block-buffer byte. A marker is not written over a solid floor.

Default decoder, until a registered retry is the one that passes:

- column `(ram[0x03AD] + 12) // 16`
- row `(ram[0x03B8] + 16) // 16`
- enemy screen position `0x03AE+i` and `0x03B9+i`, with no added bias

World x of a screen column is `level_x - ram[0x03AD] + column * 16`, with `level_x = ram[0x006D] * 256 + ram[0x0086]`. The block buffer is `0x0500 + page * 208 + sub_y * 16 + sub_x`, `page = (world_x // 256) % 2`, `sub_x = (world_x % 256) // 16`, `sub_y = screen_row - 2`. A nonzero byte is solid. Columns outside 0..15, a negative world x, and `sub_y` outside 0..12 are empty and are not read.

A drawn enemy (`ram[0x000F+i] != 0`) whose window cell is inside the grid replaces that cell with −1. Enemy id is not a distinct cell value and is not read by the vector. The row one-hot is `anchor_row - start_row`, or all zeros when that index is outside 0..9.

Bytes the vector may read: `0x006D`, `0x0086`, `0x03AD`, `0x03B8`, `0x0500`–`0x069F`, `0x000F`–`0x0013`, and the selected enemy pair (`0x03AE`–`0x03B2` with `0x03B9`–`0x03BD`, or `0x0087`–`0x008B` with `0x00CF`–`0x00D3`). It does not read `0x000A`, `0x000D`, `0x06FC`, `0x074A`, `0x0016`, `0x0057`, or `0x009F`.

## Acceptance

`validate.py` plays scripted chords on the real ROM and core. It does not call `learn`, does not write a population, and does not resume a lab generation. The cap is 2000 emulator frames per attempt.

Preconditions, checked before unserialize: core SHA1 `e3d3a8436a3a0f3cc2c9164945dc4f87e616f243`, ROM SHA1 `ea343f4e445a9050d4b4fbac2c77d0693b1d0922`, approach `state.bin` length 13758 and sha256 `72c3ea8bd337c489e2a0c1adb3253de22457c8617c8162816dfbd25ae014a97e`. A reset that is not x=197, y=79 aborts that attempt.

`ground_index` is the one-hot index on that approach frame. It is Mario's body row. The brick floor is the window row under it.

At the contact frame the NES pixels put Mario's red sprite on screen row 12 (pixels 192–207), the same row as the one-hot. RAM `0x03B8` is 176, and the +16 row bias lands on that sprite. Ground bricks fill screen rows 13 and 14. Pipe green fills screen rows 11 and 12 in the columns beside him, which are window rows 7 and 8 when the one-hot is window row 8. Screen row 10 is sky. The block buffer matches those rows. The first acceptance rule treated the one-hot as the floor and looked for the pipe on the two rows above it. That was the validator, and the decoder rows were left as they are. The grid stays 7×10.

`pipe_columns` are offsets `1 .. width-1` with solids on both the one-hot row and the row above it. The floor check is column 0 of the row under the one-hot. A solid on the one-hot row is not the floor.

The drawn goomba shares Mario's screen row. `0x03B9 // 16` writes the −1 one window row higher, which is the reviewed enemy formula, and the slack of one row accepts it. Those bytes were not given a bias.

| Sample | Accept when |
|---|---|
| Approach x=197, y=79 | One-hot is a single 1 in 0..9, `pipe_columns` is empty, and the floor cell under the one-hot is solid |
| Goomba | Some decision with x<313, at least two decisions before death, has enemy id 6, column offset in `1 .. width-1`, window-row distance from `ground_index` in {0, 1}, and that cell is −1 |
| Lead | `lead_decisions` ≥ 4. That is the decision gap from the first nonempty `pipe_columns` to the first x≥434 while holding RIGHT+A+B |
| Contact | `pipe_columns` nonempty, minimum offset in {1, 2}, one-hot still `ground_index`, cells above the two-high run are 0 |
| On the pipe | One-hot equals `ground_index - 2`, and column 0 has a solid on a lower window row. At the sampled landing the pipe has left the anchor column, so that solid is the level floor |
| Past x≥505, y back on the ground | One-hot returns to `ground_index`, and the vector differs from the contact vector. A nonempty `pipe_columns` is allowed. x=458 and x=472 are not this sample |
| Held versus released | Eight emulator frames of RIGHT+A+B and eight of RIGHT+B, from the contact state, produce the same vector |
| Scripted cross | Three decisions of RIGHT+B, then RIGHT+A+B, still reach x≥505 |
| Five sites | Title x=40, goomba, contact, on the pipe, and past are pairwise unequal |
| Held-out states | `held-out-past-pipe.bin` and `held-out-later.bin` restore as evaluation reads. Their vectors differ. They are not a training reset |

## Registered retries

Each retry runs once from the default decoder. A retry is not stacked onto another retry. There is no third grid and no `start_row` search.

- Contact offset outside {1, 2}: one run with x bias 0. Y bias stays 16.
- One-hot all zeros on the ground, floor cell under the one-hot not solid, or on-pipe row delta other than 2: one run with y bias 0. X bias stays 12.
- Goomba check fails: one run that places enemies from `0x0087` and `0x00CF`, still with `(byte // 16)` minus the same origin and the same slack {0, 1}.
- If every check passes except `lead_decisions < 4`: one run at width 10, spec id `smb-tiles-v1w10`. A nonempty `pipe_columns` at x≥505 is not a failure of that run.
- A second failure of the same check stops the slice. Width 10 failing lead, or failing any other check, stops the slice.

The accepted `decoder` is the one recorded in `validation.json`. The committed `observation_spec()` decoder has to match it. The next slice reads that record and does not hardcode 80 or 1500.

## How to reproduce

From `C:\Users\Mike\Documents\Code\ai-arcade-objective`, with the mario-lab Python 3.12 environment:

```text
python games/lab/experiments/tile-observation/validate.py
```

The script sets `CUDA_VISIBLE_DEVICES=-1`, `SDL_AUDIODRIVER=dummy`, and `LAB_RUNS` to a temp directory. Fast tests stay on Python 3.13 and do not import the emulator:

```text
python -m pytest games/lab/tests/test_lab.py games/lab/tests/test_synthetic.py games/lab/tests/test_boundaries.py games/lab/tests/test_objective.py games/lab/tests/test_observation_spec.py games/lab/tests/test_smb_tiles.py -p no:cacheprovider -q --tb=short
```

## Out of scope

`games/lab/evolve.py`, `ppo_vector`, `vector_view`, registry changes, stamp comparison of the observation key, `*.npz` gitignore, and every training run. World 1-2, the live cabinet, and the paused generation are untouched.
