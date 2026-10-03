# Battlezone

The third game, and the test of breadth (docs/REFACTOR_PLAN.md, phase 5): a first-person tank in a continuous world,
two tread sticks used together, decisions on a beat instead of at junctions.

## Workshop stages (docs/GAME_WORKSHOP.md)

| Stage | Status |
|---|---|
| 0 Feasibility | done: 100% speed on the Pi 5 (MAME 0.251) with no exporter and with all 1 KB of work RAM exported every frame (`mame_speed_test.py`); unthrottled with no display 1,350% |
| 1 Controls | `profile.json` written. Left tread on Player 1's stick (up = forward), right tread on Player 2's, fire on Player 1's button 1, coin, start: the `bzone` section of `tools/configure_mame_controller.py`. All checked to reach the game (`tools/mame_inputs_probe.lua`); the broker needs no change. Default coinage is 2 coins, 1 play. Press-to-effect latency not measured yet |
| 2 State | done for what the lab needs: Atari's own RAM names (RAM_MAP.md), the decoder (`state.py`) tested on a scripted recording (`tests/`), and in live runs: credits, lives, attract flag, heading, position, score (`HITS`, thousands in BCD), hits taken, death counter, the enemy's shell and its hold-fire timer |
| 3 Decision | on a beat: the real-time lab (below). Facts (`facts.py`) are what a player sees: the screen's left/right/rear warning always; bearing, distance and whether a shot would hit only while the enemy is on the radar, which shows it only within firing range |
| 4-8 | not started: no model plays yet |

## The real-time lab

`scripts/lab.py` runs a diagnostic policy (`policies.py`: code choosing, a control, never AI play) on a fixed-rate
clock (`arcadekit/clock.py`) and logs every tick: when it ran and how late, the snapshot it saw and how old it was when
the command went out, the decoded state, the facts, what the policy held and why, what was pressed and released, and
what changed. `scripts/explain.py` reads a run back tick by tick; `scripts/summarize.py` gives one line per run.

    python tools/start_pi_game.py --game arcade/bzone --speed 1.0
    python games/arcade/bzone/scripts/lab.py --policy track_and_fire --hz 10

Found on 2 October 2026:
- The 10 Hz clock held to within 0.6 ms; observations were about 13 ms old; a command shows in the state 100-200 ms
  later. The game's frame counter runs at about 41 a second.
- A shell hits only within 224-320 world units of the enemy (the game's SHRTCK), about +-0.6 degrees at 25,000 units,
  finer than the heading's step: aiming by angle (4 degrees) gave 1 kill in a game, aiming by where the shot would pass
  gave 8 (`track_and_fire`, 10 Hz).
- The video export showed nothing for Battlezone: it copied MAME's screen bitmap, and a vector game does not draw into
  it. Vector screens now use MAME's rendered snapshot (`tools/mame_video_export.lua`): 640 x 480, about 6 ms a capture,
  10.6 frames a second to the Observatory at 17 KB a frame (3 October 2026).

The enemy's fire, 3 October 2026 (Atari's FIREIT and SHUPDT, checked on the scripted recording and a lab game):
- It never fires in its first 32 game frames (`FTIMER` below `$20`); the earliest live shot came at 33.
- It fires only when its heading is within 2 units of the bearing to the tank, so the shell flies at where the tank
  was. Every killing shot (2 recorded, 3 live) was fired 0-1 units off and exploded where the tank stood.
- The shell covers about 23,000 units a second and gives out at about 32,000, the radar's range: from the radar's edge
  it arrives in about 1.2 s.
- All three deaths in the lab game (`track_and_fire`, 6 kills, 6,000 points) came while the tank stood still:
  `track_and_fire` pivots in place. Moving off the line during that second is the obvious test.

Track & Fire against Mobile Track & Fire, 3 October 2026 (3 games each, alternating, 10 Hz, full speed):

| | Track & Fire | Mobile Track & Fire |
|---|---|---|
| Score (each game) | 6,000 / 25,000 / 6,000 | 8,000 / 6,000 / 6,000 |
| Survived (s) | 50 / 173 / 79 | 89 / 61 / 152 |
| Distance moved | 666 / 288 / 0 | 116,980 / 114,515 / 285,603 |
| Still while the enemy may fire (s) | 21 / 63 / 40 | 4 / 1 / 7 |
| Enemy shots survived | 11 of 20 (55 %) | 15 of 22 (68 %) |

- Moving survived more shots but not longer games, and scored less: aiming while arcing is coarser (on target 9-51 %
  of radar time against 47-60 %).
- Arcing away from a shot fired from near the nose failed 3 times out of 3: the shell comes along the nose line and
  an arc barely leaves it. Driving forward works when the enemy is well off the nose. This is the doctrine's case for
  flanking: approach off the enemy's line, turn in only to fire.
- One death was a shell fired by an enemy that was then destroyed (the policy ignored the shell once it saw no
  enemy: fixed); three deaths in all were the homing missile (`R2D3FL` = `FF`), which neither policy handles.

Adding Flank & Fire (skills.py: flank 30 degrees off the enemy's line, dodge, turn in while its one shell is busy),
3 October 2026, 3 games each, alternating:

| | Track & Fire | Mobile Track & Fire | Flank & Fire |
|---|---|---|---|
| Score | 10,000 / 7,000 / 14,000 | 11,000 / 7,000 / 6,000 | 5,000 / 7,000 / 7,000 |
| Survived (s) | 112 / 78 / 123 | 123 / 73 / 96 | 99 / 73 / 90 |
| Enemy shots survived | 9 of 15 | 9 of 16 | 10 of 17 |
| Moves that went nowhere | (hardly moves) | 26 % | 16 % |

- No policy dodged better: about 60 % of shots were survived whatever was done. `scripts/dodges.py` shows why: the
  "dodging" tank was often pinned against an obstacle (driving, position unchanged for the whole flight), and the
  shells it survived mostly exploded on that obstacle. A quarter of the mobile policies' moves went nowhere.
- So obstacles come before any dodge can be judged: they block the tank and they block shells (cover). They are
  fixed: 21 positions in ROM (`PTBLX1`/`PTBLY1`, types at `$3FCC`).
- The pivot-and-reverse dodge (from near the nose) and the arc away both survived 5-6 of 10, untested in open ground.

With the obstacle map and skills.steer_clear (Flank & Fire only), 3 October 2026, 3 games each, alternating:

| | Track & Fire | Mobile Track & Fire (no avoidance) | Flank & Fire (avoids) |
|---|---|---|---|
| Score | 17,000 / 5,000 / 7,000 | 3,000 / 20,000 / 5,000 | 6,000 / 7,000 / 14,000 |
| Survived (s) | 143 / 52 / 53 | 45 / 215 / 52 | 70 / 89 / 94 |
| Blocked by obstacles (s) | 0 | 4 / 62 / 18 | 0 / 0 / 0 |
| Enemy shots survived | 2 of 12 | 10 of 17 | 7 of 14 |

Shots by where they came from (scripts/dodges.py), all nine games:

| Response | Shots | Survived |
|---|---|---|
| From off the nose: drive forward across the line | 11 | 10 |
| From near the nose: pivot away ~0.3 s, then reverse (the suggested dodge) | 11 | 5 |
| From near the nose: arc away | 9 | 2 |
| From near the nose: no dodge (Track & Fire, aiming) | 12 | 2 |

- Steering clear works: Flank & Fire was never blocked; Mobile Track & Fire (which does not avoid) was blocked up to
  62 s in a game.
- Driving across the line beats a shot almost every time; a shot from near the nose is the dangerous one, and the
  pivot-and-reverse dodge survives it more than twice as often as arcing or not dodging.
- Most shots come from near the nose. The source says why: until the player has 2,000 points the enemy fires only
  when it is on the player's screen and close (FIREIT, the "rookie" rule), and later whenever it is aimed. Turning in
  to fire puts the enemy on the nose: that is when to have the dodge ready.
- Scores are too noisy at 3 games each to rank the policies.

## Getting the ROM

The collection's `bzone.zip` matches an older MAME and lacks 8 lookup chips. A newer `bzone.zip` was added with
`python tools/add_rom_files.py PATH/bzone.zip --sets bzone bzonea` (docs/PI_SETUP.md): MAME 0.251 verified both
revisions. Human mode still plays the collection's copy in AdvanceMAME.
