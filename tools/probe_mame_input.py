"""Launch Pac-Man in standalone MAME with the input probe script and stream its report.

Press C (and other controls) in tools/cabinet_test.py while this runs.
"""
import argparse
import time
from pathlib import Path

import paramiko
from gamelib import DEFAULT_PI_HOST

MAME_LOG = "/tmp/ai-arcade-mame.log"


def run(ssh, command):
    _, out, err = ssh.exec_command(command, timeout=20)
    stdout = out.read().decode()
    stderr = err.read().decode()
    if out.channel.recv_exit_status() != 0:
        raise RuntimeError(stderr or stdout)
    return stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--user", default="pi")
    parser.add_argument("--key", default=None)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--script", default="mame_input_probe.lua",
                        help="Lua file in tools/ to autoboot")
    parser.add_argument("--log", default="/tmp/ai-arcade-probe.log",
                        help="Pi-side log file the Lua script writes")
    args = parser.parse_args()

    lua_local = Path(__file__).with_name(args.script)
    lua_remote = f"/home/pi/ai-arcade/{args.script}"
    probe_log = args.log

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    connect_args = {"hostname": args.host, "username": args.user, "timeout": 10}
    if args.key:
        connect_args["key_filename"] = args.key
    ssh.connect(**connect_args)

    try:
        run(ssh, "mkdir -p /home/pi/ai-arcade")
        sftp = ssh.open_sftp()
        sftp.put(str(lua_local), lua_remote)
        sftp.close()

        run(ssh, "pkill -9 -x mame || true")
        run(ssh, f"rm -f {probe_log}")
        run(
            ssh,
            "nohup mame pacman -rompath /home/pi/RetroPie/roms/arcade "
            "-sound none -video accel -nowindow -skip_gameinfo "
            "-joystick -joystickprovider sdl "
            "-ctrlrpath /home/pi/.mame/ctrlr -ctrlr aiarcade "
            f"-autoboot_script {lua_remote} "
            f"> {MAME_LOG} 2>&1 < /dev/null &",
        )

        print(f"MAME launched with probe. Press controls for {args.seconds}s...\n")
        seen = 0
        deadline = time.time() + args.seconds
        while time.time() < deadline:
            time.sleep(1)
            lines = run(ssh, f"cat {probe_log} 2>/dev/null || true").splitlines()
            for line in lines[seen:]:
                print(line)
            seen = len(lines)

        print(f"\nIf nothing printed, check {MAME_LOG} on the Pi.")
    finally:
        ssh.close()


if __name__ == "__main__":
    main()
