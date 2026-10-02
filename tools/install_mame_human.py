"""Install standalone MAME 0.251 for human mode on the Pi: the launcher EmulationStation calls, its MAME settings,
the game checker and the conversion tools (pi/mame_human/), and their folders. Safe to re-run; it does not move any
game to MAME 0.251 (pi/mame_human/convert.py does that, one checked game at a time).

    python tools/install_mame_human.py [--host ADDRESS]
"""
import argparse
import sys

import paramiko

from gamelib import DEFAULT_PI_HOST, ROOT
from probe_mame_input import run

CODE = "/home/pi/ai-arcade/mame_human"
CONFIG = "/opt/retropie/configs/mame-0251"
ROMS = "/home/pi/RetroPie/mame-0251/roms"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    args = parser.parse_args()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.host, username="pi", timeout=10)
    try:
        dirs = " ".join(f"{CONFIG}/{d}" for d in ("cfg", "nvram", "inp", "sta", "snap", "diff", "checks"))
        run(ssh, f"mkdir -p {CODE} {ROMS} {dirs}")
        sftp = ssh.open_sftp()
        for path in sorted((ROOT / "pi" / "mame_human").iterdir()):
            if path.is_file():
                sftp.put(str(path), f"{CODE}/{path.name}")
        sftp.close()
        run(ssh, f"chmod +x {CODE}/*.sh {CODE}/*.py && cp {CODE}/mame.ini {CONFIG}/mame.ini")
        print(run(ssh, f"cd {CODE} && python3 convert.py status").strip())
        print(f"Installed to {CODE}; settings in {CONFIG}")
    finally:
        ssh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
