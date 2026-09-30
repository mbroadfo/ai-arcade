# AI Arcade

AI Arcade is an experimental architecture for allowing AI systems to discover, launch, observe, and play games on a real RetroPie/EmulationStation cabinet while keeping game control, observation, reasoning, and emulator integration cleanly separated.

The project is intentionally built around reproducible infrastructure and observable decision layers rather than one monolithic game-playing model.

## Current milestone

The first complete vertical slice is working:

```text
Windows AI/controller client
        |
        | TCP
        v
Raspberry Pi Controller Broker
        |
        +--> AI Arcade Player 1
        +--> AI Arcade Player 2
        |
        v
EmulationStation / RetroArch / emulator
```

The broker exposes two stable virtual Linux controllers that match the planned physical arcade panel. Windows can already navigate EmulationStation and launch a selected game through the network controller API.

## Canonical controller contract

Each player has:

- joystick X/Y;
- six primary action buttons;
- two stick buttons;
- Coin;
- Start.

AI code emits semantic actions such as `LEFT`, `BUTTON_1`, `COIN`, and `START`; it does not depend on physical encoder terminals or emulator-specific button numbers. See `docs/CONTROLLER_LAYOUT.md`.

## Reproducible Pi installation

Persistent Pi configuration is automated. Do not manually copy service files, edit emulator mappings, or enable services as the normal installation path.

From Windows:

```powershell
python .\tools\install_pi.py --host 192.168.10.155
```

The deployment tool uploads the repository-controlled Pi bundle, runs the privileged installer, enables the controller broker at boot, installs EmulationStation and RetroArch mappings, and verifies the result. Verification retries readiness for up to 30 seconds; failed installs automatically print service status and the current boot's recent journal. Use `--timeout 60` for a longer retry window.

After installation, reboot and verify automatic startup (allow SSH to return after reboot):

```powershell
ssh pi@192.168.10.155 "sudo reboot"
python .\tools\verify_pi.py --host 192.168.10.155 --timeout 60
python .\tools\controller_client.py --host 192.168.10.155 ping
python .\tools\controller_client.py --host 192.168.10.155 status
```

Systemd starts the broker and creates both controllers on every boot. The Windows commands only verify or send controller requests.

See `docs/PI_SETUP.md` for details.

## Controller testing

Once the broker is installed and running:

```powershell
python .\tools\controller_client.py --host 192.168.10.155 ping
python .\tools\controller_client.py --host 192.168.10.155 status
python .\tools\controller_client.py --host 192.168.10.155 tap 1 LEFT
python .\tools\controller_client.py --host 192.168.10.155 tap 1 BUTTON_1
```

## Architecture direction

The larger design separates:

- Arcade Director / game selection;
- emulator integration;
- game-specific state adapters;
- canonical game state;
- fast tactical action selection;
- slower strategic reasoning;
- progress/futility monitoring and escalation;
- observability and decision lineage.

See `docs/AI_ARCADE_ARCHITECTURE.md` for the detailed design.

## ROM and asset policy

This repository contains no commercial ROMs, BIOS files, CHDs, disk/tape images, or copyrighted game assets. Game data remains on the user's local RetroPie system and private backup storage. See `LEGAL.md`.

## Repository layout

```text
pi/                 Pi runtime, installer, service, emulator mappings
scripts/            backup/inventory/repository support tooling
tools/              operator/deployment clients
docs/               architecture and setup documentation
infra/               backup infrastructure definitions
config/              example/local configuration
```

## Development rule

Read-only diagnostic commands may be run manually. Persistent privileged changes to the Pi should be captured in automation before the feature is considered complete.
