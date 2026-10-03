"""Install the cabinet controls the Observatory uses (pi/cabinet/): status, catalog, starting and stopping games.

Uploads pi/cabinet/ to the Pi and adds one line to RetroPie's autostart (/opt/retropie/configs/all/autostart.sh), before
EmulationStation: the hook that runs a game the Observatory asked for (pending.sh). The original autostart is kept once
as autostart.sh.before-ai-arcade. Safe to re-run.

    python tools/install_cabinet.py [--host ADDRESS]
"""
import argparse
import sys

import paramiko

from gamelib import DEFAULT_PI_HOST, ROOT
from probe_mame_input import run

CODE = "/home/pi/ai-arcade/cabinet"
AUTOSTART = "/opt/retropie/configs/all/autostart.sh"
HOOK = f"bash {CODE}/pending.sh  # ai-arcade: a game the Observatory asked for, before the menu"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    args = parser.parse_args()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.host, username="pi", timeout=10)
    try:
        run(ssh, f"mkdir -p {CODE}")
        sftp = ssh.open_sftp()
        for path in sorted((ROOT / "pi" / "cabinet").iterdir()):
            if path.is_file():
                sftp.put(str(path), f"{CODE}/{path.name}")
        sftp.close()
        run(ssh, f"chmod +x {CODE}/*.sh {CODE}/*.py")
        run(ssh, f"test -e {AUTOSTART}.before-ai-arcade || cp {AUTOSTART} {AUTOSTART}.before-ai-arcade")
        run(ssh, f"grep -qF '{CODE}/pending.sh' {AUTOSTART} || sed -i '1i {HOOK}' {AUTOSTART}")
        print(run(ssh, f"cat {AUTOSTART}").strip())
        print(run(ssh, f"python3 {CODE}/cabinet.py status").strip())
        print(f"Installed to {CODE}")
    finally:
        ssh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
