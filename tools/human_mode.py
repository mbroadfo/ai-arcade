"""Hand the Pi back to people: stop AI mode (MAME, the state server) and bring EmulationStation back on the screen.

EmulationStation runs from the console autologin on tty1 (pi/setup_pi5.sh autostart); restarting that login starts it
again, the same as a reboot does. tools/start_pi_game.py goes the other way.

    python tools/human_mode.py [--host ADDRESS]
"""
import argparse
import sys

import paramiko

from gamelib import DEFAULT_PI_HOST
from probe_mame_input import run
from start_pi_game import ES_PROCESS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--user", default="pi")
    args = parser.parse_args()

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(hostname=args.host, username=args.user, timeout=10)
    try:
        run(ssh, "pkill -9 -x mame || true; pkill -f '[p]acman_agent.py' || true; "
                 "pkill -f '[s]tate_server.py' || true")
        run(ssh, "sudo systemctl restart getty@tty1")
        up = run(ssh, f"timeout 8 sh -c \"until pgrep -f '{ES_PROCESS}' >/dev/null; do sleep 0.5; done\" "
                      "&& echo up || echo down").strip()
        print(f"EmulationStation is {up} on {args.host}")
        return 0 if up == "up" else 1
    finally:
        ssh.close()


if __name__ == "__main__":
    sys.exit(main())
