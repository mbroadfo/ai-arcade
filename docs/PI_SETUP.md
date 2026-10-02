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
   mode (EmulationStation, RetroArch, the core libretro emulators). Optional emulators the old Pi had (AdvanceMAME,
   MAME4All, Amiberry, Frotz, sdltrs, ScummVM) are not part of the basic install.
4. ROMs and BIOS, straight from the old Pi through this PC (nothing is stored in the repository):
   `ssh pi@<old> 'tar cf - -C ~/RetroPie roms BIOS' | ssh pi@<pi> 'tar xf - -C ~/RetroPie'`.
5. `python tools/install_pi.py --host <pi>` (the broker, below) and `python tools/configure_mame_controller.py`.
6. Check: `python tools/start_pi_game.py`, then `python tools/state_client.py --measure`.

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
