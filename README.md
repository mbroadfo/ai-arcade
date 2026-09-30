# AI Arcade Controller Broker — First Vertical Slice

This package contains the first implementation of the canonical AI Arcade
controller layer.

## Files

- `pi/controller_broker.py` — runs on the RetroPie Pi; creates P1/P2 virtual gamepads and accepts TCP commands.
- `tools/controller_client.py` — simple command-line client for Windows/Linux.
- `docs/CONTROLLER_LAYOUT.md` — canonical logical controller contract.

## Pi setup

The Pi already needs `/dev/uinput` and `evdev`.

Copy the broker:

```powershell
scp .\pi\controller_broker.py pi@192.168.10.155:/home/pi/
```

Run it:

```bash
sudo python3 /home/pi/controller_broker.py
```

Expected output:

```text
AI Arcade Controller Broker
---------------------------
P1: AI Arcade Player 1 -> /dev/input/eventX
P2: AI Arcade Player 2 -> /dev/input/eventY
Listening on 0.0.0.0:8765
```

## Test from Windows

```powershell
python .\tools\controller_client.py --host 192.168.10.155 ping
python .\tools\controller_client.py --host 192.168.10.155 status
python .\tools\controller_client.py --host 192.168.10.155 tap 1 LEFT
python .\tools\controller_client.py --host 192.168.10.155 tap 1 BUTTON_1
```

At this stage EmulationStation will see the devices but will not yet have
mappings for their names/GUIDs. The next step is to create explicit
EmulationStation and RetroArch mappings for these permanent device identities.

## Safety

If a direction or button is ever left held:

```powershell
python .\tools\controller_client.py --host 192.168.10.155 release-all
```

Stopping the broker also releases all controls before closing the virtual
devices.
