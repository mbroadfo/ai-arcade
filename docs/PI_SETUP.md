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

## Install or update from Windows

From the repository root and activated virtual environment:

```powershell
python .\tools\install_pi.py --host 192.168.10.155
```

Defaults:

- SSH user: `pi`
- SSH key: `~/.ssh/id_rsa`
- SSH port: `22`

Override them with `--user`, `--key`, or `--port`.

The deployment tool uploads a temporary installation bundle over SSH, invokes the privileged Pi installer, and runs verification. The Pi does not require GitHub credentials.

## Verify directly on the Pi

Normally verification is run automatically by the deployment tool. It can also be run locally:

```bash
sudo /usr/bin/python3 /opt/ai-arcade/verify.py
```

Expected checks include:

- `/dev/uinput` exists;
- controller broker systemd service is active;
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
