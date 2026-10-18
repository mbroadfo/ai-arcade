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

Stick, after the wire swap (17 October): up = axis 1 positive, down = axis 1 negative, right = axis 0 negative, left = axis 0
positive. Each axis has one pair of opposite directions (so diagonals work), but both are the reverse of Player 1's. (Before
the swap up and left shared an axis and the diagonals up-left and down-right were lost.)

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
| 1 | Player 2's stick wires were on mixed-up terminals (up and left shared an axis, so the up-left and down-right diagonals cancelled). **Fixed on 17 October by swapping two wires**: up and down now share Y and left and right share X, so all four diagonals work. Both axes are now **inverted relative to Player 1** (up = Y positive, down = Y negative, right = X negative, left = X positive), which software handles (or swap up with down and left with right) | resolved, with the inversion to handle in the mapping |
| 2 | The two encoders number their buttons differently (P1's action buttons are 294 to 299, P2's 288 to 293; the extra buttons differ in position and order too), so no single profile fits both | open: decided with the mapping approach below |
| 3 | The two encoders have the same name, id and GUID; only the USB port differs, and Player 1 and 2 are told apart by enumeration order | open |
| 4 | Another gamepad (the F310) took `js0`, putting the panel at `js1` and `js2` | unplug the spare; `audit_controls.py` warns |
| 5 | Esc, Tab, Enter and Pause are joystick buttons, not keys | they need a mapping in each emulator |
| 6 | The flight controller's two buttons are on P2's encoder (codes 298, 299), the same numbers as P1's Y and A | captured; mapped by port |
| 7 | One spinner turn was reported while only the trackball was rolled; the trackball's axes are turned a quarter turn | probably touched; the rotation is handled in the mapping |

### Mapping approach, awaiting a decision

A. per-player maps by USB position in RetroArch, MAME and AdvanceMAME (no new software; the order problem stays);
B. a small daemon on the Pi that reads the two encoders by USB port and presents two clean virtual pads in the
standard layout with fixed names and order (same pattern as the broker); recommended, because every emulator then
sees one layout and problems 2, 3 and 5 are solved in one place;
C. rewire P2's terminals to match P1 (solves only problem 2).

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
| `tools/catalog_controls.py` | classifies the arcade catalog by control type and emulator | `docs/data/cabinet-controls-catalog.json` |

Tests: `tests/test_audit_controls.py` (against a saved copy of the live Pi's files, plus a made-up panel).

## Rollback

Until `install_controls.py --apply` runs, there is nothing to roll back. After it, each replaced file is kept as
`*.before-panel` next to the original and `--rollback` restores them; ES's `es_input.cfg` already has
`.bak` and `.pre-ai-arcade` copies from earlier.
