"""Measure standalone MAME's emulation speed on the Pi with each state-export variant. Any game.

    python tools/mame_speed_test.py --game arcade/pacman

Runs the game in attract mode for a fixed time per variant (no script, the game's full REGIONS if it has them, its
AGENT_REGIONS) and reads the "Average speed" line MAME prints on clean exit (100% = full speed). This is the first
feasibility check for a new game (docs/GAME_WORKSHOP.md, stage 0). Do not run while an agent game is in progress:
it stops MAME.
"""
import argparse
import re
import sys
import time

import paramiko

from gamelib import DEFAULT_GAME, ROOT, load_game, load_profile, split_spec
from probe_mame_input import run
from state_regions import regions_lua

REMOTE_DIR = "/home/pi/ai-arcade"
LOG = "/tmp/ai-arcade-speed.log"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--user", default="pi")
    parser.add_argument("--seconds", type=int, default=40)
    parser.add_argument("--game", default=DEFAULT_GAME, help="<system>/<name>")
    args = parser.parse_args()
    game, (system, _) = load_game(args.game), split_spec(args.game)
    romset = load_profile(args.game)["romset"]

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(hostname=args.host, username=args.user, timeout=10)

    variants = [("no script", None)]
    if getattr(game, "REGIONS", None):
        variants.append(("full export (REGIONS)", game.REGIONS))
    variants.append(("light export (AGENT_REGIONS)", game.AGENT_REGIONS))
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
            run(ssh, f"nohup mame {romset} -rompath /home/pi/RetroPie/roms/{system} -sound none "
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
