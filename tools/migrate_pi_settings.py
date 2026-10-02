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
# Vector games: lr-mame2000 (the MAME4All stand-in) draws them at a small fixed size that a 1080p screen stretches into
# jagged lines; lr-mame2003 draws them at the screen's height, antialiased. Each of these loads its ROM there (checked
# on the Pi 5); the Cinematronics ones have no sound samples on either cabinet. A game the old cabinet gave another
# emulator (AdvanceMAME, lr-mame2003) keeps it.
VECTOR_GAMES = ("asteroid astdelux barrier boxingb bradley bwidow demon elim2 esb gravitar llander mhavoc redbaron "
                "ripoff spacduel spacewar spacfury speedfrk starhawk starwars tailg warrior wotw").split()
VECTOR_OPTIONS = {"mame2003_vector_resolution": "1440x1080", "mame2003_vector_antialias": "enabled"}
LINE = re.compile(r'^\s*([^=\s]+)\s*=\s*"(.*)"\s*$')


def connect(host):
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(hostname=host, username="pi", timeout=10)
    return ssh


def parse(text):
    return [(m.group(1), m.group(2)) for m in map(LINE.match, text.splitlines()) if m]


def set_options(ssh, sftp, options):
    """Set libretro core options, leaving the others as they are."""
    path = f"{CONFIGS}/all/retroarch-core-options.cfg"
    current = dict(parse(run(ssh, f"cat {path} 2>/dev/null || true")))
    current.update(options)
    with sftp.file(path, "w") as f:
        f.write("".join(f'{k} = "{v}"\n' for k, v in current.items()))


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

        games = {}
        for key, emulator in parse(run(old, f"cat {CONFIGS}/all/emulators.cfg 2>/dev/null || true")):
            system = key.split("_", 1)[0]
            emulator = TRANSLATE.get(emulator, emulator)
            if emulator in offers(system):
                games[key] = emulator
            else:
                skipped.append(f"{key} {emulator}")
        arcade_default = dict(parse(run(new, f"cat {CONFIGS}/arcade/emulators.cfg"))).get("default")
        moved = [g for g in VECTOR_GAMES if games.get(f"arcade_{g}", arcade_default) == "lr-mame2000"]
        if moved and "lr-mame2003" in offers("arcade"):
            games.update({f"arcade_{g}": "lr-mame2003" for g in moved})
            set_options(new, sftp, VECTOR_OPTIONS)
            print(f"Vector games moved to lr-mame2003 ({VECTOR_OPTIONS['mame2003_vector_resolution']}): {' '.join(moved)}")
        with sftp.file(f"{CONFIGS}/all/emulators.cfg", "w") as f:
            f.write("\n".join(f'{k} = "{v}"' for k, v in games.items()) + "\n")
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
