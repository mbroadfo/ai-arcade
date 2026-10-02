# Ms. Pac-Man (Midway `mspacman`) RAM map

Read from standalone MAME 0.206 via Lua: `:maincpu` program space, like Pac-Man.

## Sources

- Commented Ms. Pac-Man disassembly (Scott Lawrence): <https://github.com/BleuLlama/GameDocs/blob/master/disassemble/mspac.asm>.
  Ms. Pac-Man keeps Pac-Man's code at `0000-3FFF`; its additions sit on an auxiliary board at `8000-9FFF`.
- MAME's cheat.dat, via `profile.json` (`tools/game_profile.py`): named addresses for lives, dots and the blue flags.
- Pac-Man's map, `games/arcade/pacman/RAM_MAP.md`, for what has been validated on Pac-Man.
- Behaviour (community): two of the ghosts move semi-randomly for the first seconds of a level instead of heading for
  their corners; four mazes rotate across levels; the bonus fruit enters through a tunnel and wanders the maze.

## Provenance

As in Pac-Man's map: **validated** (checked here on Ms. Pac-Man), **source** (stated by the disassembly or community,
not yet checked here), **verify** (a hypothesis to test).

## Variables shared with Pac-Man

The disassembly gives these the same meaning as in Pac-Man; the decoder is the shared one
(`arcadekit/kits/pacman_board/state.py`).

| Address | Meaning | Provenance |
|---|---|---|
| `4E00` | Game mode: 0 init, 1 demo, 2 coin inserted, 3 playing | source |
| `4E04` | Sub-state while playing; `3` = normal play | source (Pac-Man) |
| `4E6E` | Credits (BCD; `FF` free play) | source |
| `4E14` | Lives remaining | source; cheat.dat "Infinite Lives" |
| `4E80-4E82` | P1 score, 6 BCD digits, least-significant byte first | source |
| `4E88-4E8A` | High score | source |
| `4E0E` | Dots eaten this level | source; cheat.dat "Finish this Level"; total per maze differs from Pac-Man's 244 (verify per maze) |
| `4E13` | Level counter (0-based) | source |
| `4D00-4D07` | Ghost positions (l,h): red, pink, blue, orange | source |
| `4D08-4D09` | Ms. Pac-Man position (l,h) | source |
| `4D0A-4D11` | Ghost tile in the middle of a move (the tile it is entering) | source |
| `4D28-4D2F` | Ghost orientations (previous, current) | source |
| `4D30` | Ms. Pac-Man orientation | source |
| `4D31-4D3A` | Ghost and Ms. Pac-Man tiles (l,h) | source |
| `4DA6` | An energizer is active | source; validated on Pac-Man |
| `4DA7-4DAA` | Ghost blue flags: red, pink, blue, orange | source; validated on Pac-Man; cheat.dat "Red/Pink/Green/Orange always blue" at `4DA7`/`4DA8`/`4DA9`/`4DAA` |
| `4DAC-4DAF` | Ghost state (eyes when eaten) | source |
| `4DD2-4DD3` | Fruit position ("sometimes for other sprite") | source; the fruit moves in Ms. Pac-Man (verify) |
| `4DD4` | Fruit points entry, 0 = no fruit | source |

## To check on the Pi (stage 2)

| Question | How |
|---|---|
| Same dot, energizer and blank tile codes (`0x10`, `0x14`, `0x40`) in all four mazes | maze 1: yes (v20 attract recording, 220 dots + 4 energizers); mazes 2-4 to check |
| Walls: `(code & 0xC0) == 0xC0` as in Pac-Man | same |
| Dots per maze (`4E0E` at a cleared board) | play or use the level-skip cheat (`4E0E`) |
| Tunnel rows per maze | maze 1 has two tunnel rows; the shared maze reader does not join tunnels across the screen edge (true for Pac-Man too), so tunnel ends look like dead ends: to fix in the family kit |
| The fruit: does `4DD2-4DD3` follow it while it wanders | record a stream with the fruit on screen |
| Which level shows which maze | community: maze 1 on levels 1-2, maze 2 on 3-5, then 3 and 4 (verify) |
