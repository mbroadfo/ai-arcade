"""Deploy and run the Pac-Man agent on the Pi, streaming its log here until the game ends.

Usage: python tools/run_pacman_agent.py [--seconds 600]
"""
import argparse
import sys
import time
from pathlib import Path

import paramiko

import _bootstrap  # noqa: F401
from games.arcade.pacman.state import AGENT_REGIONS
from probe_mame_input import MAME_LOG, run

REMOTE_DIR = "/home/pi/ai-arcade"
STATE_FILE = "/dev/shm/ai-arcade-state.bin"
AGENT_LOG = "/tmp/ai-arcade-agent.log"
ROOT = _bootstrap.ROOT
GAME = ROOT / "games" / "arcade" / "pacman"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--user", default="pi")
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--quiet", action="store_true", help="print only GAME/agent lines")
    args = parser.parse_args()

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(hostname=args.host, username=args.user, timeout=10)

    try:
        run(ssh, f"mkdir -p {REMOTE_DIR}")
        sftp = ssh.open_sftp()
        sftp.put(str(ROOT / "tools" / "mame_state_export.lua"), f"{REMOTE_DIR}/mame_state_export.lua")
        sftp.put(str(GAME / "state.py"), f"{REMOTE_DIR}/pacman_state.py")
        sftp.put(str(ROOT / "tools" / "state_regions.py"), f"{REMOTE_DIR}/state_regions.py")
        sftp.put(str(GAME / "scripts" / "pi_pacman_agent.py"), f"{REMOTE_DIR}/pacman_agent.py")
        with sftp.file(f"{REMOTE_DIR}/regions.lua", "w") as f:
            f.write("return {" + ", ".join(f"{{0x{a:X}, 0x{b:X}, {n}}}" for a, b, n in AGENT_REGIONS) + "}\n")
        sftp.close()

        run(ssh, "pkill -9 -x mame || true; pkill -f '[p]acman_agent.py' || true")
        run(ssh, f"rm -f {STATE_FILE} {AGENT_LOG}")
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
        time.sleep(15)  # boot RAM test

        run(ssh, f"nohup python3 {REMOTE_DIR}/pacman_agent.py --seconds {args.seconds} "
                 f"--games {args.games} --log {AGENT_LOG} > /tmp/ai-arcade-agent.out 2>&1 < /dev/null &")
        print("agent started; streaming log...\n")

        seen, deadline = 0, time.time() + args.seconds + 20
        while time.time() < deadline:
            time.sleep(2)
            lines = run(ssh, f"cat {AGENT_LOG} 2>/dev/null || true").splitlines()
            for line in lines[seen:]:
                if not args.quiet or line.startswith(('GAME', 'agent')):
                    print(line, flush=True)
            seen = len(lines)
            if lines and lines[-1] == "agent exit":
                break
        else:
            print("timed out waiting for the agent to finish")

        errors = run(ssh, "cat /tmp/ai-arcade-agent.out 2>/dev/null || true").strip()
        if errors:
            print("\nagent stderr/stdout:\n" + errors)
    finally:
        ssh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
