# Battlezone (Atari `bzone`) RAM map

Read from standalone MAME 0.251 via Lua: `:maincpu` program space, work RAM `0000-03FF`.

## Sources

- Full disassembly from Atari's own source, with every RAM variable named (Tim Cottrill, GPL-2.0):
  <https://github.com/tcottrill/BattleZone-Full-Disassembly-and-C-Port>, `disasm/bzone_defines.asm` (commit
  `ce189a8`). Names below are Atari's identifiers; quoted descriptions are Atari's comments on them. The disassembly
  reassembles to Revision 1 (`bzonea`) byte for byte; Revision 2 (`bzone`, the set we run) differs only in 149 bytes of
  the high-score display (`disasm/bzone_alt_5000_diff.asm`), so the RAM map is the same for both.
- MAME's cheat.dat, via `profile.json`: credits `$0E`, lives `$CC`, enemy fire `$26`, homing missiles `$CB`.
- Discovery (`tools/discover_state.py`, `discovered.json`) and a scripted recording (2 October 2026).

## Provenance

**observed** (checked here by experiment), **source** (named in Atari's source, not yet checked here), **verify** (a
hypothesis to test). Multi-byte values are little-endian.

## Game control

| Address | Name | Meaning | Provenance |
|---|---|---|---|
| `0E` | `$CRDT` | Credits. Default coinage is 2 coins, 1 play (DSW1) | observed: 0 → 1 after two coins, 0 on start; cheat.dat |
| `21` | `$CNCT` | Coin count (coins toward the next credit) | source |
| `CC` | `LIVES` | Lives remaining | observed: 3 at start, 2 and 1 after each death; cheat.dat |
| `CD` | `GOVER` | Game over and high-score table display | observed: 1 in attract, 0 once playing |
| `CE` | `ATRACT` | Attract flag: `00` attract, `FF` playing | observed |
| `CF` | `SKILL` | Skill of player | source |
| `C6` | `FRAME` | Frame counter | source |
| `B8-B9` | `HITS` | "Number of hits (score)": the player's hits, the score | source; stayed 0 in a run that hit nothing (the screen showed 0000). The screen prints the digits then a fixed "000" (message `YSCORE`), so probably thousands (verify with a kill) |
| `BA-BB` | `HITS+2` | The enemy's hits: the hits the player's tank has taken | observed: +1 at each of two deaths, with `LIVES` -1 and `CRACK` counting |
| `0300-031D` | `HSCTBL` | High scores, 30 bytes (also hiscore.dat's region) | source |

## The player's tank

| Address | Name | Meaning | Provenance |
|---|---|---|---|
| `2A` | `TANGLE` | Tank angle: 256 = a full circle, counterclockwise from +X (turning left raises it) | observed: turning left adds about 15.5 a second (22 degrees, 16.5 s a full turn) and wraps 255 → 0; the tank drives along (cos, sin) of it (lab run, 2 October 2026) |
| `27` | `LANGLE` | Least significant bit of the 9-bit angle, in bit 7 | source; seen as `80`/`00` |
| `2D-2E` | `TPOSX` | Tank X position, signed 16-bit (`2F-30`: the enemy's, as the `,X` index 2 twin) | observed: driving moves it about 1,900 units a second along the heading (heading 44 degrees: +4140, +3960 in 2 s), turning does not; enemy half: source |
| `31-32` | `TPOSY` | Tank Y position, signed 16-bit (`33-34`: the enemy's) | observed as `TPOSX`; enemy half: source |
| `24` | `FIRECT` | Shell timer counter (`26`: the enemy's) | source; cheat.dat "Enemy Tanks Can't Fire" writes `26` |
| `A8-AB` | `SHELLX` | Shell X: the tank's at `A8`, the enemy's at `AA` | observed: `A8` changes after each press of fire |
| `AC-AF` | `SHELLY` | Shell Y, as `SHELLX` | source |
| `C7` | `CRACK` | Cracked windshield counter (the death screen) | observed: counts up by about 4 every 6 frames for about 1 s after each death, then 0 |
| `C9` | `EIRNGE` | "Enemy in range" flag (the on-screen message) | source |

The game's frame counter (and the exporter's frames) run at about 41 a second. In the 10 Hz lab run a command showed
in the state 100-200 ms after it was sent (one or two ticks), and observations were 13 ms old at the median.

## The enemy and the world

| Address | Name | Meaning | Provenance |
|---|---|---|---|
| `2B` | `NTHETA` | Object's orientation; `2C` = the enemy's angle (`TANGLE+2`) | source |
| `BC` | `RGOAL` | Target angle for the enemy ("robot") | source |
| `BE` | `RANGLE` | Radar sweep angle | source |
| `C4` | `ACTION` | Enemy's behaviour countdown; 0 = picks a new behaviour | source |
| `C5` | `STATE` | Enemy behaviour flags | source |
| `CB` | `R2D3FL` | Missile ("buzz bomb") flag | source; cheat.dat "No Homing Missiles" |
| `D5-D8` | `SAPOSX`, `SAPOSY` | Saucer position | source |
| `DE` | `SAUCER` | Saucer flag | source |
| `02E8` | `TDIST` | Distance to the enemy (high byte), from the radar routine | source |
| `02E9` | `BLIP` | Radar blip brightness | source |
| `3D-A4` | `PNTTBL` | Point table, 104 bytes | source; the 4-byte entries from `5C` move when the tank turns (discovery) |
| `0200-0237` | `PTBLX2` | "Rotated & translated object table": X of each object relative to the tank, 2 bytes each | source |
| `0238-026F` | `PTBLY2` | Its Y | source |
| `0270-02A7` | `PTBLO2` | Each object's type/orientation byte | source |

Vector RAM (`2000-2FFF`) and the math box are not read.
