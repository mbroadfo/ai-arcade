# Cabinet controls: mapping the physical P1/P2 panel

Status: **plan and read-only tooling. Nothing on the live Pi has been changed.** Written 15 October 2026 on branch
`cabinet/controls` (worktree `ai-arcade-cabinet`, from `origin/main` at `7fd3ad2`). Everything under "What is there
today" was read from the Pi on 15 October with `tools/audit_controls.py` and a few `cat`s; claims about how an
emulator behaves that were not read from a file or tried are marked *(expected, untested)*.

The goal: when the new panel is plugged in, EmulationStation, every emulator on the cabinet and the existing AI Arcade
controls all work with it, from a few reusable profiles, with a per-game exception only where a game cannot work
without one.

## What is there today

### Devices on the Pi (no panel connected)

| Device | Kind | Used for |
| --- | --- | --- |
| `AI Arcade Player 1` / `2` (`1209:a101` / `a102`, `js0` / `js1`) | virtual gamepads made by the broker (`pi/controller_broker.py`, uinput), always present | the AI, and Windows driving EmulationStation (`tools/controller_client.py`, `test_es_navigation.py`) |
| Logitech wireless keyboard and mouse (one receiver) | real keyboard | EmulationStation, the text games (Zork, TRS-80 Time Trek), RetroArch hotkeys |
| `pwr_button`, `vc4-hdmi-0/1` | system | nothing |

The Pi's user `pi` is in the `input` group and `/etc/udev/rules.d/99-input.rules` makes every input node `0660 root:input`,
so a new device is readable without further setup.

### The logical contract (`docs/CONTROLLER_LAYOUT.md`)

Each player has: a stick (left/right = axis 0, up/down = axis 1), buttons 1 to 6 (joystick buttons 0 to 5), `STICK_1/2`
(6, 7), **Select/Coin = button 8**, **Start = button 9**. The virtual pads follow it exactly. A physical panel that
sends the same codes needs no new thinking in any program that already knows the virtual pads.

### How each program reads input now

| Layer | Configuration found | Notes |
| --- | --- | --- |
| EmulationStation | `/opt/retropie/configs/all/emulationstation/es_input.cfg`: `AI Arcade Player 1`, `AI Arcade Player 2` (stick = axes 1/0, a/b/x/y = buttons 0 to 3, pageup/pagedown = 4/5, select = 8, start = 9) and one `Keyboard` entry (arrows, A/S/D/F, Enter, `'` = select, Q/W, Esc = hotkey) shared by every keyboard | a joystick not listed here does nothing in the menu. `inputconfiguration.sh` (run by ES after a pad is configured) also writes the RetroArch and SDL2 files for it |
| RetroArch (every `lr-*` core: 55 + 38 arcade games on lr-mame2000/2003, NES, Atari 2600, 32X...) | `retroarch.cfg`: `input_joypad_driver = udev`, `input_autodetect_enable = true`; keyboard **Player 1 only** (`input_player1_*`: arrows, A S D F, Q W E R, Enter, `quote` = select); joypads by name in `retroarch-joypads/` and `retroarch/autoconfig/` (only the two virtual pads: B/A/Y/X = 0 to 3, L/R/L2/R2 = 4 to 7, select 8, start 9) | hotkeys are keyboard only: `input_enable_hotkey = escape`, `input_exit_emulator = escape`, `input_menu_toggle = d`, save/load = `w`/`q`. No `*_btn` hotkey, so a panel with no keyboard cannot leave a RetroArch game. Per-system `retroarch.cfg` files only `#include` the global one and set `input_remapping_directory` for arcade |
| MAME 0.251 (human mode, 116 arcade games, and AI mode) | `mame.ini`: `ctrlr aiarcade`, `joystick 1`, `joystickprovider sdl`. `/home/pi/.mame/ctrlr/aiarcade.cfg`, section `default`: COIN1, START1 and P1's four stick directions (joystick 1 or the arrow keys); section `bzone`: the two tread sticks (`P1_JOYSTICKLEFT_*` on joystick 1, `P1_JOYSTICKRIGHT_*` on **joystick 2**) | no Player 2 and no action buttons in `default`: they fall back to MAME's defaults *(expected, untested)*: Left Ctrl/Alt/Space/Shift and joystick buttons 1 to 4 in order for P1, R/F/D/G and A/S/Q/W for P2, `5`/`6` coin, `1`/`2` start, Esc exits, Tab menu, P pause. AI mode and human mode share this file, so one edit changes both |
| AdvanceMAME 3 (24 arcade games, e.g. Donkey Kong, Joust, Tempest, Gauntlet, Battlezone) | `advmame.rc`: `device_joystick auto`, `device_keyboard sdl`, `input_map[...] auto`, `input_hotkey yes` | its own mapping, from the first two SDL joysticks *(expected, untested)* |
| sdltrs (TRS-80), Frotz (Zork) | keyboard only | need a real keyboard; a joystick panel cannot type |

Launchers across the 233 arcade zips: mame-0.251 116, lr-mame2000 55, lr-mame2003 38, advmame 24. Plus NES (lr-fceumm,
one lr-quicknes), Atari 2600, 32X, TRS-80, Zork.

### What the games need (`docs/data/cabinet-controls-catalog.json`, from MAME 0.251's own descriptions)

233 arcade games, 0 unknown to MAME 0.251; 164 are 2-player, 4 are 4-player, 65 are 1-player.

| Player 1 control | Games | Comment |
| --- | ---: | --- |
| 8-way stick | 54 | |
| 4-way stick | 53 | Pac-Man, Ms. Pac-Man, Frogger |
| 2-way (left/right) | 48 | Galaga, Joust, Mario Bros |
| twin sticks (`doublejoy`) | 9 | Robotron, Black Widow, Battlezone. Left stick = P1's stick, right = P2's, as `bzone` already does |
| dial / spinner | 16 (+ 8 combined) | Tempest, Arkanoid, Omega Race. Digital left/right works, poorly |
| analog stick (`stick`) | 12 | flight and Star Wars games |
| trackball | 7 (+ 4 combined with a stick) | Missile Command, Marble Madness. A mouse is the real answer |
| up/down only (`joy-vertical2`) | 3 | Defender, Stargate, Pooyan |
| paddle, positional, lightgun, pedal | about 10 | |
| buttons only | 5 | Asteroids |

Buttons: 106 games use 1, 62 use 2, 18 use 3, 11 use 4, 4 use 5, 3 use 6, **3 use more than 6** (Sky Raid 7, Night Driver 8,
Bradley 10). Six action buttons per player plus Start and Coin therefore covers all but three, which would be exceptions.

## Findings

| # | Finding | Why it matters |
| --- | --- | --- |
| R1 | The broker's two virtual pads are `js0` and `js1`. A panel plugged in later is `js2` and `js3`. | RetroArch, standalone MAME and AdvanceMAME give Player 1 and 2 to the first two joysticks. The panel would be Players 3 and 4, and the virtual pads would play. **The main risk.** |
| R2 | `aiarcade.cfg` and RetroArch's autoconfig exist only for the virtual pads. | a new joystick-class device is dead in the menu and in RetroArch until a profile exists |
| R3 | RetroArch's keyboard bindings are Player 1 only. | a keyboard-style panel cannot do two-player RetroArch games |
| R4 | RetroArch's hotkeys and MAME's exit are keyboard keys. | a panel with no keyboard cannot quit a game or open a menu |
| R5 | MAME's `default` ctrlr section has no Player 2, no buttons, no twin-stick right stick. | the second stick and the fire sticks fall back to defaults, or nothing |
| R6 | ES's `Keyboard` entry is shared by every keyboard. | a keyboard-style panel inherits (or must change) the Logitech's menu keys |
| R7 | Text games (Frotz, sdltrs) need a keyboard. | the Logitech stays plugged in |

## The panel as captured (17 October 2026)

From `tools/guided_capture.py` with the panel wired (raw copy: `docs/data/panel-capture-2026-10-17.json`).

### Devices

| Device | USB port | Presents as | Notes |
| --- | --- | --- | --- |
| Player 1 encoder | `usb-xhci-hcd.0-1.2` | gamepad, `0079:0006` DragonRise Generic USB Joystick | 12 buttons (codes 288 to 299), axes X, Y, Z, RX, RZ and a hat; only X and Y are wired |
| Player 2 encoder | `usb-xhci-hcd.0-1.3` | the same model, **the same name and id** | |
| Spinner (GGG TurboTwist 2) | `usb-xhci-hcd.0-1.1` | mouse, `fafa:0060` | |
| Trackball (GGG ICE-T) | `usb-xhci-hcd.0-1.4` | mouse, `fafa:0020` | its three mouse buttons are not used |
| Flight controller | on the **Player 2 encoder** (`1.3`) | two buttons, codes 299 and 298 (buttons 11 and 10), the encoder's two spare terminals | its stick is not used |
| Logitech F310 | `usb-xhci-hcd.1-2` | gamepad | a spare: it takes Player 1's slot when plugged in |

A button's number in SDL, RetroArch and the Linux joystick interface is its code minus 288.

### Player 1 (port 1.2)

Stick: axis 1 negative = up, positive = down; axis 0 negative = left, positive = right (the standard sense).

| Control | Code | Button | Control | Code | Button |
| --- | ---: | ---: | --- | ---: | ---: |
| A | 299 | 11 | Coin 1 | 293 | 5 |
| B | 297 | 9 | P1 Start | 292 | 4 |
| X | 296 | 8 | Esc | 291 | 3 |
| Y | 298 | 10 | Tab | 290 | 2 |
| Snowflake | 295 | 7 | Star | 294 | 6 |

### Player 2 (port 1.3)

| Control | Code | Button | Control | Code | Button |
| --- | ---: | ---: | --- | ---: | ---: |
| A | 293 | 5 | Coin 2 | 294 | 6 |
| B | 291 | 3 | P2 Start | 295 | 7 |
| X | 290 | 2 | Enter | 296 | 8 |
| Y | 292 | 4 | Pause | 297 | 9 |
| Snowflake | 289 | 1 | Star | 288 | 0 |

Stick, final (19 October, 15:56, after the rewiring was checked): up = axis 1 negative, down = axis 1 positive, left =
axis 0 negative, right = axis 0 positive: **the same as Player 1's**. (History: all four reversed until 17 October; up and
down matched on 19 October 15:45; then three more changes of the wires.) EmulationStation, which cannot tell the encoders
apart, now takes Player 2's stick as it takes Player 1's. `tools/stick_check.py` says which wires to swap if a stick drifts
out of line again.

### Spinner and trackball

The capture judges a spinner or trackball by its gain, not its first touch: motion is added up for half a second, and the
direction with the most movement counts if it moved at least 12 counts and made up 60 % of everything it moved (`--min-motion`
changes the 12).

Captured with the gain-based detection (17 October, second run):

| Control | Signal |
| --- | --- |
| Spinner clockwise / counter-clockwise | relative axis 0 positive / negative |
| Trackball up / down | relative axis 0 positive / negative |
| Trackball left / right | relative axis 1 positive / negative |

The trackball's axes are **turned a quarter turn**: a mouse's right is relative X positive and its down is Y positive, so
this trackball is mounted rotated (its right is the panel's up, its down the panel's left). The mapping must turn the axes
back (MAME can map a trackball axis to either mouse axis, inverted or not; RetroArch cores take the mouse as it comes).
The three mouse buttons are unused. One spinner turn was reported while only the trackball was being rolled: probably a
touch on the spinner, not yet confirmed (`--idle 10` would show chatter).

The flight controller's buttons are on the Player 2 encoder at codes 299 and 298, which on the Player 1 encoder are A and
Y. A profile that goes by the pad's name would therefore read P2's flight buttons as A and Y: another reason to map each
encoder by its USB port (and to give P2's spare terminals their own meaning).

### Problems found

| # | Problem | Status |
| --- | --- | --- |
| 1 | Player 2's stick wires were on mixed-up terminals (up and left shared an axis, so the up-left and down-right diagonals cancelled), then reversed against Player 1's | **fixed on 19 October**: wired like Player 1's, checked with the stick capture |
| 2 | The two encoders number their buttons differently (P1's action buttons are 294 to 299, P2's 288 to 293; the extra buttons differ in position and order too), so no single profile fits both | open: decided with the mapping approach below |
| 3 | The two encoders have the same name, id and GUID; only the USB port differs, and Player 1 and 2 are told apart by enumeration order | open |
| 4 | Another gamepad (the F310) took `js0`, putting the panel at `js1` and `js2` | unplug the spare; `audit_controls.py` warns |
| 5 | Esc, Tab, Enter and Pause are joystick buttons, not keys | they need a mapping in each emulator |
| 6 | The flight controller's two buttons are on P2's encoder (codes 298, 299), the same numbers as P1's Y and A | captured; mapped by port |
| 7 | One spinner turn was reported while only the trackball was rolled; the trackball's axes are turned a quarter turn | probably touched; the rotation is handled in the mapping |

### Decisions so far (17 October)

- **MAME's menu on the panel:** Tab opens it, the stick moves up and down, Enter selects, Esc backs out, Pause pauses MAME
  (read from the owner's description; the panel's Esc and Tab are on the P1 encoder, Enter and Pause on the P2 encoder).
  These are MAME's own default keys (Tab, Up/Down, Enter, Esc, P), so a mapping that delivers them as keyboard keys needs
  no MAME configuration for them.
- **Flight controller:** button 1 is the trigger, button 2 the secondary (codes 299 and 298 on the P2 encoder, taking
  them in the order the capture asked, trigger first; to be confirmed).
- **Trackball:** mounted with up toward the monitor, so the quarter turn is in its electronics. It has jumpers that can
  swap and reverse its axes: to deliver up = relative Y negative and left = relative X negative they would have to swap
  X and Y and reverse both. Or software can do it (below).

## Mapping approaches compared

The panel has to serve two kinds of player. **People**: one or two at the panel, in the menu, in MAME's own menu, in
two-player games, with a spinner and a trackball, and with text games on the keyboard. **AI**, of several flavors:
(1) the System One players, which play standalone MAME through the broker's virtual pads `AI Arcade Player 1/2`
(MAME reads them as joysticks 1 and 2: `aiarcade.cfg`, and `bzone` uses joystick 2 as the right tread); (2) Windows-side
automation that drives EmulationStation through the same pads (`controller_client.py`, `test_es_navigation.py`, the
Observatory); (3) the lab policies (Battlezone) on the same path; (4) the Learning Lab, which trains on the PC and does not
use the Pi's controls (not read for this document: if it ever plays on the cabinet it should use the same canonical
actions); and later (5) a trained policy replayed on the cabinet, or learning from logged human play.

The AI's pads must stay what MAME reads as joysticks 1 and 2. That is the constraint every approach has to respect, and
the catch: standalone MAME numbers joysticks by the order they appear, and the panel's two encoders sort before the
virtual pads.

| | **A. Per-player maps in each emulator** | **B. A panel daemon: clean panel pads of its own** | **B2. A panel daemon feeding the existing `AI Arcade Player 1/2` pads** | **C. Rewire P2's buttons** |
| --- | --- | --- | --- | --- |
| What it is | write P1's and P2's button and axis maps into ES, RetroArch, MAME and AdvanceMAME by USB position | a service on the Pi reads the encoders by USB port (grabbing them), fixes axes, and creates `AI Arcade Panel P1/P2` in the standard layout, plus a virtual keyboard for Esc/Tab/Enter/Pause and virtual mice for the spinner and trackball | the same, but its output goes into the broker's existing pads, so people and AI share one pair of devices | change terminals so both encoders match |
| New software | none | one service | one service **and a change to the broker** (a shared interface) | none |
| **People: who is Player 1** | depends on enumeration order of two identical encoders (the same name, id and GUID); a flip swaps the players' maps; a spare gamepad (the F310) shifts everyone | the daemon decides by USB port and creates its pads in a fixed order, so it is deterministic (the spare gamepad can still sort first) | the same, and the only joysticks the emulators see are the broker's two (the encoders are grabbed) | no change |
| People: menus and UI keys | per-emulator: MAME's ctrlr, RetroArch hotkey chords, ES's one map for both encoders (P2's buttons cannot drive the menu) | Esc/Tab/Enter/Pause become real key presses, which MAME, RetroArch (`escape` is already its hotkey) and ES already read: no per-emulator work | the same | no change |
| People: spinner and trackball | rotation fixable in MAME and AdvanceMAME only; the four trackball games on RetroArch cores and AdvanceMAME need the jumpers | the daemon rotates and inverts the motion for every emulator | the same | no change |
| People: P2's inverted stick, the flight buttons that share P1's button numbers | per-player maps handle them, but only if the order holds | handled once, in the daemon | handled once, in the daemon | partial |
| **AI (System One, lab policies): MAME AI mode** | **breaks**: the virtual pads become joysticks 3 and 4 and `aiarcade.cfg` (joysticks 1 and 2) would point at the panel, so AI mode needs its own controller file and joystick numbers, which change with every spare gamepad | **still breaks**: the AI's pads are now behind the panel pads; the same numbering problem remains for AI mode | **unchanged**: the AI's pads remain joysticks 1 and 2, no file changes in AI mode | unchanged |
| AI: Windows automation of ES | unchanged | unchanged | unchanged, and still the same devices | unchanged |
| Human takes over from an AI run | the panel sees different joysticks than the AI: it can only steer if MAME is configured to read both | same | the panel and the AI drive the same pads: a rule is needed (for example in an AI run the panel may only pause, stop and use the MAME menu, not steer), which is a feature | n/a |
| Learning Lab | no effect | no effect | one canonical interface on the Pi; human input could be logged in the same form for imitation learning | no effect |
| Failure mode | a wrong order silently swaps or mangles players | a dead daemon means a dead panel; the AI is unaffected | a dead daemon means a dead panel; the AI and Windows keep working; a broker bug would affect everything | none |
| Work and risk | many files, redone per emulator and per added emulator; fragile numbering | one service; AI mode still needs the numbering fix | one service plus the broker change (coordinate with the other owners of shared interfaces); least change to what already works | a soldering job that solves one of five problems |
| Reversible | yes, per file | yes, stop the service | yes, stop the service; the broker change reverts | yes |

**Recommendation: B2.** It is the only one that leaves AI mode alone. The AI keeps the two pads it has, and the emulators
see only those two, so none of the panel's oddities (identical encoders, different button numbers, an inverted stick, a
rotated trackball, flight buttons that look like P1's A and Y, Esc/Tab/Enter/Pause as buttons) reach any emulator. The
cost is one service and a small broker change. If a broker change is not acceptable yet, **A plus an AI-mode setting that
hides the panel from MAME** (to be tested: SDL can ignore a device by id with `SDL_GAMECONTROLLER_IGNORE_DEVICES`, and I have
not confirmed that MAME honours it for joysticks) is the fallback, but it leaves the order fragility for people.

Not yet verified for any of these: MAME's handling of two mice and an inverted or swapped trackball axis, and whether
EmulationStation takes input from a virtual keyboard while a game is not running. Both are quick to test on the Pi when
we get there.

## Chosen approach: A, per-emulator maps (17 October)

Decision: no panel daemon. Each emulator gets a map for the panel's controllers, and the panel is treated like any pair of
identical USB gamepads. It must also take **two more USB controllers** (an F310 or any pad) for the four-player games
(Gauntlet, Gauntlet II and Warlords on AdvanceMAME, Demolition Derby on lr-mame2003) and for games that play better with
a real stick.

The consequences for the plan:

1. **One map per emulator, not one per player, if both encoders are wired the same.** ES and RetroArch match a pad by
   name, and the two encoders have the same name, so they share one profile. Today their buttons are on different inputs, so
   a shared profile would give P2 the wrong buttons. Rewiring P2 to P1's inputs (below) makes both encoders look like two
   ordinary identical pads, and an extra pair of F310s works the same way. Without the rewiring the fallback is explicit
   per-player bindings (`input_player2_*_btn` in RetroArch, `JOYCODE_2_*` in MAME), which work only while the order holds.
2. **Player order is the one remaining risk.** Joysticks are numbered by the order they appear. The two encoders have
   come up in the same order every time seen (port 1.2 first), but the F310 on the Pi's other USB bus came up before them.
   An extra controller may do the same at boot. To be tested with controllers plugged in at boot and hot-plugged, over several
   reboots, before anything is relied on. Mitigations to try: plug the extra pads into free ports on the panel's own hub;
   RetroArch's per-player device reservation by name (the panel and the extra pads have different names); MAME's player
   numbers are order only.
3. **AI mode needs a safeguard.** The broker's virtual pads must be joysticks 1 and 2 for standalone MAME (`aiarcade.cfg`).
   With the panel plugged in they would be 3 and 4. The AI-mode launch (`tools/start_pi_game.py`) will be changed to build
   its controller file from the live joystick order, or to hide the panel from MAME, whichever tests out; it must be checked
   before the panel's maps are installed. People playing never use that file.
4. **Trackball:** no daemon, so only the jumpers fix the quarter turn for the RetroArch and AdvanceMAME trackball games
   (Reactor, Missile Command, Crystal Castles, Marble Madness, Quantum). MAME can remap it in software for its own games.
5. **Esc, Tab, Enter, Pause** are joystick buttons here, so each emulator maps them: MAME's UI keys to them, RetroArch's
   hotkey chord (Select-style) for exit and menu.

### Wiring changes asked for (all optional, but they make A robust)

Assuming the encoder's input *n* is button *n*, code 287 + *n* (check with the capture afterwards).

**Player 2's stick:** swap the up and down wires, and swap the left and right wires. Result: up = Y negative, down = Y
positive, left = X negative, right = X positive, the same as Player 1.

**Player 2's buttons:** move each to the input Player 1 uses for the same control:

| Control | Now (input) | Move to (input) | Control | Now (input) | Move to (input) |
| --- | ---: | ---: | --- | ---: | ---: |
| A | 6 | 12 | Coin 2 | 7 | 6 |
| B | 4 | 10 | P2 Start | 8 | 5 |
| X | 3 | 9 | Enter (menu select) | 9 | 4 |
| Y | 5 | 11 | Pause | 10 | 3 |
| Snowflake | 2 | 8 | Flight trigger | 12 | 1 |
| Star | 1 | 7 | Flight secondary | 11 | 2 |

(Player 1 keeps inputs 3 to 12 as captured: Tab 3, Esc 4, Start 5, Coin 6, Star 7, Snowflake 8, X 9, B 10, Y 11, A 12;
inputs 1 and 2 are unused on P1, and P2's flight buttons take them.)

**Trackball jumpers:** swap X and Y and reverse both, so up = Y negative and left = X negative.

Nothing else needs to move: Player 1, the spinner and the flight controller's buttons are fine as wired.

After the rewiring only the changed controls are captured again (`guided_capture.py --section p2,trackball`), and then the
profiles are built into a folder and shown as a diff before anything is installed.

## Installed on the Pi (17 October 2026)

`python tools/install_controls.py` (dry run), `--apply`, `--rollback`. Two backups: `controls-20261017-204007` (ES, RetroArch,
MAME) and `controls-20261017-215236` (AdvanceMAME and the launcher moves), both in `/home/pi/ai-arcade/backups/`. Profiles are
generated from `pi/controls/panel.json` by `tools/panel_profiles.py`.

| Where | What changed |
| --- | --- |
| EmulationStation | `es_input.cfg`: an entry for "DragonRise Inc. Generic USB Joystick" (SDL's name and GUID): A accept, B back, Star and Snowflake page up and down, Tab select, Start the menu. Both encoders share it, so Player 2's buttons act as Player 1's in the menu (and its stick is inverted) |
| RetroArch (the `lr-*` cores) | an autoconfig for the encoder by its kernel name: RetroPad B, A, Y, X, L, R are arcade buttons 1 to 6, Select is Coin, Start is Start; Esc is the hotkey and exit, Tab with Esc held the menu |
| MAME 0.251 (human mode) | `/home/pi/.mame/ctrlr/panel.cfg`, and `mame.ini` uses it: both sticks, six buttons each, coin, start, the twin-stick right stick on the P2 stick, menu keys (Tab menu, Enter select, Esc back, Pause pause) |
| AdvanceMAME | `device_joystick sdl` and the `input_map[...]` lines of `advmame.rc` (all twelve buttons, joysticks named `dragonrise_inc_generic_usb_joystick` and `_2`); the launcher line in both `emulators.cfg` files starts it with the AI Arcade pads hidden from SDL, so up to four controllers fit |
| Launchers | Battlezone, Bradley, Donkey Kong and Pisces moved from AdvanceMAME to MAME 0.251 (`mame -verifyroms` says it runs them from the cabinet's ROMs) |
| Battlezone | the flight stick's trigger is fire (not Player 1's A); one coin is one credit (`panel.json` `game_overrides` and `game_dips`) |
| AI mode | `tools/start_pi_game.py` tells SDL to ignore every device except the broker's two pads when it starts MAME, and gives it `-audio_latency 4` |
| Sound | `audio_latency 4` in `mame.ini` (and the launcher says `SDL_AUDIODRIVER=alsa`): MAME 0.251's default latency of 2 sends the USB adapter only silence |

### Tested with the pretend panel (`tools/synth_panel.py`: two virtual encoders with the real name, id and buttons)

| Check | Result |
| --- | --- |
| ES starts and calls both encoders "known joystick" (also after an unplanned reset) | pass |
| ES key sequences against the AI Arcade pads' (`tools/check_es_panel.py`): move, open, back, launch, page down | 8 of 10 sequence runs match; the page-down sequences differ now and then (the panel's sometimes went one page further), cause not found |
| MAME 0.251, Pac-Man: both sticks, coin, start, both players (`tools/check_mame_panel.py`) | pass, including Player 2's inverted stick |
| MAME 0.251, Skydiver: buttons 1 and 2 for both players, and the flight stick's trigger and secondary | pass (the game has only two buttons, so buttons 3 to 6 are untested) |
| MAME 0.251, Battlezone: left tread on the P1 stick, right tread on the P2 stick, fire, coin, start | pass |
| MAME menu: Tab opens, Esc closes, Pause pauses and resumes | pass |
| MAME: Esc leaving a game | **not shown**: it did not leave MAME in the test, nor did a real Esc key from a virtual keyboard, so the test setup may be the cause |
| Sound from MAME 0.251 (what SDL hands ALSA, captured during a Battlezone game) | with the default `audio_latency 2`: **all zeros**, though MAME's own mix was loud; with 3, 4 or 5: full level in every repeat. Fixed with 4 |
| AdvanceMAME, Battlezone (`tools/check_advmame_panel.py`, recorded input): sticks, coin, start | pass (8 of the 10 presses reached the game; the others were buttons Battlezone does not use or ones AdvanceMAME cannot see) |
| AI mode with the panel plugged in: Pac-Man started with `start_pi_game.py`, one game played by the rule player | pass (3 lives, about 5,000 points) |

### Limits found

- **AdvanceMAME** (the 20 games that stay on it). Its default joystick driver shows each encoder with only six of its
  twelve buttons (codes 292 to 297) and no way to use the others, so it is switched to its `sdl` driver, which shows all
  twelve but handles at most four joysticks: the launcher hides the AI Arcade pads from it. Checked on Arkanoid with the
  pretend panel (recorded input): every control the game uses reached it, for both players (coin, start, button), and the
  Pause button paused it. **Not shown:** that Tab opens its main menu and that Esc quits (AdvanceMAME asks for confirmation
  before it quits, and the confirmation did not end the game in the test). If they do not work on the cabinet, the keyboard's
  Tab and Esc do. Joust does not run at all on this Pi: its decoder ROM files are missing (the ROM audit lists them).
- **Not tested:** the RetroArch cores (installed, not run), buttons 3 to 6 of MAME games, the spinner and the trackball,
  two extra USB controllers, the real panel in any of this.
- **The Pi reset itself** several times in ten minutes on 17 October (an "orphan cleanup" on the next boot: a hard reset),
  once with nothing running. It was stable for the next two hours. Cause unknown.

## The plan

### 1. One contract, three profile layers

1. **The contract is the existing one** (above). The panel is made to look like it: each player is one gamepad-class
   device, or one keyboard-class device, with the same ordering of controls. Every profile is written once, against
   the contract.
2. **Device profile** (per panel device, generated from one template by `name`, `VID:PID` and the captured button
   codes): the EmulationStation `inputConfig`, the RetroArch autoconfig `.cfg`, the SDL game-controller line, and the
   `JOYCODE` numbers for MAME. Two devices (P1, P2) means two small files from one template.
3. **Emulator profile** (once per emulator, not per game):
   - **RetroArch**: the global `retroarch.cfg` gets Player 2 bindings and a **joypad hotkey chord** (hold Select/Coin,
     Start = exit, so the panel can leave a game).
   - **MAME 0.251**: the `default` section of `aiarcade.cfg` gets Player 2's stick, Coin2/Start2, buttons 1 to 6 for both
     players, and the **right stick of a twin-stick game on Player 2's stick**, so Robotron-type games need no per-game
     file. An exit chord (Coin + Start) is added.
   - **AdvanceMAME**: confirm its `auto` mapping gives the panel the right buttons; map only if it does not.
4. **Exceptions only when required** (each recorded with a reason): the three games above 6 buttons; dial, trackball
   and light-gun games, which get digital emulation on the stick (or a mouse later); text games stay on the keyboard.

### 2. The ordering problem (R1), the part to get right

For a joystick-class panel the panel must be enumerated before the virtual pads. Proposed: the broker's service waits
(up to about 30 seconds) for the panel's `VID:PID` before it creates its pads, so at boot the panel is `js0/js1` and the
virtual pads `js2/js3`. The AI and Windows reach the menu through the **same virtual pads** whichever index they have,
because ES and the broker match by name. `audit_controls.py` reports the order and warns when it is wrong. The test is
in the session below (T3). If the order cannot be made reliable, the fallback is to keep the virtual pads out of human
mode (the cabinet service already knows the mode) and start them only for AI runs and Windows navigation.

For a **keyboard-class panel** (an I-PAC style encoder) there is no ordering problem. Every emulator already reads a
keyboard, MAME's default keys already cover both players, and the work is RetroArch Player 2's keys (R3), the exit key
(R4) and ES's shared `Keyboard` entry (R6).

### 3. What gets built, in order (nothing installs until you approve)

1. `tools/probe_panel.py --capture`: learn the panel's real codes (session T1). Output: `panel.json`.
2. `pi/controls/` templates and `tools/build_controls.py`: from `panel.json`, write every profile into a build folder.
   Nothing touches the Pi.
3. `tools/install_controls.py --dry-run` (diff of what would change), then `--apply`: backs up each file it replaces as
   `*.before-panel`, writes the profiles, and runs `tools/audit_controls.py`. `--rollback` restores the backups.
   Everything the Pi keeps is reproducible from the repo, per the rule that persistent Pi changes live in automation.
4. The validation below, run together.

## Missing information (answered in part on 17 October: see "The panel as captured")

1. **The encoder**: make and model (I-PAC, Zero Delay, Brook, a Pi GPIO board...)? Does it show up as a **keyboard** or
   as **gamepads**, and is that selectable? A photo of the board, or `python tools/probe_panel.py --list` with it
   plugged in, answers most of this.
2. **One device or two** for P1 and P2?
3. **Buttons per player**, and their physical order and layout (a row of 6? 3 + 3?).
4. **Start and Coin**: on each player's side, or one shared cluster? Any extra buttons (Menu, Exit, Pause, Reset)?
5. **Sticks**: 8-way with restrictor plates to 4-way for the 4-way games, or fixed 4-way?
6. Does the **keyboard stay** plugged in (text games, Zork, Time Trek need one)?
7. A trackball or spinner planned? Without one, those 35 or so games stay digital.
8. **Exit chord** preference (proposed: hold Coin, press Start).
9. For a gamepad-style panel: is **Select/Coin** the same button as in the contract (button 8)?

## What we will test together

Before you plug the panel in I will run the read-only checks (T0). Everything else needs you at the cabinet.

| # | Test | You | I do | Pass |
| --- | --- | --- | --- | --- |
| T0 | Baseline | nothing | `python tools/audit_controls.py --save before.json`, and run the AI Arcade checks below | no FAIL; AI controls pass |
| T1 | Identify the panel | plug it in; with the Logitech on, press each control once, about a second apart, in the order I print (P1 up, down, left, right, buttons 1 to 6, Start, Coin; then P2) | `probe_panel.py --capture --out panel.json` | 24 distinct presses on the expected device(s), no PROBLEM line |
| T2 | Menu and launching | move, select, go back, switch systems with the panel only (Logitech unplugged for this step); launch Ms. Pac-Man and leave it | drive nothing; read `es_state.py` for the view and selection | navigation and launching work with P1; P2's stick also moves the menu |
| T3 | Player order | none | `audit_controls.py` after a reboot **with the panel connected at boot** and again **hot-plugged**; watch the `order` line | the panel is `js0/js1` both ways (or the fallback is chosen) |
| T4 | Controls matrix | for each game below, press every control of P1 then P2 and say what happens | note the results in a table | every stick direction, every button, Start and Coin act for the right player |
| T5 | Persistence | relaunch each emulator type twice; reboot; relaunch | `audit_controls.py` before and after each reboot, diffed | the same mapping works after both |
| T6 | AI Arcade controls | nothing | `controller_client.py` taps; `test_es_navigation.py`; the Observatory starts Ms. Pac-Man in AI mode, then Battlezone, then Autoplay for a minute; the page's PAUSE and EXIT | all still work with the panel connected and idle, and the panel does not move the AI's game |

**T4 games** (chosen from the catalog so every emulator and control class is hit):

| Class | Game | Emulator | What it proves |
| --- | --- | --- | --- |
| 4-way, alternating 2P | Ms. Pac-Man | MAME 0.251 | P1 and P2 sticks, Start 1/2, Coin |
| 4-way, 1 button | Donkey Kong | AdvanceMAME | AdvanceMAME's auto mapping |
| 4-way | Dig Dug | lr-mame2000 | RetroArch mapping, hotkey exit |
| 2-way, 2P simultaneous | Joust | AdvanceMAME | both players at once |
| 2-way, 2P simultaneous | Mario Bros | lr-mame2000 | both players, RetroArch |
| 8-way, 4 buttons | Vanguard | MAME 0.251 | four fire buttons, 8-way |
| 8-way, 3 buttons | Galaga '88 | lr-mame2000 | multi-button on a core |
| 4 buttons, 2P | Star Hawk | lr-mame2003 | lr-mame2003 |
| 5 buttons | Defender | lr-mame2003 | the most buttons on one stick |
| buttons only | Asteroids | lr-mame2003 | rotate and thrust on buttons |
| twin stick | Battlezone | AdvanceMAME (and MAME 0.251 in AI mode) | P1 stick = left tread, P2 stick = right |
| twin stick | Robotron | lr-mame2000 | exception path |
| NES, 2 pads | Super Mario Bros. 3 | lr-fceumm | non-arcade RetroPad, P2 |
| Genesis-style 3 buttons | Sonic the Hedgehog 2 | lr-picodrive | A/B/C and Start |
| Atari 2600 | Combat | lr-stella2014 | a console with one button |
| dial (digital) | Tempest | AdvanceMAME | the known weak case |
| text | Zork, Time Trek | Frotz, sdltrs | keyboard still works |

In every game also check: Start, Coin, the exit chord, and that pressing P2's controls does not move P1.

## Tools in this branch

| Tool | What it does | Writes |
| --- | --- | --- |
| `tools/audit_controls.py` | reads the Pi, reports devices, which program maps them, who is Player 1 and 2, and what is missing (FAIL = a device nothing maps, WARN = misbehaves in some emulator). `--save` keeps the raw collection | nothing on the Pi |
| `tools/probe_panel.py` | `--list`, `--watch N`, `--capture`: listens to the Pi's input devices (the virtual pads excluded), names each press from a stated order | nothing on the Pi; reads only, grabs nothing |
| `tools/guided_capture.py` | **run it yourself at the panel**: says "Press P1 A", waits for it, shows which USB port and code it came from, refuses a control it has already seen, and reports a button wired to the wrong encoder. Sections: p1, p2, p2stick, spinner, trackball, flight, free; `--idle N` lists what chatters when nothing is touched. Skip, back and stop work from the Logitech keyboard or the F310. Saves `runs/panel-capture-<time>.json` | nothing on the Pi; reads only |
| `tools/install_controls.py` | puts the panel's configuration on the Pi (ES, RetroArch, MAME 0.251, AdvanceMAME, the launcher moves): a dry run by default, `--apply` with a backup of every file and a rollback if it fails, `--rollback` | the files listed above, with `--apply` |
| `tools/synth_panel.py`, `check_es_panel.py`, `check_mame_panel.py`, `check_advmame_panel.py` | a pretend panel on the Pi and the checks that press it: they restart EmulationStation and start games, so not while someone is playing | nothing permanent |
| `tools/audit_controls.py` also warns when another pad (the F310) sorts before the panel | | |
| `tools/catalog_controls.py` | classifies the arcade catalog by control type and emulator | `docs/data/cabinet-controls-catalog.json` |

Tests: `tests/test_audit_controls.py` (against a saved copy of the live Pi's files, plus a made-up panel).

## Rollback

Until `install_controls.py --apply` runs, there is nothing to roll back. After it, each replaced file is kept as
`*.before-panel` next to the original and `--rollback` restores them; ES's `es_input.cfg` already has
`.bak` and `.pre-ai-arcade` copies from earlier.

## Adapting to what is plugged in (19 October, evening)

The panel's joystick numbers used to be fixed (encoders = 1 and 2). That broke as soon as anything else was plugged in or
the AI started. Now each launch works it out:

| Mode | Who is hidden | Who plays |
|---|---|---|
| AI run (`tools/start_pi_game.py`) | everything except the AI Arcade pads (`SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT`) | the AI pads are joysticks 1 and 2, as `aiarcade.cfg` expects |
| Human MAME 0.251 (`pi/mame_human/mame_human.sh`) | the AI pads | `pi/mame_human/pad_map.py` reads `/proc/bus/input/devices`, finds the panel's encoders by USB port, treats any other gamepad as Player 1 then Player 2 (beside the panel), and writes `/tmp/ai-arcade-ctrlr/auto.cfg` for exactly that; the keyboard always works; anything unplugged is left out |

Gamepads are assumed to be in the standard layout (Logitech F310 in XInput mode: A B X Y LB RB = buttons 1 to 6, Back =
coin, Start = start, stick or D-pad moves). EmulationStation and RetroArch already choose by device name, so each device
type has its own map there. Not yet done: AdvanceMAME and RetroArch player order with a gamepad, and pads as Players 3 and 4.

### RetroArch cores (lr-mame2003 and the rest) with a gamepad

RetroArch cannot share a player between devices, so a gamepad that is plugged in plays Player 1 (a second one Player 2) and
the panel's encoders follow; with no gamepad the panel is Players 1 and 2 (each encoder now with its own button map).
`pi/controls/runcommand-onstart.sh` (installed by `install_mame_human.py`) runs `pad_map.py --ra` before every RetroArch
core: it writes a RetroArch layout for any gamepad that has none (Back = coin, Start = start, A/B/X/Y/LB/RB = buttons 1 to 6,
Back+Start exits, Guide opens the menu) and appends explicit per-player binds to `/dev/shm/retroarch.cfg`. Explicit binds are
needed because RetroArch's autoconfig ties a pad's buttons to the port it was found in (the pad was found in port 3), not
the player it is meant to be. To play the cabinet's panel as Player 1 in RetroArch, unplug the gamepad.
