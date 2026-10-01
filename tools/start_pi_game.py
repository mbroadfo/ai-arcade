"""Start the Pi in 'dumb cabinet' mode: MAME + light state exporter + state server. No agent.

The Pi only runs the game, streams its state (port 8766), and accepts controls (broker, port 8765).
A decision-maker on the PC does the rest. Leaves everything running.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import paramiko

from pacman_state import AGENT_REGIONS
from probe_mame_input import MAME_LOG, run

REMOTE_DIR = "/home/pi/ai-arcade"
STATE_FILE = "/dev/shm/ai-arcade-state.bin"
SERVER_LOG = "/tmp/ai-arcade-state-server.log"
ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--user", default="pi")
    parser.add_argument("--state-port", type=int, default=8766)
    args = parser.parse_args()

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(hostname=args.host, username=args.user, timeout=10)
    try:
        run(ssh, f"mkdir -p {REMOTE_DIR}")
        sftp = ssh.open_sftp()
        sftp.put(str(ROOT / "tools" / "mame_state_export.lua"), f"{REMOTE_DIR}/mame_state_export.lua")
        sftp.put(str(ROOT / "pi" / "state_server.py"), f"{REMOTE_DIR}/state_server.py")
        with sftp.file(f"{REMOTE_DIR}/regions.lua", "w") as f:
            f.write("return {" + ", ".join(f"{{0x{a:X}, 0x{b:X}, {n}}}" for a, b, n in AGENT_REGIONS) + "}\n")
        sftp.close()

        run(ssh, "pkill -9 -x mame || true; pkill -f '[p]acman_agent.py' || true; "
                 "pkill -f '[s]tate_server.py' || true")
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
            print("exporter never produced state:\n" + run(ssh, f"tail -20 {MAME_LOG}"))
            return 1

        regions = json.dumps([list(r) for r in AGENT_REGIONS])
        run(ssh, f"nohup python3 {REMOTE_DIR}/state_server.py --port {args.state_port} "
                 f"--regions '{regions}' > {SERVER_LOG} 2>&1 < /dev/null &")
        time.sleep(1)
        print(run(ssh, f"pgrep -af '[s]tate_server.py'").strip())
        print(f"\nPi ready: state stream on {args.host}:{args.state_port}, controls on {args.host}:8765")
    finally:
        ssh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
