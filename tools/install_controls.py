"""Put the panel's controller configuration on the Pi (EmulationStation, RetroArch, MAME 0.251), with a backup of every
file it changes and a rollback. Generated from pi/controls/panel.json by tools/panel_profiles.py. Safe to re-run.

    python tools/install_controls.py                 # what would change (diffs); changes nothing
    python tools/install_controls.py --apply         # back up, write, check; restores the backup itself if a check fails
    python tools/install_controls.py --rollback      # put the newest backup back (or --rollback DIR)

Backups: /home/pi/ai-arcade/backups/controls-<time>/ (the old files, and manifest.json listing files created and changed).
Files written (all writable by the pi user; no sudo):
  EmulationStation  /opt/retropie/configs/all/emulationstation/es_input.cfg   the panel's <inputConfig> added or replaced
  RetroArch         /opt/retropie/configs/all/retroarch-joypads/<device>.cfg  the joypad autoconfig (cores read it by name)
  MAME 0.251        /home/pi/.mame/ctrlr/panel.cfg and the ctrlr line of /opt/retropie/configs/mame-0251/mame.ini
                    (human mode only: AI mode runs MAME with its own ctrlr file, tools/start_pi_game.py)
Restart EmulationStation afterwards (the script does not: a game may be running); `python tools/human_mode.py` does.
"""
import argparse
import difflib
import json
import sys
import time
import xml.etree.ElementTree as ET

import paramiko

import panel_profiles as pp
from gamelib import DEFAULT_PI_HOST
from probe_mame_input import run

BACKUPS = "/home/pi/ai-arcade/backups"
ES_INPUT = "/opt/retropie/configs/all/emulationstation/es_input.cfg"
RA_DIR = "/opt/retropie/configs/all/retroarch-joypads"
MAME_CTRLR = "/home/pi/.mame/ctrlr/panel.cfg"
MAME_INI = "/opt/retropie/configs/mame-0251/mame.ini"


def connect(host):
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(host, username="pi", timeout=10)
    return ssh


def read(sftp, path):
    try:
        with sftp.open(path) as f:
            return f.read().decode("utf-8")
    except IOError:
        return None


def plan(panel, sftp):
    """[(path, old text or None, new text)] for every file that would change."""
    device = panel["device"]
    entry = pp.es_input_entry(panel)
    es_old = read(sftp, ES_INPUT)
    if es_old is None:
        raise RuntimeError(f"{ES_INPUT} is missing: EmulationStation has not been run on this Pi")
    ini_old = read(sftp, MAME_INI)
    if ini_old is None:
        raise RuntimeError(f"{MAME_INI} is missing: run tools/install_mame_human.py first")
    wanted = [
        (ES_INPUT, es_old, pp.merge_es_input(es_old, entry, device["sdl_name"])),
        (f"{RA_DIR}/{device['evdev_name']}.cfg", read(sftp, f"{RA_DIR}/{device['evdev_name']}.cfg"), pp.retroarch_autoconfig(panel)),
        (MAME_CTRLR, read(sftp, MAME_CTRLR), pp.mame_ctrlr(panel)),
        (MAME_INI, ini_old, pp.mame_ini_with_ctrlr(ini_old, "panel")),
    ]
    return [(path, old, new) for path, old, new in wanted if old != new]


def show(changes):
    for path, old, new in changes:
        print(f"\n=== {path}  ({'new file' if old is None else 'changed'})")
        for line in difflib.unified_diff((old or "").splitlines(), new.splitlines(), "before", "after", lineterm="", n=1):
            print("  " + line)


def check(path, text):
    """Raise if a file that must parse does not."""
    if path.endswith(".cfg") and ("<mameconfig" in text or "<inputList" in text):
        ET.fromstring(text)
    if path == MAME_INI and "ctrlr" not in text:
        raise ValueError("mame.ini lost its ctrlr line")


def write(sftp, path, text):
    with sftp.open(path, "w") as f:
        f.write(text.encode("utf-8"))


def apply(ssh, sftp, changes):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    folder = f"{BACKUPS}/controls-{stamp}"
    run(ssh, f"mkdir -p '{folder}/files'")
    manifest = {"time": stamp, "created": [], "changed": []}
    for n, (path, old, new) in enumerate(changes):
        check(path, new)
        if old is None:
            manifest["created"].append(path)
        else:
            write(sftp, f"{folder}/files/{n}", old)
            manifest["changed"].append({"path": path, "backup": f"files/{n}"})
    write(sftp, f"{folder}/manifest.json", json.dumps(manifest, indent=1))
    print(f"backup: {folder}")
    try:
        for path, old, new in changes:
            write(sftp, path, new)
            if read(sftp, path) != new:
                raise RuntimeError(f"{path} does not read back as written")
            print(f"wrote {path}")
    except Exception as exc:
        print(f"FAILED ({exc}): restoring the backup")
        rollback(ssh, sftp, folder)
        raise
    return folder


def rollback(ssh, sftp, folder=None):
    if folder is None or folder == "latest":
        found = run(ssh, f"ls -d {BACKUPS}/controls-* 2>/dev/null | sort | tail -1").strip()
        if not found:
            print("no backup to restore")
            return
        folder = found
    manifest = json.loads(read(sftp, f"{folder}/manifest.json"))
    for item in manifest["changed"]:
        write(sftp, item["path"], read(sftp, f"{folder}/{item['backup']}"))
        print(f"restored {item['path']}")
    for path in manifest["created"]:
        run(ssh, f"rm -f '{path}'")
        print(f"removed {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", nargs="?", const="latest", metavar="DIR")
    args = parser.parse_args()
    ssh = connect(args.host)
    try:
        sftp = ssh.open_sftp()
        if args.rollback:
            rollback(ssh, sftp, args.rollback)
            return 0
        changes = plan(pp.load_panel(), sftp)
        if not changes:
            print("Nothing to change: the Pi already has the panel's configuration.")
            return 0
        show(changes)
        if not args.apply:
            print("\n(dry run: nothing changed; --apply to install)")
            return 0
        apply(ssh, sftp, changes)
        print("\nInstalled. Restart EmulationStation (python tools/human_mode.py) and relaunch any emulator to use it.")
    finally:
        ssh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
