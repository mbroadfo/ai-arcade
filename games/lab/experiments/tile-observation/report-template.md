# Tile observation validation

Filled by `validate.py`. The machine record is `validation.json` beside this report.

## Result

- Accepted:
- Spec id:
- Width:
- n:
- Body parameters:
- Value parameters:
- Spec digest:
- Decoder:
- Lead decisions:
- Emulator frames:

## Attempts

| Reason | Spec | Decoder | Accepted | Failures |
|---|---|---|---|---|

## Preconditions

- ROM SHA1:
- Core SHA1:
- Approach state:

## Samples

For each of approach, goomba, contact, on the pipe, and past: x, y, viewport `0x00B5`, screen y `0x03B8`, screen x `0x03AD`, anchor row and column, unbiased row and column, one-hot index, the width-by-10 grid, and the enemy slots (flag, id, `0x006E`, `0x0087`, `0x00CF`, `0x03AE`, `0x03B9`, both candidate cells). Every cell's block-buffer address and raw byte are in `validation.json`.

## Checks

| Check | Pass |
|---|---|

## Fixtures

Written only when the checks accept. Each file is 2048 bytes of CPU RAM.

## Out of scope

This run does not train, does not start a generation, and does not implement neuroevolution or `ppo_vector`.
