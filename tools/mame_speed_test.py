"""Measure standalone MAME's emulation speed on the Pi with each state-export variant.

Runs Pac-Man in attract mode for a fixed time per variant and reads the "Average speed" line MAME
prints on clean exit (100% = full speed). Do not run while an agent game is in progress.
"""
import argparse
import re
import sys
import time
from pathlib import Path

import paramiko

from pacman_state import AGENT_REGIONS, REGIONS
from probe_mame_input import run

REMOTE_DIR = "/home/pi/ai-arcade"
LOG = "/tmp/ai-arcade-speed.log"
ROOT = Path(__file__).resolve().parent.parent


def regions_lua(regions):
    rows = []
    for r in regions:
        every = r[2] if len(r) > 2 else 1
        rows.append(f"{{0x{r[0]:X}, 0x{r[1]:X}, {every}}}")
    return "return {" + ", ".join(rows) + "}\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--user", default="pi")
    parser.add_argument("--seconds", type=int, default=40)
    args = parser.parse_args()

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(hostname=args.host, username=args.user, timeout=10)

    variants = [
        ("no script", None),
        ("full export (4096 B/frame)", REGIONS),
        ("light export (agent regions)", AGENT_REGIONS),
    ]
    try:
        run(ssh, f"mkdir -p {REMOTE_DIR}")
        sftp = ssh.open_sftp()
        sftp.put(str(ROOT / "tools" / "mame_state_export.lua"), f"{REMOTE_DIR}/mame_state_export.lua")
        sftp.close()

        for name, regions in variants:
            run(ssh, "pkill -9 -x mame || true")
            if regions:
                sftp = ssh.open_sftp()
                with sftp.file(f"{REMOTE_DIR}/regions.lua", "w") as f:
                    f.write(regions_lua(regions))
                sftp.close()
            script = f"-autoboot_script {REMOTE_DIR}/mame_state_export.lua " if regions else ""
            run(ssh, f"rm -f {LOG}")
            run(ssh, "nohup mame pacman -rompath /home/pi/RetroPie/roms/arcade -sound none "
                     "-video accel -nowindow -skip_gameinfo -joystick -joystickprovider sdl "
                     f"-seconds_to_run {args.seconds} {script}> {LOG} 2>&1 < /dev/null &")
            time.sleep(5)
            for _ in range(60):  # -seconds_to_run is emulated time, so a slow run takes longer
                if not run(ssh, "pgrep -x mame || true").strip():
                    break
                time.sleep(5)
            text = run(ssh, f"cat {LOG}")
            m = re.search(r"Average speed: ([\d.]+)%", text)
            print(f"{name:32s} {m.group(1) + '%' if m else 'no speed line; log tail: ' + text[-200:]}",
                  flush=True)
    finally:
        run(ssh, "pkill -9 -x mame || true")
        ssh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
