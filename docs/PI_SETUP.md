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

To also install structured EmulationStation observation, add `--with-es-state`.
This builds a pinned patched frontend, preserves the original binary, and
restarts ES through its existing RetroPie wrapper. Once installed, verification
also checks fresh ES state. See [ES_STATE.md](ES_STATE.md) for commands,
prerequisites, limitations, and the automated `--restore-es` rollback option.

The deployment tool uploads a temporary installation bundle over SSH and invokes the privileged Pi installer, which runs verification before declaring success. The Pi does not require GitHub credentials. The Windows environment needs the dependencies in `requirements.txt` and a working SSH key with the Pi's host key already trusted.

Both deployment and verification accept `--timeout` (default 30 seconds, range 0–600). The verifier polls every half second until the service is active, `/dev/uinput` and both named controllers exist, and port 8765 answers with the expected broker identity and players. All readiness checks must pass in the same attempt. Individual probes have bounded timeouts, so the final attempt can finish slightly beyond the retry window. `--timeout 0` performs one attempt.

Systemd's `Type=simple` reports the service active before Python finishes creating the controllers and listening on TCP. This is why an immediate check after restart can fail despite a healthy service. Waiting happens inside the Pi installer, before it reports success; an arbitrary delay on Windows is unnecessary.

On verification failure, service status and the last 100 journal entries for this service in the current boot are printed automatically. Deployment also collects these diagnostics if an earlier installation step fails. The service runs Python unbuffered so startup messages and errors appear promptly in the journal. Failures retain a nonzero exit code.

## Verify automatic startup after reboot

From Windows, after installing the updated bundle:

```powershell
ssh pi@192.168.10.155 "sudo reboot"
```

SSH may report that the connection closed during reboot. Once SSH is available again, run:

```powershell
python .\tools\verify_pi.py --host 192.168.10.155 --timeout 60
python .\tools\controller_client.py --host 192.168.10.155 ping
python .\tools\controller_client.py --host 192.168.10.155 status
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
