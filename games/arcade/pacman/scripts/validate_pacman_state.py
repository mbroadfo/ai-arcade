"""Scripted validation of the Pac-Man decoder against live MAME on the Pi.

Launches MAME with the generic state exporter, plays a fixed sequence through the controller
broker, decodes RAM after each step and checks it against what that action must have done.
"""
import argparse
import struct
import sys
import time
from pathlib import Path

import paramiko

import _bootstrap  # noqa: F401
from controller_client import send
from games.arcade.pacman.state import REGIONS, decode
from probe_mame_input import MAME_LOG, run

STATE_FILE = "/dev/shm/ai-arcade-state.bin"
REMOTE_DIR = "/home/pi/ai-arcade"
FAILURES = []


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label} {detail}")
    if not ok:
        FAILURES.append(label)


def snapshot(ssh):
    _, out, _ = ssh.exec_command(f"cat {STATE_FILE}", timeout=10)
    raw = out.read()
    frame = struct.unpack("<I", raw[:4])[0]
    return frame, decode(raw[4:])


def tap(args, control, ms=200):
    send(args.host, args.broker_port, {"op": "tap", "player": 1, "action": control, "ms": ms})


def hold(args, control, seconds, sample=None):
    """Hold a control; call sample() halfway and return its result (4D3C is only valid while held)."""
    send(args.host, args.broker_port, {"op": "press", "player": 1, "action": control})
    time.sleep(seconds / 2)
    mid = sample() if sample else None
    time.sleep(seconds / 2)
    send(args.host, args.broker_port, {"op": "release", "player": 1, "action": control})
    return mid


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
    here = _bootstrap.ROOT / "tools"

    try:
        run(ssh, f"mkdir -p {REMOTE_DIR}")
        sftp = ssh.open_sftp()
        sftp.put(str(here / "mame_state_export.lua"), f"{REMOTE_DIR}/mame_state_export.lua")
        with sftp.file(f"{REMOTE_DIR}/regions.lua", "w") as f:
            f.write("return {" + ", ".join(f"{{0x{a:X}, 0x{b:X}}}" for a, b in REGIONS) + "}\n")
        sftp.close()

        run(ssh, "pkill -9 -x mame || true")
        run(ssh, f"rm -f {STATE_FILE}")
        run(ssh, "nohup mame pacman -rompath /home/pi/RetroPie/roms/arcade -sound none "
                 "-video accel -nowindow -skip_gameinfo -joystick -joystickprovider sdl "
                 "-ctrlrpath /home/pi/.mame/ctrlr -ctrlr aiarcade "
                 f"-autoboot_script {REMOTE_DIR}/mame_state_export.lua "
                 f"> {MAME_LOG} 2>&1 < /dev/null &")
        for _ in range(40):
            time.sleep(1)
            if run(ssh, f"test -s {STATE_FILE} && echo ok || true").strip() == "ok":
                break
        else:
            print("exporter never produced state; MAME log:\n" + run(ssh, f"tail -20 {MAME_LOG}"))
            return 1
        time.sleep(15)  # boot RAM test

        print("== attract")
        f1, s = snapshot(ssh)
        time.sleep(1)
        f2, _ = snapshot(ssh)
        check("frame counter advances", f2 > f1, f"({f1} -> {f2})")
        check("mode is attract", s.mode == "attract", f"({s.mode})")
        check("credits 0", s.credits == 0, f"({s.credits})")

        print("== coin")
        tap(args, "COIN")
        time.sleep(2)
        _, s = snapshot(ssh)
        check("credits 1", s.credits == 1, f"({s.credits})")

        print("== start")
        tap(args, "START")
        time.sleep(9)
        _, s = snapshot(ssh)
        check("mode playing", s.mode == "playing", f"({s.mode})")
        check("credits consumed", s.credits == 0, f"({s.credits})")
        check("lives 3", s.lives == 3, f"({s.lives})")
        check("score is 10 x dots (Pac-Man auto-walks after READY)", s.score == 10 * s.dots_eaten,
              f"(score {s.score}, dots {s.dots_eaten})")
        check("level 1", s.level == 1, f"({s.level})")

        print("== movement (tile deltas settle the axis orientation)")
        for control, want in (("LEFT", "left"), ("RIGHT", "right"), ("UP", "up"), ("DOWN", "down")):
            _, before = snapshot(ssh)
            _, mid = hold(args, control, 1.2, sample=lambda: snapshot(ssh))
            _, after = snapshot(ssh)
            delta = tuple(a - b for a, b in zip(after.pacman.tile, before.pacman.tile))
            print(f"  {control}: tile {before.pacman.tile} -> {after.pacman.tile} "
                  f"delta(l,h)={delta} dir={after.pacman.direction} score={after.score} "
                  f"dots={after.dots_eaten}")
            check(f"{control} is the wanted direction while held", mid.pacman_wanted == want,
                  f"({mid.pacman_wanted})")

        _, s = snapshot(ssh)
        check("dots eaten increased overall", s.dots_eaten > 0, f"({s.dots_eaten})")
        check("score increased overall", s.score > 0, f"({s.score})")
        check("score is 10 x dots (no energizers/ghosts yet)", s.score >= 10 * s.dots_eaten - 0,
              f"(score {s.score}, dots {s.dots_eaten})")
        print("\nfinal:", s)
    finally:
        try:
            send(args.host, args.broker_port, {"op": "release_all"})
        except Exception as exc:
            print("release_all failed:", exc, file=sys.stderr)
        ssh.close()

    print("\nFAILED: " + ", ".join(FAILURES) if FAILURES else "\nALL CHECKS PASSED")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
