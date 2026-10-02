# Pac-Man (Midway/Namco `pacman`) Z80 RAM map

Address space read from standalone MAME 0.206 via Lua: `:maincpu` program space.

## Sources (community)

- Commented disassembly: <http://cubeman.org/arcade-source/pacman.asm> (header lists credits, coin and score variables).
- `ablackett82/pacman` (<https://github.com/ablackett82/pacman>): reimplementation traced routine-by-routine from that
  disassembly and differential-tested against the original ROM; used here to confirm what each variable *does*
  (`src/game/actors.js`, `play.js`, `modes.js`, `core.js`).
- Ms. Pac-Man disassembly (same code base at `0000-3FFF`, same RAM variables): <https://github.com/BleuLlama/GameDocs/blob/master/disassemble/mspac.asm>
- Chris Lomont, *Pac-Man Emulation Guide*: <https://www.lomont.org/software/games/pacman/PacmanEmulation.pdf>
  (hardware map: `4000-43FF` video RAM, `4400-47FF` colour RAM, `4C00-4FEF` work RAM, `4FF0-4FFF` sprite regs).
- Pac-Man Dossier: <https://pacman.holenet.info/> (behavioural reference).

## Provenance column

- **observed** = seen changing the expected way in our scripted MAME run (scripted MAME runs, now `games/arcade/pacman/scripts/validate_pacman_state.py` and `tools/discover_state.py`).
- **source** = stated by the community code/disassembly, not yet independently observed here.
- **verify** = hypothesis; needs a targeted experiment before the decoder trusts it.

## Variables

| Address | Meaning | Provenance |
|---|---|---|
| `4E00` | Game mode: 0 init, 1 attract/demo, 2 coin inserted (waiting), 3 playing | observed (1→2 on coin, 2→3 on start) |
| `4E04` | Sub-state while playing; `3` = normal play | source |
| `4E6E` | Credits (BCD) | observed (00→01 on coin) |
| `4E6F` | Lives per game (dip setting) | source |
| `4E14` | Lives remaining | validated (=3 after start); also cheat.dat "Infinite Lives" |
| `4E15` | Lives displayed | source |
| `4E80-4E82` | P1 score, 6 BCD digits, least-significant byte first | validated (score = 10 x dots; sane through 11,720) |
| `4E83` | Not score: was 1 once score passed 10,000 (probably the bonus-life flag; unverified) | observed in a 10-game run |
| `4E88-4E8A` | High score, 6 BCD digits | validated; also MAME hiscore.dat (which lists 4 bytes) |
| `4E0E` | Dots eaten this level (244 total incl. 4 energizers) | validated; cheat.dat sets F4 = "Finish this Level" |
| `4E13` | Level counter (0-based; clamp 0x14) | source |
| `4D00-4D07` | Ghost positions, (l,h) byte pairs: red, pink, blue, orange | observed moving |
| `4D08-4D09` | Pac-Man position (l,h) | observed moving |
| `4D31-4D38` | Ghost tile coordinates, (l,h) pairs | source |
| `4D39-4D3A` | Pac-Man tile (l,h): `h` (4D3A) = horizontal, rises leftward; `l` (4D39) = vertical, rises downward | validated by scripted moves |
| `4D28-4D2B` | Ghost current direction | source |
| `4D30` | Pac-Man current direction | validated (left/right/up/down) |
| `4D3C` | Pac-Man wanted direction; only valid while the joystick is held | validated mid-hold |
| `4DA6` | An energizer is active (any ghost blue) | validated on the v3/v4 recordings; Ms. Pac-Man disassembly |
| `4DA7-4DAA` | Ghost frightened (blue) flags: red, pink, blue, orange. A flag clears when that ghost, eaten, gets home | validated: 29 of 29 single clears were the ghost whose eyes had just reached home (until 2026-10-01 the decoder read `4DA6-4DA9`, one off) |
| `4DAC-4DAF` | Ghost "eyes" (eaten, returning home) flags. Rises about 1 s after the +200/400/800 score jump; the frightened flag may already be clear then | observed (9 ghost scores = 9 rises) |
| `4DD2-4DD3` | Fruit position in pixels (l,h); spawns at (0x94, 0x80) = tile (50, 46), zeroed when it leaves or is eaten. Pixel to tile: `(p >> 3) + (32, 30)` | observed (240 s recording: 4 appearances, at 70 and 170 dots, all timed out after about 6 s) |
| `4DD4` | Fruit code on screen (6 on level 1), 0 = none; stays set a little after the fruit vanishes | observed |
| `4DC1` | Scatter/chase phase counter | source |
| `4FF0-4FFF` | Sprite attribute regs | hardware map |
| `4000-43FF` | Video RAM (maze tiles incl. dots/energizers) | hardware map |

## Encodings

- Directions index vector table `$32FF`: `0` right, `1` down, `2` left, `3` up (on screen).
- Tile pairs are `(l, h)`; maze occupies `l = $20-$3F`, `h = $1E-$3D`. Screen is rotated, so `h` increases leftward.
- Position to tile: `l_tile = (l >> 3) + 0x20`, `h_tile = (h >> 3) + 0x1E`.
- Video-RAM address of tile `(l, h)`: `0x4040 + (h - 0x20) * 32 + (l - 0x20)`.
  Dot tile `0x10`, energizer `0x14`, blank `0x40` (standard Pac-Man char codes; verify).
