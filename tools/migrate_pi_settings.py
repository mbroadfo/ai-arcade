"""Bring the old cabinet's emulator choices to a new one: each system's default emulator and the per-game choices
(RetroPie's /opt/retropie/configs/<system>/emulators.cfg and configs/all/emulators.cfg).

Emulators the old Pi 3 had and a 64-bit Pi does not are translated to their nearest replacement (TRANSLATE). A choice
whose emulator is not installed on the new Pi is skipped and reported, so this can be run again after more emulators
are installed (pi/setup_pi5.sh emulators). Safe to re-run.

    python tools/migrate_pi_settings.py [--old 192.168.10.155] [--new ADDRESS]
"""
import argparse
import re
import sys

import paramiko

from gamelib import DEFAULT_PI_HOST
from probe_mame_input import run

CONFIGS = "/opt/retropie/configs"
TRANSLATE = {
    "mame4all": "lr-mame2000",      # the same MAME 0.37b5 ROM sets
    "advmame-1.4": "advmame",       # AdvanceMAME 3 reads the 0.106 sets 1.4 did
    "advmame-0.94": "advmame",
    "lr-snes9x2010": "lr-snes9x",
}
LINE = re.compile(r'^\s*([^=\s]+)\s*=\s*"(.*)"\s*$')


def connect(host):
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(hostname=host, username="pi", timeout=10)
    return ssh


def parse(text):
    return [m.groups() for m in map(LINE.match, text.splitlines()) if m]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", default="192.168.10.155")
    parser.add_argument("--new", default=DEFAULT_PI_HOST)
    args = parser.parse_args()
    old, new = connect(args.old), connect(args.new)
    try:
        sftp = new.open_sftp()
        installed = {}  # system -> the emulator names its emulators.cfg offers on the new Pi

        def offers(system):
            if system not in installed:
                text = run(new, f"cat {CONFIGS}/{system}/emulators.cfg 2>/dev/null || true")
                installed[system] = {k for k, _ in parse(text) if k != "default"}
            return installed[system]

        skipped = []
        print("System defaults:")
        for line in run(old, f"grep -H '^default' {CONFIGS}/*/emulators.cfg || true").splitlines():
            path, _, setting = line.partition(":")
            system = path.split("/")[-2]
            (_, emulator), = parse(setting)
            emulator = TRANSLATE.get(emulator, emulator)
            if emulator not in offers(system):
                skipped.append(f"{system} default {emulator}")
                continue
            cfg = f"{CONFIGS}/{system}/emulators.cfg"
            lines = [f'{k} = "{v}"' for k, v in parse(run(new, f"cat {cfg}")) if k != "default"]
            with sftp.file(cfg, "w") as f:
                f.write("\n".join(lines + [f'default = "{emulator}"']) + "\n")
            print(f"  {system}: {emulator}")

        games = []
        for key, emulator in parse(run(old, f"cat {CONFIGS}/all/emulators.cfg 2>/dev/null || true")):
            system = key.split("_", 1)[0]
            emulator = TRANSLATE.get(emulator, emulator)
            if emulator in offers(system):
                games.append(f'{key} = "{emulator}"')
            else:
                skipped.append(f"{key} {emulator}")
        with sftp.file(f"{CONFIGS}/all/emulators.cfg", "w") as f:
            f.write("\n".join(games) + "\n")
        print(f"Per-game choices: {len(games)} written")
        sftp.close()

        if skipped:
            print(f"\nSkipped (emulator not installed on {args.new}; run again once it is):")
            for item in skipped:
                print("  " + item)
    finally:
        old.close()
        new.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
