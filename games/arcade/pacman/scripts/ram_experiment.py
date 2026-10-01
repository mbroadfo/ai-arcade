"""Scripted Pac-Man RAM experiment: no human input needed.

Launches standalone MAME with tools/mame_ram_probe.lua, drives a fixed sequence of
controls through the controller broker, and reports which working-RAM addresses
changed after each action (addresses that change during idle are treated as noise).
"""
import argparse
import re
import sys
import time
from pathlib import Path

import paramiko

import _bootstrap  # noqa: F401
from controller_client import send
from probe_mame_input import MAME_LOG, run

LUA_NAME = "mame_ram_probe.lua"
LUA_REMOTE = f"/home/pi/ai-arcade/{LUA_NAME}"
RAM_LOG = "/tmp/ai-arcade-ram.log"

CHANGE = re.compile(r"f(\d+) ([0-9A-F]{4}): ([0-9A-F]{2}) -> ([0-9A-F]{2})")
VIDEO = re.compile(r"video/color RAM bytes changed: (\d+)")

# (label, action, seconds to wait afterwards)
STEPS = [
    ("baseline (idle attract)", None, 4),
    ("coin", ("tap", "COIN"), 2),
    ("start", ("tap", "START"), 8),
    ("hold LEFT", ("hold", "LEFT"), 2),
    ("hold RIGHT", ("hold", "RIGHT"), 2),
    ("hold UP", ("hold", "UP"), 2),
    ("hold DOWN", ("hold", "DOWN"), 2),
]


def broker(args, payload):
    reply = send(args.host, args.broker_port, payload)
    if not reply.get("ok"):
        raise RuntimeError(f"broker rejected {payload}: {reply}")


def perform(args, action):
    if action is None:
        return
    kind, control = action
    if kind == "tap":
        broker(args, {"op": "tap", "player": 1, "action": control, "ms": 200})
    else:
        broker(args, {"op": "press", "player": 1, "action": control})
        time.sleep(1.2)
        broker(args, {"op": "release", "player": 1, "action": control})


def summarize(lines):
    changes = {}
    video = 0
    for line in lines:
        m = CHANGE.search(line)
        if m:
            addr = m.group(2)
            first, last = changes.get(addr, (m.group(3), None))[0], m.group(4)
            changes[addr] = (first, last)
            continue
        m = VIDEO.search(line)
        if m:
            video += int(m.group(1))
    changes = {a: v for a, v in changes.items() if v[0] != v[1]}  # net change only
    return changes, video


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--user", default="pi")
    parser.add_argument("--broker-port", type=int, default=8765)
    args = parser.parse_args()

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(hostname=args.host, username=args.user, timeout=10)

    try:
        run(ssh, "mkdir -p /home/pi/ai-arcade")
        sftp = ssh.open_sftp()
        sftp.put(str(Path(__file__).with_name(LUA_NAME)), LUA_REMOTE)
        sftp.close()

        run(ssh, "pkill -9 -x mame || true")
        run(ssh, f"rm -f {RAM_LOG}")
        run(
            ssh,
            "nohup mame pacman -rompath /home/pi/RetroPie/roms/arcade "
            "-sound none -video accel -nowindow -skip_gameinfo "
            "-joystick -joystickprovider sdl "
            "-ctrlrpath /home/pi/.mame/ctrlr -ctrlr aiarcade "
            f"-autoboot_script {LUA_REMOTE} "
            f"> {MAME_LOG} 2>&1 < /dev/null &",
        )

        for _ in range(30):
            time.sleep(1)
            if "maincpu space ok" in run(ssh, f"cat {RAM_LOG} 2>/dev/null || true"):
                break
        else:
            print("Lua probe never reported; MAME log tail:")
            print(run(ssh, f"tail -20 {MAME_LOG}"))
            return 1
        print(run(ssh, f"head -1 {RAM_LOG}").strip())
        time.sleep(15)  # let boot RAM clear/self-test finish before baselining

        seen = len(run(ssh, f"cat {RAM_LOG}").splitlines())
        noise = set()

        for label, action, wait in STEPS:
            perform(args, action)
            time.sleep(wait)
            lines = run(ssh, f"cat {RAM_LOG}").splitlines()
            new, seen = lines[seen:], len(lines)
            changes, video = summarize(new)

            if action is None:
                noise = set(changes)
            shown = {a: v for a, v in changes.items() if a not in noise}
            if len(changes) <= 40:
                shown = changes  # small enough to show unfiltered

            print(f"\n== {label}: {len(changes)} addrs changed, "
                  f"{len(shown)} shown, video/color bytes {video}")
            for addr in sorted(shown):
                first, last = shown[addr]
                print(f"   {addr}: {first} -> {last}")
            if action is None:
                print("   noise addrs:", " ".join(sorted(noise)) or "(none)")
                if len(noise) > 200:
                    print("   WARNING: baseline still looks like boot, not attract mode")
    finally:
        try:
            send(args.host, args.broker_port, {"op": "release_all"})
        except Exception as exc:
            print("release_all failed:", exc, file=sys.stderr)
        ssh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
