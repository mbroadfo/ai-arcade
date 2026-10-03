# Raspberry Pi installation and verification

The Raspberry Pi is treated as reproducible infrastructure, not a hand-configured appliance.

## Rule

Read-only diagnosis can be performed manually. Persistent or privileged configuration belongs in the installer.

The installer owns:

- loading `uinput` at boot;
- installing the Python `evdev` dependency when necessary;
- installing the controller broker under `/opt/ai-arcade`;
- installing and enabling the `ai-arcade-controller.service` systemd unit;
- adding the two canonical AI Arcade controllers to EmulationStation;
- installing the matching RetroArch autoconfig mappings;
- making timestamped backups before changing emulator input configuration;
- verifying service, virtual devices, mappings, and the broker TCP endpoint.

## The cabinet: Raspberry Pi 5 (since 2026-10-02)

The cabinet runs on a Raspberry Pi 5 (4 GB) at `192.168.10.122`; the Pi 3 at `192.168.10.155` is the spare. Every tool
defaults to `DEFAULT_PI_HOST` in `tools/gamelib.py` (override with the `ARCADE_PI_HOST` environment variable or
`--host`). Setting up a new one, from a fresh Raspberry Pi OS Bookworm Lite (64-bit) with SSH enabled:

1. Trust its host key and install this PC's key: `ssh-keyscan <pi> >> ~/.ssh/known_hosts`, then (asks for the Pi's
   password once) `type $env:USERPROFILE\.ssh\id_rsa.pub | ssh pi@<pi> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"`.
2. `scp pi/setup_pi5.sh pi@<pi>:~` then `ssh pi@<pi> 'sh ~/setup_pi5.sh mame'`: standalone MAME from the OS (0.251 on
   Bookworm), git, python3-evdev.
3. `ssh pi@<pi> 'nohup sh ~/setup_pi5.sh retropie > ~/setup_retropie.log 2>&1 &'`: RetroPie's basic install for human
   mode (EmulationStation, RetroArch, the core libretro emulators). Then, the same way, `setup_pi5.sh emulators`: the
   extras the cabinet's ROM folders use (AdvanceMAME, sdltrs, Frotz and the ports: Aleph One, Descent, Doom, Duke 3D,
   Quake, Quake 3, Wolfenstein, Cannonball, Mr. Boom, OpenTyrian). The old Pi's Dreamcast (Reicast) and PC (rpix86)
   launchers and MAME4All are 32-bit Pi 3 programs with no 64-bit build; those folders hold no games.
   `setup_pi5.sh autostart` boots straight into EmulationStation (console autologin, then ES). Only one program can
   hold the Pi 5's screen, so `tools/start_pi_game.py` (AI mode) closes ES first, and `python tools/human_mode.py`
   stops AI mode and brings ES back.
   Sound: the Pi 5 has no headphone jack, so plug in a USB audio adapter (a UGREEN USB-to-3.5 mm, then a 3.5 mm-to-RCA
   cable to the speakers) and run `setup_pi5.sh audio` to make it the default card.
4. ROMs and BIOS, straight from the old Pi through this PC (nothing is stored in the repository):
   `ssh pi@<old> 'tar cf - -C ~/RetroPie roms BIOS' | ssh pi@<pi> 'tar xf - -C ~/RetroPie'`.
5. `python tools/install_pi.py --host <pi>` (the broker, below) and `python tools/configure_mame_controller.py`.
   For the Observatory's control panel: `python tools/install_cabinet.py` (pi/cabinet/ to `~/ai-arcade/cabinet`, and one
   line at the top of `/opt/retropie/configs/all/autostart.sh` that runs a game the page asked for before the menu; the
   original is kept as `autostart.sh.before-ai-arcade`).
6. Check: `python tools/start_pi_game.py`, then `python tools/state_client.py --measure`.

### A USB keyboard for human mode

The installer gives EmulationStation the keyboard as a whole controller, in the old cabinet's layout
(`pi/patch_es_input.py`), and runs RetroPie's own `inputconfiguration.sh` on it, which writes the same keys into
RetroArch and the other emulators that take a keyboard:

| Controller | Key | | Controller | Key |
| --- | --- | --- | --- | --- |
| D-pad | arrows | | L / R shoulder | Q / W |
| A / B | A / S | | L2 / R2 trigger | E / R |
| X / Y | D / F | | L3 / R3 thumb | T / Y |
| Start | Enter | | Left stick | U I O P (up down left right) |
| Select | ' (quote) | | Right stick | [ ] \ Delete |
| Hotkey | Escape | | | |

In RetroArch games Escape on its own quits the game; hold it with D for RetroArch's menu, Q / W to load / save state,
S to reset, left / right to change the state slot. Zork (Frotz) runs in the text console and reads the whole keyboard.
For standalone MAME (AI mode), `configure_mame_controller.py` adds the arrows, `1` / Enter (start) and `5` / Right
Shift (coin) beside the joystick codes.

`python tools/migrate_pi_settings.py` copies the old cabinet's emulator choices (each system's default and the
per-game ones), translating the Pi 3's MAME4All to lr-mame2000 and its AdvanceMAME versions to AdvanceMAME 3. Vector
games that would land on lr-mame2000 go to lr-mame2003 instead, drawn at 1440x1080 and antialiased (lr-mame2000 draws
them small, and a 1080p screen stretches them jagged).

### Arcade games in MAME 0.251 (human mode)

Arcade games EmulationStation runs in standalone MAME 0.251, the same emulator as AI mode, go through
`pi/mame_human/mame_human.sh` with their own settings (`/opt/retropie/configs/mame-0251/`). Install or update it with
`python tools/install_mame_human.py`. Games were moved one at a time by `pi/mame_human/convert.py`, each only after
`game_check.py` showed it launching, taking a coin (5) and start (1), and quitting on Escape at full speed, and its
screenshots (`python tools/mame_human_review.py OUTDIR`) had been looked at. Sets that 0.251 names differently were
rebuilt from the collection into `~/RetroPie/mame-0251/roms` (the cabinet's zips are not touched) and kept only if MAME
verified them. The ledger (`/opt/retropie/configs/mame-0251/ledger.json`, `python3 convert.py status`) records each
game's result, its previous emulator (`convert.py revert`), and why any game stayed where it was.

On 2 October 2026: 116 of the 233 arcade games run in MAME 0.251; the rest are pinned to the emulator they had (missing
chip dumps, a rebuild MAME rejected, or a fault in 0.251 such as Donkey Kong freezing or Galaxian's sound crashing), and
MAME 0.251 is the arcade default for games added later. Some games open on a MAME warning screen; press any key.

Measured on the Pi 5 with MAME 0.251: Pac-Man at full speed with the agent export (60.7 emulated frames a second; the
Pi 3 managed about 51), press to visible effect 66 ms median. The Lua scripts in `tools/` run on both MAME versions.

## Install or update from Windows

From the repository root and activated virtual environment:

```powershell
python .\tools\install_pi.py --host 192.168.10.122
```

Defaults:

- SSH user: `pi`
- SSH key: `~/.ssh/id_rsa`
- SSH port: `22`

Override them with `--user`, `--key`, or `--port`.

To also install structured EmulationStation observation, add `--with-es-state`.
This builds a pinned patched frontend, preserves the original binary, and
restarts ES through its existing RetroPie wrapper. Once installed, verification
also checks fresh ES state and the loaded catalog. See [ES_STATE.md](ES_STATE.md) for commands,
prerequisites, limitations, and the automated `--restore-es` rollback option.

The deployment tool uploads a temporary installation bundle over SSH and invokes the privileged Pi installer, which runs verification before declaring success. The Pi does not require GitHub credentials. The Windows environment needs the dependencies in `requirements.txt` and a working SSH key with the Pi's host key already trusted.

Both deployment and verification accept `--timeout` (default 30 seconds, range 0–600). The verifier polls every half second until the service is active, `/dev/uinput` and both named controllers exist, and port 8765 answers with the expected broker identity and players. All readiness checks must pass in the same attempt. Individual probes have bounded timeouts, so the final attempt can finish slightly beyond the retry window. `--timeout 0` performs one attempt.

Systemd's `Type=simple` reports the service active before Python finishes creating the controllers and listening on TCP. This is why an immediate check after restart can fail despite a healthy service. Waiting happens inside the Pi installer, before it reports success; an arbitrary delay on Windows is unnecessary.

On verification failure, service status and the last 100 journal entries for this service in the current boot are printed automatically. Deployment also collects these diagnostics if an earlier installation step fails. The service runs Python unbuffered so startup messages and errors appear promptly in the journal. Failures retain a nonzero exit code.

## Verify automatic startup after reboot

From Windows, after installing the updated bundle:

```powershell
ssh pi@192.168.10.122 "sudo reboot"
```

SSH may report that the connection closed during reboot. Once SSH is available again, run:

```powershell
python .\tools\verify_pi.py --host 192.168.10.122 --timeout 60
python .\tools\controller_client.py --host 192.168.10.122 ping
python .\tools\controller_client.py --host 192.168.10.122 status
```

The verification timeout covers Pi runtime readiness after SSH connects; it does not retry the SSH connection during reboot. Expect every verification check to pass, ping to report players 1 and 2, and status to list both named controllers and their event devices. These commands do not start a broker. Systemd owns it throughout installation and subsequent boots; no PowerShell-launched broker is needed. A full power-off/start can be checked with the same commands to validate a physical cold boot.

## Verify directly on the Pi

Normally verification is run automatically by the deployment tool. It can also be run locally:

```bash
sudo /usr/bin/python3 /opt/ai-arcade/verify.py
```

Expected checks include:

- `/dev/uinput` exists;
- controller broker systemd service is active and enabled at boot;
- `AI Arcade Player 1` exists;
- `AI Arcade Player 2` exists;
- broker TCP ping succeeds;
- EmulationStation input XML parses;
- P1/P2 EmulationStation GUID mappings are present;
- P1/P2 RetroArch mappings are present.

## Idempotence

The installer is intended to be safe to run repeatedly. EmulationStation mappings for the two AI Arcade devices are removed and recreated rather than duplicated. RetroArch mapping files and service files are replaced from repository-controlled source.

Before each installation a timestamped backup of the existing EmulationStation input file and any existing AI Arcade RetroArch mappings is stored under:

```text
/opt/ai-arcade/backups/<timestamp>/
```

## Canonical device identities

Player 1:

```text
Name: AI Arcade Player 1
Vendor: 0x1209
Product: 0xA101
SDL GUID: 030000000912000001a1000001000000
```

Player 2:

```text
Name: AI Arcade Player 2
Vendor: 0x1209
Product: 0xA102
SDL GUID: 030000000912000002a1000001000000
```

These identities are part of the AI Arcade controller contract and should not be changed casually.
